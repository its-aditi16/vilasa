import pytest

from vilasa.extractor import guess_language, match_village, parse_house, parse_landmark, parse_yes_no
from vilasa.normalize import detect_language, phonetic_key, to_latin

CANDS = [("Kyathsandra", "572104"), ("Hirehalli", "572140"), ("Bellavi", "572107"), ("Urdigere", "572140"),
         ("Sira Gate", "572101"), ("Tumkur", "572101"), ("Gubbi", "572216")]


@pytest.mark.parametrize("text,lang", [
    ("ಕ್ಯಾತಸಂದ್ರ", "kn-IN"), ("हिरेहल्ली", "hi-IN"), ("கோவில்", "ta-IN"), ("గుడి", "te-IN"), ("Bellavi", "en-IN"),
])
def test_detect_language(text, lang):
    assert detect_language(text) == lang


def test_to_latin_handles_short_vowels_and_digits():
    assert to_latin("ಮನೆ ನಂಬರ್ ೨೩") == "mane nanbar 23"


def test_phonetic_key_merges_spellings():
    assert phonetic_key("ಕ್ಯಾತಸಂದ್ರ") == phonetic_key("kyathasandra")
    assert phonetic_key("Hirehalli") == phonetic_key("हिरेहल्ली")


@pytest.mark.parametrize("said,village", [
    ("ನಮ್ಮ ಊರು ಕ್ಯಾತಸಂದ್ರ", "Kyathsandra"),
    ("kyatha sandra", "Kyathsandra"),
    ("मैं हिरेहल्ली में रहता हूँ", "Hirehalli"),
    ("Belavi madam", "Bellavi"),
    ("ஊர்டிகெரே", "Urdigere"),
    ("మా ఊరు సిర గతె", "Sira Gate"),
])
def test_match_village(said, village):
    assert match_village(said, CANDS, own_pin="572104").name == village


def test_unknown_village_is_rejected():
    m = match_village("Mysore", CANDS)
    assert m.name is None and not m.accepted


def test_wrong_pin_on_parcel_is_corrected():
    m = match_village("ಕ್ಯಾತಸಂದ್ರ", CANDS, own_pin="572101")
    assert (m.name, m.pin) == ("Kyathsandra", "572104")


@pytest.mark.parametrize("said,lang,expected", [
    ("ಆಂಜನೇಯ ಗುಡಿ ಹಿಂದೆ", "kn-IN", "Behind Anjaneya temple"),
    ("ಆಲದ ಮರದ ಹತ್ರ", "kn-IN", "Near banyan tree"),
    ("ಶಾಲೆಯ ಹಿಂದೆ", "kn-IN", "Behind school"),
    ("सरकारी स्कूल के सामने", "hi-IN", "Opposite Government school"),
    ("bus stand ke paas", "hi-IN", "Near bus stand"),
    ("near the Anjaneya temple", "en-IN", "Near Anjaneya temple"),
    ("opposite the milk dairy", "en-IN", "Opposite milk dairy"),
    ("கோவில் எதிரே", "ta-IN", "Opposite temple"),
    ("చెరువు దగ్గర", "te-IN", "Near lake"),
    ("bus stand hatra, Ganesha temple pakka", "kn-IN", "Near bus stand; Next to Ganesha temple"),
])
def test_parse_landmark(said, lang, expected):
    assert parse_landmark(said, lang).english() == expected


@pytest.mark.parametrize("said,expected", [
    ("ಮನೆ ನಂಬರ್ ೨೩, ನೀಲಿ ಮನೆ", "House no. 23, blue house"),
    ("house number 14 b", "House no. 14B"),
    ("नीला घर, नंबर 7", "House no. 7, blue house"),
    ("number illa, green house", "green house"),
])
def test_parse_house(said, expected):
    assert parse_house(said).english() == expected


@pytest.mark.parametrize("said,yes", [
    ("ಹೌದು ಸರಿ", True), ("illa", False), ("haan ji", True), ("nahi galat hai", False),
    ("avunu", True), ("இல்லை", False), ("yes correct", True), ("hmm", None),
])
def test_yes_no(said, yes):
    assert parse_yes_no(said) is yes


@pytest.mark.parametrize("said,lang", [
    ("kyathsandra, anjaneya gudi hatra", "kn-IN"),
    ("mera ghar mandir ke paas hai", "hi-IN"),
    ("my village is Bellavi", "en-IN"),
])
def test_guess_language_romanised(said, lang):
    assert guess_language(said) == lang
