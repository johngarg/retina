# Migration Plan

## Goals

- preserve legacy domain concepts that are real
- avoid porting legacy implementation choices
- ship a maintainable local-first rewrite quickly
- validate behavior against legacy data and workflows

## What to extract from `retina-racket-full/`

Extract as requirements and sample data:

- patient fields: first name, last name, DOB, gender, archived
- visit/image linkage: one patient has many captures over time
- local import-first workflow
- filename convention `<patient_id>_<visit_id>.*`
- notes paired with image imports
- archive semantics
- list/browse/edit patient workflow

Extract as migration inputs:

- `database_dir/patient_database.db`
- `image_data_dir/`
- `text_data_dir/`

Do not preserve as architecture:

- Racket GUI event structure
- string parsing of display rows
- text file note storage as the system of record
- macOS `open` shell commands

## Parity definition

For the first rewrite, parity should mean:

- can create a patient
- can browse/search patients
- can open a patient detail page
- can create a session for that patient
- can import at least one retinal image into that session
- can assign laterality explicitly
- can persist notes with the image record
- can browse prior imported images and open a full view

It does not need to preserve:

- legacy UI layout
- exact ID format
- external default image opening behavior
- notes as separate filesystem text files

## Recommended migration stages

### Stage 1: Documentation and reverse engineering

- document the legacy schema and workflow
- capture unknowns explicitly
- identify broken/missing legacy sample references

### Stage 2: New scaffold

- create `apps/api`
- create `apps/desktop`
- create shared docs and root README
- establish app data layout

### Stage 3: Core backend domain

- define SQLAlchemy models
- add Alembic-ready migration support
- implement storage service
- implement patient/session/image CRUD

### Stage 4: Vertical slice UI

- patient list
- patient creation
- session creation
- image import
- image browse/view

### Stage 5: Legacy import utility

- read legacy SQLite
- match/import patients
- import image and note files when present
- mark missing assets explicitly
- infer laterality from notes heuristically when possible

### Stage 6: Hardening

- tests
- backup/export commands
- validation improvements
- packaging

## Legacy data import strategy

### Patients

For each legacy patient row:

- parse DOB from `D/M/YYYY`
- preserve original numeric patient ID as `legacy_patient_id`
- preserve archived state

### Visits

For each legacy visit row:

- create one session per legacy visit
- create one retinal image under that session
- copy image if present
- inline note text from corresponding `.txt` file if present
- if image or notes are missing, keep the record and mark import warnings

### Laterality inference

Best-effort heuristics from note text:

- `"left"`, `"l eye"`, `"os"` -> `left`
- `"right"`, `"r eye"`, `"od"` -> `right`
- otherwise -> `unknown`

This inference must be marked as inferred, not guaranteed.

## Tests to write first

### Backend unit tests

- patient name normalization
- duplicate patient detection rules
- DOB parsing from legacy format
- visit timestamp parsing from legacy format
- laterality inference from note text
- managed file naming and collision handling

### Backend integration tests

- create patient
- create session
- import left and right images
- persist and retrieve notes
- generate browseable image lists for a patient
- reject import when patient/session does not exist
- handle missing source file cleanly

### Migration tests

- import sample legacy DB rows
- verify counts of imported patients and visits
- verify missing-asset rows are reported
- verify legacy filenames are preserved in metadata

### UI tests

- create patient flow
- create session flow
- import image flow
- patient search/filter
- image viewer route renders selected image

## Known unknowns to keep explicit

- actual Canon CR6-45NM export naming conventions
- whether a real clinic session usually contains multiple images per eye
- whether operators need additional patient identifiers such as MRN
- whether notes belong at session level, image level, or both
- whether any regulated audit-trail requirement applies in deployment

## Success criteria for the first milestone

- rewrite runs locally with SQLite-backed persistence
- user can complete the core workflow without touching legacy code
- docs explain how legacy concepts were mapped
- sample legacy data can be reasoned about and partially imported later
