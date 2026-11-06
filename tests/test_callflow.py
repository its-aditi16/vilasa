import json
from pathlib import Path

import pytest

from vilasa.callflow import DONE, HANDOFF, LANDMARK, VILLAGE, CallSession
from vilasa.lexicon import LANDMARKS, RELATIONS, landmark_keyterms
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


@pytest.mark.parametrize("language", ["kn-IN", "hi-IN", "ta-IN", "te-IN", "en-IN"])
def test_keyterms_never_use_another_languages_script(language):
    for pin in PINS.pins:
        terms = PINS.keyterms(pin, language)
        assert len(terms) <= 200
        assert {detect_language(t) for t in terms} <= {language, "en-IN"}


@pytest.mark.parametrize("language,own,foreign", [
    ("kn-IN", ["ಗುಡಿ", "gudi", "ಹತ್ರ", "hatra", "temple"], ["mandir", "kovil", "paas", "मंदिर"]),
    ("hi-IN", ["मंदिर", "mandir", "पास", "paas", "temple"], ["gudi", "kovil", "hatra", "ಗುಡಿ"]),
    ("ta-IN", ["கோவில்", "kovil", "பக்கத்துல", "pakkathula", "temple"], ["gudi", "hatra", "paas", "ಗುಡಿ"]),
    ("te-IN", ["గుడి", "gudi", "దగ్గర", "daggara", "temple"], ["mandir", "kovil", "hatra", "ಗುಡಿ"]),
])
def test_landmark_keyterms_are_the_callers_own_words(language, own, foreign):
    terms = landmark_keyterms(language)
    assert set(own) <= set(terms)
    assert not set(foreign) & set(terms)


@pytest.mark.parametrize("language", [None, "en-IN", "mr-IN"])
def test_landmark_keyterms_without_a_known_language_are_english_labels(language):
    assert landmark_keyterms(language) == list(LANDMARKS) + list(RELATIONS)


def test_direction_words_survive_the_keyterm_limit():
    for pin in PINS.pins:
        assert {"paas", "पास", "right of", "दाएं"} <= set(PINS.keyterms(pin, "hi-IN"))


def test_hindi_caller_gets_no_kannada_keyterms_on_a_kannada_delivery():
    d = next(x for x in DELIVERIES if x["default_language"] == "kn-IN")
    s = CallSession(d, PINS)
    s.start()
    assert all(t.isascii() for t in s.stt_context()["keyterms"])  # language still unknown
    s.handle("मेरा गाँव हिरेहल्ली है", "hi-IN")
    assert s.language == "hi-IN"
    assert {detect_language(t) for t in s.stt_context()["keyterms"]} == {"hi-IN", "en-IN"}


def _card(landmark, house):
    answers = {"village": "ನಮ್ಮೂರು ಕ್ಯಾತಸಂದ್ರ", "landmark": landmark, "house": house, "confirm": "ಹೌದು ಸರಿ"}
    return run(DELIVERIES[0], answers).card()


def test_card_does_not_repeat_the_landmark_in_the_house():
    card = _card("ಆಂಜನೇಯ ಗುಡಿ ಹಿಂದೆ", "ಆಂಜನೇಯ ಗುಡಿ ಹಿಂದೆ ಮನೆ, ಮನೆ ನಂಬರ್ 23")
    assert card["landmark"] == "Behind Anjaneya temple"
    assert card["house"] == "House no. 23"


def test_card_keeps_a_different_landmark_in_the_house():
    card = _card("ಆಂಜನೇಯ ಗುಡಿ ಹಿಂದೆ", "ಶಾಲೆ ಎದುರು ಮನೆ, ಮನೆ ನಂಬರ್ 23")
    assert card["house"] == "House no. 23, opposite school"


def test_card_house_is_empty_when_it_only_repeats_the_landmark():
    assert _card("ಆಂಜನೇಯ ಗುಡಿ ಹಿಂದೆ", "ಆಂಜನೇಯ ಗುಡಿ ಹಿಂದೆ")["house"] is None
