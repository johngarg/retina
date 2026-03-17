import base64
import os
import sqlite3
from datetime import date
from io import BytesIO
from itertools import count
from pathlib import Path

TEST_DATA_DIR = Path(__file__).resolve().parent / ".test-data"
os.environ["RETINA_DATA_DIR"] = str(TEST_DATA_DIR)

if TEST_DATA_DIR.exists():
    for path in sorted(TEST_DATA_DIR.rglob("*"), reverse=True):
        if path.is_file():
            path.unlink()
        elif path.is_dir():
            path.rmdir()

from fastapi.testclient import TestClient

from app.config import DATA_DIR
from app.database import SessionLocal
from app.integrity import scan_storage_integrity
from app.main import app


client = TestClient(app)
PATIENT_SEQUENCE = count(1)


def create_patient() -> dict:
    sequence = next(PATIENT_SEQUENCE)
    response = client.post(
        "/patients",
        json={
            "first_name": f"Ada{sequence}",
            "last_name": "Lovelace",
            "date_of_birth": "1815-12-10",
            "gender_text": "F",
        },
    )
    assert response.status_code == 201
    return response.json()


def create_session(patient_id: str) -> dict:
    response = client.post(
        f"/patients/{patient_id}/sessions",
        json={
            "session_date": str(date.today()),
            "operator_name": "Operator One",
            "notes": "Initial intake",
        },
    )
    assert response.status_code == 201
    return response.json()


def import_test_image(
    session_id: str,
    *,
    laterality: str,
    image_type: str = "color_fundus",
    notes: str | None = None,
    filename: str | None = None,
) -> dict:
    response = client.post(
        f"/sessions/{session_id}/images/import",
        data={
            "laterality": laterality,
            "image_type": image_type,
            "notes": notes or "",
        },
        files={
            "file": (
                filename or f"{laterality}-eye.png",
                BytesIO(tiny_png_bytes()),
                "image/png",
            )
        },
    )
    assert response.status_code == 201
    return response.json()


def tiny_png_bytes() -> bytes:
    return base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+c6XQAAAAASUVORK5CYII=")


def test_database_bootstraps_with_alembic_version() -> None:
    connection = sqlite3.connect(DATA_DIR / "app.db")
    try:
        version = connection.execute("SELECT version_num FROM alembic_version").fetchone()
        columns = connection.execute("PRAGMA table_info(retinal_images)").fetchall()
    finally:
        connection.close()

    assert version == ("20260318_0002",)
    assert any(column[1] == "width_px" for column in columns)
    assert any(column[1] == "height_px" for column in columns)
    assert any(column[1] == "thumbnail_relpath" for column in columns)
    assert any(column[1] == "thumbnail_width_px" for column in columns)
    assert any(column[1] == "thumbnail_height_px" for column in columns)


def test_patient_session_and_image_flow() -> None:
    patient = create_patient()
    session_obj = create_session(patient["id"])
    left_image = import_test_image(
        session_obj["id"],
        laterality="left",
        notes="Baseline left eye",
    )
    right_image = import_test_image(
        session_obj["id"],
        laterality="right",
        image_type="red_free",
        notes="Baseline right eye",
    )

    response = client.patch(
        f"/sessions/{session_obj['id']}",
        json={
            "operator_name": "Operator Two",
            "notes": "Bilateral baseline session",
        },
    )
    assert response.status_code == 200

    response = client.patch(
        f"/images/{right_image['id']}",
        json={
            "image_type": "color_fundus",
            "notes": "Updated right eye note",
        },
    )
    assert response.status_code == 200
    updated_right_image = response.json()

    response = client.get(f"/patients/{patient['id']}")
    assert response.status_code == 200
    body = response.json()
    assert len(body["sessions"]) == 1
    imported_session = next(session for session in body["sessions"] if session["id"] == session_obj["id"])
    assert imported_session["notes"] == "Bilateral baseline session"
    assert imported_session["operator_name"] == "Operator Two"
    assert len(imported_session["images"]) == 2
    assert {image["laterality"] for image in imported_session["images"]} == {"left", "right"}
    assert left_image["width_px"] == 1
    assert left_image["height_px"] == 1
    assert left_image["thumbnail_width_px"] == 1
    assert left_image["thumbnail_height_px"] == 1
    assert updated_right_image["image_type"] == "color_fundus"
    assert updated_right_image["notes"] == "Updated right eye note"

    stored_file = DATA_DIR / "images"
    assert stored_file.exists()

    response = client.get(f"/images/{left_image['id']}/thumbnail")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"


def test_invalid_image_import_rolls_back_files() -> None:
    patient = create_patient()
    session_obj = create_session(patient["id"])

    response = client.post(
        f"/sessions/{session_obj['id']}/images/import",
        data={"laterality": "left", "image_type": "color_fundus"},
        files={"file": ("not-an-image.txt", BytesIO(b"not a real image"), "text/plain")},
    )
    assert response.status_code == 400

    response = client.get(f"/patients/{patient['id']}")
    assert response.status_code == 200
    assert response.json()["sessions"][0]["images"] == []

    with SessionLocal() as session:
        result = scan_storage_integrity(session)

    assert result.ok


def test_duplicate_patient_conflict() -> None:
    response = client.post(
        "/patients",
        json={
            "first_name": "Grace",
            "last_name": "Hopper",
            "date_of_birth": "1906-12-09",
            "gender_text": "F",
        },
    )
    assert response.status_code == 201

    response = client.post(
        "/patients",
        json={
            "first_name": " Grace ",
            "last_name": " Hopper ",
            "date_of_birth": "1906-12-09",
            "gender_text": "f",
        },
    )
    assert response.status_code == 409


def test_invalid_laterality_is_rejected() -> None:
    patient = create_patient()
    session_obj = create_session(patient["id"])

    response = client.post(
        f"/sessions/{session_obj['id']}/images/import",
        data={"laterality": "temporal", "image_type": "color_fundus"},
        files={"file": ("bad-eye.png", BytesIO(tiny_png_bytes()), "image/png")},
    )
    assert response.status_code == 400
    assert "laterality" in response.json()["detail"]


def test_invalid_image_type_is_rejected() -> None:
    patient = create_patient()
    session_obj = create_session(patient["id"])

    response = client.post(
        f"/sessions/{session_obj['id']}/images/import",
        data={"laterality": "left", "image_type": "angiography"},
        files={"file": ("bad-eye.png", BytesIO(tiny_png_bytes()), "image/png")},
    )
    assert response.status_code == 400
    assert "image_type" in response.json()["detail"]


def test_integrity_scan_reports_missing_and_orphaned_files() -> None:
    patient = create_patient()
    session_obj = create_session(patient["id"])

    response = client.post(
        f"/sessions/{session_obj['id']}/images/import",
        data={"laterality": "left", "image_type": "color_fundus"},
        files={"file": ("left-eye.png", BytesIO(tiny_png_bytes()), "image/png")},
    )
    assert response.status_code == 201
    image = response.json()

    original_path = DATA_DIR / image["storage_relpath"]
    thumbnail_path = DATA_DIR / image["thumbnail_relpath"]
    original_path.unlink()
    orphan_thumbnail = DATA_DIR / "images" / "thumbnail" / "orphan.png"
    orphan_thumbnail.parent.mkdir(parents=True, exist_ok=True)
    orphan_thumbnail.write_bytes(thumbnail_path.read_bytes())

    with SessionLocal() as session:
        result = scan_storage_integrity(session)

    assert not result.ok
    assert len(result.missing_originals) == 1
    assert result.missing_originals[0].image_id == image["id"]
    assert len(result.orphaned_thumbnails) == 1
    assert result.orphaned_thumbnails[0].path.endswith("orphan.png")


def teardown_module() -> None:
    if DATA_DIR.exists():
        for path in sorted(DATA_DIR.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
