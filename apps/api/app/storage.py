from __future__ import annotations

import hashlib
import mimetypes
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import NamedTuple

from fastapi import UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError

from .config import DATA_DIR
from .constants import IMAGE_ORIGINAL_ROOT, IMAGE_THUMBNAIL_ROOT, THUMBNAIL_MAX_DIMENSION


class StorageValidationError(ValueError):
    pass


class StoredUpload(NamedTuple):
    stored_filename: str
    storage_relpath: str
    thumbnail_relpath: str
    mime_type: str
    file_extension: str | None
    file_size_bytes: int
    sha256: str
    width_px: int
    height_px: int
    thumbnail_width_px: int
    thumbnail_height_px: int


class StoredThumbnail(NamedTuple):
    thumbnail_relpath: str
    thumbnail_width_px: int
    thumbnail_height_px: int


def normalize_name(value: str) -> str:
    return " ".join(value.strip().split())


def normalize_upper(value: str) -> str:
    return normalize_name(value).upper()


def ensure_suffix(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix:
        return suffix
    return ".bin"


def build_original_storage_name(image_id: str, original_filename: str) -> tuple[Path, str]:
    suffix = ensure_suffix(original_filename)
    today = datetime.now(timezone.utc)
    relative = Path(IMAGE_ORIGINAL_ROOT) / f"{today:%Y}" / f"{today:%m}" / f"{image_id}{suffix}"
    return DATA_DIR / relative, relative.as_posix()


def build_thumbnail_storage_name(image_id: str, original_relative: str | None = None) -> tuple[Path, str]:
    if original_relative:
        original_path = Path(original_relative)
        if len(original_path.parts) >= 4:
            year = original_path.parts[-3]
            month = original_path.parts[-2]
            relative = Path(IMAGE_THUMBNAIL_ROOT) / year / month / f"{image_id}.png"
            return DATA_DIR / relative, relative.as_posix()

    today = datetime.now(timezone.utc)
    relative = Path(IMAGE_THUMBNAIL_ROOT) / f"{today:%Y}" / f"{today:%m}" / f"{image_id}.png"
    return DATA_DIR / relative, relative.as_posix()


def remove_storage_path(relative_path: str | None) -> None:
    if not relative_path:
        return
    path = DATA_DIR / relative_path
    if path.exists():
        path.unlink()


def remove_storage_artifacts(*relative_paths: str | None) -> None:
    for relative_path in relative_paths:
        remove_storage_path(relative_path)


def inspect_image_bytes(raw_bytes: bytes) -> tuple[str, int, int]:
    if not raw_bytes:
        raise StorageValidationError("Uploaded file is empty")

    try:
        with Image.open(BytesIO(raw_bytes)) as image:
            normalized = ImageOps.exif_transpose(image)
            width_px, height_px = normalized.size
            mime_type = Image.MIME.get(normalized.format or "")
    except (UnidentifiedImageError, OSError) as exc:
        raise StorageValidationError("Uploaded file is not a valid image") from exc

    if width_px < 1 or height_px < 1:
        raise StorageValidationError("Uploaded image has invalid dimensions")

    return mime_type or "application/octet-stream", width_px, height_px


def read_upload_bytes(upload: UploadFile) -> tuple[bytes, str, int, int]:
    raw_bytes = upload.file.read()
    mime_type, width_px, height_px = inspect_image_bytes(raw_bytes)
    return raw_bytes, mime_type, width_px, height_px


def write_original_file(destination: Path, raw_bytes: bytes) -> tuple[int, str]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as output:
        output.write(raw_bytes)
    return len(raw_bytes), hashlib.sha256(raw_bytes).hexdigest()


def write_thumbnail_file(destination: Path, raw_bytes: bytes) -> tuple[int, int]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(BytesIO(raw_bytes)) as image:
        normalized = ImageOps.exif_transpose(image)
        thumbnail = normalized.copy()
        thumbnail.thumbnail((THUMBNAIL_MAX_DIMENSION, THUMBNAIL_MAX_DIMENSION))
        thumbnail.save(destination, format="PNG", optimize=True)
        return thumbnail.size


def create_thumbnail_from_original(image_id: str, storage_relpath: str) -> StoredThumbnail:
    original_path = DATA_DIR / storage_relpath
    if not original_path.exists():
        raise StorageValidationError("Stored original image file is missing")

    raw_bytes = original_path.read_bytes()
    inspect_image_bytes(raw_bytes)
    thumbnail_path, thumbnail_relative = build_thumbnail_storage_name(image_id, storage_relpath)

    try:
        thumbnail_width_px, thumbnail_height_px = write_thumbnail_file(thumbnail_path, raw_bytes)
    except Exception:
        remove_storage_artifacts(thumbnail_relative)
        raise

    return StoredThumbnail(
        thumbnail_relpath=thumbnail_relative,
        thumbnail_width_px=thumbnail_width_px,
        thumbnail_height_px=thumbnail_height_px,
    )


def store_image_bytes(
    image_id: str,
    *,
    filename: str,
    raw_bytes: bytes,
    mime_type_override: str | None = None,
) -> StoredUpload:
    original_path, original_relative = build_original_storage_name(image_id, filename or "upload.bin")
    thumbnail_path, thumbnail_relative = build_thumbnail_storage_name(image_id, original_relative)
    detected_mime_type, width_px, height_px = inspect_image_bytes(raw_bytes)
    mime_type = mime_type_override or detected_mime_type

    try:
        file_size, sha256 = write_original_file(original_path, raw_bytes)
        thumbnail_width_px, thumbnail_height_px = write_thumbnail_file(thumbnail_path, raw_bytes)
    except Exception:
        remove_storage_artifacts(original_relative, thumbnail_relative)
        raise

    suffix = ensure_suffix(filename or "upload.bin").lstrip(".")
    stored_filename = original_path.name

    return StoredUpload(
        stored_filename=stored_filename,
        storage_relpath=original_relative,
        thumbnail_relpath=thumbnail_relative,
        mime_type=mime_type,
        file_extension=suffix,
        file_size_bytes=file_size,
        sha256=sha256,
        width_px=width_px,
        height_px=height_px,
        thumbnail_width_px=thumbnail_width_px,
        thumbnail_height_px=thumbnail_height_px,
    )


def store_file_path(image_id: str, source_path: Path) -> StoredUpload:
    mime_type = mimetypes.guess_type(source_path.name)[0]
    return store_image_bytes(
        image_id,
        filename=source_path.name,
        raw_bytes=source_path.read_bytes(),
        mime_type_override=mime_type,
    )


def store_upload(image_id: str, upload: UploadFile) -> StoredUpload:
    raw_bytes, mime_type, _, _ = read_upload_bytes(upload)
    return store_image_bytes(
        image_id,
        filename=upload.filename or "upload.bin",
        raw_bytes=raw_bytes,
        mime_type_override=mime_type,
    )
