"""Pull structured address parts out of a (possibly code-mixed, any-script) transcript."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from rapidfuzz import fuzz

from .lexicon import (
    FILLER_WORDS,
    HOUSE_WORDS,
    LANGS,
    NUMBER_WORDS,
    POSTPOSITIONAL,
    colour_index,
    landmark_index,
    language_evidence_index,
    language_hint_index,
    non_name_keys,
    polarity_index,
    relation_index,
)
from .normalize import _ascii_digits, detect_language, phonetic_key, to_latin

ACCEPT = 85.0  # village match accepted
UNSURE = 72.0  # accepted, but flagged for the read-back
CERTAIN = 95.0  # at or above this, a short word or a close second place no longer makes a match unsure
SHORT_WORD = 4  # a match on one word this short (phonetic-key letters) needs CERTAIN to be confident
CLOSE_CALL = 4.0  # points between first and second place that count as too close to call
SAME_SCORE = 3.0  # candidates this close are separated by how much of the answer they cover
MAX_NAME_WORDS = 5
JOINED_NAME = 90.0  # two words joined must spell a name this closely; 'house number' is not Hussainpura

FILLERS = {phonetic_key(w) for words in FILLER_WORDS.values() for w in words} | {
    phonetic_key(w) for w in ["um", "uh", "hmm", "madam", "okay"]  # not "sir": it collides with Sira/Shira
} | {phonetic_key(w) for w in HOUSE_WORDS}


@dataclass
class Token:
    orig: str
    key: str


def tokenize(text: str) -> list[Token]:
    out = []
    for raw in re.findall(r"[^\s,.;:!?।|\"'()]+", text or ""):
        key = phonetic_key(raw)
        if key:
            out.append(Token(raw, key))
    return out


def _pretty(tokens: list[Token]) -> str:
    """Native words → readable Latin for the courier card ('ಆಂಜನೇಯ' → 'Anjaneya', 'ಸರ್ಕಾರಿ' → 'Government')."""
    out = []
    for t in tokens:
        adj = ADJECTIVES.get(t.key)
        out.append(adj or (to_latin(t.orig).title() if not t.orig.isascii() else t.orig))
    return " ".join(out).strip()


# ------------------------------------------------------------------ language


def guess_language(text: str, stt_language: str | None = None) -> str:
    """Prisma's detection first; for Latin text, spot Kanglish/Hinglish from known words."""
    if stt_language in LANGS and stt_language != "en-IN":
        return stt_language
    script_lang = detect_language(text)
    if script_lang in LANGS and script_lang != "en-IN":
        return script_lang
    hints = language_hint_index()
    votes: dict[str, int] = {}
    for t in tokenize(text):
        for lang in hints.get(t.key, ()):
            votes[lang] = votes.get(lang, 0) + 1
    votes.pop("en-IN", None)
    if votes:
        return max(votes, key=votes.get)
    return "en-IN"


def language_evidence(text: str, village_names: set[str] | frozenset[str] = frozenset()) -> dict[str, int]:
    """How many words in the text belong to each language. Village names say nothing about the language spoken."""
    index = language_evidence_index()
    counts: dict[str, int] = {}
    for t in tokenize(text):
        if t.key not in village_names:
            for lang in index.get(t.key, ()):
                counts[lang] = counts.get(lang, 0) + 1
    return counts


def language_to_switch_to(current: str, detected: str, evidence: dict[str, int], previous: str | None) -> str | None:
    """The language to move to, or None to stay. Prisma's tag alone is not enough: it comes from the transcript's script.

    Words beat the tag, so Kannada written in Telugu letters stays Kannada. Without words, the same new
    language twice in a row is enough, except for two cases where the tag proves little: Kannada and Telugu,
    which Prisma mixes up on bad lines, and English, because a village name in Latin letters is tagged English.
    """
    top = max(evidence.values(), default=0)
    if top > evidence.get(current, 0):
        leaders = [lang for lang, n in evidence.items() if n == top]
        if detected in leaders:
            return detected
        native = [lang for lang in leaders if lang != "en-IN"]
        if len(native) == 1:
            return native[0]
    if detected == previous and detected not in (current, "en-IN") and {current, detected} != {"kn-IN", "te-IN"}:
        return detected
    return None


# ------------------------------------------------------------------ village


@dataclass
class VillageMatch:
    name: str | None
    pin: str | None
    score: float
    heard: str = ""
    alternatives: list[tuple[str, str, float]] = field(default_factory=list)
    unsure: bool = False  # short word or close call, even if the score is high
    runner_up: str | None = None  # the other village, when it's a close call

    @property
    def accepted(self) -> bool:
        return self.name is not None and self.score >= UNSURE

    @property
    def confident(self) -> bool:
        return self.name is not None and self.score >= ACCEPT and not self.unsure


def _skeleton(key: str) -> str:
    return key[:1] + re.sub(r"[aeiou\s]", "", key[1:])


def _score(a: str, b: str) -> float:
    full = fuzz.ratio(a, b)
    sa, sb = _skeleton(a), _skeleton(b)
    if len(sa) >= 3 and len(sb) >= 3:
        full = max(full, 0.85 * fuzz.ratio(sa, sb) + 0.15 * full)
    return full


def _could_name_a_village(key: str, names: set[str]) -> bool:
    """Words that describe an address can't name a village, unless a real village on the list uses them ('Sira Gate')."""
    if key.isdigit():
        return False
    if key in names:
        return True
    if key in FILLERS or key in non_name_keys():
        return False
    return not any(form in landmark_index() for form in _inflections(key))  # 'ಗುಡಿಯ' is still 'ಗುಡಿ'


def _words_that_join_into_a_name(toks: list[Token], candidates: list[tuple[str, str]]) -> set[int]:
    """'Bili Devalaya' is Bilidevalaya, though on their own the words mean 'white' and 'temple'."""
    names = [phonetic_key(name).replace(" ", "") for name, _ in candidates]
    keep: set[int] = set()
    for i in range(len(toks) - 1):
        joined = toks[i].key + toks[i + 1].key
        if any(fuzz.ratio(joined, name) >= JOINED_NAME for name in names):
            keep.update((i, i + 1))
    return keep


def match_village(text: str, candidates: list[tuple[str, str]], own_pin: str | None = None) -> VillageMatch:
    names = {part for name, _ in candidates for part in phonetic_key(name).split()}
    all_toks = tokenize(text)
    joined = _words_that_join_into_a_name(all_toks, candidates)
    toks = [t for i, t in enumerate(all_toks) if i in joined or _could_name_a_village(t.key, names)]
    if not toks or not candidates:
        return VillageMatch(None, None, 0.0, heard=text.strip())
    grams: list[tuple[str, list[Token]]] = []
    for n in range(1, MAX_NAME_WORDS + 1):
        for i in range(len(toks) - n + 1):
            span = toks[i:i + n]
            grams.append((" ".join(t.key for t in span), span))
            if n > 1:
                grams.append(("".join(t.key for t in span), span))
    scored = []
    for name, pin in candidates:
        ck = phonetic_key(name)
        best, best_span = 0.0, []
        for gk, span in grams:
            s = max(_score(gk, ck), _score(gk.replace(" ", ""), ck.replace(" ", "")))
            if s > best:
                best, best_span = s, span
        if best >= ACCEPT and len(best_span) > 1:
            best += 1.0 * (len(best_span) - 1)  # 'Sira Gate' should beat 'Sira' when both words were said
        if own_pin and pin != own_pin:
            best -= 3.0  # prefer villages in the PIN on the parcel, unless clearly another
        scored.append((best, name, pin, best_span))
    scored.sort(key=lambda x: -x[0])
    level = [c for c in scored if scored[0][0] - c[0] <= SAME_SCORE]
    widest = max(level, key=lambda c: len(c[3]))  # 'K R S Agrahara Kunigal' beats 'Kunigal'
    scored.remove(widest)
    scored.insert(0, widest)
    best, name, pin, span = scored[0]
    best = min(best, 100.0)
    alts = [(n, p, round(s, 1)) for s, n, p, _ in scored[1:4]]
    heard = " ".join(t.orig for t in span) if span else text.strip()
    if best < UNSURE:
        return VillageMatch(None, None, round(best, 1), heard=text.strip(), alternatives=[(name, pin, round(best, 1))] + alts)
    second = scored[1] if len(scored) > 1 else None
    runner_up = second[1] if second and best < CERTAIN and best - second[0] <= CLOSE_CALL else None
    short_word = len(span) == 1 and len(span[0].key) <= SHORT_WORD and best < CERTAIN
    return VillageMatch(name, pin, round(best, 1), heard=heard, alternatives=alts, unsure=short_word or bool(runner_up), runner_up=runner_up)


# ------------------------------------------------------------------ landmark


@dataclass
class Landmark:
    relation: str | None
    kind: str | None
    name: str
    heard: str
    also: list["Landmark"] = field(default_factory=list)

    @property
    def found(self) -> bool:
        return bool(self.kind or self.name)

    def _one(self) -> str:
        name = self.name
        if self.kind and name and set(name.lower().split()) <= set(self.kind.lower().split()):
            name = ""  # "milk" + "milk dairy" → "milk dairy"
        what = " ".join(p for p in (name, self.kind) if p).strip()
        if not what:
            return ""
        return f"{(self.relation or 'near').capitalize()} {what}"

    def _names(self) -> set[str]:
        return {phonetic_key(w) for w in self.name.split()}

    def same_place(self, other: "Landmark") -> bool:
        """'Behind temple' and 'Behind Anjaneya temple' are one place; 'Behind Shiva temple' is another."""
        if (self.relation, self.kind) != (other.relation, other.kind):
            return False
        return self._names() <= other._names() or other._names() <= self._names()

    def parts(self) -> list["Landmark"]:
        return [self] + self.also

    def english(self) -> str:
        return "; ".join(x for x in [a._one() for a in self.parts()] if x)


ADJECTIVES = {phonetic_key(w): label for label, words in {
    "Government": ["sarkari", "sarakari", "sarkaari", "government", "govt", "ಸರ್ಕಾರಿ", "सरकारी", "அரசு", "prabhutva", "ప్రభుత్వ"],
    "Old": ["haleya", "purana", "purani", "pazhaya", "paata", "old", "ಹಳೆಯ", "पुराना", "पुरानी", "பழைய", "పాత"],
    "New": ["hosa", "naya", "nayi", "pudhu", "puthiya", "kotha", "new", "ಹೊಸ", "नया", "नई", "புது", "కొత్త"],
    "Big": ["dodda", "bada", "badi", "periya", "pedda", "big", "ದೊಡ್ಡ", "बड़ा", "பெரிய", "పెద్ద"],
    "Small": ["chikka", "chota", "chhota", "chinna", "small", "ಚಿಕ್ಕ", "छोटा", "சின்ன", "చిన్న"],
}.items() for w in words}


def _find_relation(toks: list[Token]):
    """First direction word that is not part of a landmark name ('ಬಸ್' bus ≠ 'पास' near)."""
    idx = relation_index()
    covered = set()
    for i0, i1, _kind, _exact in _landmark_hits(toks, 0, len(toks)):
        if i1 - i0 > 1:
            covered.update(range(i0, i1))
    for n in (3, 2, 1):
        for i in range(len(toks) - n + 1):
            if covered & set(range(i, i + n)):
                continue
            k = " ".join(t.key for t in toks[i:i + n])
            if k in idx:
                return i, i + n, idx[k][0]
    return None


# case endings glued to nouns, written in phonetic-key form:
# ಮರದ marada→"marat", ಗುಡಿಯ→"kutiy", ಕೆರೆಯಲ್ಲಿ→"kereyali", கோவில்ல→"kovila", చెరువులో→"ceruvulo"
_SUFFIXES = sorted(["yali", "tali", "ali", "ke", "ku", "la", "il", "lu", "lo", "nu", "t", "y", "at"], key=len, reverse=True)


def _stem(key: str) -> str:
    return key.rstrip("aeiou") if len(key.rstrip("aeiou")) >= 3 else key


def _inflections(key: str) -> list[str]:
    """Forms of `key` with one case ending removed (not including key itself)."""
    return [key[: -len(suf)] for suf in _SUFFIXES if key.endswith(suf) and len(key) - len(suf) >= 3]


_LOOSE: dict[str, str] | None = None


def _loose_landmarks() -> dict[str, str]:
    global _LOOSE
    if _LOOSE is None:
        _LOOSE = {_stem(k): v for k, v in landmark_index().items() if " " not in k and len(k) >= 4}
    return _LOOSE


def _landmark_hits(toks: list[Token], lo: int, hi: int):
    """All (start, end, kind, exact) landmark-noun matches inside toks[lo:hi]."""
    idx, loose = landmark_index(), _loose_landmarks()
    lo, hi = max(lo, 0), min(hi, len(toks))
    hits = []
    for n in (3, 2, 1):
        for i in range(lo, hi - n + 1):
            head = " ".join(t.key for t in toks[i:i + n - 1])
            last = toks[i + n - 1].key
            k = f"{head} {last}".strip()
            if k in idx:
                hits.append((i, i + n, idx[k], True))
                continue
            for form in _inflections(last):
                k = f"{head} {form}".strip()
                if k in idx:
                    hits.append((i, i + n, idx[k], False))
                    break
                if n == 1 and _stem(form) in loose:
                    hits.append((i, i + 1, loose[_stem(form)], False))
                    break
    return hits


def _find_landmark_noun(toks: list[Token], lo: int, hi: int, anchor: int | None = None):
    """Best landmark noun in the window: exact over inflected, longer over shorter, closest to the direction word."""
    hits = _landmark_hits(toks, lo, hi)
    if not hits:
        return None

    def rank(h):
        i0, i1, _k, exact = h
        dist = 0 if anchor is None else min(abs(anchor - i1), abs(anchor - i0))
        return (not exact, -(i1 - i0), dist, i0)

    i0, i1, kind, _ = min(hits, key=rank)
    return i0, i1, kind


def _name_before(toks: list[Token], i: int, limit: int = 2) -> list[Token]:
    out = []
    j = i - 1
    rel = relation_index()
    while j >= 0 and len(out) < limit and toks[j].key not in FILLERS and toks[j].key not in rel and not toks[j].key.isdigit():
        out.insert(0, toks[j])
        j -= 1
    return out


def _parse_clause(toks: list[Token], language: str) -> Landmark:
    rel = _find_relation(toks)
    if rel:
        r0, r1, relation = rel
        rel_lang = relation_index()[" ".join(t.key for t in toks[r0:r1])][1]
        postpositional = (rel_lang in POSTPOSITIONAL or (rel_lang == "en-IN" and r1 == len(toks) and language in POSTPOSITIONAL))
        before = (max(0, r0 - 5), r0)
        after = (r1, min(len(toks), r1 + 5))
        windows = [before, after] if (postpositional and r0 > 0) else [after, before]
    else:
        relation, r0, postpositional = None, 0, False
        windows = [(0, len(toks))]

    for lo, hi in windows:
        noun = _find_landmark_noun(toks, lo, hi, anchor=r0 if rel else None)
        if noun:
            n0, n1, kind = noun
            name = _name_before(toks, n0)
            heard_span = toks[(n0 - len(name)):n1]
            return Landmark(relation or "near", kind, _pretty(name), " ".join(t.orig for t in heard_span))
    if rel:
        # no known landmark noun: keep the words next to the direction word as the landmark name
        for k, (lo, hi) in enumerate(windows):
            words = [t for t in toks[lo:hi] if t.key not in FILLERS]
            if words:
                words = words[-3:] if (k == 0 and postpositional and r0 > 0) else words[:3]
                return Landmark(relation, None, _pretty(words), " ".join(t.orig for t in words))
    return Landmark(None, None, "", " ".join(t.orig for t in toks))


_CLAUSE = re.compile(r"[,;।.!?]|(?:^|\s)(?:and|aur|mattu|matthu|mathu|mariyu|innum|matte|ಮತ್ತು|ಮತ್ತೆ|और|மற்றும்|మరియు)(?=\s|$)", re.I)


def parse_landmark(text: str, language: str = "kn-IN") -> Landmark:
    """One primary landmark, plus any extra ones said in the same answer ('bus stand hatra, temple pakka')."""
    found = []
    for clause in _CLAUSE.split(text or ""):
        toks = tokenize(clause or "")
        if toks:
            lm = _parse_clause(toks, language)
            if lm.found:
                found.append(lm)
    if not found:
        return Landmark(None, None, "", (text or "").strip())
    first = found[0]
    first.also = found[1:3]
    return first


# ------------------------------------------------------------------ house


@dataclass
class House:
    number: str | None
    colour: str | None
    notes: str
    landmark: Landmark | None = None

    @property
    def found(self) -> bool:
        return bool(self.number or self.colour or (self.landmark and self.landmark.found))

    def english(self, main: Landmark | None = None) -> str:
        """`main` is the address's main landmark: anything that repeats it is left out."""
        parts = []
        if self.number:
            parts.append(f"House no. {self.number}")
        if self.colour:
            parts.append(f"{self.colour} house")
        if self.landmark and self.landmark.found:
            seen = main.parts() if main else []
            new = [a._one() for a in self.landmark.parts() if not any(a.same_place(m) for m in seen)]
            parts += [x.lower() for x in new if x]
        return ", ".join(parts) if parts else ""


_NUM = re.compile(r"\b\d{1,4}(?:\s*[/-]\s*\d{1,4})?(?:\s?[a-zA-Z]\b)?")


def parse_house(text: str, language: str = "kn-IN") -> House:
    ascii_text = _ascii_digits(text or "")
    m = _NUM.search(ascii_text)
    number = re.sub(r"\s+", "", m.group(0)).upper() if m else None
    colours = colour_index()
    colour = next((colours[t.key] for t in tokenize(text) if t.key in colours), None)
    lm = parse_landmark(text, language)
    return House(number, colour, text.strip(), lm if lm.kind else None)


# ------------------------------------------------------------------ yes / no


def parse_yes_no(text: str) -> bool | None:
    toks = tokenize(text)
    idx = polarity_index()
    for n in (2, 1):
        for i in range(len(toks) - n + 1):
            k = " ".join(t.key for t in toks[i:i + n])
            if n == 2 and k in idx:
                return idx[k][0]
    for t in toks:
        if t.key in idx:
            return idx[t.key][0]
    return None


NUMBER_KEYS = {phonetic_key(w) for w in NUMBER_WORDS}
