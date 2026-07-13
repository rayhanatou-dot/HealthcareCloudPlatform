import os

from sqlalchemy import select

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.role import Role
from app.models.user import User


DEMO_PASSWORD = os.getenv(
    "DEMO_ADMIN_PASSWORD",
    "ChangeMe123!",
)


DEMO_USERS = [
    {
        "username": "demo_doctor",
        "email": "demo.doctor@example.local",
        "full_name": "Demo Doctor",
        "role_name": "Doctor",
    },
    {
        "username": "demo_nurse",
        "email": "demo.nurse@example.local",
        "full_name": "Demo Nurse",
        "role_name": "Nurse",
    },
    {
        "username": "demo_lab_staff",
        "email": "demo.labstaff@example.local",
        "full_name": "Demo Lab Staff",
        "role_name": "Lab Staff",
    },
    {
        "username": "demo_pharmacist",
        "email": "demo.pharmacist@example.local",
        "full_name": "Demo Pharmacist",
        "role_name": "Pharmacist",
    },
    {
        "username": "demo_data_manager",
        "email": "demo.datamanager@example.local",
        "full_name": "Demo Data Manager",
        "role_name": "Data Manager",
    },
]


def get_or_create_role(
    db,
    role_name: str,
) -> Role:
    role = db.scalar(
        select(Role).where(
            Role.name == role_name
        )
    )

    if role is not None:
        return role

    role = Role(
        name=role_name,
        description=f"Demo {role_name} role",
    )

    db.add(role)
    db.commit()
    db.refresh(role)

    return role


def get_or_create_user(
    db,
    user_data: dict,
) -> User:
    role = get_or_create_role(
        db=db,
        role_name=user_data["role_name"],
    )

    user = db.scalar(
        select(User).where(
            User.username == user_data["username"]
        )
    )

    password_hash = hash_password(
        DEMO_PASSWORD
    )

    if user is not None:
        user.role_id = role.id
        user.email = user_data["email"]
        user.full_name = user_data["full_name"]
        user.hashed_password = password_hash
        user.is_active = True

        db.add(user)
        db.commit()
        db.refresh(user)

        return user

    user = User(
        username=user_data["username"],
        email=user_data["email"],
        full_name=user_data["full_name"],
        hashed_password=password_hash,
        is_active=True,
        role_id=role.id,
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return user


def main():
    db = SessionLocal()

    try:
        for user_data in DEMO_USERS:
            user = get_or_create_user(
                db=db,
                user_data=user_data,
            )

            print(
                f"User ready: {user.username} "
                f"role={user_data['role_name']}"
            )

    finally:
        db.close()


if __name__ == "__main__":
    main()