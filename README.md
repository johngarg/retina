# Retina Rewrite

Modern rewrite of the legacy retinal camera workflow app.

## Repository layout

- `retina-racket/`: small early prototype
- `retina-racket-full/`: fuller legacy Racket app plus sample database and assets
- `docs/`: legacy assessment, domain model, architecture, and migration plan
- `apps/api/`: FastAPI backend for local-first persistence and image import
- `apps/desktop/`: React desktop UI scaffolded for Tauri packaging

## Current status

The repository now contains:

- reverse-engineered legacy documentation
- a new SQLite-backed FastAPI service
- thumbnail-backed image import, browsing, and integrity scanning
- audit logging for create/edit/import/backup operations
- a React UI for patient creation, session creation, image import, browsing, and viewing
- a Tauri shell scaffold under `apps/desktop/src-tauri`

## Legacy findings

The legacy app stores:

- patients in SQLite
- one image-like "visit" row per import
- note text in separate `.txt` files
- images in a managed local folder

Important legacy gaps:

- no structured left/right eye field
- no true multi-image session model
- weak DB constraints
- missing/orphaned sample assets
- macOS-specific image opening

See:

- `docs/legacy-assessment.md`
- `docs/domain-model.md`
- `docs/architecture.md`
- `docs/migration-plan.md`

## Running the prototype

### API

```bash
cd apps/api
uv sync
uv run uvicorn app.main:app --reload
```

The API stores development data in `apps/api/data/`.

### Storage integrity scan

```bash
cd apps/api
uv run python scripts/scan_integrity.py
```

This reports missing original files, missing thumbnails, and orphaned files under managed storage.

### Backup export

```bash
cd apps/api
uv run python scripts/backup_data.py
```

This creates a timestamped zip archive under `apps/api/data/backups/` containing:

- a consistent snapshot of `app.db`
- managed original and thumbnail image files
- a `manifest.json` summary of record and file counts

Backup creation is also recorded in the audit log.

### Legacy import

```bash
cd apps/api
uv run python scripts/import_legacy.py ../../retina-racket-full
```

The importer:

- reads `database_dir/patient_database.db`
- copies legacy images into managed storage
- inlines note text when the `.txt` file exists
- preserves `legacy_patient_id` and `legacy_visit_id`
- reports missing legacy files and laterality inference warnings as JSON
- records a summary audit event for the import run

### Desktop UI

```bash
cd apps/desktop
npm install
npm run dev
```

The Vite dev server proxies `/api` to `http://127.0.0.1:8000`.

### Tauri desktop dev mode

```bash
cd apps/desktop
npm install
npm run tauri dev
```

In Tauri dev mode, the desktop shell now starts the FastAPI backend automatically from `apps/api/.venv/bin/python`.

### Current runtime note

- browser/Vite mode still expects the API to be started separately
- Tauri debug/dev mode can now manage backend startup automatically
- Tauri release builds now bundle a packaged backend sidecar on macOS

### Tauri release build

```bash
cd apps/desktop
npm install
npm run tauri build
```

The release build now:

- builds the React frontend
- packages the Python backend into a standalone executable via PyInstaller
- bundles that executable into the desktop app resources
- launches the bundled backend sidecar at runtime on macOS release builds

## Tauri note

Tauri debug/dev mode is verified, and macOS release builds now bundle a packaged backend executable. Browser-only mode still expects the API to be started separately.

## Next steps

1. Install dependencies and run the API/UI locally.
2. Verify the create patient -> create session -> import left/right images workflow.
3. Add migration tooling for `retina-racket-full/database_dir/patient_database.db`.
4. Experiment with the core workflow, then decide whether Milestone 10 should focus on release packaging polish or additional clinic workflow detail.
