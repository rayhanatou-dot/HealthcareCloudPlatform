import os

from sqlalchemy import select

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.role import Role
from app.models.user import User


ROLE_NAMES = [
    "Admin",
    "Doctor",
    "Nurse",
    "Lab Staff",
    "Pharmacist",
    "Data Manager",
]


def ensure_roles(db) -> dict[str, Role]:
    """
    Create the application roles when they do not
    already exist.
    """

    roles: dict[str, Role] = {}

    for role_name in ROLE_NAMES:
        role = db.execute(
            select(Role).where(
                Role.name == role_name
            )
        ).scalar_one_or_none()

        if role is None:
            role = Role(
                name=role_name,
                description=(
                    f"{role_name} role for the "
                    "healthcare cloud platform"
                ),
            )

            db.add(role)
            db.flush()

            print(
                f"Role created: {role_name}"
            )
        else:
            print(
                f"Role already exists: {role_name}"
            )

        roles[role_name] = role

    return roles


def create_demo_admin(
    db,
    roles: dict[str, Role],
) -> User:
    """
    Create a demonstration administrator account
    using a bcrypt password hash.
    """

    username = os.getenv(
        "DEMO_ADMIN_USERNAME",
        "demo_admin",
    )

    email = os.getenv(
        "DEMO_ADMIN_EMAIL",
        "demo.admin@example.local",
    )

    password = os.getenv(
        "DEMO_ADMIN_PASSWORD"
    )

    if not password:
        raise RuntimeError(
            "DEMO_ADMIN_PASSWORD environment variable "
            "must be defined"
        )

    existing_user = db.execute(
        select(User).where(
            User.username == username
        )
    ).scalar_one_or_none()

    if existing_user is not None:
        print(
            f"Demo user already exists: {username}"
        )

        return existing_user

    user = User(
        username=username,
        email=email,
        hashed_password=hash_password(
            password
        ),
        full_name="Demo Administrator",
        is_active=True,
        role_id=roles["Admin"].id,
    )

    db.add(user)
    db.flush()

    print(
        f"Demo user created: {username}"
    )

    return user


def main() -> None:
    db = SessionLocal()

    try:
        roles = ensure_roles(
            db
        )

        user = create_demo_admin(
            db,
            roles,
        )

        db.commit()
        db.refresh(user)

        print("Bootstrap completed successfully")
        print(f"User ID: {user.id}")
        print(f"Username: {user.username}")
        print(f"Email: {user.email}")
        print(
            f"Role: "
            f"{user.role.name if user.role else None}"
        )
        print(
            f"Active: {user.is_active}"
        )

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


if __name__ == "__main__":
    main()