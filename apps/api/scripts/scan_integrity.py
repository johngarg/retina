from __future__ import annotations

import json
import sys

from app.database import SessionLocal
from app.integrity import scan_storage_integrity
from app.migrations import run_migrations


def main() -> int:
    run_migrations()
    with SessionLocal() as session:
        result = scan_storage_integrity(session)

    print(json.dumps(result.to_dict(), indent=2))
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
