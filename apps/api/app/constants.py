LATERALITY_VALUES = ("left", "right", "both", "unknown")
IMAGE_TYPE_VALUES = (
    "color_fundus",
    "red_free",
    "fluorescein",
    "autofluorescence",
    "oct",
    "external_photo",
    "other",
)
SESSION_STATUS_VALUES = ("draft", "completed")
SESSION_SOURCE_VALUES = ("filesystem_import", "legacy_import")
AUDIT_ACTION_VALUES = (
    "patient_created",
    "session_created",
    "session_updated",
    "image_imported",
    "image_updated",
    "legacy_import_completed",
    "backup_created",
)
AUDIT_ENTITY_VALUES = ("patient", "session", "image", "system", "backup")
AUDIT_SOURCE_VALUES = ("api", "legacy_import", "backup")
THUMBNAIL_MAX_DIMENSION = 480
IMAGE_ORIGINAL_ROOT = "images/original"
IMAGE_THUMBNAIL_ROOT = "images/thumbnail"
BACKUP_ROOT = "backups"
