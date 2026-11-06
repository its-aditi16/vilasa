"""Synthesize benchmark/utterances.csv with Timbre v3.0 → benchmark/audio/<id>.wav

Voices rotate across speakers. Real (consented) recordings beat synthetic ones: put them
in benchmark/recordings/<id>.wav and benchmark.py will use those instead.

    python scripts/make_benchmark_audio.py            # only missing files
    python scripts/make_benchmark_audio.py --limit 5  # try a few first
    python scripts/make_benchmark_audio.py --per-language 2  # a small sample of every language
"""

import argparse
import csv
import time

import _path  # noqa: F401
from vilasa.config import ROOT, settings
from vilasa.gnani import GnaniError, MockTTS, TimbreTTS, wav_seconds


def per_language(rows: list[dict], n: int) -> list[dict]:
    """The first n utterances of each language."""
    counts: dict[str, int] = {}
    out = []
    for r in rows:
        counts[r["lang"]] = counts.get(r["lang"], 0) + 1
        if counts[r["lang"]] <= n:
            out.append(r)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--per-language", type=int, default=0)
    args = ap.parse_args()
    rows = list(csv.DictReader((ROOT / "benchmark" / "utterances.csv").open(encoding="utf-8")))
    if args.per_language:
        rows = per_language(rows, args.per_language)
    if args.limit:
        rows = rows[: args.limit]
    out_dir = ROOT / "benchmark" / "audio"
    out_dir.mkdir(parents=True, exist_ok=True)
    tts = MockTTS(settings) if settings.mock else TimbreTTS(settings)
    chars = made = 0
    for r in rows:
        out = out_dir / f"{r['id']}.wav"
        if out.exists():
            continue
        try:
            audio = tts.synthesize(r["text"], language=r["tts_language"], voice=r["voice"])
        except GnaniError as e:
            print(f"  {r['id']} FAIL {e}")
            if e.status in (401, 402, 403):
                break
            time.sleep(2)
            continue
        out.write_bytes(audio)
        chars += len(r["text"])
        made += 1
        print(f"  {r['id']} [{r['lang']}] {r['voice']:<8} {wav_seconds(audio):4.1f}s  {r['text'][:60]}")
    print(f"Made {made} clips ({chars} characters){' — MOCK chimes, set your key for real audio' if settings.mock else ''}.")


if __name__ == "__main__":
    main()
