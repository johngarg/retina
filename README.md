# Retina

Retina is a local-first desktop app for managing retinal-image patient records, visits, and imported eye images. 

This is a modern rewrite of an older retinal workflow prototype, with the current focus on a maintainable local desktop app. The legacy code is here: https://github.com/johngarg/racket-optical.

The rewrite uses:

- `apps/desktop`: React + Tauri desktop app
- `apps/api`: FastAPI local backend
- SQLite + managed filesystem storage for images and thumbnails

Please see the [user manual](user_manual.md) for details on how to use the app.

## Current status

The app currently supports:

- creating and searching patients
- creating visits
- importing left/right retinal images from the filesystem
- viewing thumbnails and full-resolution images
- editing visit notes and image metadata
- legacy data import
- local backup export
- audit logging for core create/edit/import/backup actions

This is already usable as a developer-run prototype. It also now has a defined packaging path for macOS and Windows.

The current release path is:

- macOS builds produce `Retina.app`, which can be zipped for distribution
- Windows builds produce an NSIS installer `.exe`
- the Python backend is bundled as a sidecar inside the desktop build
- the app runs locally and stores its own data

## Installation

Download the app from the [latest release](../../releases/latest).

### macOS

1. Open the [Releases page](../../releases/latest).
2. Download the latest macOS release artifact:
   - `Retina.app.zip` for the simplest install path
   - or a `.dmg` if a DMG release is provided
3. Unzip `Retina.app.zip`.
4. Move `Retina.app` into `Applications`.
5. Open `Applications` and launch Retina.

If the app is not yet signed and notarized, macOS may warn that the app is from an unidentified developer. That is expected for pre-release or internal builds.

### Windows

1. Open the [Releases page](../../releases/latest).
2. Download the latest Windows installer:
   - `Retina Setup ... .exe`
3. Run the installer.
4. Follow the installer prompts.
5. Launch Retina from the Start menu or desktop shortcut.

If the app is not yet code-signed, Windows SmartScreen may warn before launch. That is expected for pre-release or internal builds.

## Repository layout

- `docs/`: legacy assessment, domain model, architecture, migration plan, implementation plan
- `apps/api/`: FastAPI backend, migrations, import/export tooling, tests
- `apps/desktop/`: React/Tauri desktop app

## Running the app in development

### Recommended: Tauri desktop dev mode

```bash
cd apps/desktop
npm install
npm run tauri dev
```

This is the best current way to try the app because the desktop shell starts the backend automatically.

### Browser-only UI

```bash
cd apps/api
uv sync
uv run uvicorn app.main:app --reload
```

In another terminal:

```bash
cd apps/desktop
npm install
npm run dev
```

Browser mode is still useful for frontend development, but it expects the API to be started separately.

## Packaging

### macOS

Typical release build:

```bash
cd apps/desktop
npm install
npm run build:desktop:macos
```

Artifacts:

- `apps/desktop/src-tauri/target/release/bundle/macos/Retina.app`

Optional DMG build:

```bash
cd apps/desktop
npm run build:desktop:macos:dmg
```

### Windows

Run on a Windows machine:

```powershell
cd apps\desktop
npm install
npm run build:desktop:windows
```

Artifact:

- `apps/desktop/src-tauri/target/release/bundle/nsis/*.exe`

### CI packaging

GitHub Actions now builds desktop bundles on both macOS and Windows via `.github/workflows/build-desktop.yml`. This is the main automated packaging validation path for Windows until installer testing is done on a clean Windows machine.

## Data and operations

The app is local-first:

- the backend binds to localhost only
- data lives under the app data directory
- images are copied into managed storage
- thumbnails are generated on import

Operational tooling currently available:

### Storage integrity scan

```bash
cd apps/api
uv run python scripts/scan_integrity.py
```

### Backup export

```bash
cd apps/api
uv run python scripts/backup_data.py
```

This creates a timestamped zip archive containing:

- a consistent snapshot of `app.db`
- managed original image files
- managed thumbnails
- `manifest.json`

### Legacy import

```bash
cd apps/api
uv run python scripts/import_legacy.py /path/to/legacy-export
```

The importer preserves legacy identifiers where available and reports missing legacy assets as JSON warnings.

## Documentation

See:

- `docs/legacy-assessment.md`
- `docs/domain-model.md`
- `docs/architecture.md`
- `docs/migration-plan.md`
- `docs/implementation-plan.md`
- `docs/distribution.md`
- `docs/installer-testing.md`
- `docs/install.md`

## Near-term priority

The main product priority is to finish the last mile of distribution:

- clean-machine installer validation on macOS and Windows
- user-facing install guidance
- code signing
- macOS notarization
