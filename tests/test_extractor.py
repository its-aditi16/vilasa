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


@pytest.mark.parametrize("main,said,expected", [
    # same place: left out
    ("ಆಂಜನೇಯ ಗುಡಿ ಹಿಂದೆ", "ಆಂಜನೇಯ ಗುಡಿ ಹಿಂದೆ ಮನೆ, ಮನೆ ನಂಬರ್ 23", "House no. 23"),
    ("Anjaneya gudi hinde", "gudi hinde number 23", "House no. 23"),  # name said only once
    ("gudi hinde", "Anjaneya gudi hinde number 23", "House no. 23"),
    ("सरकारी स्कूल के सामने", "सरकारी स्कूल के सामने, घर नंबर 7", "House no. 7"),
    ("gudi hinde, shaale hatra", "shaale hatra, number 23", "House no. 23"),  # repeats the second landmark
    # a different place: kept
    ("Anjaneya gudi hinde", "Shiva gudi hinde number 23", "House no. 23, behind shiva temple"),
    ("gudi hinde", "gudi hatra number 23", "House no. 23, near temple"),
    ("shaale hatra", "gudi hatra number 23", "House no. 23, near temple"),
])
def test_house_does_not_repeat_the_main_landmark(main, said, expected):
    assert parse_house(said).english(parse_landmark(main)) == expected


def test_house_keeps_its_landmark_when_no_main_landmark_is_given():
    assert parse_house("gudi hinde number 23").english() == "House no. 23, behind temple"


@pytest.mark.parametrize("said,village", [
    ("ಹತ್ತಿರ", "Huthri"),      # direction word; this one matched at 91%
    ("hatra", "Hatna"),
    ("gudi", "Kutir"),         # landmark noun
    ("ಗುಡಿಯ", "Kutir"),        # landmark noun with a case ending
    ("kempu", "Kempur"),       # colour
    ("nambar", "Nambur"),      # number word
    ("mane", "Manu"),          # house word
    ("haudu", "Haudur"),       # yes word
])
def test_words_that_describe_an_address_are_not_village_names(said, village):
    assert match_village(said, [(village, "572101")]).name is None


@pytest.mark.parametrize("said,village", [
    ("Sira Gate", "Sira Gate"),
    ("Kere Palya", "Kere Palya"),        # a village name with a landmark word in it
    ("Kere Palya hatra", "Kere Palya"),
])
def test_words_in_a_real_village_name_are_never_ignored(said, village):
    cands = [("Sira Gate", "572101"), ("Kere Palya", "572101"), ("Bellavi", "572107")]
    assert match_village(said, cands).name == village


def test_short_word_needs_95_to_be_confident():
    m = match_village("Tipu", [("Tiptu", "572101")])
    assert m.name == "Tiptu" and m.accepted and 85 <= m.score < 95
    assert m.unsure and not m.confident and m.runner_up is None
    assert match_village("Sira", [("Sira", "572101")]).confident  # short, but exact


def test_longer_word_is_confident_at_85():
    m = match_village("Tiptu", [("Tiptur", "572101")])
    assert 85 <= m.score < 95 and m.confident


def test_level_scores_go_to_the_name_covering_more_of_the_answer():
    cands = [("Kunigal", "572130"), ("K R S Agrahara Kunigal", "572130")]
    assert match_village("K R S Agrahara Kunigal", cands).name == "K R S Agrahara Kunigal"
    # the wider name wins inside the 3-point window even when its own score is a little lower
    m = match_village("Hosa Kunigal", [("Kunigal", "572130"), ("Hosa Kunigala", "572130")])
    assert m.name == "Hosa Kunigala" and len(m.heard.split()) == 2


def test_close_call_keeps_the_best_and_names_the_runner_up():
    m = match_village("Kadavige", [("Kadavigere", "572137"), ("Kadavigeri", "572137")])
    assert m.name == "Kadavigere" and m.runner_up == "Kadavigeri"
    assert m.accepted and m.unsure and not m.confident


def test_clear_winner_has_no_runner_up():
    m = match_village("Hirehalli", [("Hirehalli", "572140"), ("Hirehalla", "572140")])  # second is close, but best is 95+
    assert m.score >= 95 and m.runner_up is None and m.confident
    m = match_village("Tiptu", [("Tiptur", "572101"), ("Gubbi", "572216")])  # under 95, but far ahead
    assert m.runner_up is None and m.confident
