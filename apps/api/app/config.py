import os
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.getenv("RETINA_DATA_DIR", APP_DIR / "data"))
DB_PATH = DATA_DIR / "app.db"
IMAGE_ROOT = DATA_DIR / "images"
IMAGE_ORIGINALS_DIR = IMAGE_ROOT / "original"


def ensure_app_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    IMAGE_ORIGINALS_DIR.mkdir(parents=True, exist_ok=True)
