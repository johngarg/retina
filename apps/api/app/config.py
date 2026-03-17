import os
from pathlib import Path

from .constants import IMAGE_ORIGINAL_ROOT, IMAGE_THUMBNAIL_ROOT


APP_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.getenv("RETINA_DATA_DIR", APP_DIR / "data"))
DB_PATH = DATA_DIR / "app.db"
IMAGE_ROOT = DATA_DIR / "images"
IMAGE_ORIGINALS_DIR = DATA_DIR / IMAGE_ORIGINAL_ROOT
IMAGE_THUMBNAILS_DIR = DATA_DIR / IMAGE_THUMBNAIL_ROOT


def ensure_app_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    IMAGE_ORIGINALS_DIR.mkdir(parents=True, exist_ok=True)
    IMAGE_THUMBNAILS_DIR.mkdir(parents=True, exist_ok=True)
