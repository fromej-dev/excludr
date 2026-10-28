"""Append-only audit trail service."""

from typing import Any, Optional

from sqlmodel import Session, select

from .models import AuditEvent

# Action names (kept in one place so callers and tests agree on them).
CRITERION_CREATED = "criterion.created"
CRITERION_UPDATED = "criterion.updated"
CRITERION_DELETED = "criterion.deleted"
DECISION_CREATED = "decision.created"
DECISION_UPDATED = "decision.updated"
DECISION_RESOLVED = "decision.resolved"
MEMBER_ADDED = "member.added"
MEMBER_ROLE_CHANGED = "member.role_changed"
MEMBER_REMOVED = "member.removed"
IMPORT_COMPLETED = "import.completed"
AI_BATCH_STARTED = "ai_batch.started"
AI_BATCH_FINISHED = "ai_batch.finished"
FULLTEXT_BATCH_STARTED = "fulltext_batch.started"
FULLTEXT_BATCH_FINISHED = "fulltext_batch.finished"
FULLTEXT_PDFS_UPLOADED = "fulltext.pdfs_uploaded"
EXPORT_CREATED = "export.created"
PROJECT_SETTINGS_UPDATED = "project.settings_updated"


def record_event(
    session: Session,
    project_id: int,
    action: str,
    entity_type: str,
    entity_id: Optional[int] = None,
    user_id: Optional[int] = None,
    details: Optional[dict[str, Any]] = None,
) -> AuditEvent:
    """Append an audit event and commit it.

    Args:
        session: Database session.
        project_id: Project the event belongs to.
        action: Dotted action name, e.g. ``"decision.created"``.
        entity_type: Kind of entity affected (``"criterion"``, ``"decision"``, ...).
        entity_id: Primary key of the affected entity, if any.
        user_id: Acting user; None for system actions.
        details: JSON-serialisable context (kept small and free of secrets).
    """
    event = AuditEvent(
        project_id=project_id,
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details,
    )
    session.add(event)
    session.commit()
    session.refresh(event)
    return event


def get_events_query(project_id: int):
    """Select statement for a project's events, newest first."""
    return (
        select(AuditEvent)
        .where(AuditEvent.project_id == project_id)
        .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
    )
