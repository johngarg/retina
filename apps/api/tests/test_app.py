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


def tiny_png_bytes() -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR"
        b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
        b"\x1f\x15\xc4\x89"
        b"\x00\x00\x00\rIDATx\x9cc`\x00\x00\x00\x02\x00\x01"
        b"\xe2!\xbc3"
        b"\x00\x00\x00\x00IEND\xaeB`\x82"
    )


def test_database_bootstraps_with_alembic_version() -> None:
    connection = sqlite3.connect(DATA_DIR / "app.db")
    try:
        version = connection.execute("SELECT version_num FROM alembic_version").fetchone()
        columns = connection.execute("PRAGMA table_info(retinal_images)").fetchall()
    finally:
        connection.close()

    assert version == ("20260318_0001",)
    assert any(column[1] == "width_px" for column in columns)
    assert any(column[1] == "height_px" for column in columns)


def test_patient_session_and_image_flow() -> None:
    patient = create_patient()
    session_obj = create_session(patient["id"])

    response = client.post(
        f"/sessions/{session_obj['id']}/images/import",
        data={"laterality": "left", "image_type": "color_fundus", "notes": "Baseline left eye"},
        files={"file": ("left-eye.png", BytesIO(tiny_png_bytes()), "image/png")},
    )
    assert response.status_code == 201
    image = response.json()

    response = client.get(f"/patients/{patient['id']}")
    assert response.status_code == 200
    body = response.json()
    assert len(body["sessions"]) == 1
    imported_session = next(session for session in body["sessions"] if session["id"] == session_obj["id"])
    assert len(imported_session["images"]) == 1
    assert imported_session["images"][0]["laterality"] == "left"
    assert image["width_px"] == 1
    assert image["height_px"] == 1

    stored_file = DATA_DIR / "images"
    assert stored_file.exists()


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


def teardown_module() -> None:
    if DATA_DIR.exists():
        for path in sorted(DATA_DIR.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
