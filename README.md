# Vilasa · ವಿಳಾಸ

**Vilasa is a multilingual voice agent that fixes rural delivery addresses.** When a rider can't find a house, Vilasa calls the customer and asks three short questions in the customer's own language: which village, what landmark, and which house. It reads the answer back to confirm, then sends the rider a clean address card with a Maps link.

> *"near temple, kyatsandra, tumkur · PIN 572101"* → **Kyathsandra, Tumakuru taluk (PIN corrected 572101 → 572104) · Behind Anjaneya temple · House no. 23, blue house**

Built on Gnani's **Prisma v3.0** (speech-to-text) and **Timbre v3.0** (text-to-speech) for the Great Indian AI Internship Challenge.

## Why it's hard, and what Vilasa does about it

| Problem | What Vilasa does |
|---|---|
| Speech models misspell village names nobody has heard of | For each PIN, Vilasa sends Prisma up to 200 **keyterms**: village names from the India Post directory for that PIN and nearby PINs, plus landmark words |
| People give landmarks, not street names | Direction words in 5 languages (*hatra, ke paas, pakkathula, daggara, near*…) plus landmark nouns are turned into "Behind Anjaneya temple" |
| The customer may not speak the rider's language | Prisma runs with `indic-auto` language detection. Vilasa greets in the local language, then **switches to the language the customer replies in**: Kannada, Hindi, English, Tamil, Telugu, and Kanglish/Hinglish |
| Native script vs English spellings (ಕ್ಯಾತಸಂದ್ರ vs Kyathsandra) | Everything is reduced to one phonetic key, so a single fuzzy matcher works across scripts |
| The PIN on the parcel is often wrong | The matcher also searches neighbouring PINs and shows the correction on the card |
| Bad phone lines | `scripts/benchmark.py` tests 8 kHz phone audio with crowd and traffic noise, with keyterms on and off |

## Quick start (about 10 minutes)

You need Python 3.10+ and Git. Use your personal laptop.

```bash
git clone https://github.com/<you>/vilasa.git
cd vilasa
python -m venv .venv
# Windows:  .venv\Scripts\activate        Mac/Linux:  source .venv/bin/activate
pip install -r requirements.txt
```

**1. Run in mock mode first (no key, no credits).**

```bash
uvicorn vilasa.app:app --reload
```

Open http://127.0.0.1:8000, click **Call with Vilasa**, then use **Use the scripted demo answer** or type an answer. You'll see the whole flow, but voices are replaced by a chime.

**2. Add your key.**

```bash
cp .env.example .env        # Windows: copy .env.example .env
```

Open `.env` and paste your key after `GNANI_API_KEY=`. **`.env` is git-ignored. Never commit it, paste it in chat, or show it in a video.**

**3. Smoke test the live API.**

```bash
python scripts/smoke_test.py
```

This makes a Kannada clip and a Hindi clip with Timbre, transcribes both with Prisma (keyterms off and on), and prints what Vilasa extracted. If anything fails, paste the output (it never contains your key).

**4. Run live.** Restart `uvicorn`. The pill at the top now says **LIVE**. Hold the mic button (or the space bar) and speak.

## Load the real India Post data

The repo ships with a small **demo** PIN file (`data/pincodes_tumakuru.json`; the village↔PIN pairs are approximate). Before you run the benchmark or record the demo, replace it with the official directory:

1. Download **"All India Pincode Directory"** (CSV) from data.gov.in into `data/raw/`
2. Build the file:
   ```bash
   python scripts/build_keyterms.py data/raw/<file>.csv --district TUMKUR --district TUMAKURU
   ```
3. Update the PINs in `data/deliveries.json` to match, then restart the app. The demo banner disappears.

## Benchmark: does it get village names right on a bad line?

```bash
python scripts/make_utterances.py --n 40          # synthetic answers from real village names, 5 languages + Kanglish
python scripts/make_benchmark_audio.py --limit 3  # try a few TTS clips first, then run without --limit
python scripts/benchmark.py --dry-run             # see how many STT calls it will make
python scripts/benchmark.py                       # → benchmark/results/summary.md + chart.html
```

The benchmark scores the audio in five conditions: clean, phone (8 kHz, 300–3400 Hz), phone + crowd noise at 10 dB, phone + traffic noise at 5 dB, and phone + crowd noise at 0 dB. Each condition runs **with and without keyterms**. It reports:

- **Village (Vilasa):** the right village was picked
- **Exact:** the raw transcript already matched the name with no fuzzy help
- **House no.:** the house number was captured
- **Landmark:** the landmark type was recognised

Results are cached, so a re-run costs nothing for items already done.

Synthetic TTS audio is easier than real people. For stronger evidence, record friends or family **with their consent** saying the lines in `benchmark/utterances.csv`. Save the clips as `benchmark/recordings/<id>.wav`. The benchmark uses them automatically.

## How it works

```
customer audio ─► Prisma v3.0 (indic-auto, keyterms = villages for this PIN + landmark words)
                     │ native-script transcript + detected language
                     ▼
            normalize.py   any script → Latin → phonetic key
            extractor.py   village fuzzy match · landmark + direction · house no./colour · yes/no
            callflow.py    village → landmark → house → read-back ("Sari na?"), follows customer's language
                     │
         Timbre v3.0 speaks the next question ◄─┘      courier card (English) + Google Maps link
```

| File | What it does |
|---|---|
| `vilasa/gnani.py` | Prisma/Timbre REST clients: retries on 429/5xx, disk cache, usage log, mock mode |
| `vilasa/pincodes.py` | India Post CSV → per-PIN villages → keyterms (≤200) |
| `vilasa/lexicon.py` | Direction words, landmarks, colours and yes/no in 5 languages (romanised + native script) |
| `vilasa/extractor.py` | The parsing and matching logic |
| `vilasa/callflow.py` | The 4-step call and the courier card |
| `vilasa/prompts.py` | What Vilasa says, per language |
| `vilasa/app.py` | FastAPI app (`/api/calls`, `/api/calls/{id}/turn`, `/api/speech/...`) |
| `static/` | Courier dashboard + customer phone (records 16 kHz WAV in the browser, so no ffmpeg needed) |

Tests: `pytest` (60 tests, always in mock mode).

## Before the demo: get it checked

- **Native speakers:** the prompts (`vilasa/prompts.py`) and word lists (`vilasa/lexicon.py`) need checking by a native speaker of each language.
- **Synthetic data only:** customers, phone numbers and orders in `data/deliveries.json` are invented. Don't put real phone numbers, Aadhaar, PAN or recorded calls in the repo or the video.
- **Honest greeting:** Vilasa says it is an automated delivery assistant.

## Limits

- The REST API caps each request at 30 s of audio, so the recorder stops at 28 s. Streaming STT would make it feel more like a real call.
- In the demo, a browser "phone" stands in for a real phone call. A real deployment would put this behind telephony (for example SIP, or Gnani's own stack).
- The Maps link is a search, not a geocode.

---
All customer data in this repo is synthetic.
