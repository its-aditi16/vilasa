"""Rough Latin → native script for place names (used only to build synthetic benchmark sentences).

India Post spells villages in English ('Kyathsandra'). To make a Kannada sentence that
Timbre will read the way a local would say it, we approximate the native spelling.
It does not need to be perfect: it only seeds test audio.
"""

from __future__ import annotations

import re

from indic_transliteration import sanscript
from indic_transliteration.sanscript import transliterate

SCHEME = {
    "kn-IN": sanscript.KANNADA,
    "hi-IN": sanscript.DEVANAGARI,
    "ta-IN": sanscript.TAMIL,
    "te-IN": sanscript.TELUGU,
}

# common Karnataka place-name endings, spelled natively (retroflex ḷḷ is hard to reach via OPTITRANS)
_ENDINGS = {
    "halli": {"kn-IN": "ಹಳ್ಳಿ", "hi-IN": "हल्ली", "ta-IN": "ஹள்ளி", "te-IN": "హళ్ళి"},
    "palya": {"kn-IN": "ಪಾಳ್ಯ", "hi-IN": "पाल्या", "ta-IN": "பாளையா", "te-IN": "పాళ్య"},
}

_RULES = [  # English spelling → OPTITRANS
    (r"(?<=[bcdfghjklmnpqrstvwxz])y(?=[bcdfghjklmnpqrstvwxz])", "ai"),  # Bhyra → Bhaira
    (r"aa", "A"), (r"ee", "I"), (r"ii", "I"), (r"oo", "U"), (r"uu", "U"),
    (r"w", "v"), (r"z", "j"), (r"f", "ph"), (r"q", "k"), (r"x", "kSh"),
    (r"th", "t"), (r"dh", "d"),
]


def _to_optitrans(word: str, dravidian: bool) -> str:
    w = word.lower()
    for pat, rep in _RULES:
        w = re.sub(pat, rep, w)
    if dravidian:  # Kannada/Tamil/Telugu: plain e/o are short (E/O in OPTITRANS)
        w = w.replace("e", "E").replace("o", "O")
    return w


def latin_to_native(text: str, language: str) -> str:
    scheme = SCHEME.get(language)
    if not scheme:
        return text
    out = []
    for word in text.split():
        if not word.isascii() or not word.isalpha():
            out.append(word)
            continue
        low, tail = word.lower(), ""
        for end, native in _ENDINGS.items():
            if low.endswith(end) and len(low) > len(end):
                low, tail = low[: -len(end)], native[language]
                break
        head = transliterate(_to_optitrans(low, language != "hi-IN"), sanscript.OPTITRANS, scheme) if low else ""
        out.append(head + tail)
    return " ".join(out)
