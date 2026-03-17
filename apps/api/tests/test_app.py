import os
from datetime import date
from io import BytesIO
from pathlib import Path

TEST_DATA_DIR = Path(__file__).resolve().parent / ".test-data"
os.environ["RETINA_DATA_DIR"] = str(TEST_DATA_DIR)

from fastapi.testclient import TestClient

from app.config import DATA_DIR
from app.main import app


client = TestClient(app)


def test_patient_session_and_image_flow() -> None:
    response = client.post(
        "/patients",
        json={
            "first_name": "Ada",
            "last_name": "Lovelace",
            "date_of_birth": "1815-12-10",
            "gender_text": "F",
        },
    )
    assert response.status_code == 201
    patient = response.json()

    response = client.post(
        f"/patients/{patient['id']}/sessions",
        json={
            "session_date": str(date.today()),
            "operator_name": "Operator One",
            "notes": "Initial intake",
        },
    )
    assert response.status_code == 201
    session_obj = response.json()

    png_bytes = (
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR"
        b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
        b"\x1f\x15\xc4\x89"
        b"\x00\x00\x00\rIDATx\x9cc`\x00\x00\x00\x02\x00\x01"
        b"\xe2!\xbc3"
        b"\x00\x00\x00\x00IEND\xaeB`\x82"
    )

    response = client.post(
        f"/sessions/{session_obj['id']}/images/import",
        data={"laterality": "left", "image_type": "color_fundus", "notes": "Baseline left eye"},
        files={"file": ("left-eye.png", BytesIO(png_bytes), "image/png")},
    )
    assert response.status_code == 201
    image = response.json()

    response = client.get(f"/patients/{patient['id']}")
    assert response.status_code == 200
    body = response.json()
    assert len(body["sessions"]) == 1
    assert len(body["sessions"][0]["images"]) == 1
    assert body["sessions"][0]["images"][0]["laterality"] == "left"

    stored_file = DATA_DIR / "images"
    assert stored_file.exists()


def teardown_module() -> None:
    if DATA_DIR.exists():
        for path in sorted(DATA_DIR.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
