"""Words people use when describing where they live, in Kannada, Hindi, Tamil, Telugu and English.

Each entry lists romanised spellings AND native script. Everything is compared through
normalize.phonetic_key, so 'hatra', 'hathra' and 'ಹತ್ರ' all match the same entry.

These lists were written from general knowledge and need a check by native speakers
before the demo. Add spellings freely; nothing else needs to change.
"""

from __future__ import annotations

from functools import lru_cache

from .normalize import detect_language, phonetic_key

LANGS = {
    "kn-IN": "Kannada",
    "hi-IN": "Hindi",
    "en-IN": "English",
    "ta-IN": "Tamil",
    "te-IN": "Telugu",
}

# Languages where the landmark comes BEFORE the direction word ("gudi hatra" = near the temple)
POSTPOSITIONAL = {"kn-IN", "hi-IN", "ta-IN", "te-IN"}

# relation → language → words
RELATIONS: dict[str, dict[str, list[str]]] = {
    "near": {
        "kn-IN": ["hatra", "hattira", "hathra", "hattra", "hathira", "ಹತ್ರ", "ಹತ್ತಿರ"],
        "hi-IN": ["paas", "pass", "pas", "nazdeek", "najdik", "पास", "नज़दीक", "नजदीक"],
        "ta-IN": ["pakkathula", "pakkathil", "arugil", "aruge", "arugae", "kitta", "பக்கத்துல", "பக்கத்தில்", "அருகில்", "அருகே"],
        "te-IN": ["daggara", "dhaggara", "దగ్గర"],
        "en-IN": ["near", "nearby", "close to"],
    },
    "next to": {
        "kn-IN": ["pakka", "pakkadalli", "pakkadha", "ಪಕ್ಕ", "ಪಕ್ಕದಲ್ಲಿ", "ಪಕ್ಕದ"],
        "hi-IN": ["bagal", "bagal mein", "बगल", "बगल में"],
        "ta-IN": ["pakkam", "பக்கம்"],
        "te-IN": ["pakkana", "pakkane", "పక్కన"],
        "en-IN": ["next to", "beside", "adjacent"],
    },
    "behind": {
        "kn-IN": ["hindhe", "hinde", "hindugade", "hindgade", "ಹಿಂದೆ", "ಹಿಂದುಗಡೆ", "ಹಿಂಭಾಗ"],
        "hi-IN": ["peeche", "piche", "pichhe", "पीछे"],
        "ta-IN": ["pinnadi", "pinnaadi", "pinnal", "பின்னாடி", "பின்னால்"],
        "te-IN": ["venaka", "venuka", "venakala", "వెనక", "వెనుక"],
        "en-IN": ["behind", "back side of", "backside"],
    },
    "in front of": {
        "kn-IN": ["munde", "mundhe", "mundugade", "ಮುಂದೆ", "ಮುಂದುಗಡೆ"],
        "hi-IN": ["aage", "agey", "आगे"],
        "ta-IN": ["munnadi", "munnaadi", "munnal", "முன்னாடி", "முன்னால்"],
        "te-IN": ["mundu", "mundhu", "ముందు"],
        "en-IN": ["in front of", "front of", "front"],
    },
    "opposite": {
        "kn-IN": ["eduru", "edhuru", "edurugade", "ಎದುರು", "ಎದುರುಗಡೆ"],
        "hi-IN": ["saamne", "samne", "saamane", "सामने"],
        "ta-IN": ["ethire", "edhire", "ethirla", "எதிரே", "எதிர்ல", "எதிரில்"],
        "te-IN": ["eduruga", "edurugaa", "ఎదురుగా", "ఎదురుగ"],
        "en-IN": ["opposite", "opposite to", "across from"],
    },
    "after": {
        "kn-IN": ["dati", "daati", "ದಾಟಿ"],
        "hi-IN": ["ke baad", "baad", "बाद"],
        "ta-IN": ["thaandi", "thandi", "தாண்டி"],
        "te-IN": ["daati", "దాటి"],
        "en-IN": ["after", "past", "beyond"],
    },
    "left of": {
        "kn-IN": ["edagade", "edakke", "ಎಡಗಡೆ", "ಎಡಕ್ಕೆ"],
        "hi-IN": ["baayen", "baaye", "baen", "बाएं", "बाएँ", "बायें"],
        "ta-IN": ["idathu", "idadhu", "idathula", "இடது", "இடதுபக்கம்"],
        "te-IN": ["edama", "edamavaipu", "ఎడమ"],
        "en-IN": ["left of", "left side of", "left"],
    },
    "right of": {
        "kn-IN": ["balagade", "balakke", "ಬಲಗಡೆ", "ಬಲಕ್ಕೆ"],
        "hi-IN": ["daayen", "daaye", "daen", "दाएं", "दाएँ", "दायें"],
        "ta-IN": ["valathu", "valadhu", "valathula", "வலது", "வலதுபக்கம்"],
        "te-IN": ["kudivaipu", "kudi vaipu", "కుడి వైపు"],
        "en-IN": ["right of", "right side of", "right"],
    },
}

# landmark type (English label for the courier) → words in all languages
LANDMARKS: dict[str, list[str]] = {
    "temple": ["gudi", "devasthana", "devastana", "devalaya", "temple", "mandir", "mandira", "kovil", "koil", "devalayam",
               "ಗುಡಿ", "ದೇವಸ್ಥಾನ", "ದೇವಾಲಯ", "मंदिर", "மந்திர்", "கோவில்", "கோயில்", "గుడి", "దేవాలయం", "ఆలయం"],
    "mosque": ["masjid", "maseedi", "masidi", "mosque", "ಮಸೀದಿ", "मस्जिद", "பள்ளிவாசல்", "மசூதி", "మసీదు"],
    "church": ["church", "charch", "ಚರ್ಚ್", "चर्च", "சர்ச்", "చర్చి"],
    "school": ["shaale", "shale", "school", "iskool", "skool", "pathshala", "vidyalaya", "pallikoodam", "badi",
               "ಶಾಲೆ", "ಸ್ಕೂಲ್", "स्कूल", "विद्यालय", "पाठशाला", "பள்ளிக்கூடம்", "ஸ்கூல்", "బడి", "స్కూల్", "పాఠశాల"],
    "anganwadi": ["anganwadi", "anganavadi", "ಅಂಗನವಾಡಿ", "आंगनवाड़ी", "அங்கன்வாடி", "అంగన్వాడీ"],
    "bus stand": ["bus stand", "bus stop", "bus nildana", "bus adda", "ಬಸ್ ನಿಲ್ದಾಣ", "ಬಸ್ ಸ್ಟ್ಯಾಂಡ್", "ಬಸ್ ಸ್ಟಾಪ್", "बस स्टैंड", "बस अड्डा",
                  "பஸ் ஸ்டாண்ட்", "பஸ் ஸ்டாப்", "బస్ స్టాండ్", "బస్ స్టాప్"],
    "lake": ["kere", "talab", "talaab", "eri", "cheruvu", "lake", "ಕೆರೆ", "तालाब", "ஏரி", "చెరువు"],
    "water tank": ["water tank", "tank", "tanki", "neerina tank", "ಟ್ಯಾಂಕ್", "ನೀರಿನ ಟ್ಯಾಂಕ್", "टंकी", "पानी की टंकी", "டேங்க்", "తొట్టి", "ట్యాంక్"],
    "banyan tree": ["aalada mara", "alada mara", "bargad", "aalamaram", "marri chettu", "banyan tree", "banyan",
                    "ಆಲದ ಮರ", "बरगद", "ஆலமரம்", "మర్రి చెట్టు"],
    "peepal tree": ["arali mara", "arali katte", "peepal", "pipal", "arasa maram", "raavi chettu", "peepal tree",
                    "ಅರಳಿ ಮರ", "ಅರಳಿ ಕಟ್ಟೆ", "पीपल", "அரச மரம்", "రావి చెట్టు"],
    "tree": ["mara", "ped", "maram", "chettu", "tree", "ಮರ", "पेड़", "மரம்", "చెట్టు"],
    "shop": ["angadi", "dukaan", "dukan", "kadai", "kottu", "shop", "store", "ಅಂಗಡಿ", "दुकान", "கடை", "కొట్టు", "షాప్", "దుకాణం"],
    "hospital": ["aspatre", "aaspatre", "hospital", "aspatal", "clinic", "maruthuvamanai", "aasupatri", "asupatri",
                 "ಆಸ್ಪತ್ರೆ", "अस्पताल", "மருத்துவமனை", "ஆஸ்பத்திரி", "ఆసుపత్రి", "హాస్పిటల్"],
    "panchayat office": ["panchayat", "panchayath", "panchayathi", "ಪಂಚಾಯತ್", "ಪಂಚಾಯಿತಿ", "पंचायत", "பஞ்சாயத்து", "పంచాయతీ"],
    "milk dairy": ["milk dairy", "dairy", "diary", "halina dairy", "doodh dairy", "milk society", "ಡೈರಿ", "ಹಾಲಿನ ಡೈರಿ", "डेयरी", "பால் சொசைட்டி", "డెయిరీ", "పాల కేంద్రం"],
    "circle": ["circle", "circal", "ಸರ್ಕಲ್", "सर्कल", "சர்க்கிள்", "సర్కిల్"],
    "petrol bunk": ["petrol bunk", "petrol pump", "bunk", "ಪೆಟ್ರೋಲ್ ಬಂಕ್", "पेट्रोल पंप", "பெட்ரோல் பங்க்", "పెట్రోల్ బంక్"],
    "rice mill": ["rice mill", "mill", "chakki", "ಮಿಲ್", "ರೈಸ್ ಮಿಲ್", "चक्की", "மில்", "మిల్లు"],
    "post office": ["post office", "anche kacheri", "dak ghar", "ಪೋಸ್ಟ್ ಆಫೀಸ್", "ಅಂಚೆ ಕಚೇರಿ", "डाकघर", "தபால் நிலையம்", "పోస్ట్ ఆఫీస్"],
    "bank": ["bank", "ಬ್ಯಾಂಕ್", "बैंक", "பேங்க்", "வங்கி", "బ్యాంక్"],
    "well": ["baavi", "bavi", "kuan", "kuaan", "kinaru", "borewell", "ಬಾವಿ", "कुआँ", "கிணறு", "బావి"],
    "bridge": ["sethuve", "pul", "palam", "vanthena", "bridge", "ಸೇತುವೆ", "पुल", "பாலம்", "వంతెన"],
    "railway gate": ["railway gate", "railway station", "ರೈಲ್ವೆ ಗೇಟ್", "रेलवे फाटक", "ரயில்வே கேட்", "రైల్వే గేట్"],
}

COLOURS: dict[str, list[str]] = {
    "red": ["kempu", "laal", "lal", "sivappu", "erra", "red", "ಕೆಂಪು", "लाल", "சிவப்பு", "ఎరుపు", "ఎర్ర"],
    "green": ["hasiru", "hara", "hare", "pachai", "pacha", "green", "ಹಸಿರು", "हरा", "हरे", "பச்சை", "ఆకుపచ్చ", "పచ్చ"],
    "blue": ["neeli", "neela", "neele", "neelam", "nila", "blue", "ನೀಲಿ", "नीला", "नीले", "நீலம்", "నీలం", "నీలి"],
    "yellow": ["haladi", "peela", "peele", "manjal", "pasupu", "yellow", "ಹಳದಿ", "पीला", "पीले", "மஞ்சள்", "పసుపు"],
    "white": ["bili", "bilee", "safed", "vellai", "tella", "white", "ಬಿಳಿ", "सफ़ेद", "सफेद", "வெள்ளை", "తెల్ల", "తెలుపు"],
    "pink": ["gulabi", "pink", "ಗುಲಾಬಿ", "गुलाबी", "பிங்க்", "గులాబీ"],
    "orange": ["kesari", "orange", "ಕೇಸರಿ", "केसरी", "நாரங்கி", "ఆరెంజ్"],
}

HOUSE_BY_LANG: dict[str, list[str]] = {
    "kn-IN": ["mane", "ಮನೆ"],
    "hi-IN": ["ghar", "घर"],
    "ta-IN": ["veedu", "veettu", "வீடு", "வீட்டு"],
    "te-IN": ["illu", "ఇల్లు", "ఇంటి"],
    "en-IN": ["house", "home"],
}
# 'number' is used in every language, so its Latin spellings say nothing about which one is being spoken
NUMBER_BY_LANG: dict[str, list[str]] = {
    "kn-IN": ["sankhye", "ನಂಬರ್", "ಸಂಖ್ಯೆ"],
    "hi-IN": ["नंबर"],
    "ta-IN": ["நம்பர்", "எண்"],
    "te-IN": ["నంబర్"],
}
HOUSE_WORDS = [w for words in HOUSE_BY_LANG.values() for w in words]
NUMBER_WORDS = ["number", "nambar", "numbar", "no"] + [w for words in NUMBER_BY_LANG.values() for w in words]

# Words that only carry the sentence along: 'my', 'is', 'our village'. Never part of a village name.
FILLER_WORDS: dict[str, list[str]] = {
    "kn-IN": ["namma", "nimma", "nam", "ide", "ive", "alli", "inda", "ri", "ree", "andre", "anta", "aytu", "ನಮ್ಮ", "ಇದೆ", "ಅಲ್ಲಿ", "ರೀ",
              "nammuru", "nammooru", "ooru", "uru", "ನಮ್ಮೂರು", "ಊರು", "ಊರಿನ"],
    "hi-IN": ["mera", "meri", "hamara", "hamare", "hai", "hain", "ke", "ki", "ka", "wala", "wali", "mein", "se", "ji",
              "मेरा", "मेरी", "मैं", "हूँ", "हूं", "रहता", "रहती", "हमारा", "है", "के", "की", "का", "वाला", "में", "gaon", "gaanv", "gav", "गाँव", "गांव"],
    "ta-IN": ["enga", "engal", "en", "irukku", "iruku", "da", "la", "ta", "எங்க", "எங்கள்", "என்", "இருக்கு",
              "oor", "ooru", "enga ooru", "ஊர்", "ஊரு"],
    "te-IN": ["maa", "maadi", "undi", "lo", "మా", "ఉంది", "ooru", "uuru", "ఊరు", "ఊరి"],
    "en-IN": ["my", "our", "is", "the", "a", "an", "it", "its", "i", "we", "am", "live", "stay", "in", "at",
              "near", "village", "there", "located", "of", "to"],
}

YES: dict[str, list[str]] = {
    "kn-IN": ["haudu", "howdu", "houdu", "hau", "hu", "sari", "sariyagide", "ಹೌದು", "ಹೂಂ", "ಸರಿ", "ಸರಿಯಾಗಿದೆ"],
    "hi-IN": ["haan", "han", "ha", "ji", "ji haan", "sahi", "theek", "thik", "हाँ", "हां", "जी", "सही", "ठीक"],
    "ta-IN": ["aamaa", "aama", "aam", "aamam", "seri", "ஆமா", "ஆமாம்", "சரி"],
    "te-IN": ["avunu", "aunu", "sare", "sari", "అవును", "సరే", "సరి"],
    "en-IN": ["yes", "yeah", "yep", "correct", "right", "ok", "okay", "fine"],
}
NO: dict[str, list[str]] = {
    "kn-IN": ["illa", "alla", "beda", "tappu", "ಇಲ್ಲ", "ಅಲ್ಲ", "ತಪ್ಪು", "ಬೇಡ"],
    "hi-IN": ["nahi", "nahin", "nai", "galat", "नहीं", "नही", "गलत", "ग़लत"],
    "ta-IN": ["illai", "illa", "thappu", "இல்லை", "இல்ல", "தப்பு"],
    "te-IN": ["kaadu", "kadu", "ledu", "tappu", "కాదు", "లేదు", "తప్పు"],
    "en-IN": ["no", "nope", "wrong", "incorrect", "not correct"],
}


# ------------------------------------------------------------------ compiled lookups


def _keyed(words):
    return {phonetic_key(w): w for w in words if phonetic_key(w)}


@lru_cache(maxsize=1)
def relation_index() -> dict[str, tuple[str, str]]:
    """phonetic key → (relation, language)"""
    idx: dict[str, tuple[str, str]] = {}
    for rel, by_lang in RELATIONS.items():
        for lang, words in by_lang.items():
            for k in _keyed(words):
                idx.setdefault(k, (rel, lang))
    return idx


@lru_cache(maxsize=1)
def landmark_index() -> dict[str, str]:
    return {k: label for label, words in LANDMARKS.items() for k in _keyed(words)}


@lru_cache(maxsize=1)
def colour_index() -> dict[str, str]:
    return {k: label for label, words in COLOURS.items() for k in _keyed(words)}


@lru_cache(maxsize=1)
def polarity_index() -> dict[str, tuple[bool, str]]:
    idx: dict[str, tuple[bool, str]] = {}
    for value, table in ((False, NO), (True, YES)):
        for lang, words in table.items():
            for k in _keyed(words):
                idx.setdefault(k, (value, lang))
    return idx


@lru_cache(maxsize=1)
def non_name_keys() -> frozenset[str]:
    """Keys of single words that describe an address but don't name a village: 'hatra', 'bus', 'blue', 'mane', 'haan'."""
    words = [*relation_index(), *landmark_index(), *colour_index(), *polarity_index()]
    words += [phonetic_key(w) for w in HOUSE_WORDS + NUMBER_WORDS]
    return frozenset(part for key in words for part in key.split())


@lru_cache(maxsize=1)
def language_evidence_index() -> dict[str, set[str]]:
    """Key of a word → the languages it belongs to, whatever script it was written in ('నమ్మూరు' is still 'ನಮ್ಮೂರು')."""
    idx: dict[str, set[str]] = {}
    for table in (*RELATIONS.values(), YES, NO, HOUSE_BY_LANG, NUMBER_BY_LANG, FILLER_WORDS):
        for lang, words in table.items():
            for w in words:
                for part in phonetic_key(w).split():
                    idx.setdefault(part, set()).add(lang)
    return idx


@lru_cache(maxsize=1)
def language_hint_index() -> dict[str, set[str]]:
    """Romanised word key → languages it belongs to (for spotting Kanglish/Hinglish typed in Latin)."""
    idx: dict[str, set[str]] = {}

    def add(words, lang):
        for w in words:
            if w.isascii():
                idx.setdefault(phonetic_key(w), set()).add(lang)

    for by_lang in RELATIONS.values():
        for lang, words in by_lang.items():
            add(words, lang)
    for table in (YES, NO):
        for lang, words in table.items():
            add(words, lang)
    for w, lang in (("mane", "kn-IN"), ("ghar", "hi-IN"), ("veedu", "ta-IN"), ("illu", "te-IN"), ("gudi", "kn-IN"),
                    ("mandir", "hi-IN"), ("kovil", "ta-IN"), ("ooru", "kn-IN"), ("gaon", "hi-IN"), ("ooru", "ta-IN"),
                    ("shaale", "kn-IN"), ("angadi", "kn-IN"), ("dukaan", "hi-IN"), ("kadai", "ta-IN"), ("kere", "kn-IN")):
        idx.setdefault(phonetic_key(w), set()).add(lang)
    return idx


def _romanised_words(words: list[str], language: str) -> list[str]:
    """One language's words in Latin letters: a spelling counts if it sounds like that language's word ('gudi' = 'ಗುಡಿ')."""
    keys = {phonetic_key(w) for w in words if not w.isascii() and detect_language(w) == language}
    romanised: dict[str, str] = {}
    for w in words:
        if w.isascii() and phonetic_key(w) in keys:
            romanised.setdefault(phonetic_key(w), w)
    return list(romanised.values())


def landmark_keyterms(language: str | None = None) -> list[str]:
    """A short set of landmark/direction words to bias Prisma with (keyterms budget is 200).

    Latin script only, on every turn: native-script keyterms pull Prisma's transcript into
    that script, so a caller who moved from Kannada to Hindi came back in Kannada letters,
    tagged kn-IN. English labels always; romanised words only in the caller's language.
    Direction words go first because the list is cut at the budget.
    """
    out = list(LANDMARKS) + list(RELATIONS)
    if language not in LANGS or language == "en-IN":
        return out
    for by_lang in RELATIONS.values():
        out += [w for w in by_lang.get(language, []) if w.isascii()][:1]
    for words in LANDMARKS.values():
        out += _romanised_words(words, language)
    return out
