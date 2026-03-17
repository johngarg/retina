from __future__ import annotations

import hashlib
import mimetypes
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple
from uuid import uuid4

from fastapi import UploadFile

from .config import DATA_DIR, IMAGE_ORIGINALS_DIR


class StoredUpload(NamedTuple):
    stored_filename: str
    storage_relpath: str
    mime_type: str | None
    file_extension: str | None
    file_size_bytes: int
    sha256: str


def normalize_name(value: str) -> str:
    return " ".join(value.strip().split())


def normalize_upper(value: str) -> str:
    return normalize_name(value).upper()


def ensure_suffix(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix:
        return suffix
    return ".bin"


def build_storage_name(image_id: str, original_filename: str) -> tuple[Path, str]:
    suffix = ensure_suffix(original_filename)
    today = datetime.now(timezone.utc)
    relative = Path("images") / "original" / f"{today:%Y}" / f"{today:%m}" / f"{image_id}{suffix}"
    return DATA_DIR / relative, str(relative)


def store_upload(image_id: str, upload: UploadFile) -> StoredUpload:
    destination, relative = build_storage_name(image_id, upload.filename or "upload.bin")
    destination.parent.mkdir(parents=True, exist_ok=True)

    hasher = hashlib.sha256()
    file_size = 0

    with destination.open("wb") as output:
        while True:
            chunk = upload.file.read(1024 * 1024)
            if not chunk:
                break
            output.write(chunk)
            hasher.update(chunk)
            file_size += len(chunk)

    mime_type = upload.content_type or mimetypes.guess_type(upload.filename or "")[0]
    suffix = ensure_suffix(upload.filename or "upload.bin").lstrip(".")
    stored_filename = destination.name

    return StoredUpload(
        stored_filename=stored_filename,
        storage_relpath=relative,
        mime_type=mime_type,
        file_extension=suffix,
        file_size_bytes=file_size,
        sha256=hasher.hexdigest(),
    )


def remove_storage_path(relative_path: str) -> None:
    path = DATA_DIR / relative_path
    if path.exists():
        path.unlink()
