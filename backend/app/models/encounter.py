from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Encounter(Base):
    """
    Represents a healthcare encounter or visit record
    managed by the Healthcare Cloud Platform.

    The model supports structured healthcare data
    management, multi-source ingestion, and a lightweight
    FHIR-inspired design without claiming full compliance.
    """

    __tablename__ = "encounters"

    __table_args__ = (
        UniqueConstraint(
            "source_system",
            "external_id",
            name="uq_encounters_source_external_id",
        ),
    )

    id: Mapped[int] = mapped_column(
    primary_key=True,
    )

    patient_id: Mapped[int] = mapped_column(
        ForeignKey("patients.id"),
        nullable=False,
        index=True,
    )

    external_id: Mapped[str | None] = mapped_column(
    String(100),
    nullable=True,
   )

    source_system: Mapped[str | None] = mapped_column(
    String(100),
    nullable=True,
    )

    encounter_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="active",
        index=True,
    )

    start_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    end_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    location: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )