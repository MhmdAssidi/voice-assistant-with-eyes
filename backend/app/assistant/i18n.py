"""Fixed sentences the assistant says, in English, French and Arabic (owner: Student B).

B6: "no question heard". B7: no evidence / model unavailable. B8: honesty phrases.
"""

from app.contracts import Language

SUPPORTED_LANGUAGES: tuple[Language, ...] = ("en", "fr", "ar")

NOT_HEARD: dict[Language, str] = {
    "en": "I didn't hear a question. Please tap and ask again.",
    "fr": "Je n'ai pas entendu de question. Touchez et posez-la à nouveau.",
    "ar": "لم أسمع سؤالاً. انقر واطرح سؤالك مرة أخرى.",
}

# Every not-confident answer starts with this (B8).
NOT_SURE: dict[Language, str] = {
    "en": "I'm not sure.",
    "fr": "Je ne suis pas sûr.",
    "ar": "لست متأكدًا.",
}

# Replaces any sentence that calls something "safe" (B8): we can never promise safety.
CHECK_CAREFULLY: dict[Language, str] = {
    "en": "Please check carefully around you.",
    "fr": "Vérifiez bien autour de vous.",
    "ar": "يرجى التحقق بعناية مما حولك.",
}

NO_EVIDENCE: dict[Language, str] = {
    "en": "I'm not sure. I haven't seen anything yet; check that the camera is connected.",
    "fr": "Je ne suis pas sûr. Je n'ai encore rien vu ; vérifiez que la caméra est connectée.",
    "ar": "لست متأكدًا. لم أرَ شيئًا بعد؛ تأكد من أن الكاميرا متصلة.",
}

VLM_UNAVAILABLE: dict[Language, str] = {
    "en": "I'm not sure. I can't analyse the images right now; please try again.",
    "fr": "Je ne suis pas sûr. Je ne peux pas analyser les images pour le moment ; réessayez.",
    "ar": "لست متأكدًا. لا أستطيع تحليل الصور الآن؛ يرجى المحاولة مرة أخرى.",
}


def phrase(table: dict[Language, str], language: str) -> str:
    """The sentence in `language`, or in English if that language is unknown."""
    return table.get(language, table["en"])  # type: ignore[call-overload]
