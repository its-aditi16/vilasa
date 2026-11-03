"""What Vilasa says, in each language. Native-speaker review needed before the demo.

The greeting says Vilasa is an automated assistant and that any language is fine.
After the customer's first answer, Vilasa continues in the language they spoke.
"""

from __future__ import annotations

PROMPTS: dict[str, dict[str, str]] = {
    "kn-IN": {
        "greet": "ನಮಸ್ಕಾರ! ನಾನು ವಿಲಾಸ, ಡೆಲಿವರಿ ಸಹಾಯಕಿ. ನಿಮ್ಮ ಪಾರ್ಸೆಲ್ ತಲುಪಿಸಲು ವಿಳಾಸ ಬೇಕು. ನಿಮ್ಮ ಊರಿನ ಹೆಸರು ಹೇಳಿ. ಯಾವ ಭಾಷೆಯಲ್ಲಾದರೂ ಹೇಳಬಹುದು.",
        "village": "ನಿಮ್ಮ ಊರಿನ ಹೆಸರು ಹೇಳಿ.",
        "landmark": "ಸರಿ. ನಿಮ್ಮ ಮನೆ ಹತ್ತಿರ ಯಾವುದಾದರೂ ಗುರುತು ಹೇಳಿ. ಗುಡಿ, ಶಾಲೆ, ಅಂಗಡಿ, ಕೆರೆ, ಏನಾದರೂ.",
        "house": "ಮನೆ ನಂಬರ್ ಅಥವಾ ಮನೆಯ ಗುರುತು ಹೇಳಿ, ಉದಾಹರಣೆಗೆ ಮನೆಯ ಬಣ್ಣ.",
        "confirm": "ನಾನು ಬರೆದುಕೊಂಡಿದ್ದು: {summary}. ಸರಿನಾ?",
        "done": "ಧನ್ಯವಾದಗಳು! ಈ ವಿಳಾಸವನ್ನು ಡೆಲಿವರಿ ಹುಡುಗನಿಗೆ ಕಳಿಸಿದ್ದೇನೆ.",
        "retry": "ಕ್ಷಮಿಸಿ, ಸರಿಯಾಗಿ ಕೇಳಿಸಲಿಲ್ಲ. ಇನ್ನೊಮ್ಮೆ ಹೇಳಿ.",
        "yesno_retry": "ದಯವಿಟ್ಟು ಹೌದು ಅಥವಾ ಇಲ್ಲ ಅಂತ ಹೇಳಿ.",
        "restart": "ಸರಿ, ಮತ್ತೆ ಕೇಳುತ್ತೇನೆ. ನಿಮ್ಮ ಊರಿನ ಹೆಸರು ಹೇಳಿ.",
        "handoff": "ಪರವಾಗಿಲ್ಲ. ಡೆಲಿವರಿ ಹುಡುಗ ನಿಮಗೆ ನೇರವಾಗಿ ಕರೆ ಮಾಡುತ್ತಾರೆ. ಧನ್ಯವಾದಗಳು!",
    },
    "hi-IN": {
        "greet": "नमस्ते! मैं विलासा हूँ, डिलीवरी सहायक। आपका पार्सल पहुँचाने के लिए पता चाहिए। अपने गाँव का नाम बताइए। आप किसी भी भाषा में बोल सकते हैं।",
        "village": "अपने गाँव का नाम बताइए।",
        "landmark": "ठीक है। आपके घर के पास कोई निशानी बताइए। मंदिर, स्कूल, दुकान, तालाब, कुछ भी।",
        "house": "घर का नंबर या घर की पहचान बताइए, जैसे घर का रंग।",
        "confirm": "मैंने लिखा है: {summary}। सही है?",
        "done": "धन्यवाद! यह पता डिलीवरी वाले भैया को भेज दिया है।",
        "retry": "माफ़ कीजिए, ठीक से सुनाई नहीं दिया। एक बार फिर बताइए।",
        "yesno_retry": "कृपया हाँ या नहीं बताइए।",
        "restart": "ठीक है, फिर से पूछती हूँ। अपने गाँव का नाम बताइए।",
        "handoff": "कोई बात नहीं। डिलीवरी वाले भैया आपको सीधे कॉल करेंगे। धन्यवाद!",
    },
    "en-IN": {
        "greet": "Hello! I'm Vilasa, a delivery assistant. I need your address to deliver your parcel. Please tell me your village name. You can speak in any language.",
        "village": "Please tell me your village name.",
        "landmark": "Okay. Tell me a landmark near your house, like a temple, school, shop or lake.",
        "house": "Tell me your house number, or how to spot your house, like its colour.",
        "confirm": "I have noted: {summary}. Is that correct?",
        "done": "Thank you! I've sent this address to your delivery partner.",
        "retry": "Sorry, I didn't catch that. Please say it once more.",
        "yesno_retry": "Please say yes or no.",
        "restart": "Okay, let me ask again. Please tell me your village name.",
        "handoff": "No problem. Your delivery partner will call you directly. Thank you!",
    },
    "ta-IN": {
        "greet": "வணக்கம்! நான் விலாசா, டெலிவரி உதவியாளர். உங்கள் பார்சலைக் கொண்டு வர முகவரி வேண்டும். உங்கள் ஊரின் பெயரைச் சொல்லுங்கள். எந்த மொழியிலும் பேசலாம்.",
        "village": "உங்கள் ஊரின் பெயரைச் சொல்லுங்கள்.",
        "landmark": "சரி. உங்கள் வீட்டின் அருகே ஏதாவது அடையாளம் சொல்லுங்கள். கோவில், பள்ளி, கடை, ஏரி, எதுவானாலும்.",
        "house": "வீட்டு எண் அல்லது வீட்டின் அடையாளம் சொல்லுங்கள், உதாரணமாக வீட்டின் நிறம்.",
        "confirm": "நான் எழுதியது: {summary}. சரியா?",
        "done": "நன்றி! இந்த முகவரியை டெலிவரி செய்பவருக்கு அனுப்பிவிட்டேன்.",
        "retry": "மன்னிக்கவும், சரியாகக் கேட்கவில்லை. மீண்டும் சொல்லுங்கள்.",
        "yesno_retry": "தயவுசெய்து ஆமாம் அல்லது இல்லை என்று சொல்லுங்கள்.",
        "restart": "சரி, மீண்டும் கேட்கிறேன். உங்கள் ஊரின் பெயரைச் சொல்லுங்கள்.",
        "handoff": "பரவாயில்லை. டெலிவரி செய்பவர் உங்களை நேரடியாக அழைப்பார். நன்றி!",
    },
    "te-IN": {
        "greet": "నమస్కారం! నేను విలాస, డెలివరీ సహాయకురాలిని. మీ పార్సెల్ అందించడానికి అడ్రస్ కావాలి. మీ ఊరి పేరు చెప్పండి. ఏ భాషలోనైనా మాట్లాడవచ్చు.",
        "village": "మీ ఊరి పేరు చెప్పండి.",
        "landmark": "సరే. మీ ఇంటి దగ్గర ఏదైనా గుర్తు చెప్పండి. గుడి, బడి, షాపు, చెరువు, ఏదైనా.",
        "house": "ఇంటి నంబర్ లేదా ఇంటి గుర్తు చెప్పండి, ఉదాహరణకు ఇంటి రంగు.",
        "confirm": "నేను రాసుకున్నది: {summary}. సరేనా?",
        "done": "ధన్యవాదాలు! ఈ అడ్రస్ డెలివరీ అబ్బాయికి పంపించాను.",
        "retry": "క్షమించండి, సరిగ్గా వినబడలేదు. మళ్ళీ చెప్పండి.",
        "yesno_retry": "దయచేసి అవును లేదా కాదు అని చెప్పండి.",
        "restart": "సరే, మళ్ళీ అడుగుతాను. మీ ఊరి పేరు చెప్పండి.",
        "handoff": "పర్వాలేదు. డెలివరీ అబ్బాయి మీకు నేరుగా కాల్ చేస్తారు. ధన్యవాదాలు!",
    },
}

# Topic hints sent to Prisma for each step (English is fine; it is context, not output)
TOPICS = {
    "village": "A customer in rural Karnataka is saying the name of their village for a parcel delivery.",
    "landmark": "A customer is describing a landmark near their house (temple, school, shop, lake, tree) for a delivery rider.",
    "house": "A customer is giving their house number or how to recognise their house (colour, gate) for a delivery.",
    "confirm": "A customer is answering yes or no to confirm their delivery address.",
}


def say(language: str, key: str, **kwargs) -> str:
    table = PROMPTS.get(language) or PROMPTS["en-IN"]
    return table[key].format(**kwargs)
