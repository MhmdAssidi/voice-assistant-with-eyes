"""Honesty rules applied to every answer, after the model (owner: Student B, task B8).

The prompt already asks the model for these rules, but a model can ignore its
instructions, so we enforce them again in plain code:
1. confident=False when the evidence is weak; then the answer starts with "I'm not sure".
2. Never call anything "safe" (en/fr/ar): such a sentence becomes "Please check carefully".
3. At most 2 sentences.
"""

import re

from app.assistant.i18n import CHECK_CAREFULLY, NOT_SURE, phrase
from app.config import settings

MAX_SENTENCES = 2

# ---------- 1. confidence ----------

# Questions about the live view ("what is in front of me?") are answered from the
# latest frame, so they do not need a good search score.
_LIVE_WORDS = [
    # English
    "in front", "ahead", "right now", "now", "see", "what is this", "what's this",
    "around me", "where am i",
    # French
    "devant", "maintenant", "en face", "vois", "voit", "qu'est-ce que c'est",
    "autour de moi", "où suis-je",
    # Arabic (standard + Lebanese)
    "أمامي", "امامي", "قدامي", "الآن", "هلق", "هلأ", "ما هذا", "شو هيدا", "حولي", "أرى", "بشوف",
]


def is_live_question(question: str) -> bool:
    text = question.lower().replace("’", "'")
    return any(word in text for word in _LIVE_WORDS)


def is_confident(
    model_confident: bool,
    question: str,
    hit_scores: list[float],
    has_latest: bool,
    threshold: float | None = None,
) -> bool:
    """False when the model is unsure, there is no evidence, or the evidence is weak.

    Weak = the best search score is below CONFIDENCE_THRESHOLD, except for live-view
    questions when a recent frame exists (they are answered from that frame).
    """
    if not model_confident:
        return False
    if not hit_scores and not has_latest:
        return False  # no evidence at all
    if has_latest and is_live_question(question):
        return True
    limit = settings.confidence_threshold if threshold is None else threshold
    return bool(hit_scores) and max(hit_scores) >= limit


_NOT_SURE_START = re.compile(
    r"^\s*(i'?m not sure|i am not sure|je ne suis pas s[uû]re?|لست متأكد)", re.IGNORECASE
)


def with_not_sure(answer: str, language: str) -> str:
    """Puts the localized "I'm not sure." in front, unless the answer already says it."""
    if _NOT_SURE_START.match(answer.replace("’", "'")):
        return answer
    return f"{phrase(NOT_SURE, language)} {answer}".strip()


# ---------- 2. never "safe" ----------

_SAFE_CLAIMS = [
    # English: "safe", "safely", "secure", "all clear", "clear to cross/go/walk".
    # \b keeps "unsafe" out (a warning, not a promise).
    re.compile(r"\b(safe|safely|secure)\b", re.IGNORECASE),
    re.compile(r"\ball clear\b|\bclear to (cross|go|walk|pass)\b", re.IGNORECASE),
    # French: "sans danger", "sans risque", "en (toute) sécurité", "sécurisé", "sécuritaire",
    # and "sûr" only after a verb like "est/sont/semble" (= "is safe"), with up to 3 words
    # between ("semble tout à fait sûr"). "Je ne suis pas sûr" (= "I'm not sure") is untouched:
    # "suis" is not in the list, and no in-between word may be "pas".
    re.compile(r"\bsans (danger|risque)\b|\ben (toute )?sécurité\b|\bsécuris|\bsécuritaire",
               re.IGNORECASE),
    re.compile(
        r"\b(est|sont|semble|semblent|paraît|paraissent|reste|restent)\s+"
        r"(?:(?!pas\b)\w+\s+){0,3}s[uû]r(e|s|es)?\b",
        re.IGNORECASE,
    ),
    # Arabic: آمن / آمنة (safe), أمان / بأمان / الأمان (safety). Arabic glues prefixes to
    # words (ب، ال), so we search inside words. "أمامك" (in front of you) is different:
    # it ends in م, not ن.
    re.compile(r"آمن|أمان"),
]


def has_safety_claim(sentence: str) -> bool:
    return any(pattern.search(sentence) for pattern in _SAFE_CLAIMS)


def split_sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?؟])\s+", text.strip()) if s]


def remove_safety_claims(answer: str, language: str) -> str:
    """Replaces every sentence that promises safety by one "please check carefully"."""
    check = phrase(CHECK_CAREFULLY, language)
    kept: list[str] = []
    for sentence in split_sentences(answer):
        if has_safety_claim(sentence):
            if check not in kept:
                kept.append(check)
        else:
            kept.append(sentence)
    return " ".join(kept) or check


# ---------- all rules together ----------


def apply_rules(
    answer: str,
    model_confident: bool,
    language: str,
    question: str,
    hit_scores: list[float],
    has_latest: bool,
) -> tuple[str, bool]:
    """The final (answer, confident) sent to the phone."""
    confident = is_confident(model_confident, question, hit_scores, has_latest)
    text = " ".join(split_sentences(answer)[:MAX_SENTENCES])
    text = remove_safety_claims(text, language)
    if not confident:
        text = with_not_sure(text, language)
    return text, confident
