from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.backup import create_backup_archive
from app.database import SessionLocal
from app.migrations import run_migrations


def main() -> None:
    run_migrations()
    with SessionLocal() as session:
        result = create_backup_archive(session)
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
