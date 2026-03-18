from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

from sqlalchemy.orm import Session

from .models import AuditEvent


def serialize_audit_value(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def log_audit_event(
    db: Session,
    *,
    action: str,
    entity_type: str,
    entity_id: str | None,
    source: str,
    summary: str,
    patient_id: str | None = None,
    session_id: str | None = None,
    image_id: str | None = None,
    actor_name: str | None = None,
    payload: dict[str, Any] | None = None,
) -> AuditEvent:
    event = AuditEvent(
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        patient_id=patient_id,
        session_id=session_id,
        image_id=image_id,
        source=source,
        actor_name=actor_name,
        summary=summary,
        payload_json=(
            json.dumps(payload, sort_keys=True, default=serialize_audit_value)
            if payload is not None
            else None
        ),
    )
    db.add(event)
    return event
