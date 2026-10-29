"""Fixed sentences the assistant says, in English, French and Arabic (owner: Student B).

B6 adds the "no question heard" sentence; B8 adds the honesty phrases.
"""

from app.contracts import Language

SUPPORTED_LANGUAGES: tuple[Language, ...] = ("en", "fr", "ar")

NOT_HEARD: dict[Language, str] = {
    "en": "I didn't hear a question. Please tap and ask again.",
    "fr": "Je n'ai pas entendu de question. Touchez et posez-la à nouveau.",
    "ar": "لم أسمع سؤالاً. انقر واطرح سؤالك مرة أخرى.",
}


def phrase(table: dict[Language, str], language: str) -> str:
    """The sentence in `language`, or in English if that language is unknown."""
    return table.get(language, table["en"])  # type: ignore[call-overload]
