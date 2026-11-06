"""Does Vilasa get village names right on bad phone lines? Measure it.

For every utterance × audio condition × (keyterms off / on) we ask Prisma v3.0 for a
transcript, then score these against ground truth:

  village   – Vilasa's matcher picks the right village (and so the right PIN)
  exact     – the raw transcript already spells the village so it matches exactly (no fuzzy help)
  house     – the house number digits appear in the transcript
  landmark  – the landmark type is recognised (temple, school, lake …)
  language  – Prisma's detected language is the utterance's language (Kanglish counts as Kannada)

    python scripts/benchmark.py --dry-run                 # how many calls / seconds of audio
    python scripts/benchmark.py --limit 5                 # quick check
    python scripts/benchmark.py --per-language 2          # a small sample of every language
    python scripts/benchmark.py                           # full run → benchmark/results/

Results are cached per audio+settings, so re-running costs nothing for finished items.
"""

import argparse
import csv
import json
import re
import time
from collections import defaultdict

import _path  # noqa: F401
from make_benchmark_audio import per_language
from vilasa.audio import add_noise, phone_quality
from vilasa.callflow import CallSession
from vilasa.config import ROOT, settings
from vilasa.extractor import match_village, parse_landmark, tokenize
from vilasa.gnani import GnaniError, MockSTT, PrismaSTT, wav_seconds
from vilasa.normalize import _ascii_digits, phonetic_key
from vilasa.pincodes import PinDirectory

CONDITIONS = {
    "clean": lambda a: a,
    "phone": phone_quality,
    "phone+crowd 10dB": lambda a: add_noise(phone_quality(a), 10, "crowd"),
    "phone+traffic 5dB": lambda a: add_noise(phone_quality(a), 5, "traffic", seed=11),
    "phone+crowd 0dB": lambda a: add_noise(phone_quality(a), 0, "crowd", seed=13),
}
BENCH = ROOT / "benchmark"


def load_audio(uid: str) -> bytes | None:
    for folder in ("recordings", "audio"):
        p = BENCH / folder / f"{uid}.wav"
        if p.exists():
            return p.read_bytes()
    return None


def variant(uid: str, cond: str, clean: bytes) -> bytes:
    slug = re.sub(r"[^a-z0-9]+", "_", cond)
    path = BENCH / "variants" / f"{uid}__{slug}.wav"
    if path.exists():
        return path.read_bytes()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = CONDITIONS[cond](clean)
    path.write_bytes(data)
    return data


def exact_hit(transcript: str, village: str) -> bool:
    key = phonetic_key(village).replace(" ", "")
    toks = [t.key for t in tokenize(transcript)]
    joined = {"".join(toks[i:i + n]) for n in (1, 2, 3) for i in range(len(toks) - n + 1)}
    return key in joined


def app_keyterms(row: dict, pins: PinDirectory) -> list[str]:
    """What the app sends for a caller's first answer, before it knows their language or village."""
    session = CallSession({"pin": row["pin"]}, pins)
    session.start()
    return session.stt_context()["keyterms"]


def expected_language(row: dict) -> str:
    return "kn-IN" if row["lang"] == "kn-en" else row["lang"]


def score(row: dict, transcript: str, pins: PinDirectory, detected: str | None = None) -> dict:
    m = match_village(transcript, pins.candidates(row["pin"]), own_pin=row["pin"])
    lm = parse_landmark(transcript, expected_language(row))
    kinds = {lm.kind} | {a.kind for a in lm.also}
    digits = re.findall(r"\d+", _ascii_digits(transcript))
    return {
        "village_ok": int(m.name == row["village"]),
        "exact_ok": int(exact_hit(transcript, row["village"])),
        "house_ok": int(row["house_number"] in digits),
        "landmark_ok": int(row["landmark_kind"] in kinds),
        "language_ok": int(detected == expected_language(row)),
        "matched": m.name or "",
        "match_score": m.score,
    }


def summarise(results: list[dict]) -> dict:
    groups = defaultdict(list)
    for r in results:
        groups[(r["condition"], r["keyterms"])].append(r)
    table = []
    for cond in CONDITIONS:
        for kt in ("off", "on"):
            g = groups.get((cond, kt))
            if not g:
                continue
            n = len(g)
            table.append({
                "condition": cond, "keyterms": kt, "n": n,
                "village": round(100 * sum(x["village_ok"] for x in g) / n, 1),
                "exact": round(100 * sum(x["exact_ok"] for x in g) / n, 1),
                "house": round(100 * sum(x["house_ok"] for x in g) / n, 1),
                "landmark": round(100 * sum(x["landmark_ok"] for x in g) / n, 1),
                "language": round(100 * sum(x["language_ok"] for x in g) / n, 1),
                "latency_s": round(sum(float(x["latency"] or 0) for x in g) / n, 2),
            })

    def by_language(field: str) -> dict:
        by_lang = defaultdict(lambda: defaultdict(list))
        for r in results:
            by_lang[r["lang"]][r["keyterms"]].append(r[field])
        return {lang: {kt: round(100 * sum(v) / len(v), 1) for kt, v in d.items()} for lang, d in by_lang.items()}

    return {"table": table, "village_by_language": by_language("village_ok"), "language_by_language": by_language("language_ok")}


def write_reports(summary: dict, mock: bool):
    out = BENCH / "results"
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False), encoding="utf-8")
    lines = ["# Vilasa benchmark" + (" (MOCK — not real Prisma results)" if mock else ""), "",
             "| Audio | Keyterms | n | Village (Vilasa) | Village exact in transcript | House no. | Landmark | Language detected | Latency |",
             "|---|---|---|---|---|---|---|---|---|"]
    for t in summary["table"]:
        lines.append(f"| {t['condition']} | {t['keyterms']} | {t['n']} | {t['village']}% | {t['exact']}% | {t['house']}% | {t['landmark']}% | {t['language']}% | {t['latency_s']}s |")
    for title, key in (("Village accuracy by language", "village_by_language"), ("Language detected correctly, by language", "language_by_language")):
        lines += ["", f"## {title}", "", "| Language | Keyterms off | Keyterms on |", "|---|---|---|"]
        for lang, d in summary[key].items():
            lines.append(f"| {lang} | {d.get('off', '–')}% | {d.get('on', '–')}% |")
    (out / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (out / "chart.html").write_text(chart_html(summary, mock), encoding="utf-8")
    print("\n".join(lines))
    print(f"\nReports → {out.relative_to(ROOT)}/summary.md, summary.json, chart.html")


def chart_html(summary: dict, mock: bool) -> str:
    rows = {}
    for t in summary["table"]:
        rows.setdefault(t["condition"], {})[t["keyterms"]] = t["village"]
    w, bar, gap, top = 640, 18, 30, 60
    h = top + len(rows) * (2 * bar + gap) + 30
    parts = []
    y = top
    for cond, d in rows.items():
        parts.append(f'<text x="0" y="{y + bar + 4}" class="lbl">{cond}</text>')
        for i, (kt, cls) in enumerate((("off", "off"), ("on", "on"))):
            v = d.get(kt)
            if v is None:
                continue
            bw = (w - 200) * v / 100
            yy = y + i * bar
            parts.append(f'<rect x="170" y="{yy}" width="{bw:.1f}" height="{bar - 3}" rx="3" class="{cls}"/>')
            parts.append(f'<text x="{176 + bw:.1f}" y="{yy + bar - 7}" class="val">{v:g}%</text>')
        y += 2 * bar + gap
    title = "Right village picked, by phone-line quality" + (" — MOCK" if mock else "")
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>Vilasa benchmark</title>
<style>
:root{{--bg:#f7f3ea;--ink:#1d1b16;--muted:#5c574b;--off:#c9c1ae;--on:#b3261e}}
@media (prefers-color-scheme:dark){{:root{{--bg:#15140f;--ink:#f1ece0;--muted:#a9a291;--off:#4a463c;--on:#e5544b}}}}
body{{background:var(--bg);color:var(--ink);font-family:system-ui,sans-serif;margin:24px}}
svg{{max-width:100%;height:auto}} .lbl{{fill:var(--ink);font-size:13px}} .val{{fill:var(--muted);font-size:12px}}
.off{{fill:var(--off)}} .on{{fill:var(--on)}} .key{{font-size:13px;fill:var(--muted)}}
</style></head><body>
<svg viewBox="0 0 {w} {h}" role="img" aria-label="{title}">
<text x="0" y="22" style="font-size:18px;font-weight:600;fill:var(--ink)">{title}</text>
<rect x="0" y="34" width="12" height="12" class="off"/><text x="18" y="45" class="key">Prisma v3.0, no keyterms</text>
<rect x="200" y="34" width="12" height="12" class="on"/><text x="218" y="45" class="key">Prisma v3.0 + India Post village keyterms</text>
{''.join(parts)}
</svg></body></html>"""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int, default=0, help="Only the first N utterances")
    ap.add_argument("--per-language", type=int, default=0, help="Only the first N utterances of each language")
    ap.add_argument("--conditions", nargs="*", default=list(CONDITIONS), choices=list(CONDITIONS))
    ap.add_argument("--keyterms", choices=["both", "on", "off"], default="both")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    pins = PinDirectory.load(settings.pin_file)
    rows = list(csv.DictReader((BENCH / "utterances.csv").open(encoding="utf-8")))
    if args.per_language:
        rows = per_language(rows, args.per_language)
    if args.limit:
        rows = rows[: args.limit]
    kt_modes = ["off", "on"] if args.keyterms == "both" else [args.keyterms]
    have = [(r, load_audio(r["id"])) for r in rows]
    missing = [r["id"] for r, a in have if a is None]
    if missing:
        print(f"Missing audio for {len(missing)} utterances (run scripts/make_benchmark_audio.py): {', '.join(missing[:8])}…")
    have = [(r, a) for r, a in have if a is not None]
    seconds = sum(wav_seconds(a) for _, a in have)
    calls = len(have) * len(args.conditions) * len(kt_modes)
    print(f"{len(have)} utterances × {len(args.conditions)} conditions × {len(kt_modes)} keyterm modes = {calls} STT calls, "
          f"~{seconds * len(args.conditions) * len(kt_modes) / 60:.1f} min of audio (cached calls are free).")
    if args.dry_run or not have:
        return

    stt = MockSTT(settings) if settings.mock else PrismaSTT(settings, use_cache=True)
    results = []
    for r, clean in have:
        for cond in args.conditions:
            audio = variant(r["id"], cond, clean)
            for kt in kt_modes:
                terms = app_keyterms(r, pins) if kt == "on" else None
                try:
                    res = stt.transcribe(audio, filename="a.wav", language_code="indic-auto", keyterms=terms, hint=r["text"])
                except GnaniError as e:
                    print(f"  {r['id']} {cond} kt={kt} FAIL {e}")
                    if e.status in (401, 402, 403):
                        return
                    time.sleep(2)
                    continue
                s = score(r, res.text, pins, res.language)
                results.append({"id": r["id"], "lang": r["lang"], "condition": cond, "keyterms": kt, "transcript": res.text,
                                "detected": res.language, "latency": res.latency, "cached": res.cached, **s})
                flag = "✓" if s["village_ok"] else "✗"
                print(f"  {r['id']} {r['lang']:<5} {cond:<18} kt={kt:<3} {flag} {s['matched'] or '-':<16} {res.text[:50]}")

    out = BENCH / "results"
    out.mkdir(parents=True, exist_ok=True)
    with (out / "results.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(results[0]))
        w.writeheader()
        w.writerows(results)
    write_reports(summarise(results), settings.mock)


if __name__ == "__main__":
    main()
