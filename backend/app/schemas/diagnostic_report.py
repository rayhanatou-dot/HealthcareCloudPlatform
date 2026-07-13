from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DiagnosticReportResponse(BaseModel):
    """
    Public API representation of a diagnostic report.
    """

    model_config = ConfigDict(
        from_attributes=True
    )

    id: int
    patient_id: int
    encounter_id: int | None

    external_id: str | None
    source_system: str | None

    report_type: str
    status: str
    title: str
    conclusion: str | None

    original_filename: str | None
    content_type: str | None
    file_size_bytes: int | None
    checksum_sha256: str | None

    issued_at: datetime
    created_at: datetime
    updated_at: datetime