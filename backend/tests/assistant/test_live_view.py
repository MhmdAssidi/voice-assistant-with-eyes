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


# ---------- privacy: same rules as Student A's stored frames (A9) ----------


class _FakeBlurred:
    def __init__(self, image, faces) -> None:  # noqa: ANN001
        self.image, self.faces = image, faces


class _FakeBlurrer:
    def blur(self, image):  # noqa: ANN001, ANN201
        return _FakeBlurred("pixelated " + image, [(0, 0, 10, 10)])


def test_faces_are_blurred_before_the_snapshot_is_used(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(live_view, "_blurrer", _FakeBlurrer())
    assert live_view.blur_faces("frame") == "pixelated frame"


def test_no_snapshot_when_the_face_blurrer_cannot_run(monkeypatch) -> None:  # noqa: ANN001
    from app.vision import faces

    def broken() -> None:
        raise RuntimeError("model download failed")

    monkeypatch.setattr(live_view, "_blurrer", None)
    monkeypatch.setattr(faces, "FaceBlurrer", broken)
    assert live_view.blur_faces("frame") is None  # grab() then returns None: not used


def test_old_snapshots_are_deleted(tmp_path, monkeypatch) -> None:  # noqa: ANN001
    import os

    monkeypatch.setattr(live_view.settings, "retention_minutes", 30)
    now = 1_000_000.0
    ages_min = {"20261108-100000.jpg": 45, "20261108-102000.jpg": 31, "20261108-103000.jpg": 5}
    for name, age in ages_min.items():
        path = tmp_path / name
        path.write_bytes(b"jpg")
        os.utime(path, (now - age * 60, now - age * 60))

    assert live_view.delete_old_snapshots(tmp_path, now=now) == 2
    assert [p.name for p in tmp_path.iterdir()] == ["20261108-103000.jpg"]


def test_at_most_100_snapshots_are_kept(tmp_path) -> None:  # noqa: ANN001
    for i in range(105):
        (tmp_path / f"20261108-1000{i:03d}.jpg").write_bytes(b"jpg")  # all brand new
    assert live_view.delete_old_snapshots(tmp_path) == 5
    assert len(list(tmp_path.iterdir())) == 100
    assert not (tmp_path / "20261108-1000000.jpg").exists()  # the oldest went first
