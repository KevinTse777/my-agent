from __future__ import annotations

import logging
from typing import Any

from app.services.audit_store import get_audit_store

logger = logging.getLogger("app.audit")


def record_audit_event(
    *,
    event_type: str,
    user_id: str | None,
    event_payload: dict[str, Any] | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    payload = dict(event_payload or {})
    event = get_audit_store().create_event(
        user_id=user_id,
        event_type=event_type,
        event_payload=payload,
        request_id=request_id,
    )
    logger.info(
        "audit_event=true event_type=%s user_id=%s request_id=%s",
        event_type,
        user_id,
        request_id,
    )
    return event
