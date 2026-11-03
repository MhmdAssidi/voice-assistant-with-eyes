"""Synthetic 640x480 test scenes (owner: Student A).

Drawn with OpenCV so the tests need no image files and give the same pixels on
every machine. Real-camera calibration uses: python -m app.vision.quality <files>
"""

import cv2
import numpy as np

W, H = 640, 480


def _rng() -> np.random.Generator:
    return np.random.default_rng(0)


def wall(level: int = 150, noise: float = 4.0) -> np.ndarray:
    """A plain wall: one gray level plus a little sensor noise."""
    image = np.full((H, W, 3), level, np.float64) + _rng().normal(0, noise, (H, W, 3))
    return np.clip(image, 0, 255).astype(np.uint8)


def dark_noisy_wall() -> np.ndarray:
    """A wall in low light: noise makes it look 'sharp', but there is nothing to see."""
    return wall(level=25, noise=6.0)


def exit_sign() -> np.ndarray:
    """A door next to a green EXIT sign with a French caption."""
    image = wall()
    cv2.rectangle(image, (380, 40), (600, 440), (90, 60, 40), -1)  # door
    cv2.rectangle(image, (380, 40), (600, 440), (30, 20, 10), 4)
    cv2.circle(image, (580, 250), 8, (200, 200, 200), -1)  # handle
    cv2.rectangle(image, (60, 120), (340, 220), (40, 140, 40), -1)  # sign
    cv2.putText(image, "EXIT", (90, 195), cv2.FONT_HERSHEY_SIMPLEX, 2.2, (255, 255, 255), 6)
    cv2.putText(image, "Sortie de secours", (60, 280), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (20,) * 3, 2)
    return image


def boxes() -> np.ndarray:
    """A different scene: a row of boxes on a floor line, no text."""
    image = wall(110)
    for i in range(5):
        cv2.rectangle(image, (40 + i * 120, 300), (120 + i * 120, 460), (60 + 30 * i, 80, 160), -1)
    cv2.line(image, (0, 290), (W, 290), (30, 30, 30), 3)
    return image


def blurred(image: np.ndarray, sigma: float) -> np.ndarray:
    return cv2.GaussianBlur(image, (0, 0), sigma)


def darkened(image: np.ndarray, factor: float = 0.2) -> np.ndarray:
    return (image * factor).astype(np.uint8)


def jittered(image: np.ndarray) -> np.ndarray:
    """The same view a moment later: shifted 3 px, with new sensor noise."""
    moved = np.roll(image, 3, axis=1).astype(np.float64) + _rng().normal(0, 3, image.shape)
    return np.clip(moved, 0, 255).astype(np.uint8)
