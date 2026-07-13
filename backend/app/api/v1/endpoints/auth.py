from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    status,
)
from fastapi.security import (
    OAuth2PasswordRequestForm,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies.auth import (
    get_current_user,
)
from app.core.security import (
    create_access_token,
    verify_password,
)
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import (
    CurrentUserResponse,
    TokenResponse,
)
from app.services.audit_service import audit_service


router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


@router.post(
    "/login",
    response_model=TokenResponse,
)
def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
) -> TokenResponse:
    """
    Authenticate a user and issue a JWT access token.
    """

    user = db.execute(
        select(User).where(
            User.username == form_data.username
        )
    ).scalar_one_or_none()

    if user is None:
        audit_service.safe_record_event(
            db,
            action="LOGIN_FAILED",
            outcome="FAILURE",
            request=request,
            details={
                "username": form_data.username,
                "reason": "unknown_user",
            },
        )

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={
                "WWW-Authenticate": "Bearer"
            },
        )

    if not verify_password(
        form_data.password,
        user.hashed_password,
    ):
        audit_service.safe_record_event(
            db,
            action="LOGIN_FAILED",
            outcome="FAILURE",
            user_id=user.id,
            resource_type="User",
            resource_id=user.id,
            request=request,
            details={
                "username": user.username,
                "reason": "invalid_password",
            },
        )

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={
                "WWW-Authenticate": "Bearer"
            },
        )

    if not user.is_active:
        audit_service.safe_record_event(
            db,
            action="LOGIN_FAILED",
            outcome="DENIED",
            user_id=user.id,
            resource_type="User",
            resource_id=user.id,
            request=request,
            details={
                "username": user.username,
                "reason": "inactive_account",
            },
        )

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user account",
        )

    role_name = (
        user.role.name
        if user.role is not None
        else None
    )

    access_token = create_access_token(
        subject=str(user.id),
        extra_claims={
            "username": user.username,
            "role": role_name,
        },
    )

    audit_service.safe_record_event(
        db,
        action="LOGIN_SUCCESS",
        outcome="SUCCESS",
        user_id=user.id,
        resource_type="User",
        resource_id=user.id,
        request=request,
        details={
            "username": user.username,
            "role": role_name,
        },
    )

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
    )


@router.get(
    "/me",
    response_model=CurrentUserResponse,
)
def read_current_user(
    current_user: User = Depends(
        get_current_user
    ),
) -> CurrentUserResponse:
    """
    Return the currently authenticated user.
    """

    role_name = (
        current_user.role.name
        if current_user.role is not None
        else None
    )

    return CurrentUserResponse(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        full_name=current_user.full_name,
        is_active=current_user.is_active,
        role=role_name,
    )