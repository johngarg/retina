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
4. Add automated tests and backup/export tooling.
