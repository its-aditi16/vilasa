import json
from pathlib import Path

import pytest

from vilasa.callflow import DONE, HANDOFF, LANDMARK, VILLAGE, CallSession
from vilasa.extractor import match_village
from vilasa.lexicon import LANDMARKS, RELATIONS, landmark_keyterms
from vilasa.normalize import detect_language
from vilasa.pincodes import PinDirectory, PinInfo

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
def test_keyterms_are_latin_script_only(language):
    for pin in PINS.pins:
        terms = PINS.keyterms(pin, language)
        assert len(terms) <= 200
        assert all(t.isascii() for t in terms)


@pytest.mark.parametrize("language,own,foreign", [
    ("kn-IN", ["gudi", "hatra", "temple", "near"], ["mandir", "kovil", "paas", "ಗುಡಿ", "ಹತ್ರ"]),
    ("hi-IN", ["mandir", "paas", "temple", "near"], ["gudi", "kovil", "hatra", "मंदिर", "पास"]),
    ("ta-IN", ["kovil", "pakkathula", "temple", "near"], ["gudi", "hatra", "paas", "கோவில்", "பக்கத்துல"]),
    ("te-IN", ["gudi", "daggara", "temple", "near"], ["mandir", "kovil", "hatra", "గుడి", "దగ్గర"]),
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
        assert {"paas", "right of", "daayen"} <= set(PINS.keyterms(pin, "hi-IN"))


def test_keyterms_stay_latin_on_every_turn_of_a_call_that_switches_language():
    d = next(x for x in DELIVERIES if x["default_language"] == "kn-IN")
    s = CallSession(d, PINS)
    s.start()
    assert all(t.isascii() for t in s.stt_context()["keyterms"])  # language still unknown
    s.handle("मेरा गाँव हिरेहल्ली है", "hi-IN")
    assert s.language == "hi-IN"
    terms = s.stt_context()["keyterms"]
    assert "paas" in terms and all(t.isascii() for t in terms)


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


def test_stt_context_never_sends_vilasas_prompt_as_previous_text():
    d = DELIVERIES[0]
    s = CallSession(d, PINS)
    s.start()
    for step in ("village", "landmark", "house", "confirm"):
        assert set(s.stt_context()) == {"keyterms", "topic", "language_code"}
        s.handle(d["mock_answers"][step], "kn-IN")


def _replies(delivery, answers):
    s = CallSession(delivery, PINS)
    s.start()
    return [s.handle(text, detect_language(text)).language for text in answers]


def test_hindi_from_the_first_answer_switches_and_stays_in_hindi():
    d = next(x for x in DELIVERIES if x["id"] == "VIL-1002")
    a = d["mock_answers"]
    assert _replies(d, [a["village"], a["landmark"], a["house"], a["confirm"]]) == ["hi-IN"] * 4


def test_reply_switches_once_the_transcript_turns_hindi_at_the_landmark_step():
    # Call-flow logic only: this hands in clean Hindi text, so it says nothing about what live Prisma writes.
    answers = ["ನಮ್ಮೂರು ಕ್ಯಾತಸಂದ್ರ", "आंजनेय मंदिर के पीछे", "घर नंबर 23, नीला घर", "हाँ सही है"]
    assert _replies(DELIVERIES[0], answers) == ["kn-IN", "hi-IN", "hi-IN", "hi-IN"]


@pytest.mark.parametrize("pin,transcript,village", [
    ("572129", "ನಮ್ಮೂರು ಬದ್ದಗೆರೆ, bus ನಿಲ್ದಾಣ ಹತ್ತಿರ. ನಮ್ಮ ಮನೆ ಮನೆ number 105.", "Vaddagere"),
    ("572129", "ನಮ್ಮೂರು ಬತ್ತಗೆರೆ, bus ನಿಲ್ದಾಣ ಹತ್ತಿರ. ನಮ್ಮ ಮನೆ, ಮನೆ number 105.", "Vaddagere"),
    ("572225", "என் ஊர் Sampige. ஏரி எதிரே எங்கள் வீடு, வீட்டு number 76.", "Sampige"),
    ("572225", "என் ஊர் சம்பிகே ஏரி எதிரே எங்க வீடு, வீட்டு நம்பர் 76.", None),  # was 'Settikere', from 'opposite'
    ("572138", "రామాలయం గుడి వెనక మా ఇల్లు, ఇంటి number 21.", None),  # Prisma lost the village; was 'Tovinakere'
])
def test_real_transcripts_no_longer_match_a_direction_word(pin, transcript, village):
    assert match_village(transcript, PINS.candidates(pin), own_pin=pin).name == village


def _pin_of(name):
    return next(p for p, info in PINS.pins.items() if name in info.villages)


def test_real_village_whose_name_is_also_a_direction_word_still_matches():
    pin = _pin_of("Thadi")  # same phonetic key as ದಾಟಿ, 'after'
    m = match_village("Thadi", PINS.candidates(pin), own_pin=pin)
    assert m.name == "Thadi" and m.confident


@pytest.mark.parametrize("name", ["Samige Road Railway Station", "K R S Agrahara Kunigal", "R M Yard Madhugiri", "K R Extn Tiptur"])
def test_real_long_village_names_match_in_full(name):
    pin = _pin_of(name)
    m = match_village(name, PINS.candidates(pin), own_pin=pin)
    assert m.name == name and m.confident


def test_every_real_village_name_matches_itself_confidently():
    for pin, info in PINS.pins.items():
        for name in info.villages:
            m = match_village(name, PINS.candidates(pin), own_pin=pin)
            assert m.name == name and m.confident, (name, pin, m)


def test_short_name_still_wins_when_only_the_short_name_is_said():
    assert match_village("Kunigal", PINS.candidates(_pin_of("K R S Agrahara Kunigal")), own_pin=_pin_of("K R S Agrahara Kunigal")).name == "Kunigal"


@pytest.mark.parametrize("pin_of,transcript,village", [
    ("Bilidevalaya", "My village is Bili Devalaya, near the government school, house number 2", "Bilidevalaya"),
    ("Bilidevalaya", "ನಮ್ಮೂರು ಬಿಳಿ ದೇವಾಲಯ ನೀರಿನ tank ಹತ್ತಿರ, ನಮ್ಮ ಮನೆ ಮನೆ number 3.", "Bilidevalaya"),
    ("Galigekere", "ನಮ್ಮೂರು ಗಲ್ಲಿಗೆ ಕೆರೆ, bus ನಿಲ್ದಾಣ ಎದುರು ನಮ್ಮ ಮನೆ. ಮನೆ number 161.", "Galigekere"),
])
def test_a_village_said_as_two_lexicon_words_still_matches(pin_of, transcript, village):
    pin = _pin_of(pin_of)
    assert match_village(transcript, PINS.candidates(pin), own_pin=pin).name == village


def test_the_same_words_apart_are_still_ignored():
    pin = _pin_of("Bilidevalaya")
    assert match_village("ಬಿಳಿ ಮನೆ", PINS.candidates(pin), own_pin=pin).name is None  # 'white house'


@pytest.mark.parametrize("pin_of,transcript,not_this", [
    ("Dyagerahalli", "ನಮ್ಮೂರು Devalahalli, bus stand ಎಡೂರು, house number 172.", "Hussainpura"),
    ("Mavinahalli", "मेरा गाँव मबिनहल्ली है। bus stand के पास घर है।", "Heggere"),
])
def test_address_words_side_by_side_do_not_join_into_a_village(pin_of, transcript, not_this):
    pin = _pin_of(pin_of)
    assert match_village(transcript, PINS.candidates(pin), own_pin=pin).name != not_this


def test_village_not_found_asks_again():
    s = CallSession({"pin": "572138"}, PINS)
    s.start()
    reply = s.handle("రామాలయం గుడి వెనక మా ఇల్లు, ఇంటి number 21.", "te-IN")
    assert s.state == VILLAGE and reply.meta["prompt"] == "retry"
    assert s.village is None


def test_card_shows_the_runner_up_on_a_close_call_and_the_call_still_confirms():
    pins = PinDirectory({"572137": PinInfo(pin="572137", villages=["Kadavigere", "Kadavigeri"])})
    s = CallSession({"pin": "572137"}, pins)
    s.start()
    for answer in ("Kadavige", "temple near", "house number 5", "yes correct"):
        s.handle(answer, "en-IN")
    card = s.card()
    assert s.state == DONE and card["status"] == "confirmed"
    assert card["village"] == "Kadavigere" and card["village_or"] == "or Kadavigeri?"
    assert card["village_confident"] is False


def test_card_has_no_runner_up_when_the_match_is_clear():
    assert run(DELIVERIES[0]).card()["village_or"] is None


def _call(*turns, default="kn-IN", pin="572101"):
    """Answers as (text, Prisma's detected language). Returns the reply language after each."""
    s = CallSession({"pin": pin, "default_language": default}, PINS)
    s.start()
    return [s.handle(text, detected).language for text, detected in turns]


def test_kanglish_in_telugu_script_stays_kannada():
    u016 = "నమ్మూరు కత్తిగే గొల్లహళ్లి government school, ఎదురు house number 60."
    assert _call((u016, "te-IN"), pin="572104") == ["kn-IN"]


def test_telugu_script_with_no_evidence_stays_kannada_even_twice_in_a_row():
    assert _call(("తమ్మదిహళ్ళి", "te-IN"), ("రామాలయం", "te-IN"), pin="572226") == ["kn-IN", "kn-IN"]


def test_real_telugu_answer_switches_to_telugu():
    assert _call(("మా ఊరు నాగలమడికె, చెరువు దగ్గర", "te-IN"), pin="572136") == ["te-IN"]


def test_telugu_call_does_not_fall_back_to_kannada_on_detection_alone():
    assert _call(("కేస్తూర్", "kn-IN"), ("రామాలయం", "kn-IN"), default="te-IN", pin="572138") == ["te-IN", "te-IN"]


def test_kannada_to_hindi_at_the_landmark_step_with_prisma_tags():
    turns = [("ನಮ್ಮೂರು Kyathasandra.", "kn-IN"), ("आंजनेय मंदिर के पीछे।", "hi-IN"), ("घर नंबर 23, नीला घर।", "hi-IN"), ("हाँ, सही है।", "hi-IN")]
    assert _call(*turns) == ["kn-IN", "hi-IN", "hi-IN", "hi-IN"]


def test_hindi_from_the_first_turn_with_prisma_tags():
    turns = [("मैं Hirehalli में रहता हूँ।", "hi-IN"), ("सरकारी school के सामने।", "hi-IN"), ("घर नंबर 7, पीला घर।", "hi-IN"), ("हाँ, सही है।", "hi-IN")]
    assert _call(*turns, pin="572168") == ["hi-IN"] * 4


def test_words_beat_the_tag_when_hindi_comes_back_in_kannada_script():
    assert _call(("ಮೇರಾ ಗಾಂವ್ Hirehalli, ಕೆ ಸಾಮ್ನೆ", "kn-IN"), pin="572168") == ["hi-IN"]


def test_same_new_language_twice_in_a_row_switches_without_words():
    assert _call(("हिरेहल्ली", "hi-IN"), ("सरकारी स्कूल", "hi-IN"), pin="572168") == ["kn-IN", "hi-IN"]


def test_detection_that_changes_between_turns_does_not_switch():
    assert _call(("हिरेहल्ली", "hi-IN"), ("ஏரி", "ta-IN"), pin="572168") == ["kn-IN", "kn-IN"]


def test_village_names_in_latin_letters_do_not_switch_to_english():
    assert _call(("Kyathasandra", "en-IN"), ("Anjaneya temple", "en-IN")) == ["kn-IN", "kn-IN"]


def test_english_answer_switches_to_english():
    assert _call(("My village is Kyathasandra", "en-IN")) == ["en-IN"]


def test_kanglish_typed_in_latin_moves_an_english_call_to_kannada():
    assert _call(("bus stand hatra", None), default="en-IN") == ["kn-IN"]


def test_a_village_name_is_not_evidence_even_if_it_sounds_like_a_direction_word():
    pin = _pin_of("Thadi")  # same phonetic key as ದಾಟಿ, 'after', in Kannada and Telugu
    assert _call(("Thadi", "te-IN"), default="hi-IN", pin=pin) == ["hi-IN"]
