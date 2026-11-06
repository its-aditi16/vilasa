"""The voice-activity logic runs in the browser, so these need node. Skipped if it isn't installed."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

RECORDER = Path(__file__).resolve().parent.parent / "static" / "recorder.js"
FRAME = 43  # ms of audio in one frame
QUIET, TALK = 0.002, 0.1

pytestmark = pytest.mark.skipif(not shutil.which("node"), reason="node is not installed")


def run(levels):
    """Feeds the levels to VoiceActivity; returns [(event, ms)] plus when speech started and ended."""
    script = f"""
        const window = {{}};
        {RECORDER.read_text(encoding="utf-8")}
        const vad = new window.VoiceActivity();
        const events = [];
        for (const level of {json.dumps(levels)}) {{
            const e = vad.feed(level, {FRAME});
            if (e) events.push([e, vad.now]);
        }}
        console.log(JSON.stringify({{ events, start: vad.speechStart, end: vad.speechEnd }}));
    """
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True, encoding="utf-8", check=True).stdout
    return json.loads(out)


def frames(ms, level):
    return [level] * round(ms / FRAME)


def names(result):
    return [e for e, _ in result["events"]]


def test_finds_speech_and_stops_after_about_900_ms_of_silence():
    r = run(frames(1000, QUIET) + frames(2000, TALK) + frames(1500, QUIET))
    assert names(r)[:2] == ["speech", "end"]
    assert 950 <= r["start"] <= 1050
    assert 2850 <= r["end"] <= 3100
    assert 850 <= r["events"][1][1] - r["end"] <= 950


def test_short_pauses_between_words_do_not_end_the_answer():
    r = run(frames(500, QUIET) + frames(800, TALK) + frames(600, QUIET) + frames(800, TALK) + frames(1000, QUIET))
    assert names(r) == ["speech", "end"]
    assert r["end"] > 2500


def test_says_so_after_six_seconds_of_nothing():
    r = run(frames(6200, QUIET))
    assert names(r)[0] == "no-speech"
    assert 5950 <= r["events"][0][1] <= 6050


def test_stops_at_the_fifteen_second_limit():
    r = run(frames(500, QUIET) + frames(16000, TALK))
    assert names(r)[:2] == ["speech", "max"]
    assert 15400 <= r["events"][1][1] <= 15600


def test_a_click_is_not_speech():
    assert names(run(frames(500, QUIET) + [TALK] + frames(1000, QUIET))) == []


def test_steady_room_noise_is_not_speech():
    assert names(run(frames(4000, 0.02))) == []


def test_speech_is_found_over_room_noise():
    r = run(frames(500, 0.02) + frames(1000, 0.12) + frames(1200, 0.02))
    assert names(r) == ["speech", "end"]


def test_talking_during_calibration_still_counts():
    assert names(run(frames(1500, TALK) + frames(1200, QUIET)))[:2] == ["speech", "end"]
