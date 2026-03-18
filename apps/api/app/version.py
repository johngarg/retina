from __future__ import annotations

import sys
from pathlib import Path


def _version_candidates() -> list[Path]:
    candidates: list[Path] = []
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        candidates.append(Path(sys._MEIPASS) / "VERSION")  # type: ignore[attr-defined]
    candidates.append(Path(__file__).resolve().parents[3] / "VERSION")
    return candidates


def load_app_version() -> str:
    for candidate in _version_candidates():
        if candidate.exists():
            value = candidate.read_text(encoding="utf-8").strip()
            if value:
                return value
    return "0.1.0"


APP_VERSION = load_app_version()
