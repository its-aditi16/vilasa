# Vilasa · ವಿಳಾಸ

**Vilasa is a multilingual voice agent that fixes rural delivery addresses.** When a rider can't find a house, Vilasa calls the customer and asks three short questions in the customer's own language: which village, what landmark, and which house. It reads the answer back to confirm, then sends the rider a clean address card with a Maps link.

> *"near temple, kyatsandra, tumkur · PIN 572101"* → **Kyathsandra, Tumakuru taluk (PIN corrected 572101 → 572104) · Behind Anjaneya temple · House no. 23, blue house**

Built on Gnani's **Prisma v3.0** (speech-to-text) and **Timbre v3.0** (text-to-speech) for the Great Indian AI Internship Challenge.

## Why it's hard, and what Vilasa does about it

| Problem | What Vilasa does |
|---|---|
| Speech models misspell village names nobody has heard of | For each PIN, Vilasa sends Prisma up to 200 **keyterms**: village names from the India Post directory for that PIN and nearby PINs, plus landmark words, all in Latin script (native-script keyterms pull the transcript into that script) |
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

**4. Run live.** Restart `uvicorn`. The pill at the top now says **LIVE**. See [Demo](#demo) for how to run a call.

## Demo

```bash
uvicorn vilasa.app:app --reload
```

Open http://127.0.0.1:8000 in Chrome or Edge. The mic only works on `localhost` or HTTPS.

1. Press **Call with Vilasa** on a failed delivery and allow the microphone. **Hands-free** is on by default.
2. Vilasa speaks, then listens by itself. Answer when the status line says **Listening…**. It stops about 0.9 s after you finish, so just pause.
3. Answer in any of the five languages. The chip at the top flashes when Vilasa switches.
4. When the call ends, the card shows **Address fixed in N seconds · N turns**.

Use headphones if you can, so the mic doesn't pick up Vilasa's voice. There is no interrupting: wait for Vilasa to finish speaking. If nobody speaks for 6 s, Vilasa asks again, and a call with nobody there ends in a hand-off to the rider.

If the mic misbehaves, **Hold to talk** (or the space bar), the text box and **Use the scripted demo answer** all still work. Turn off Hands-free to stop the automatic listening.

The first call in a language makes that language's fixed prompts in the background, and they are cached on disk after that. Do one rehearsal call before recording.

## India Post data

`data/pincodes_tumakuru.json` is built from the official **All India Pincode Directory** (data.gov.in). It covers 60 PIN codes and 566 post-office/village names in Tumakuru district. The raw CSV is ~22 MB and git-ignored. To rebuild, or to add another district:

```bash
# put the CSV from data.gov.in in data/raw/
python scripts/build_keyterms.py data/raw/pincode_directory.csv --district TUMAKURU --district TUMKUR
```

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
- **Language detected:** Prisma's detected language matched the utterance's language (Kanglish counts as Kannada)

Results are cached, so a re-run costs nothing for items already done.

Synthetic TTS audio is easier than real people. For stronger evidence, record friends or family **with their consent** saying the lines in `benchmark/utterances.csv`. Save the clips as `benchmark/recordings/<id>.wav`. The benchmark uses them automatically.

## Results

40 synthetic clips (Timbre voices with real Tumakuru village names) in Kannada, Kanglish, Hindi, English, Tamil and Telugu, in 3 audio conditions, keyterms off vs on: 240 Prisma v3.0 calls. Every transcript goes through Vilasa's own matcher.

| Audio | Keyterms | Clips | Right village | Spelled right in transcript | House no. | Landmark | Language tag right |
|---|---|---|---|---|---|---|---|
| Clean | off | 40 | 97.5% | 72.5% | 97.5% | 97.5% | 100% |
| Clean | on | 40 | 100% | 95% | 95% | 97.5% | 92.5% |
| Phone | off | 40 | 97.5% | 62.5% | 95% | 100% | 100% |
| Phone | on | 40 | 97.5% | 95% | 92.5% | 97.5% | 87.5% |
| Phone + crowd 10 dB | off | 40 | 87.5% | 37.5% | 95% | 95% | 100% |
| Phone + crowd 10 dB | on | 40 | 87.5% | 80% | 95% | 92.5% | 90% |
| **All audio** | **off** | **120** | **94.2%** | **57.5%** | **95.8%** | **97.5%** | **100%** |
| **All audio** | **on** | **120** | **95%** | **90%** | **94.2%** | **95.8%** | **90%** |

| Right village, by language | Keyterms off | Keyterms on |
|---|---|---|
| Kannada | 41/42 | 41/42 |
| Kanglish | 16/18 | 14/18 |
| Hindi | 24/24 | 24/24 |
| English | 18/18 | 18/18 |
| Tamil | 6/9 | 9/9 |
| Telugu | 8/9 | 8/9 |

- **Keyterms mainly fix spelling:** the village name is spelled right in 90% of transcripts instead of 57.5%. The right village only moves from 94.2% to 95%, because Vilasa's fuzzy matcher already recovers most misspellings.
- **The gain is uneven:** Tamil goes from 6/9 to 9/9, but Kanglish drops from 16/18 to 14/18, and both wrong villages in the run came with keyterms on (the other misses are "not found", which gets a retry). Keyterms also lower Prisma's raw language tag on Kanglish, which is why Vilasa doesn't trust the tag alone.
- **Reply language:** replaying these transcripts through the call, Vilasa replies in the wrong language on 1 of 240, down from 3 before its language-switch guard.

These are synthetic voices and only a few clips per language (Tamil and Telugu have 3 each), so treat this as a spot check. It has not been tested with real callers. The "on" list is the one the app sends for a caller's first answer. To reproduce: `python scripts/make_benchmark_audio.py`, then `python scripts/benchmark.py --conditions clean phone "phone+crowd 10dB"`.

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

Tests: `pytest` (157 tests, always in mock mode; the voice-detection tests need `node` and are skipped without it).

## Before the demo: get it checked

- **Native speakers:** the prompts (`vilasa/prompts.py`) and word lists (`vilasa/lexicon.py`) need checking by a native speaker of each language.
- **Synthetic data only:** customers, phone numbers and orders in `data/deliveries.json` are invented. Don't put real phone numbers, Aadhaar, PAN or recorded calls in the repo or the video.
- **Honest greeting:** Vilasa says it is an automated delivery assistant.

## Limits

- The REST API caps each request at 30 s of audio, so hold-to-talk stops at 28 s and hands-free at 15 s. Streaming STT would make it feel more like a real call.
- Hands-free waits for Vilasa to finish speaking: you can't interrupt it. Its silence detection uses mic level only, so a noisy room can start or hold open a turn.
- In the demo, a browser "phone" stands in for a real phone call. A real deployment would put this behind telephony (for example SIP, or Gnani's own stack).
- The Maps link is a search, not a geocode.

---
All customer data in this repo is synthetic.
