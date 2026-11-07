"""Live snapshot usability (real measurements from the phone camera)."""

import pytest

from app.assistant import live_view


@pytest.mark.parametrize(
    ("brightness", "sharpness", "informativeness", "expected"),
    [
        (5, 3, 0.000, (False, "too_dark")),  # finger on the lens
        (97, 127, 0.033, (True, "ok")),  # cigarette box, clear
        (111, 57, 0.017, (True, "ok")),  # mouse on a table: slightly soft but readable
        (120, 8, 0.010, (False, "blurry")),  # phone moving fast
        (150, 40, 0.001, (False, "not_informative")),  # lens against a blank surface
    ],
)
def test_judge(brightness, sharpness, informativeness, expected) -> None:  # noqa: ANN001
    assert live_view.judge(brightness, sharpness, informativeness) == expected
