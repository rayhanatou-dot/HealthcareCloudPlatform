import json
from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog


class AuditService:
    """
    Centralized service for recording security-relevant
    and healthcare-data access events.

    Sensitive values such as passwords, JWT tokens,
    authorization headers, and file contents must never
    be stored in audit details.
    """

    @staticmethod
    def _get_client_ip(
        request: Request | None,
    ) -> str | None:
        """
        Extract the client IP address from the request.
        """

        if request is None:
            return None

        forwarded_for = request.headers.get(
            "x-forwarded-for"
        )

        if forwarded_for:
            return (
                forwarded_for.split(",")[0].strip()
            )

        if request.client is not None:
            return request.client.host

        return None

    @staticmethod
    def _get_user_agent(
        request: Request | None,
    ) -> str | None:
        """
        Extract and limit the User-Agent value.
        """

        if request is None:
            return None

        user_agent = request.headers.get(
            "user-agent"
        )

        if not user_agent:
            return None

        return user_agent[:500]

    @staticmethod
    def _serialize_details(
        details: dict[str, Any] | None,
    ) -> str | None:
        """
        Serialize structured audit details as JSON text.
        """

        if details is None:
            return None

        return json.dumps(
            details,
            ensure_ascii=False,
            default=str,
            separators=(",", ":"),
        )

    def record_event(
        self,
        db: Session,
        *,
        action: str,
        outcome: str,
        user_id: int | None = None,
        resource_type: str | None = None,
        resource_id: str | int | None = None,
        request: Request | None = None,
        details: dict[str, Any] | None = None,
        commit: bool = True,
    ) -> AuditLog:
        """
        Persist an audit event in PostgreSQL.
        """

        if not action.strip():
            raise ValueError(
                "action must not be empty"
            )

        if not outcome.strip():
            raise ValueError(
                "outcome must not be empty"
            )

        audit_log = AuditLog(
            user_id=user_id,
            action=action.strip(),
            resource_type=(
                resource_type.strip()
                if resource_type
                else None
            ),
            resource_id=(
                str(resource_id)
                if resource_id is not None
                else None
            ),
            outcome=outcome.strip(),
            http_method=(
                request.method
                if request is not None
                else None
            ),
            endpoint=(
                request.url.path
                if request is not None
                else None
            ),
            ip_address=self._get_client_ip(
                request
            ),
            user_agent=self._get_user_agent(
                request
            ),
            details=self._serialize_details(
                details
            ),
        )

        db.add(audit_log)

        if commit:
            db.commit()
            db.refresh(audit_log)
        else:
            db.flush()

        return audit_log

    def safe_record_event(
        self,
        db: Session,
        *,
        action: str,
        outcome: str,
        user_id: int | None = None,
        resource_type: str | None = None,
        resource_id: str | int | None = None,
        request: Request | None = None,
        details: dict[str, Any] | None = None,
    ) -> AuditLog | None:
        """
        Attempt to record an audit event without causing
        the primary application operation to fail if the
        audit write itself encounters an error.
        """

        try:
            return self.record_event(
                db,
                action=action,
                outcome=outcome,
                user_id=user_id,
                resource_type=resource_type,
                resource_id=resource_id,
                request=request,
                details=details,
                commit=True,
            )

        except Exception:
            db.rollback()
            return None


audit_service = AuditService()