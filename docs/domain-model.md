# Domain Model

## Modeling goals

The legacy app treated each imported image as a "visit". That is too narrow for the rewrite because real retinal workflows typically involve:

- a patient
- one clinic session or study date
- one or more retinal images captured during that session
- explicit eye laterality
- optional notes and future analysis results

The rewrite should therefore separate `Patient`, `Session`, and `Image`.

## Core entities

### Patient

Represents the person being imaged.

Recommended fields:

- `id`: UUID or ULID primary key
- `legacy_patient_id`: nullable integer for imported Racket IDs
- `mrn`: nullable clinic medical record number
- `first_name`
- `last_name`
- `display_name`
- `date_of_birth`
- `sex_at_birth`: nullable enum if needed
- `gender_text`: nullable free text for compatibility
- `archived_at`: nullable timestamp
- `created_at`
- `updated_at`

Legacy-derived fields to preserve:

- legacy used `firstname`, `lastname`, `dob`, `gender`, `archived`

### Operator

Optional now, useful later.

- `id`
- `display_name`
- `initials`
- `role`
- `created_at`
- `updated_at`

### Session

Represents a patient encounter, visit, or study session. A session may contain multiple images.

- `id`
- `patient_id`
- `legacy_visit_group_key`: nullable for imported data if grouping is inferred later
- `captured_at`: nullable timestamp
- `session_date`: date
- `operator_id`: nullable
- `status`: enum such as `draft`, `completed`, `archived`
- `notes`: nullable session-level text
- `source`: enum such as `filesystem_import`, `camera_export`, `migration`
- `created_at`
- `updated_at`

Reasoning:

- legacy `visit` is better mapped to either a one-image session or to an image within a session
- a first pass can create one session per import event and allow multiple images later

### RetinalImage

Represents one imported retinal image file.

- `id`
- `session_id`
- `patient_id`
- `laterality`: enum `left`, `right`, `unknown`
- `image_type`: enum `color_fundus`, `red_free`, `fluorescein`, `other`, initially default `other`
- `captured_at`: nullable timestamp
- `imported_at`
- `original_filename`
- `stored_filename`
- `storage_relpath`
- `mime_type`
- `file_extension`
- `file_size_bytes`
- `sha256`
- `width_px`: nullable
- `height_px`: nullable
- `notes`: nullable text
- `legacy_visit_id`: nullable integer
- `legacy_notes_filename`: nullable text
- `legacy_image_filename`: nullable text
- `created_at`
- `updated_at`

### FileAsset

Optional abstraction if the system later stores derived files or analyses.

- `id`
- `owner_type`: e.g. `retinal_image`, `analysis_result`
- `owner_id`
- `kind`: e.g. `original_image`, `thumbnail`, `export`, `note_attachment`
- `storage_relpath`
- `mime_type`
- `file_size_bytes`
- `sha256`
- `created_at`

This can be deferred in code if premature, but the storage layout should leave room for it.

## Enumerations

### Laterality

- `left`
- `right`
- `both`
- `unknown`

For retinal images, `both` is usually less useful than separate images, but keeping it avoids schema churn.

### SessionStatus

- `draft`
- `completed`
- `archived`

### ImageSource

- `filesystem_import`
- `camera_export`
- `migration`

## Relationships

- one `Patient` has many `Session`
- one `Session` has many `RetinalImage`
- one `Operator` may have many `Session`
- one `RetinalImage` may have zero or many future analysis results

## Storage model

Database stores structured metadata.

Filesystem stores binary image assets and generated thumbnails.

Recommended relative storage layout:

```text
data/
  app.db
  images/
    original/
      YYYY/
        MM/
          <image-id>.<ext>
    thumbnails/
      <image-id>.jpg
  imports/
  backups/
```

Key rule:

- database rows should reference relative storage paths, never absolute machine-specific paths

## Validation rules inferred from legacy behavior

Keep:

- trim and normalize whitespace on patient names
- prevent accidental duplicate patient creation
- retain archive behavior instead of hard delete

Improve:

- laterality must be required for retinal images unless explicitly marked `unknown`
- session must belong to an existing patient
- imported file must exist and be copied atomically
- stored file hash should be computed
- DB write and file move/copy should be treated as one import transaction
- DOB should be stored as ISO date, not display string
- timestamps should be ISO 8601 / UTC-aware

## Legacy-to-new mapping

### Legacy patient row

Map to:

- `legacy_patient_id` -> `Patient.legacy_patient_id`
- `firstname` -> `Patient.first_name`
- `lastname` -> `Patient.last_name`
- `dob` -> parsed `Patient.date_of_birth`
- `gender` -> `Patient.gender_text` or mapped field
- `archived=1` -> `Patient.archived_at`

### Legacy visit row

Map to:

- `visit_id` -> `RetinalImage.legacy_visit_id`
- `patient_id` -> `Patient.legacy_patient_id` lookup
- `d` -> parsed best-effort `Session.captured_at` or `RetinalImage.captured_at`
- `image_path` -> `RetinalImage.legacy_image_filename`
- `notes` -> `RetinalImage.legacy_notes_filename`
- text file content -> `RetinalImage.notes`
- laterality -> inferred from notes when possible, else `unknown`

### Suggested import grouping rule

Initial migration rule:

- create one `Session` per legacy visit row

Rationale:

- it is lossless
- the legacy data does not contain enough structure to safely combine visits into multi-image sessions
- later sessions can be manually merged or grouped by patient/date in later tooling if needed
