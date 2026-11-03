"""Script detection, Indic → Latin transliteration and a phonetic key for fuzzy matching.

Why: Prisma returns native script (ಕ್ಯಾತಸಂದ್ರ), India Post lists English spellings
(Kyathsandra), and people type Kanglish (kyathasandra). Everything is reduced to one
loose Latin "phonetic key" so a single matcher works across all five languages.
"""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache

from indic_transliteration import sanscript
from indic_transliteration.sanscript import transliterate

# Unicode block → (sanscript scheme, language code)
SCRIPTS = [
    (0x0900, 0x097F, sanscript.DEVANAGARI, "hi-IN"),
    (0x0980, 0x09FF, sanscript.BENGALI, "bn-IN"),
    (0x0A00, 0x0A7F, sanscript.GURMUKHI, "pa-IN"),
    (0x0A80, 0x0AFF, sanscript.GUJARATI, "gu-IN"),
    (0x0B80, 0x0BFF, sanscript.TAMIL, "ta-IN"),
    (0x0C00, 0x0C7F, sanscript.TELUGU, "te-IN"),
    (0x0C80, 0x0CFF, sanscript.KANNADA, "kn-IN"),
    (0x0D00, 0x0D7F, sanscript.MALAYALAM, "ml-IN"),
]


def _script_of(ch: str):
    cp = ord(ch)
    for lo, hi, scheme, lang in SCRIPTS:
        if lo <= cp <= hi:
            return scheme, lang
    return None


def script_counts(text: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for ch in text:
        s = _script_of(ch)
        if s:
            counts[s[1]] = counts.get(s[1], 0) + 1
        elif ch.isascii() and ch.isalpha():
            counts["latin"] = counts.get("latin", 0) + 1
    return counts


def detect_language(text: str) -> str | None:
    """Language from script alone. Latin text → en-IN (call flow refines Kanglish/Hinglish)."""
    counts = script_counts(text or "")
    if not counts:
        return None
    indic = {k: v for k, v in counts.items() if k != "latin"}
    if indic:
        return max(indic, key=indic.get)
    return "en-IN"


def _ascii_digits(text: str) -> str:
    out = []
    for ch in text:
        if ch.isdigit() and not ch.isascii():
            out.append(str(unicodedata.digit(ch)))
        else:
            out.append(ch)
    return "".join(out)


@lru_cache(maxsize=4096)
def to_latin(text: str) -> str:
    """Transliterate any Indic-script runs to plain lowercase Latin; Latin passes through."""
    text = _ascii_digits(unicodedata.normalize("NFC", text or ""))
    out, run, run_scheme = [], [], None

    def flush():
        if run:
            itrans = transliterate("".join(run), run_scheme, sanscript.ITRANS)
            itrans = itrans.replace("M", "n").replace(".n", "n").replace("~N", "n").replace("~n", "n")
            out.append(itrans)
            run.clear()

    for ch in text:
        s = _script_of(ch)
        if s:
            if run_scheme is not None and s[0] != run_scheme:
                flush()
            run_scheme = s[0]
            run.append(ch)
        else:
            flush()
            run_scheme = None
            out.append(ch)
    flush()
    latin = "".join(out)
    # strip diacritics (ITRANS writes short e/o as è/ò) before lower-casing
    latin = "".join(c for c in unicodedata.normalize("NFKD", latin) if not unicodedata.combining(c)).lower()
    latin = re.sub(r"[^a-z0-9\s]", "", latin)
    return " ".join(latin.split())


def tokens(text: str) -> list[str]:
    return to_latin(text).split()


_PAIRS = [
    ("chh", "c"), ("ch", "c"), ("sh", "s"), ("zh", "l"),
    ("th", "t"), ("dh", "d"), ("ph", "p"), ("bh", "b"), ("kh", "k"), ("gh", "g"), ("jh", "j"),
    ("aa", "a"), ("ee", "i"), ("ii", "i"), ("oo", "u"), ("uu", "u"),
    ("w", "v"), ("z", "j"), ("q", "k"), ("x", "ks"), ("f", "p"),
]
_VOICING = str.maketrans({"g": "k", "d": "t", "b": "p", "j": "c"})


@lru_cache(maxsize=8192)
def phonetic_key(text: str) -> str:
    """Loose key: 'Kyathsandra', 'kyatasandra' and 'ಕ್ಯಾತಸಂದ್ರ' all land close together."""
    words = []
    for w in to_latin(text).split():
        if w.isdigit():
            words.append(w)
            continue
        for a, b in _PAIRS:
            w = w.replace(a, b)
        w = w.translate(_VOICING)
        w = re.sub(r"(.)\1+", r"\1", w)  # collapse doubles: halli → hali
        if len(w) > 3 and w.endswith("a"):
            w = w[:-1]  # drop trailing schwa: mandira → mandir
        words.append(w)
    return " ".join(words)
