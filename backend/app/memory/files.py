"""Frame image files on disk (owner: Student A, tasks A7 and A9).

Layout under FRAMES_DIR (served by the API at /media):
    frames/<id>.jpg   full frame, JPEG quality 85        -> /media/frames/<id>.jpg
    thumbs/<id>.jpg   320 px wide, for the dashboard     -> /media/thumbs/<id>.jpg
The database stores these RELATIVE paths, so the data folder can move.
"""

from pathlib import Path

import cv2
import numpy as np

from app.config import settings

JPEG_QUALITY = 85
THUMB_WIDTH = 320


def absolute(relative_path: str) -> Path:
    return settings.frames_path / relative_path


def _write_jpeg(path: Path, image: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(path), image, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY]):
        raise OSError(f"Could not write {path}")


def save_frame_images(frame_id: int, image: np.ndarray) -> tuple[str, str]:
    """Write the full JPEG and its thumbnail; return their relative paths."""
    image_path = f"frames/{frame_id}.jpg"
    thumb_path = f"thumbs/{frame_id}.jpg"
    _write_jpeg(absolute(image_path), image)
    height = round(image.shape[0] * THUMB_WIDTH / image.shape[1])
    thumb = cv2.resize(image, (THUMB_WIDTH, height), interpolation=cv2.INTER_AREA)
    _write_jpeg(absolute(thumb_path), thumb)
    return image_path, thumb_path


def delete_files(*relative_paths: str) -> None:
    """Remove frame files; a file that is already gone is fine."""
    for relative_path in relative_paths:
        absolute(relative_path).unlink(missing_ok=True)
