# Implementation Plan

## Current baseline

The repository currently has:

- legacy assessment and rewrite design documentation
- a FastAPI backend with a minimal SQLite-backed domain model
- a React UI that can create patients, create sessions, import images, browse sessions, and view images
- a Tauri shell scaffold

What is still missing is the integration and hardening required to make this a usable desktop app rather than a two-process prototype.

## Primary gaps

### Runtime integration

- the frontend expects the API on `127.0.0.1:8000`
- Tauri does not yet launch or supervise the backend
- startup failures currently surface as generic request errors

### Data integrity

- schema creation is implicit via `create_all()`, not versioned migrations
- image import metadata is still minimal
- no thumbnail generation yet
- no integrity scan or repair tooling yet

### Migration and operational readiness

- no legacy import command yet
- no backup/export workflow yet
- no audit trail yet
- no final packaging workflow yet

## Delivery plan

## Milestone 1: Single-launch desktop runtime

### Goal

Make the desktop app launch and function without manually starting the Python API.

### Work

- add Tauri-side backend process management
- start the FastAPI service automatically on app launch
- wait for API readiness via `/health`
- show explicit startup states in the UI:
  - starting backend
  - backend unavailable
  - retrying connection
- ensure backend shutdown when desktop app exits

### Implementation approach

- add a small Rust/Tauri module that spawns the backend process
- define separate dev and packaged runtime paths for the backend executable/interpreter
- add frontend bootstrap logic so patient/session requests do not fire before health succeeds
- add structured logging for backend startup errors

### Validation

Automated:

- frontend startup-state tests
- a small integration test for health polling behavior

Manual:

1. Launch desktop app with no separately running backend.
2. Confirm the app waits for backend readiness.
3. Confirm the patient list loads after readiness.
4. Quit app and confirm backend process exits.

Acceptance criteria:

- no `ECONNREFUSED 127.0.0.1:8000` during normal desktop launch
- user can reach the patient screen by launching a single app process

## Milestone 2: Stable backend packaging strategy

### Goal

Define and implement how the Python backend is distributed with the desktop app.

### Work

- choose runtime packaging strategy
- document dev-mode vs packaged-mode backend execution
- make packaged Tauri builds aware of backend runtime files

### Recommended initial approach

Bundle a Python runtime or a packaged backend artifact with the app rather than requiring the clinic machine to run `uv sync`.

This is the simplest path for the current architecture because the backend is already separated cleanly and should remain testable outside Tauri.

### Validation

Automated:

- build-time checks that required backend files are present in bundle inputs

Manual:

1. Build debug Tauri app.
2. Launch packaged app.
3. Verify API starts from packaged runtime, not from a dev shell.

Acceptance criteria:

- desktop build can run on a target machine without manual backend startup

## Milestone 3: Versioned schema and persistence hardening

### Goal

Move from ad hoc persistence to controlled schema evolution and stronger constraints.

### Work

- introduce Alembic
- create an initial migration for patients, sessions, and images
- replace `create_all()` bootstrapping with migration-driven startup
- add indexes and uniqueness constraints where appropriate
- formalize enum/string validation for:
  - laterality
  - image type
  - session status

### Validation

Automated:

- migration tests on an empty DB
- migration tests on an existing DB
- API tests against migrated schemas

Acceptance criteria:

- schema can be created and upgraded reproducibly
- API behavior does not depend on implicit model auto-creation

## Milestone 4: Storage integrity and thumbnails

### Goal

Make file storage reliable and browse-friendly.

### Work

- generate thumbnails on import
- store thumbnail paths or deterministic thumbnail naming
- capture richer metadata when possible:
  - width
  - height
  - mime type
  - hash
  - file size
- add an integrity scan command to find:
  - DB rows with missing files
  - files with no DB rows
  - thumbnail mismatches

### Implementation approach

- centralize all file import logic in the backend storage service
- treat DB insert + file copy + thumbnail generation as one transaction boundary
- on failure, roll back DB changes and delete partial files

### Validation

Automated:

- integration test for successful image import
- integration test for rollback on failed import
- integrity-scan tests using corrupted fixture data

Manual:

1. Import left and right images.
2. Verify originals and thumbnails exist on disk.
3. Verify UI renders the imported images after app restart.

Acceptance criteria:

- imported records always reference real files
- failures do not leave partial data behind

## Milestone 5: Session and image workflow refinement

### Goal

Align the data model and UI with the likely clinic workflow of multiple images per session.

### Work

- improve session editing
- support import of multiple images into one session cleanly
- make left/right eye comparison easier
- allow image metadata edits after import
- distinguish session notes from image notes clearly

### Validation

Automated:

- API integration tests for:
  - create patient
  - create session
  - import left image
  - import right image
  - fetch complete patient detail
- UI tests for bilateral import flow

Manual:

1. Create patient.
2. Create one session.
3. Import left eye image.
4. Import right eye image.
5. Reopen patient and confirm both images are attached to the same session.

Acceptance criteria:

- bilateral image import works naturally in a single session
- metadata remains explicit and editable

## Milestone 6: Frontend reliability and user experience

### Goal

Replace prototype-level fetch behavior with robust application UX.

### Work

- add a typed API client error layer
- improve loading, empty, and retry states
- introduce route structure or clearer state boundaries for:
  - patient list
  - patient detail
  - image viewer
- improve connectivity and backend-status messaging

### Validation

Automated:

- `vitest` component tests
- React Testing Library coverage for forms and error states
- mocked API tests for connection failure and validation errors

Acceptance criteria:

- UI errors are understandable and actionable
- app does not degrade into generic `request failed` states

## Milestone 7: Legacy import tooling

### Goal

Import data from `retina-racket-full/` in a controlled and inspectable way.

### Work

- implement a backend CLI importer
- read legacy SQLite database
- import patients into new schema
- import each legacy visit as a session + image, at least initially
- copy legacy image assets into managed storage
- read note text files into structured note fields
- preserve legacy IDs in metadata
- infer laterality from notes when possible
- emit an import report with warnings

### Known migration realities

- legacy data already contains missing asset references
- laterality is often only encoded in note text
- some legacy timestamps are display strings, not proper datetimes

### Validation

Automated:

- fixture-based import tests using the legacy sample dataset
- count comparisons between source and imported records
- warning assertions for missing assets
- laterality inference tests

Manual:

1. Run importer against the sample legacy dataset.
2. Open imported patients in the new UI.
3. Confirm imported sessions and image notes match source where files exist.

Acceptance criteria:

- importer is deterministic
- missing legacy files are reported, not silently dropped

## Milestone 8: Search and clinical workflow polish

### Goal

Make the application efficient for repeated clinic use.

### Work

- improve patient search
- add session date filtering
- add image filtering by laterality and type
- improve layout for reviewing image history

### Validation

Automated:

- API search tests
- UI tests for search and filtering behavior
- Playwright end-to-end tests for lookup workflows

Acceptance criteria:

- patient/session retrieval is fast and usable under realistic data volume

## Milestone 9: Audit and backup foundations

### Goal

Add minimal operational safety without overengineering.

### Work

- add an audit/event table for create/edit/import actions
- add backup/export command for DB plus managed files
- document restore assumptions

### Validation

Automated:

- tests for audit event creation
- tests for backup artifact generation

Manual:

1. Create/import records.
2. Run backup command.
3. Confirm expected files are included.

Acceptance criteria:

- critical write operations are traceable
- local backup path exists

## Milestone 10: Packaging and release workflow

### Goal

Make desktop builds reproducible and documented.

### Work

- finalize Tauri packaging configuration
- document build prerequisites
- add release scripts
- verify debug and release builds

### Validation

Automated:

- CI build steps when project is ready

Manual:

1. Build debug Tauri app.
2. Build release Tauri app.
3. Launch packaged app on a clean local account or machine.

Acceptance criteria:

- build process is documented and repeatable

## Testing strategy

## Backend testing

Frameworks:

- `pytest`
- `fastapi.testclient` or `httpx`

Coverage priorities:

- patient creation
- duplicate detection
- session creation
- left/right image import
- rollback on storage failure
- migration/import logic
- integrity scan behavior

## Frontend testing

Frameworks to add:

- `vitest`
- `@testing-library/react`
- `msw` for controlled API mocking

Coverage priorities:

- startup health gate
- patient creation form
- session creation form
- image import form
- backend-down and validation-error states

## End-to-end testing

Framework:

- `playwright`

Coverage priorities:

- create patient -> create session -> import image
- bilateral image flow
- reopen patient after reload
- search and selection workflow

Start with browser-based end-to-end tests against the real FastAPI backend and Vite UI before investing in Tauri desktop automation.

## Data and migration testing

Coverage priorities:

- legacy date parsing
- legacy timestamp parsing
- laterality inference from note text
- missing-file detection
- import count parity

## Validation gates per milestone

Each milestone should only be considered complete when all three are true:

1. Code implemented.
2. Automated tests added or updated.
3. Manual smoke checklist passed.

## Immediate next milestone recommendation

The next highest-value step is Milestone 1: single-launch desktop runtime.

Reason:

- it removes the current `ECONNREFUSED` experience
- it turns the project from a split dev prototype into a usable desktop app shape
- it creates the foundation for later packaging and validation work

## Suggested execution order

1. Milestone 1: single-launch desktop runtime
2. Milestone 2: stable backend packaging strategy
3. Milestone 3: versioned schema and persistence hardening
4. Milestone 4: storage integrity and thumbnails
5. Milestone 5: session and image workflow refinement
6. Milestone 6: frontend reliability and user experience
7. Milestone 7: legacy import tooling
8. Milestone 8: search and workflow polish
9. Milestone 9: audit and backup foundations
10. Milestone 10: packaging and release workflow

## Definition of success for the first production-capable version

The app should:

- launch as one desktop application
- manage its own backend locally
- create and search patients
- create sessions
- import left/right retinal images from the filesystem
- persist and display images reliably after restart
- preserve data locally with backup support
- import legacy data with clear warnings for missing assets
