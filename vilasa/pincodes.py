"""India Post PIN directory → per-PIN village lists → Prisma keyterms.

Source: "All India Pincode Directory" on data.gov.in (CSV). Branch offices (B.O) are
usually named after the village they serve, so their names are the best free list of
village spellings for a PIN. scripts/build_keyterms.py turns the CSV into a JSON file
for one or more districts; this module loads that JSON.
"""

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .lexicon import landmark_keyterms

_SUFFIX = re.compile(r"\s*\b(b\.?\s*o|s\.?\s*o|h\.?\s*o|g\.?\s*p\.?\s*o|bo|so|ho)\b\.?\s*$", re.I)
_PAREN = re.compile(r"\s*\(.*?\)\s*")


def clean_office_name(name: str) -> str:
    """'Kyathsandra B.O' → 'Kyathsandra'; 'Tumkur H.O' → 'Tumkur'."""
    name = _PAREN.sub(" ", name or "")
    name = _SUFFIX.sub("", name.strip())
    name = re.sub(r"\s+", " ", name).strip(" .-")
    return name.title() if name.isupper() or name.islower() else name


@dataclass
class PinInfo:
    pin: str
    villages: list[str] = field(default_factory=list)
    taluk: str = ""
    district: str = ""
    state: str = ""
    lat: float | None = None
    lon: float | None = None


class PinDirectory:
    def __init__(self, pins: dict[str, PinInfo], meta: dict | None = None):
        self.pins = pins
        self.meta = meta or {}

    # ---------------------------------------------------------------- loading
    @classmethod
    def load(cls, path: Path) -> "PinDirectory":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        pins = {p: PinInfo(pin=p, **info) for p, info in data["pins"].items()}
        return cls(pins, data.get("meta", {}))

    @classmethod
    def from_india_post_csv(cls, csv_path: Path, districts: list[str] | None = None, states: list[str] | None = None) -> "PinDirectory":
        """Accepts both the old (Districtname/Taluk) and new (district/latitude) column layouts."""
        want_d = {d.strip().lower() for d in districts or []}
        want_s = {s.strip().lower() for s in states or []}
        pins: dict[str, PinInfo] = {}
        with open(csv_path, newline="", encoding="utf-8-sig", errors="replace") as fh:
            for row in csv.DictReader(fh):
                r = {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}
                district = r.get("district") or r.get("districtname") or ""
                state = r.get("statename") or ""
                if want_d and district.lower() not in want_d:
                    continue
                if want_s and state.lower() not in want_s:
                    continue
                pin = re.sub(r"\D", "", r.get("pincode", ""))
                if len(pin) != 6:
                    continue
                info = pins.setdefault(pin, PinInfo(pin=pin, district=district.title(), state=state.title()))
                name = clean_office_name(r.get("officename", ""))
                if name and name not in info.villages:
                    info.villages.append(name)
                info.taluk = info.taluk or (r.get("taluk") or r.get("divisionname", "")).title()
                for key, attr in (("latitude", "lat"), ("longitude", "lon")):
                    try:
                        val = float(r.get(key, ""))
                        if getattr(info, attr) is None and val:
                            setattr(info, attr, val)
                    except ValueError:
                        pass
        return cls(pins, {"source": str(Path(csv_path).name), "districts": sorted(want_d), "states": sorted(want_s)})

    def save(self, path: Path):
        out = {
            "meta": self.meta,
            "pins": {
                p: {k: v for k, v in vars(i).items() if k != "pin"}
                for p, i in sorted(self.pins.items())
            },
        }
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    # ---------------------------------------------------------------- queries
    def get(self, pin: str) -> PinInfo | None:
        return self.pins.get(str(pin))

    def neighbours(self, pin: str, limit: int = 8) -> list[PinInfo]:
        """PINs sharing the first 4–5 digits (same delivery area), closest numbers first."""
        pin = str(pin)
        near = [p for p in self.pins if p != pin and p[:4] == pin[:4]]
        near.sort(key=lambda p: (p[:5] != pin[:5], abs(int(p) - int(pin))))
        return [self.pins[p] for p in near[:limit]]

    def candidates(self, pin: str) -> list[tuple[str, str]]:
        """(village, pin) pairs to match against: own PIN first, then neighbours (a wrong PIN is common)."""
        out, seen = [], set()
        info = self.get(pin)
        groups = ([info] if info else []) + self.neighbours(pin)
        for g in groups:
            for v in g.villages:
                if v.lower() not in seen:
                    seen.add(v.lower())
                    out.append((v, g.pin))
        return out

    def keyterms(self, pin: str, language: str | None = None, extra: list[str] | None = None, limit: int = 200) -> list[str]:
        """Prisma keyterms for a call: villages (own PIN, then nearby), taluk/district, landmark words."""
        info = self.get(pin)
        terms: list[str] = list(extra or [])
        terms += [v for v, _ in self.candidates(pin)]
        if info:
            terms += [t for t in (info.taluk, info.district) if t]
        terms += landmark_keyterms(language)
        seen, out = set(), []
        for t in terms:
            if t and t.lower() not in seen:
                seen.add(t.lower())
                out.append(t)
        return out[:limit]
