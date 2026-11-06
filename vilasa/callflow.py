"""The four-question call: village → landmark → house → read-back. Language follows the customer."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from urllib.parse import quote_plus

from .extractor import (
    House,
    Landmark,
    VillageMatch,
    guess_language,
    language_evidence,
    language_to_switch_to,
    match_village,
    parse_house,
    parse_landmark,
    parse_yes_no,
    tokenize,
)
from .lexicon import LANGS
from .normalize import phonetic_key
from .pincodes import PinDirectory
from .prompts import TOPICS, say

MAX_RETRIES = 2
MAX_RESTARTS = 1

VILLAGE, LANDMARK, HOUSE, CONFIRM, DONE, HANDOFF = "village", "landmark", "house", "confirm", "done", "handoff"


@dataclass
class Turn:
    role: str  # "vilasa" | "customer"
    text: str
    language: str
    state: str
    ts: float = field(default_factory=time.time)
    meta: dict = field(default_factory=dict)


@dataclass
class CallSession:
    delivery: dict
    pins: PinDirectory
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])
    language: str = "kn-IN"
    state: str = VILLAGE
    turns: list[Turn] = field(default_factory=list)
    retries: int = 0
    restarts: int = 0
    village: VillageMatch | None = None
    village_text: str = ""
    landmark: Landmark | None = None
    landmark_text: str = ""
    house: House | None = None
    house_text: str = ""
    language_switched: bool = False
    last_detected: str | None = None

    def __post_init__(self):
        self.language = self.delivery.get("default_language") or "kn-IN"

    # ------------------------------------------------------------ STT context
    @property
    def pin(self) -> str:
        return str(self.delivery.get("pin", ""))

    def stt_context(self) -> dict:
        """keyterms / topic for the next Prisma call."""
        extra = []
        if self.village and self.village.name:
            extra.append(self.village.name)
        lang = self.language if self.turns and len(self.turns) > 1 else None
        return {
            "keyterms": self.pins.keyterms(self.pin, language=lang, extra=extra),
            "topic": TOPICS.get(self.state, ""),
            "language_code": "indic-auto",
        }

    # ------------------------------------------------------------ dialog
    def _say(self, key: str, **kw) -> Turn:
        t = Turn("vilasa", say(self.language, key, **kw), self.language, self.state, meta={"prompt": key})
        self.turns.append(t)
        return t

    def start(self) -> Turn:
        return self._say("greet")

    def _update_language(self, text: str, stt_language: str | None):
        if not tokenize(text):
            return
        detected = guess_language(text, stt_language)
        names = {part for name, _ in self.pins.candidates(self.pin) for part in phonetic_key(name).split()}
        new = language_to_switch_to(self.language, detected, language_evidence(text, names), self.last_detected)
        self.last_detected = detected
        if new in LANGS:
            self.language = new
            self.language_switched = True

    def handle(self, text: str, stt_language: str | None = None, meta: dict | None = None) -> Turn:
        text = (text or "").strip()
        self.turns.append(Turn("customer", text, stt_language or "", self.state, meta=meta or {}))
        self._update_language(text, stt_language)
        handler = {VILLAGE: self._on_village, LANDMARK: self._on_landmark, HOUSE: self._on_house, CONFIRM: self._on_confirm}
        if self.state not in handler:
            return self.turns[-1]
        return handler[self.state](text)

    def _retry_or(self, advance) -> Turn:
        if self.retries < MAX_RETRIES:
            self.retries += 1
            return self._say("retry")
        return advance()

    def _goto(self, state: str, key: str, **kw) -> Turn:
        self.state = state
        self.retries = 0
        return self._say(key, **kw)

    def _on_village(self, text: str) -> Turn:
        m = match_village(text, self.pins.candidates(self.pin), own_pin=self.pin)
        if m.accepted:
            self.village, self.village_text = m, text
            return self._goto(LANDMARK, "landmark")

        def keep_raw():
            self.village, self.village_text = m, text
            return self._goto(LANDMARK, "landmark")

        return self._retry_or(keep_raw) if text else self._retry_or(keep_raw)

    def _on_landmark(self, text: str) -> Turn:
        lm = parse_landmark(text, self.language)
        if lm.found:
            self.landmark, self.landmark_text = lm, text
            return self._goto(HOUSE, "house")

        def keep_raw():
            self.landmark, self.landmark_text = lm, text
            return self._goto(HOUSE, "house")

        return self._retry_or(keep_raw)

    def _on_house(self, text: str) -> Turn:
        if not tokenize(text):
            return self._retry_or(lambda: self._goto(CONFIRM, "confirm", summary=self.summary()))
        self.house, self.house_text = parse_house(text, self.language), text
        return self._goto(CONFIRM, "confirm", summary=self.summary())

    def _on_confirm(self, text: str) -> Turn:
        yes = parse_yes_no(text)
        if yes is True:
            return self._goto(DONE, "done")
        if yes is False:
            if self.restarts < MAX_RESTARTS:
                self.restarts += 1
                self.village = self.landmark = self.house = None
                self.village_text = self.landmark_text = self.house_text = ""
                return self._goto(VILLAGE, "restart")
            return self._goto(HANDOFF, "handoff")
        if self.retries < MAX_RETRIES:
            self.retries += 1
            return self._say("yesno_retry")
        return self._goto(HANDOFF, "handoff")

    # ------------------------------------------------------------ outputs
    def summary(self) -> str:
        """Read-back in the customer's own words, so it sounds natural in any language."""
        parts = []
        if self.village and self.village.heard:
            parts.append(self.village.heard)
        elif self.village_text:
            parts.append(self.village_text)
        for t in (self.landmark_text, self.house_text):
            if t:
                parts.append(t.rstrip("।.!? "))
        return ", ".join(parts)

    @property
    def finished(self) -> bool:
        return self.state in (DONE, HANDOFF)

    def card(self) -> dict:
        d = self.delivery
        info = self.pins.get(self.pin)
        v = self.village
        village_name = v.name if v and v.name else (self.village_text or None)
        matched_pin = v.pin if v and v.name else None
        pin_info = self.pins.get(matched_pin) if matched_pin else info
        landmark_en = self.landmark.english() if self.landmark and self.landmark.found else (self.landmark_text or None)
        house_en = (self.house.english(self.landmark) or None) if self.house and self.house.found else (self.house_text or None)
        place = " ".join(
            x for x in [
                (self.landmark.name + " " + (self.landmark.kind or "")).strip() if self.landmark and self.landmark.found else "",
                village_name or "",
                pin_info.taluk if pin_info else "",
                pin_info.district if pin_info else "",
            ] if x
        )
        status = {DONE: "confirmed", HANDOFF: "needs rider call"}.get(self.state, "in progress")
        return {
            "delivery_id": d.get("id"),
            "customer": d.get("customer"),
            "status": status,
            "language": LANGS.get(self.language, self.language),
            "language_code": self.language,
            "language_switched": self.language_switched,
            "before": d.get("typed_address"),
            "village": village_name,
            "village_score": v.score if v else None,
            "village_confident": bool(v and v.confident),
            "village_or": f"or {v.runner_up}?" if v and v.runner_up else None,
            "pin_on_parcel": self.pin,
            "pin_corrected": matched_pin if matched_pin and matched_pin != self.pin else None,
            "taluk": pin_info.taluk if pin_info else None,
            "district": pin_info.district if pin_info else None,
            "landmark": landmark_en,
            "house": house_en,
            "customer_words": [t.text for t in self.turns if t.role == "customer" and t.text],
            "maps_url": f"https://www.google.com/maps/search/?api=1&query={quote_plus(place)}" if place else None,
            "turns": len([t for t in self.turns if t.role == "customer"]),
        }

    def transcript(self) -> list[dict]:
        return [{"role": t.role, "text": t.text, "language": t.language, "state": t.state, "meta": t.meta} for t in self.turns]
