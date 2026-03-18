import base64
import os
import sqlite3
import zipfile
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
from sqlalchemy.orm import close_all_sessions

from app.backup import create_backup_archive
from app.config import DATA_DIR
from app.database import SessionLocal, engine
from app.integrity import scan_storage_integrity
from app.legacy_import import (
    import_legacy_dataset,
    infer_laterality_from_note_text,
    parse_legacy_dob,
    parse_legacy_visit_timestamp,
)
from app import main as main_module
from app.main import app
from app.models import AuditEvent, Patient, RetinalImage, StudySession


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
        audit_columns = connection.execute("PRAGMA table_info(audit_events)").fetchall()
    finally:
        connection.close()

    assert version == ("20260318_0004",)
    assert any(column[1] == "width_px" for column in columns)
    assert any(column[1] == "height_px" for column in columns)
    assert any(column[1] == "thumbnail_relpath" for column in columns)
    assert any(column[1] == "thumbnail_width_px" for column in columns)
    assert any(column[1] == "thumbnail_height_px" for column in columns)
    assert any(column[1] == "legacy_visit_id" for column in session_columns)
    assert any(column[1] == "action" for column in audit_columns)
    assert any(column[1] == "summary" for column in audit_columns)


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


def test_patient_can_be_updated() -> None:
    patient = create_patient()

    response = client.patch(
        f"/patients/{patient['id']}",
        json={
            "first_name": "Augusta Ada",
            "last_name": "King",
            "date_of_birth": "1815-12-10",
            "gender_text": "X",
        },
    )
    assert response.status_code == 200
    updated = response.json()
    assert updated["first_name"] == "Augusta Ada"
    assert updated["last_name"] == "King"
    assert updated["display_name"] == "King, Augusta Ada"
    assert updated["gender_text"] == "X"


def test_patient_update_rejects_duplicate_active_identity() -> None:
    archived_patient = create_patient()

    response = client.patch(
        f"/patients/{archived_patient['id']}",
        json={
            "first_name": "Ada",
            "last_name": "Lovelace",
            "date_of_birth": "1815-12-10",
            "gender_text": "F",
        },
    )
    assert response.status_code == 200

    other = create_patient()

    response = client.patch(
        f"/patients/{other['id']}",
        json={
            "first_name": "Ada",
            "last_name": "Lovelace",
            "date_of_birth": "1815-12-10",
            "gender_text": "F",
        },
    )
    assert response.status_code == 409


def test_archived_patient_is_hidden_from_active_queries() -> None:
    patient = create_patient()

    response = client.post(f"/patients/{patient['id']}/archive")
    assert response.status_code == 200
    archived = response.json()
    assert archived["archived_at"] is not None

    response = client.get("/patients")
    assert response.status_code == 200
    assert all(entry["id"] != patient["id"] for entry in response.json())

    response = client.get("/patients", params={"include_archived": "true"})
    assert response.status_code == 200
    assert any(entry["id"] == patient["id"] for entry in response.json())

    response = client.get(f"/patients/{patient['id']}")
    assert response.status_code == 404

    response = client.get(f"/patients/{patient['id']}", params={"include_archived": "true"})
    assert response.status_code == 200

    response = client.post(f"/patients/{patient['id']}/unarchive")
    assert response.status_code == 200
    restored = response.json()
    assert restored["archived_at"] is None

    response = client.get("/patients")
    assert response.status_code == 200
    assert any(entry["id"] == patient["id"] for entry in response.json())


def test_unarchive_rejects_duplicate_active_patient() -> None:
    archived_patient = create_patient()

    response = client.post(f"/patients/{archived_patient['id']}/archive")
    assert response.status_code == 200

    response = client.post(
        "/patients",
        json={
            "first_name": archived_patient["first_name"],
            "last_name": archived_patient["last_name"],
            "date_of_birth": archived_patient["date_of_birth"],
            "gender_text": archived_patient["gender_text"],
        },
    )
    assert response.status_code == 201

    response = client.post(f"/patients/{archived_patient['id']}/unarchive")
    assert response.status_code == 409
    assert "same identity already exists" in response.json()["detail"]


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

    response = client.get("/patients", params={"limit": 1})
    assert response.status_code == 200
    assert len(response.json()) == 1


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


def test_open_image_externally_endpoint_uses_default_application(monkeypatch) -> None:
    patient = create_patient()
    session_obj = create_session(patient["id"])
    image = import_test_image(session_obj["id"], laterality="left")

    opened_paths: list[str] = []

    def fake_open(path: Path) -> None:
        opened_paths.append(str(path))

    monkeypatch.setattr(main_module, "open_path_in_default_application", fake_open)

    response = client.post(f"/images/{image['id']}/open-external")
    assert response.status_code == 204
    assert opened_paths
    assert image["stored_filename"] in opened_paths[0]


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


def test_audit_events_created_for_core_workflow() -> None:
    patient = create_patient()
    session_obj = create_session(patient["id"])
    image = import_test_image(session_obj["id"], laterality="left", notes="Audit left eye")

    response = client.patch(
        f"/sessions/{session_obj['id']}",
        json={"operator_name": "Operator Audit", "notes": "Updated session"},
    )
    assert response.status_code == 200

    response = client.patch(
        f"/images/{image['id']}",
        json={"image_type": "red_free", "notes": "Updated image"},
    )
    assert response.status_code == 200

    with SessionLocal() as session:
        events = list(session.query(AuditEvent).order_by(AuditEvent.occurred_at.asc()))

    actions = [event.action for event in events[-5:]]
    assert actions == [
        "patient_created",
        "session_created",
        "image_imported",
        "session_updated",
        "image_updated",
    ]
    assert events[-5].patient_id == patient["id"]
    assert events[-4].session_id == session_obj["id"]
    assert events[-3].image_id == image["id"]


def test_backup_archive_contains_database_manifest_and_images() -> None:
    patient = create_patient()
    session_obj = create_session(patient["id"])
    image = import_test_image(session_obj["id"], laterality="left")

    with SessionLocal() as session:
        result = create_backup_archive(session)

    archive_path = Path(result.archive_path)
    assert archive_path.exists()
    assert archive_path.suffix == ".zip"
    assert result.images >= 1
    assert result.original_files >= 1
    assert result.thumbnail_files >= 1

    with zipfile.ZipFile(archive_path) as archive:
        names = set(archive.namelist())
        assert "app.db" in names
        assert "manifest.json" in names
        assert image["storage_relpath"] in names
        assert image["thumbnail_relpath"] in names
        manifest = archive.read("manifest.json").decode("utf-8")
        assert '"patients":' in manifest
        assert '"images":' in manifest

    with SessionLocal() as session:
        latest_backup_event = session.query(AuditEvent).order_by(AuditEvent.occurred_at.desc()).first()

    assert latest_backup_event is not None
    assert latest_backup_event.action == "backup_created"


def test_backup_export_and_restore_roundtrip() -> None:
    patient = create_patient()
    session_obj = create_session(patient["id"])
    import_test_image(session_obj["id"], laterality="left", notes="Roundtrip image")

    response = client.post("/backups/export")
    assert response.status_code == 201
    backup = response.json()

    backup_path = Path(backup["archive_path"])
    assert backup_path.exists()

    extra_patient = create_patient()
    response = client.get("/patients")
    assert response.status_code == 200
    current_ids = {entry["id"] for entry in response.json()}
    assert patient["id"] in current_ids
    assert extra_patient["id"] in current_ids

    with backup_path.open("rb") as archive_file:
        response = client.post(
            "/backups/restore",
            files={"file": ("retina-backup.zip", archive_file, "application/zip")},
        )

    assert response.status_code == 200
    restored = response.json()
    assert restored["source_archive_name"] == "retina-backup.zip"
    assert restored["safety_backup_path"].endswith(".zip")

    response = client.get("/patients")
    assert response.status_code == 200
    restored_ids = {entry["id"] for entry in response.json()}
    assert patient["id"] in restored_ids
    assert extra_patient["id"] not in restored_ids


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
    client.close()
    close_all_sessions()
    engine.dispose()

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
