"""Low-light enhancement: brighten dark frames before anything reads them (owner: Student A, A4).

A dark frame has two problems: everything is squeezed into a few dark gray levels
(low contrast), and the camera's noise is large compared to that little signal.
Three classic steps, on the LIGHTNESS only (LAB colour space), so colours are not
shifted:
1. Gamma correction: L' = 255 * (L / 255) ** gamma with gamma < 1 lifts the dark
   tones much more than the bright ones. Gamma is chosen per frame so that the mean
   lightness lands near TARGET_MEAN (a very dark frame gets a strong lift).
2. Denoising with a bilateral filter: it averages neighbours of SIMILAR brightness
   only, so noise on flat areas is smoothed while letter edges stay sharp.
3. CLAHE (Contrast Limited Adaptive Histogram Equalisation): equalises the histogram
   in small tiles, so a sign in a dark corridor gets local contrast.
Denoising comes BEFORE CLAHE because CLAHE also stretches noise: measured on a dark
plain wall, denoise-then-CLAHE leaves noise std 5.2, CLAHE-then-denoise 13.0.

Measured benefit (A4, real EasyOCR on en/fr/ar signs at brightness 5-8 / 255):
unenhanced reads 0-67% of the words, enhanced 67-100%. YOLO is NOT given the
enhanced image: it was trained with brightness changes and found fewer objects on
the enhanced dark photos (see ingest/pipeline.py). CLIP separates scenes better.

Only frames darker than DARK_BRIGHTNESS (mean gray, measured by A3) are enhanced;
the stored frame is then the enhanced one and its `enhanced` flag is true.

Try it on your own images (writes <name>_enhanced.jpg next to each):
    python -m app.vision.enhance dark_photo.jpg
"""

import sys
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from app.config import settings

TARGET_MEAN = 120.0  # mean lightness (0..255) after gamma
GAMMA_RANGE = (0.35, 1.0)  # never darken; never lift more than this
CLAHE_CLIP = 2.0
CLAHE_TILES = (8, 8)
DENOISE_DIAMETER = 7  # bilateral filter: neighbourhood size in pixels
DENOISE_SIGMA_COLOR = 40  # only neighbours within ~40 gray levels are averaged


@dataclass
class Enhanced:
    image: np.ndarray  # BGR, same size as the input
    enhanced: bool  # False: the frame was bright enough and is returned unchanged
    gamma: float = 1.0


def is_dark(brightness: float, threshold: float | None = None) -> bool:
    return brightness < (settings.dark_brightness if threshold is None else threshold)


def choose_gamma(mean_lightness: float) -> float:
    """Gamma that maps the current mean lightness to TARGET_MEAN, within GAMMA_RANGE."""
    mean = min(max(mean_lightness, 1.0), 254.0) / 255.0
    gamma = np.log(TARGET_MEAN / 255.0) / np.log(mean)
    return float(np.clip(gamma, *GAMMA_RANGE))


def gamma_lut(gamma: float) -> np.ndarray:
    """Lookup table: 256 values, so the gamma is applied in one fast pass."""
    levels = np.arange(256, dtype=np.float64) / 255.0
    return np.clip(255.0 * levels**gamma + 0.5, 0, 255).astype(np.uint8)


def enhance_low_light(image: np.ndarray) -> tuple[np.ndarray, float]:
    """Gamma, denoise, then CLAHE on the L channel (~6 ms at 640x480). Returns (image, gamma)."""
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    lightness, a, b = cv2.split(lab)
    gamma = choose_gamma(float(lightness.mean()))
    lightness = cv2.LUT(lightness, gamma_lut(gamma))
    lightness = cv2.bilateralFilter(lightness, DENOISE_DIAMETER, DENOISE_SIGMA_COLOR, 5)
    lightness = cv2.createCLAHE(clipLimit=CLAHE_CLIP, tileGridSize=CLAHE_TILES).apply(lightness)
    return cv2.cvtColor(cv2.merge((lightness, a, b)), cv2.COLOR_LAB2BGR), gamma


def enhance(image: np.ndarray, brightness: float) -> Enhanced:
    """Enhance the frame if it is dark (brightness = mean gray from A3's measure())."""
    if not is_dark(brightness):
        return Enhanced(image, False)
    result, gamma = enhance_low_light(image)
    return Enhanced(result, True, gamma)


def _enhance_files(paths: list[str]) -> None:
    from app.vision.quality import measure

    for path in paths:
        image = cv2.imread(path)
        if image is None:
            print(f"{path}: cannot read")
            continue
        brightness = measure(image).brightness
        result = enhance(image, brightness)
        if not result.enhanced:
            print(f"{path}: brightness {brightness:.0f}, bright enough, not changed")
            continue
        out = Path(path).with_name(f"{Path(path).stem}_enhanced.jpg")
        cv2.imwrite(str(out), result.image)
        print(f"{path}: brightness {brightness:.0f} -> {measure(result.image).brightness:.0f} "
              f"(gamma {result.gamma:.2f}), saved {out}")


if __name__ == "__main__":
    _enhance_files(sys.argv[1:])
