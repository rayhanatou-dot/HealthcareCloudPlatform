from collections.abc import Callable

from fastapi import (
    Depends,
    HTTPException,
    Request,
    status,
)
from sqlalchemy.orm import Session

from app.api.dependencies.auth import (
    get_current_user,
)
from app.db.session import get_db
from app.models.user import User
from app.services.audit_service import audit_service


def require_roles(
    *allowed_roles: str,
) -> Callable[..., User]:
    """
    Create a FastAPI dependency that authorizes
    only users whose role is explicitly allowed.
    """

    if not allowed_roles:
        raise ValueError(
            "At least one allowed role must be defined"
        )

    allowed_role_names = set(
        allowed_roles
    )

    def role_dependency(
        request: Request,
        current_user: User = Depends(
            get_current_user
        ),
        db: Session = Depends(get_db),
    ) -> User:
        role_name = (
            current_user.role.name
            if current_user.role is not None
            else None
        )

        if role_name not in allowed_role_names:
            audit_service.safe_record_event(
                db,
                action="ACCESS_DENIED",
                outcome="DENIED",
                user_id=current_user.id,
                resource_type="Endpoint",
                resource_id=request.url.path,
                request=request,
                details={
                    "user_role": role_name,
                    "allowed_roles": sorted(
                        allowed_role_names
                    ),
                },
            )

            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "Insufficient permissions for "
                    "this operation"
                ),
            )

        return current_user

    return role_dependency