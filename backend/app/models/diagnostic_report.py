from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DiagnosticReport(Base):
    """
    Represents metadata for a diagnostic report managed by
    the Healthcare Cloud Platform.

    Structured metadata is stored in PostgreSQL, while the
    associated report object can be stored in MinIO.

    The design supports secure healthcare data management,
    multi-source ingestion, and a lightweight FHIR-inspired
    structure without claiming full FHIR compliance.
    """

    __tablename__ = "diagnostic_reports"

    __table_args__ = (
        UniqueConstraint(
            "source_system",
            "external_id",
            name="uq_diagnostic_reports_source_external_id",
        ),
        UniqueConstraint(
            "bucket_name",
            "object_key",
            name="uq_diagnostic_reports_bucket_object",
        ),
        Index(
            "ix_diagnostic_reports_patient_issued_at",
            "patient_id",
            "issued_at",
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

    uploaded_by_id: Mapped[int | None] = mapped_column(
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

    report_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="final",
    )

    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    conclusion: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    bucket_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    object_key: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
    )

    original_filename: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    content_type: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    file_size_bytes: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )

    checksum_sha256: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
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