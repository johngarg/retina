from __future__ import annotations

import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from .config import DB_PATH

APPLICATION_TABLES = {"patients", "study_sessions", "retinal_images"}
COMPATIBILITY_INDEX_STATEMENTS = (
    "CREATE INDEX IF NOT EXISTS ix_patients_lookup ON patients (normalized_last_name, normalized_first_name, date_of_birth)",
    "CREATE INDEX IF NOT EXISTS ix_study_sessions_patient_date ON study_sessions (patient_id, session_date)",
    "CREATE INDEX IF NOT EXISTS ix_retinal_images_session_laterality ON retinal_images (session_id, laterality)",
)


def migrations_root() -> Path:
    return Path(__file__).resolve().parents[1] / "alembic"


def build_config() -> Config:
    config = Config()
    config.set_main_option("script_location", str(migrations_root()))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{DB_PATH}")
    return config


def bootstrap_unversioned_sqlite_database(head_revision: str) -> bool:
    if not DB_PATH.exists():
        return False

    with sqlite3.connect(DB_PATH) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        if not APPLICATION_TABLES.issubset(tables):
            return False

        has_version_table = "alembic_version" in tables
        version_rows = (
            connection.execute("SELECT version_num FROM alembic_version").fetchall()
            if has_version_table
            else []
        )
        if version_rows:
            return False

        for statement in COMPATIBILITY_INDEX_STATEMENTS:
            connection.execute(statement)

        connection.execute(
            "CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL)"
        )
        connection.execute("DELETE FROM alembic_version")
        connection.execute(
            "INSERT INTO alembic_version (version_num) VALUES (?)",
            (head_revision,),
        )
        connection.commit()
    return True


def run_migrations() -> None:
    config = build_config()
    head_revision = ScriptDirectory.from_config(config).get_current_head()
    if head_revision is None:
        raise RuntimeError("Alembic head revision is not configured")
    bootstrap_unversioned_sqlite_database(head_revision)
    command.upgrade(config, "head")
