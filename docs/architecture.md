# Architecture

## Recommended stack

- Frontend: TypeScript + React
- Desktop shell: Tauri
- Local API/service: Python + FastAPI
- Database: SQLite first, SQLAlchemy/Alembic with a clean PostgreSQL path later

This remains the right baseline after inspecting the legacy code.

## Why this structure fits the problem

The legacy app is a local clinic tool with direct filesystem import and a small persistent data model. The main risks are data integrity, maintainability, and cross-platform behavior, not cloud-scale distribution.

This stack gives:

- strong desktop UX with a modern typed UI
- a real backend boundary for import logic, validation, and future analysis pipelines
- robust local-first operation
- portable persistence with SQLite
- future migration to PostgreSQL without rewriting the domain layer

## High-level system design

```text
apps/desktop
  React UI running inside Tauri
    |
    | HTTP on localhost
    v
apps/api
  FastAPI service
    |
    | SQLAlchemy + filesystem storage service
    v
  SQLite database + managed image storage
```

## Responsibilities

### Desktop app

- patient search and browsing
- patient/session/image forms
- thumbnail grid and image viewer
- import flow UI
- laterality/type selection
- note editing
- local app settings

### FastAPI service

- data validation
- patient/session/image CRUD
- import transaction handling
- thumbnail generation
- search/filter endpoints
- legacy migration tooling
- future analysis-job orchestration

### Persistence layer

- structured relational records in SQLite
- managed filesystem storage for originals and thumbnails
- integrity checks between DB rows and files

## API shape for the first slice

Recommended initial endpoints:

- `GET /health`
- `GET /patients`
- `POST /patients`
- `GET /patients/{patient_id}`
- `POST /patients/{patient_id}/sessions`
- `GET /sessions/{session_id}`
- `POST /sessions/{session_id}/images/import`
- `GET /images/{image_id}`
- `GET /images/{image_id}/file`
- `GET /images/{image_id}/thumbnail`

Optional convenience endpoints:

- `GET /patients/{patient_id}/sessions`
- `GET /search?q=...`

## Local-first operational design

- the desktop app should work with no network connectivity
- the API binds only to localhost
- all state lives under an app data directory
- backups can be made by copying the database and managed image storage together
- no cloud dependency should be required for baseline operation

## Storage and transaction strategy

Image import must be handled centrally in the backend:

1. receive patient/session/image metadata + source filepath
2. verify source file exists
3. compute metadata and hash
4. create destination filename/path
5. copy file into managed storage
6. create thumbnail
7. insert DB records in one transaction
8. return created image record

If any step fails:

- roll back the DB transaction
- clean up partially copied files

## SQLite to PostgreSQL path

Keep the ORM and schema portable:

- use SQLAlchemy 2.x models
- avoid SQLite-only SQL tricks
- use Alembic migrations from the start
- keep IDs as UUID/ULID text if cross-database simplicity matters
- store enums as strings
- store JSON metadata only where necessary

Then later:

- switch DB URL
- run Alembic migrations
- keep file storage abstraction unchanged

## Tauri-specific guidance

Use Tauri primarily as:

- app window/container
- file dialog bridge
- secure shell for packaging
- future native integrations if camera export handling expands

Do not push all business logic into Tauri commands. The import and persistence logic should stay in the Python API so it remains testable and reusable.

## Future-ready extension points

- analysis pipelines per retinal image
- DICOM or vendor export importers
- operator accounts and audit trail
- bulk import tooling
- structured annotations
- export/report generation

## Compliance and operational concerns

First pass should not overengineer, but the design should acknowledge:

- retinal images are sensitive health data
- local backups matter
- audit history for edits may become necessary
- storage paths and logs should avoid leaking PHI where practical
- archive should mean hidden/retained, not immediate deletion
