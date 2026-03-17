from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.database import SessionLocal
from app.legacy_import import import_legacy_dataset
from app.migrations import run_migrations


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import a legacy retina-racket dataset into the new database.")
    parser.add_argument(
        "legacy_root",
        type=Path,
        help="Path to the legacy dataset root containing database_dir/, image_data_dir/, and text_data_dir/.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run_migrations()
    with SessionLocal() as session:
        report = import_legacy_dataset(args.legacy_root.resolve(), session)
    print(json.dumps(report.to_dict(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
