"""Write benchmark/utterances.csv: synthetic customer answers built from real village names.

Each line has a village, a landmark with a direction word, and a house number, in
Kannada, Kanglish, Hindi, English, Tamil or Telugu. Ground truth is stored next to the text.

    python scripts/make_utterances.py --n 40
"""

import argparse
import csv
import random
import re

import _path  # noqa: F401
from vilasa.config import ROOT, settings
from vilasa.pincodes import PinDirectory
from vilasa.translit import latin_to_native

VOICES = ["Chetana", "Avinash", "Lakshmi", "Prakash", "Kalpana", "Devansh", "Shivani", "Harshad"]

# kind → per-language noun; relation → per-language word
LM = {
    "temple": {"kn-IN": "ಗುಡಿ", "hi-IN": "मंदिर", "en-IN": "temple", "ta-IN": "கோவில்", "te-IN": "గుడి", "kn-en": "temple"},
    "school": {"kn-IN": "ಶಾಲೆ", "hi-IN": "स्कूल", "en-IN": "school", "ta-IN": "பள்ளிக்கூடம்", "te-IN": "బడి", "kn-en": "school"},
    "lake": {"kn-IN": "ಕೆರೆ", "hi-IN": "तालाब", "en-IN": "lake", "ta-IN": "ஏரி", "te-IN": "చెరువు", "kn-en": "kere"},
    "bus stand": {"kn-IN": "ಬಸ್ ನಿಲ್ದಾಣ", "hi-IN": "बस स्टैंड", "en-IN": "bus stand", "ta-IN": "பஸ் ஸ்டாண்ட்", "te-IN": "బస్ స్టాండ్", "kn-en": "bus stand"},
    "milk dairy": {"kn-IN": "ಹಾಲಿನ ಡೈರಿ", "hi-IN": "डेयरी", "en-IN": "milk dairy", "ta-IN": "பால் சொசைட்டி", "te-IN": "డెయిరీ", "kn-en": "dairy"},
    "water tank": {"kn-IN": "ನೀರಿನ ಟ್ಯಾಂಕ್", "hi-IN": "पानी की टंकी", "en-IN": "water tank", "ta-IN": "டேங்க்", "te-IN": "ట్యాంక్", "kn-en": "water tank"},
}
NAMES = {
    "temple": {"kn-IN": ["ಆಂಜನೇಯ", "ಮಾರಮ್ಮ", "ಬಸವಣ್ಣ"], "hi-IN": ["हनुमान", "राम"], "en-IN": ["Anjaneya", "Maramma"],
               "ta-IN": ["முருகன்", "அம்மன்"], "te-IN": ["ఆంజనేయ", "రామాలయం"], "kn-en": ["Anjaneya", "Ganesha"]},
    "school": {"kn-IN": ["ಸರ್ಕಾರಿ"], "hi-IN": ["सरकारी"], "en-IN": ["government"], "ta-IN": ["அரசு"], "te-IN": ["ప్రభుత్వ"], "kn-en": ["government"]},
}
REL = {
    "near": {"kn-IN": "ಹತ್ತಿರ", "hi-IN": "के पास", "en-IN": "Near", "ta-IN": "பக்கத்துல", "te-IN": "దగ్గర", "kn-en": "hatra"},
    "behind": {"kn-IN": "ಹಿಂದೆ", "hi-IN": "के पीछे", "en-IN": "Behind", "ta-IN": "பின்னாடி", "te-IN": "వెనక", "kn-en": "hinde"},
    "opposite": {"kn-IN": "ಎದುರು", "hi-IN": "के सामने", "en-IN": "Opposite", "ta-IN": "எதிரே", "te-IN": "ఎదురుగా", "kn-en": "eduru"},
}
TEMPLATE = {
    "kn-IN": "ನಮ್ಮೂರು {v}. {lm} {rel} ನಮ್ಮ ಮನೆ. ಮನೆ ನಂಬರ್ {n}.",
    "kn-en": "ನಮ್ಮೂರು {v}, {lm} {rel}. House number {n}.",
    "hi-IN": "मेरा गाँव {v} है। {lm} {rel} घर है। घर नंबर {n}.",
    "en-IN": "My village is {v}. {rel} the {lm}. House number {n}.",
    "ta-IN": "என் ஊர் {v}. {lm} {rel} எங்க வீடு. வீட்டு நம்பர் {n}.",
    "te-IN": "మా ఊరు {v}. {lm} {rel} మా ఇల్లు. ఇంటి నంబర్ {n}.",
}
MIX = [("kn-IN", 14), ("kn-en", 6), ("hi-IN", 8), ("en-IN", 6), ("ta-IN", 3), ("te-IN", 3)]


def build(n: int, seed: int):
    rng = random.Random(seed)
    pins = PinDirectory.load(settings.pin_file)
    town_words = re.compile(r"\d|\.|extn|extension|campus|nagar|city|colony|road|bazar|fort|layout|tumakuru|mutt|math|bus|market|station|kendra", re.I)
    pool = [(v, p) for p, info in sorted(pins.pins.items()) for v in info.villages if not town_words.search(v) and len(v) > 3]
    total = sum(c for _, c in MIX)
    rows, i = [], 0
    for lang, share in MIX:
        for _ in range(round(n * share / total)):
            village, pin = rng.choice(pool)
            kind = rng.choice(list(LM))
            rel = rng.choice(list(REL))
            num = str(rng.randint(1, 240))
            script_lang = "kn-IN" if lang == "kn-en" else lang
            v_text = village if lang == "en-IN" else latin_to_native(village, script_lang)
            name = rng.choice(NAMES.get(kind, {}).get(lang, [""]))
            lm_text = f"{name} {LM[kind][lang]}".strip()
            text = TEMPLATE[lang].format(v=v_text, lm=lm_text, rel=REL[rel][lang], n=num)
            i += 1
            rows.append({
                "id": f"u{i:03d}", "lang": lang, "tts_language": "auto" if lang == "kn-en" else lang,
                "voice": VOICES[i % len(VOICES)], "text": text, "pin": pin, "village": village,
                "landmark_kind": kind, "relation": rel, "house_number": num,
            })
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--seed", type=int, default=16)
    args = ap.parse_args()
    rows = build(args.n, args.seed)
    out = ROOT / "benchmark" / "utterances.csv"
    out.parent.mkdir(exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote {len(rows)} utterances → {out.relative_to(ROOT)}")
    for r in rows[:3]:
        print(f"  {r['id']} [{r['lang']}] {r['text']}")


if __name__ == "__main__":
    main()
