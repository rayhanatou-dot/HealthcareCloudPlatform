import os

from sqlalchemy import select

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.role import Role
from app.models.user import User


ROLE_NAME = "Pharmacist"


def main() -> None:
    db = SessionLocal()

    try:
        username = os.getenv(
            "DEMO_PHARMACIST_USERNAME",
            "demo_pharmacist",
        )

        email = os.getenv(
            "DEMO_PHARMACIST_EMAIL",
            "demo.pharmacist@example.local",
        )

        password = os.getenv(
            "DEMO_PHARMACIST_PASSWORD"
        )

        if not password:
            raise RuntimeError(
                "DEMO_PHARMACIST_PASSWORD environment "
                "variable must be defined"
            )

        role = db.execute(
            select(Role).where(
                Role.name == ROLE_NAME
            )
        ).scalar_one_or_none()

        if role is None:
            raise RuntimeError(
                "Pharmacist role does not exist. "
                "Run the role bootstrap first."
            )

        existing_user = db.execute(
            select(User).where(
                User.username == username
            )
        ).scalar_one_or_none()

        if existing_user is not None:
            role_name = (
                existing_user.role.name
                if existing_user.role is not None
                else None
            )

            print(
                f"Demo pharmacist already exists: "
                f"{username}"
            )
            print(
                f"User ID: {existing_user.id}"
            )
            print(
                f"Role: {role_name}"
            )

            return

        user = User(
            username=username,
            email=email,
            hashed_password=hash_password(
                password
            ),
            full_name="Demo Pharmacist",
            is_active=True,
            role_id=role.id,
        )

        db.add(user)
        db.commit()
        db.refresh(user)

        role_name = (
            user.role.name
            if user.role is not None
            else None
        )

        print(
            "Demo pharmacist created successfully"
        )
        print(
            f"User ID: {user.id}"
        )
        print(
            f"Username: {user.username}"
        )
        print(
            f"Email: {user.email}"
        )
        print(
            f"Role: {role_name}"
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