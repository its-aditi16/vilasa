"""Check that your Gnani key works with Prisma v3.0 (STT) and Timbre v3.0 (TTS).

    python scripts/smoke_test.py               # TTS makes Kannada + Hindi clips, Prisma transcribes them
    python scripts/smoke_test.py --file my.wav # also transcribe your own recording

Paste the output in chat if anything fails. The output never contains your API key.
"""

import argparse
import json
import sys
import time

import _path  # noqa: F401
from vilasa.audio import to_wav
from vilasa.config import ROOT, settings
from vilasa.extractor import guess_language, match_village, parse_house, parse_landmark
from vilasa.gnani import GnaniError, PrismaSTT, TimbreTTS, usage_summary, wav_seconds
from vilasa.pincodes import PinDirectory

SAMPLES = [
    ("kn-IN", "572104", "ನಮ್ಮೂರು ಕ್ಯಾತಸಂದ್ರ. ಆಂಜನೇಯ ಗುಡಿ ಹಿಂದೆ ಮನೆ. ಮನೆ ನಂಬರ್ 23."),
    ("hi-IN", "572168", "मेरा गाँव हिरेहल्ली है। सरकारी स्कूल के सामने। घर नंबर 7."),
]


def line(title):
    print(f"\n── {title} " + "─" * max(0, 60 - len(title)))


def show_extraction(text, pin, pins):
    lang = guess_language(text)
    m = match_village(text, pins.candidates(pin), own_pin=pin)
    print(f"   village : {m.name} ({m.score}%)  heard='{m.heard}'")
    landmark = parse_landmark(text, lang)
    print(f"   landmark: {landmark.english() or '-'}")
    print(f"   house   : {parse_house(text, lang).english(landmark) or '-'}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", action="append", default=[], help="Your own audio file(s) to transcribe")
    ap.add_argument("--pin", default="572104", help="PIN to use for keyterms with --file")
    ap.add_argument("--voice", default=None)
    args = ap.parse_args()

    line("Settings")
    print(json.dumps(settings.redacted(), indent=1))
    if not settings.api_key:
        sys.exit("\nGNANI_API_KEY is empty. Copy .env.example to .env and paste your key there.")

    pins = PinDirectory.load(settings.pin_file)
    stt = PrismaSTT(settings, use_cache=False)
    tts = TimbreTTS(settings)
    clips = []
    ok = True

    for lang, pin, text in SAMPLES:
        line(f"Timbre TTS · {lang}")
        try:
            t0 = time.time()
            audio = tts.synthesize(text, language=lang, voice=args.voice)
            out = ROOT / "samples" / f"smoke_{lang}.wav"
            out.write_bytes(audio)
            print(f"   OK  {len(audio)} bytes, {wav_seconds(audio):.1f}s audio, {time.time() - t0:.2f}s → {out.relative_to(ROOT)}")
            clips.append((lang, pin, text, audio))
        except GnaniError as e:
            ok = False
            print(f"   FAIL {e}")

    for f in args.file:
        try:
            audio = to_wav(open(f, "rb").read())
            clips.append(("?", args.pin, None, audio))
        except (OSError, RuntimeError) as e:
            ok = False
            print(f"   Could not read {f}: {e}")

    for lang, pin, text, audio in clips:
        for use_kt in (False, True):
            line(f"Prisma STT · {lang} · indic-auto · keyterms {'ON' if use_kt else 'OFF'}")
            kt = pins.keyterms(pin, None if lang == "?" else lang) if use_kt else None
            try:
                r = stt.transcribe(audio, language_code="indic-auto", keyterms=kt)
                print(f"   transcript: {r.text}")
                print(f"   detected  : {r.language}   latency: {r.latency}s   keyterms sent: {len(kt or [])}")
                if text:
                    print(f"   expected  : {text}")
                show_extraction(r.text, pin, pins)
            except GnaniError as e:
                ok = False
                print(f"   FAIL {e}")
                if use_kt:
                    print("   (If only the keyterms run fails, tell Claude — the keyterms encoding may need changing.)")

    line("Usage this machine (live calls only)")
    print(json.dumps(usage_summary(settings)))
    print("\nALL GOOD — run the app: uvicorn vilasa.app:app --reload" if ok else "\nSome steps failed — paste this output in chat.")


if __name__ == "__main__":
    main()
