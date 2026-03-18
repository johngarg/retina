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
from app.legacy_import import (
    import_legacy_dataset,
    infer_laterality_from_note_text,
    parse_legacy_dob,
    parse_legacy_visit_timestamp,
)
from app.main import app
from app.models import Patient, RetinalImage, StudySession


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


def create_session(patient_id: str, *, session_date: str | None = None) -> dict:
    response = client.post(
        f"/patients/{patient_id}/sessions",
        json={
            "session_date": session_date or str(date.today()),
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
        session_columns = connection.execute("PRAGMA table_info(study_sessions)").fetchall()
    finally:
        connection.close()

    assert version == ("20260318_0003",)
    assert any(column[1] == "width_px" for column in columns)
    assert any(column[1] == "height_px" for column in columns)
    assert any(column[1] == "thumbnail_relpath" for column in columns)
    assert any(column[1] == "thumbnail_width_px" for column in columns)
    assert any(column[1] == "thumbnail_height_px" for column in columns)
    assert any(column[1] == "legacy_visit_id" for column in session_columns)


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


def test_patient_search_matches_first_last_tokens_and_legacy_id() -> None:
    patient = create_patient()

    with SessionLocal() as session:
        db_patient = session.get(Patient, patient["id"])
        assert db_patient is not None
        db_patient.legacy_patient_id = 551234
        session.commit()

    response = client.get("/patients", params={"q": "Ada Lovelace"})
    assert response.status_code == 200
    assert any(result["id"] == patient["id"] for result in response.json())

    response = client.get("/patients", params={"q": "Lovelace Ada"})
    assert response.status_code == 200
    assert any(result["id"] == patient["id"] for result in response.json())

    response = client.get("/patients", params={"q": "551234"})
    assert response.status_code == 200
    assert any(result["id"] == patient["id"] for result in response.json())


def test_patient_detail_filters_sessions_and_images() -> None:
    patient = create_patient()
    first_session = create_session(patient["id"], session_date="2026-03-10")
    second_session = create_session(patient["id"], session_date="2026-03-15")

    import_test_image(first_session["id"], laterality="left", image_type="color_fundus")
    import_test_image(first_session["id"], laterality="right", image_type="red_free")
    import_test_image(second_session["id"], laterality="left", image_type="red_free")

    response = client.get(
        f"/patients/{patient['id']}",
        params={
            "session_date_from": "2026-03-12",
            "laterality": "left",
            "image_type": "red_free",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert [session["id"] for session in body["sessions"]] == [second_session["id"]]
    assert len(body["sessions"][0]["images"]) == 1
    assert body["sessions"][0]["images"][0]["laterality"] == "left"
    assert body["sessions"][0]["images"][0]["image_type"] == "red_free"

    response = client.get(
        f"/patients/{patient['id']}/sessions",
        params={"laterality": "right"},
    )
    assert response.status_code == 200
    sessions = response.json()
    assert [session["id"] for session in sessions] == [first_session["id"]]
    assert len(sessions[0]["images"]) == 1
    assert sessions[0]["images"][0]["laterality"] == "right"


def test_invalid_patient_filter_is_rejected() -> None:
    patient = create_patient()

    response = client.get(f"/patients/{patient['id']}", params={"laterality": "temporal"})
    assert response.status_code == 400
    assert "laterality" in response.json()["detail"]


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


def build_legacy_fixture(root: Path) -> Path:
    if root.exists():
        for path in sorted(root.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
    database_dir = root / "database_dir"
    image_dir = root / "image_data_dir"
    text_dir = root / "text_data_dir"
    database_dir.mkdir(parents=True, exist_ok=True)
    image_dir.mkdir(parents=True, exist_ok=True)
    text_dir.mkdir(parents=True, exist_ok=True)

    database_path = database_dir / "patient_database.db"
    connection = sqlite3.connect(database_path)
    try:
        connection.execute(
            "CREATE TABLE patients (patient_id INTEGER, firstname TEXT, lastname TEXT, dob TEXT, gender TEXT, archived INTEGER)"
        )
        connection.execute(
            "CREATE TABLE visits (visit_id INTEGER, patient_id INTEGER, d TEXT, image_path TEXT, notes TEXT, archived INTEGER)"
        )
        connection.executemany(
            "INSERT INTO patients VALUES (?, ?, ?, ?, ?, ?)",
            [
                (1001, "ALICE", "EXAMPLE", "1/1/1900", "F", 0),
                (1002, "BOB", "ARCHIVED", "2/2/1980", "M", 1),
            ],
        )
        connection.executemany(
            "INSERT INTO visits VALUES (?, ?, ?, ?, ?, ?)",
            [
                (2001, 1001, "t:14.18.4-d:10/9/2018", "1001_2001.png", "1001_2001.txt", 0),
                (2002, 1001, "t:14.19.5-d:10/9/2018", "1001_2002.png", "1001_2002.txt", 0),
                (2003, 1002, "t:22.17.25-d:20/5/2018", "1002_2003.png", "1002_2003.txt", 1),
            ],
        )
        connection.commit()
    finally:
        connection.close()

    (image_dir / "1001_2001.png").write_bytes(tiny_png_bytes())
    (image_dir / "1001_2002.png").write_bytes(tiny_png_bytes())
    (text_dir / "1001_2001.txt").write_text("This is the left eye.", encoding="utf-8")
    (text_dir / "1001_2002.txt").write_text("Rigth eye", encoding="utf-8")
    return root


def test_legacy_parsers_and_laterality_inference() -> None:
    assert parse_legacy_dob("6/5/1991").isoformat() == "1991-05-06"
    assert parse_legacy_visit_timestamp("t:22.17.25-d:20/5/2018").isoformat() == "2018-05-20T22:17:25+00:00"
    assert infer_laterality_from_note_text("Left eye") == ("left", True)
    assert infer_laterality_from_note_text("Rigth eye") == ("right", True)
    assert infer_laterality_from_note_text("No notes yet...") == ("unknown", False)


def test_legacy_import_reports_missing_assets_and_is_idempotent() -> None:
    legacy_root = build_legacy_fixture(DATA_DIR.parent / ".legacy-fixture")

    with SessionLocal() as session:
        report = import_legacy_dataset(legacy_root, session)

    assert report.patients_created == 2
    assert report.sessions_created == 3
    assert report.images_imported == 2
    assert any(w.warning_type == "missing_image" and w.legacy_visit_id == 2003 for w in report.warnings or [])
    assert any(w.warning_type == "missing_notes" and w.legacy_visit_id == 2003 for w in report.warnings or [])
    assert any(w.warning_type == "archived_visit" and w.legacy_visit_id == 2003 for w in report.warnings or [])

    with SessionLocal() as session:
        patients = list(
            session.query(Patient)
            .filter(Patient.legacy_patient_id.in_([1001, 1002]))
            .order_by(Patient.legacy_patient_id)
        )
        sessions = list(
            session.query(StudySession)
            .filter(StudySession.legacy_visit_id.is_not(None))
            .order_by(StudySession.legacy_visit_id)
        )
        images = list(
            session.query(RetinalImage)
            .filter(RetinalImage.legacy_visit_id.is_not(None))
            .order_by(RetinalImage.legacy_visit_id)
        )

    assert [patient.legacy_patient_id for patient in patients] == [1001, 1002]
    assert patients[1].archived_at is not None
    assert [session.legacy_visit_id for session in sessions] == [2001, 2002, 2003]
    assert sessions[0].status == "completed"
    assert sessions[1].status == "completed"
    assert sessions[2].status == "draft"
    assert "Missing legacy image file 1002_2003.png" in (sessions[2].notes or "")
    assert [image.legacy_visit_id for image in images] == [2001, 2002]
    assert images[0].laterality == "left"
    assert images[1].laterality == "right"
    assert images[0].legacy_notes_filename == "1001_2001.txt"
    assert images[1].legacy_image_filename == "1001_2002.png"

    with SessionLocal() as session:
        rerun = import_legacy_dataset(legacy_root, session)

    assert rerun.patients_reused == 2
    assert rerun.sessions_reused == 3
    assert rerun.images_reused == 2

    with SessionLocal() as session:
        assert session.query(Patient).filter(Patient.legacy_patient_id.in_([1001, 1002])).count() == 2
        assert session.query(StudySession).filter(StudySession.legacy_visit_id.is_not(None)).count() == 3
        assert session.query(RetinalImage).filter(RetinalImage.legacy_visit_id.is_not(None)).count() == 2


def teardown_module() -> None:
    if DATA_DIR.exists():
        for path in sorted(DATA_DIR.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
    legacy_fixture = DATA_DIR.parent / ".legacy-fixture"
    if legacy_fixture.exists():
        for path in sorted(legacy_fixture.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
