"""Honesty rules tests (B8): "I'm not sure", never "safe", max 2 sentences."""

from datetime import UTC, datetime, timedelta

import pytest

from app.assistant import answer, uncertainty, vlm
from app.assistant.i18n import CHECK_CAREFULLY, NOT_SURE
from app.contracts import FrameDetail, FrameSummary, SearchHit
from app.memory import search

# ---------- never "safe" ----------

UNSAFE_REPLIES = [
    ("en", "The road is safe to cross."),
    ("en", "You can walk safely, the path is clear."),
    ("en", "All clear, nothing in your way."),
    ("fr", "La route est sûre, vous pouvez traverser."),
    ("fr", "Vous pouvez avancer sans danger."),
    ("fr", "Le passage semble tout à fait sûr."),
    ("fr", "Vous êtes en sécurité ici."),
    ("ar", "الطريق آمن للعبور."),
    ("ar", "يمكنك المشي بأمان."),
    ("ar", "المكان آمنة تماماً."),
]


@pytest.mark.parametrize(("language", "reply"), UNSAFE_REPLIES)
def test_safety_claims_are_replaced(language: str, reply: str) -> None:
    result = uncertainty.remove_safety_claims(reply, language)
    assert result == CHECK_CAREFULLY[language]


@pytest.mark.parametrize(
    ("language", "text"),
    [
        ("fr", "Je ne suis pas sûr. Il y a une porte devant vous."),  # "sûr" = sure, not safe
        ("fr", "Je ne suis pas sûre de ce qui est écrit."),
        ("fr", "Ce n'est pas sûr, il y a des marches."),  # a warning, not a promise
        ("en", "The floor looks unsafe, there are cables."),  # a warning, not a promise
        ("en", "There is a door in front of you."),
        ("ar", "يوجد باب أمامك."),  # أمامك (in front of you) is not أمان (safety)
        ("ar", "لست متأكدًا مما هو مكتوب."),
    ],
)
def test_normal_sentences_are_kept(language: str, text: str) -> None:
    assert uncertainty.remove_safety_claims(text, language) == text


def test_only_the_unsafe_sentence_is_replaced() -> None:
    reply = "There is a crosswalk ahead. It is safe to cross now."
    assert uncertainty.remove_safety_claims(reply, "en") == (
        "There is a crosswalk ahead. Please check carefully around you."
    )


# ---------- "I'm not sure" ----------


@pytest.mark.parametrize("language", ["en", "fr", "ar"])
def test_not_sure_prefix(language: str) -> None:
    result = uncertainty.with_not_sure("A door.", language)
    assert result == f"{NOT_SURE[language]} A door."


@pytest.mark.parametrize(
    "text",
    ["I'm not sure, maybe a door.", "I am not sure.", "Je ne suis pas sûr, une porte.",
     "Je ne suis pas sure.", "لست متأكدًا، ربما باب.", "I’m not sure."],
)
def test_not_sure_is_not_doubled(text: str) -> None:
    assert uncertainty.with_not_sure(text, "en") == text


@pytest.mark.parametrize(
    ("model_confident", "question", "scores", "latest", "expected"),
    [
        (True, "What does the sign say?", [0.8], False, True),  # strong match
        (True, "What does the sign say?", [0.1], False, False),  # weak match
        (True, "What does the sign say?", [], False, False),  # no evidence
        (False, "What does the sign say?", [0.9], True, False),  # model unsure
        (True, "What is in front of me?", [0.1], True, True),  # live view + latest frame
        (True, "Qu'est-ce qu'il y a devant moi ?", [], True, True),
        (True, "ماذا يوجد أمامي؟", [], True, True),
        (True, "What is in front of me?", [0.1], False, False),  # live, but no latest frame
        (True, "What did the sign say?", [], True, False),  # past question: latest not enough
    ],
)
def test_is_confident(model_confident, question, scores, latest, expected) -> None:  # noqa: ANN001
    assert uncertainty.is_confident(model_confident, question, scores, latest, 0.25) is expected


def test_answers_are_cut_to_two_sentences() -> None:
    text, _ = uncertainty.apply_rules(
        "One. Two. Three. Four.", True, "en", "What is in front of me?", [0.9], True
    )
    assert text == "One. Two."


# ---------- the whole pipeline with a forced unsafe model reply ----------


class FakeProvider:
    name = "fake"

    def __init__(self, reply: vlm.VlmAnswer) -> None:
        self.reply = reply

    def generate(self, system: str, user: str, images: list[bytes]) -> vlm.VlmAnswer:
        return self.reply


def _frame(frame_id: int, seconds_ago: int) -> FrameDetail:
    return FrameDetail(
        id=frame_id, captured_at=datetime.now(UTC) - timedelta(seconds=seconds_ago),
        thumb_url="", image_url="", ocr_text="", object_labels=["road"], enhanced=False,
        width=640, height=480, sharpness=100.0, brightness=100.0, ocr_blocks=[], objects=[],
    )


@pytest.fixture
def weak_memory(monkeypatch):  # noqa: ANN201
    """A recent frame and one weak search hit (score 0.1)."""
    latest = _frame(1, 2)
    old = FrameSummary(**_frame(2, 60).model_dump(include=set(FrameSummary.model_fields)))
    monkeypatch.setattr(search, "get_latest_frame", lambda max_age_s=10: latest)
    monkeypatch.setattr(
        search, "search_frames",
        lambda q, since=None, until=None, limit=5: [SearchHit(frame=old, score=0.1,
                                                              matched_by=["text"])],
    )
    monkeypatch.setattr(search, "get_frame_image_path", lambda i: "missing.jpg")


@pytest.mark.parametrize(
    ("language", "question", "reply"),
    [
        ("en", "Can I cross?", "The road is safe to cross."),
        ("fr", "Je peux traverser ?", "La route est sûre, vous pouvez traverser."),
        ("ar", "هل يمكنني العبور؟", "الطريق آمن للعبور."),
    ],
)
def test_pipeline_rewrites_a_forced_unsafe_reply(
    weak_memory, monkeypatch, language: str, question: str, reply: str  # noqa: ANN001
) -> None:
    fake = FakeProvider(vlm.VlmAnswer(answer=reply, confident=True))
    monkeypatch.setattr(answer, "get_provider", lambda: fake)

    result = answer.answer_question(question, language)

    # weak evidence (score 0.1, not a live-view question) -> not confident
    assert result.confident is False
    assert result.answer == f"{NOT_SURE[language]} {CHECK_CAREFULLY[language]}"
    assert not uncertainty.has_safety_claim(result.answer.removeprefix(NOT_SURE[language]))
