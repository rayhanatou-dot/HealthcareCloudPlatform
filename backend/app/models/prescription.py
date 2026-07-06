from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Prescription(Base):
    """
    Represents a structured prescription or medication-related
    data record managed by the Healthcare Cloud Platform.

    The model supports secure healthcare data management,
    multi-source ingestion, and a lightweight FHIR-inspired
    structure without claiming full FHIR compliance.
    """

    __tablename__ = "prescriptions"

    __table_args__ = (
        UniqueConstraint(
            "source_system",
            "external_id",
            name="uq_prescriptions_source_external_id",
        ),
        Index(
            "ix_prescriptions_patient_authored_at",
            "patient_id",
            "authored_at",
        ),
    )

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    patient_id: Mapped[int] = mapped_column(
        ForeignKey("patients.id"),
        nullable=False,
    )

    encounter_id: Mapped[int | None] = mapped_column(
        ForeignKey("encounters.id"),
        nullable=True,
        index=True,
    )

    prescriber_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
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

    medication_code: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    code_system: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    medication_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    dosage_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 6),
        nullable=True,
    )

    dosage_unit: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    frequency: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    route: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    instructions: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="active",
    )

    authored_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    start_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    end_date: Mapped[date | None] = mapped_column(
        Date,
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