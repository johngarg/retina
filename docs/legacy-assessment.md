# Legacy Assessment

## Scope of the legacy app

The fuller legacy Racket application in `retina-racket-full/` is a small desktop GUI for:

- creating patients
- editing patient demographics
- loading an existing patient
- archiving a patient
- importing a single retinal image as a "visit"
- attaching free-text notes to that visit
- reopening prior visit images and notes

It is not a full clinical workflow system. It has no authentication, no audit trail, no structured eye laterality, no structured study/session concept, no thumbnail browser, and no robust file integrity handling.

## What the code actually stores

Legacy source files:

- `retina-racket-full/retina.rkt`
- `retina-racket-full/database.rkt`
- `retina-racket-full/patients.rkt`
- `retina-racket-full/dates.rkt`

SQLite schema in `retina-racket-full/database_dir/patient_database.sql`:

```sql
CREATE TABLE patients (
  patient_id INTEGER,
  firstname TEXT,
  lastname TEXT,
  dob TEXT,
  gender TEXT,
  archived INTEGER
);

CREATE TABLE visits (
  visit_id INTEGER,
  patient_id INTEGER,
  d TEXT,
  image_path TEXT,
  notes TEXT,
  archived INTEGER,
  FOREIGN KEY(patient_id) REFERENCES patients(patient_id)
);
```

Observed data directories:

- `retina-racket-full/database_dir/`
- `retina-racket-full/image_data_dir/`
- `retina-racket-full/text_data_dir/`

## Inferred domain model

### Patient

Fields proven by code and database:

- `patient_id`: random six-digit integer
- `firstname`: uppercased text
- `lastname`: uppercased text
- `dob`: string in `D/M/YYYY`
- `gender`: `"M"` or `"F"`
- `archived`: `0` or `1`

Validation/inference:

- patient names are normalized with trim + collapse whitespace + uppercase
- duplicate check is effectively `(firstname, lastname, dob, gender, archived=0)`
- archived patients are excluded from most queries

### Visit

The legacy "visit" is closer to a single imported image record than a true multi-image study/session.

Fields proven by code:

- `visit_id`: random seven-digit integer
- `patient_id`: foreign key to patient
- `d`: string timestamp in `t:H.M.S-d:D/M/YYYY`
- `image_path`: filename only, not full path
- `notes`: notes filename only, not inline note text
- `archived`: present in schema, but not meaningfully used in UI

### Notes and file storage

- image files are copied into `image_data_dir/`
- notes are stored in separate `.txt` files in `text_data_dir/`
- visit rows store filenames, not absolute paths

Filename convention:

- image: `<patient_id>_<visit_id>.<ext>`
- notes: `<patient_id>_<visit_id>.txt`

This convention is the main linkage between visit rows and the filesystem.

## User workflow inferred from code

1. Launch desktop GUI.
2. Connect directly to local SQLite database.
3. Create patient:
   - enter first name
   - enter last name
   - choose gender `M/F`
   - choose DOB from day/month/year dropdowns
4. Load patient from a list sorted by last name.
5. Review basic patient demographics.
6. Optionally edit patient demographics.
7. Create a new "visit":
   - choose a source image from filesystem
   - file is copied into app-managed image storage
   - image is opened externally via macOS `open`
   - operator types notes in a text box
   - on submit, notes are written to text storage and a visit row is inserted
8. Load prior visit:
   - select a prior visit row
   - app opens the stored image externally
   - app loads the paired text file into an editor
   - operator can save note changes back to disk
9. Archive patient:
   - sets patient `archived = 1`

## Left/right eye and image typing

There is no structured laterality field anywhere in schema or code.

However, sample notes in `retina-racket-full/text_data_dir/` clearly show operators used free-text notes to encode laterality:

- `Left eye`
- `Right eye`
- `L`
- `R`
- `This is the left eye.`
- `This is the right eye.`

Implication:

- the real workflow almost certainly expected separate left and right eye captures
- the legacy system failed to model that explicitly
- laterality must be promoted to first-class structured data in the rewrite

## Implicit assumptions preserved from the legacy app

- local-first storage is the default operating model
- image import from filesystem is the primary ingestion path
- patient IDs are local, app-generated identifiers
- a patient can have multiple visit/image records over time
- notes are associated with an image capture event
- archived patients should remain in the database but be hidden from routine workflows
- filenames encode both patient identity and visit identity

## Architectural problems in the legacy code

- UI, persistence, file copying, and domain logic are tightly coupled in one desktop script
- database schema uses no primary keys, no uniqueness constraints, and weak foreign key guarantees
- date/time fields are stored as display strings rather than typed timestamps
- laterality is unstructured and buried in notes
- one visit appears to support only one image
- notes are split into separate files instead of managed transactionally with the record
- image viewing depends on shelling out to `open`, which is macOS-specific
- paths assume a specific working directory layout
- random ID generation is ad hoc and race-prone
- there is no integrity check between DB rows and filesystem assets
- archive support exists only for patients, not fully for visits

## Migration risks discovered from real sample data

Observed integrity gaps:

- database row `visit_id=3144349` references missing notes file `308074_3144349.txt`
- database row `visit_id=9803550` references missing image `308074_9803550.09`
- the same row also references missing notes `308074_9803550.txt`

Additional risks:

- extension extraction is brittle and may mis-handle filenames with multiple dots
- parsing selected patient rows from display strings is fragile when names contain spaces
- patient duplicate logic treats gender as part of identity matching
- DOB format is locale-specific and string-based
- archived rows are filtered in application code, not enforced by query boundaries or views

## What is reusable vs discardable

Reusable as requirements/domain knowledge:

- patient demographic fields
- archive semantics
- one-to-many patient-to-visit relationship
- local filesystem import as core ingestion path
- filename convention `<patient_id>_<visit_id>`
- note-taking attached to captures
- need to browse prior captures for a patient

Discard or redesign:

- Racket GUI structure
- direct file/path handling inside UI event callbacks
- split notes-file storage model as the primary representation
- string timestamps and DOB storage
- laterality hidden in notes
- ad hoc random ID generation
- macOS-only image opening workflow

## Rewrite direction implied by the legacy app

The correct modernization is not a line-by-line port. The rewrite should:

- keep local-first storage
- keep patient and longitudinal capture history
- keep image import from filesystem
- introduce structured `Session` and `Image` entities
- make eye laterality explicit
- keep note editing and image browsing in the core workflow
- enforce database and filesystem integrity in one transactional service layer
