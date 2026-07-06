from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Role(Base):
    """
    Represents a system role used for
    role-based access control.
    """

    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        index=True
    )

    name: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True
    )

    description: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True
    )

    users = relationship(
        "User",
        back_populates="role"
    )