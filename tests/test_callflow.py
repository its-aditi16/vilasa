import json
from pathlib import Path

import pytest

from vilasa.callflow import DONE, HANDOFF, LANDMARK, VILLAGE, CallSession
from vilasa.normalize import detect_language
from vilasa.pincodes import PinDirectory

ROOT = Path(__file__).resolve().parent.parent
PINS = PinDirectory.load(ROOT / "data" / "pincodes_tumakuru.json")
DELIVERIES = json.loads((ROOT / "data" / "deliveries.json").read_text(encoding="utf-8"))["deliveries"]


def run(delivery, answers=None):
    s = CallSession(delivery, PINS)
    s.start()
    for step in ("village", "landmark", "house", "confirm"):
        text = (answers or delivery["mock_answers"])[step]
        s.handle(text, detect_language(text))
    return s


@pytest.mark.parametrize("d", DELIVERIES, ids=[d["id"] for d in DELIVERIES])
def test_every_scripted_call_completes(d):
    s = run(d)
    assert s.state == DONE
    card = s.card()
    assert card["status"] == "confirmed"
    assert card["village"] and card["landmark"]


def test_language_follows_customer():
    hindi = next(d for d in DELIVERIES if d["id"] == "VIL-1002")
    s = run(hindi)
    assert s.language == "hi-IN"
    assert any(t.text.startswith("मैंने लिखा है") for t in s.turns)


def test_wrong_pin_gets_corrected_on_card():
    s = run(next(d for d in DELIVERIES if d["id"] == "VIL-1001"))
    assert s.card()["pin_corrected"] == "572104"


def test_retry_then_move_on_when_village_unknown():
    s = CallSession(DELIVERIES[0], PINS)
    s.start()
    s.handle("mumbai", "en-IN")
    assert s.state == VILLAGE and s.turns[-1].meta["prompt"] == "retry"
    s.handle("delhi", "en-IN")
    s.handle("chennai", "en-IN")
    assert s.state == LANDMARK  # gave up after retries, kept the raw words for the rider


def test_no_at_readback_restarts_then_hands_off():
    d = DELIVERIES[3]
    s = run(d, {**d["mock_answers"], "confirm": "no"})
    assert s.state == VILLAGE  # restarted once
    for step in ("village", "landmark", "house"):
        s.handle(d["mock_answers"][step], "en-IN")
    s.handle("no, wrong", "en-IN")
    assert s.state == HANDOFF
    assert s.card()["status"] == "needs rider call"


def test_keyterms_fit_prisma_limit():
    for pin in PINS.pins:
        assert len(PINS.keyterms(pin, "kn-IN")) <= 200
