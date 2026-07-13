import re
from datetime import datetime
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.diagnostic_report import DiagnosticReport
from app.services.storage_service import (
    StorageService,
    storage_service,
)


class DiagnosticReportService:
    """
    Coordinates diagnostic-report persistence across
    PostgreSQL and MinIO object storage.

    PostgreSQL stores structured report metadata, while
    MinIO stores the associated binary object.

    If object upload succeeds but database persistence
    fails, compensating cleanup removes the uploaded object.
    """

    def __init__(
        self,
        storage: StorageService = storage_service,
    ) -> None:
        self.storage = storage

    @staticmethod
    def _sanitize_filename(
        filename: str,
    ) -> str:
        """
        Sanitize a user-provided filename before including
        it in a MinIO object key.
        """
        filename = filename.replace("\\", "/")
        filename = filename.split("/")[-1].strip()

        filename = re.sub(
            r"[^A-Za-z0-9._-]",
            "_",
            filename,
        )

        return filename or "report.bin"

    def _build_object_key(
        self,
        patient_id: int,
        original_filename: str,
    ) -> str:
        """
        Generate a unique and structured MinIO object key.
        """
        safe_filename = self._sanitize_filename(
            original_filename
        )

        unique_id = uuid4().hex

        return (
            f"patients/{patient_id}/"
            f"diagnostic-reports/"
            f"{unique_id}-{safe_filename}"
        )

    def create_report(
        self,
        db: Session,
        *,
        patient_id: int,
        report_type: str,
        title: str,
        issued_at: datetime,
        original_filename: str,
        content_type: str,
        data: bytes,
        encounter_id: int | None = None,
        uploaded_by_id: int | None = None,
        external_id: str | None = None,
        source_system: str | None = None,
        status: str = "final",
        conclusion: str | None = None,
    ) -> DiagnosticReport:
        """
        Upload a diagnostic-report object to MinIO and
        persist its structured metadata in PostgreSQL.

        If database persistence fails after object upload,
        the uploaded MinIO object is removed as a
        compensating cleanup operation.
        """

        if patient_id <= 0:
            raise ValueError(
                "patient_id must be greater than zero"
            )

        if not report_type.strip():
            raise ValueError(
                "report_type must not be empty"
            )

        if not title.strip():
            raise ValueError(
                "title must not be empty"
            )

        if not original_filename.strip():
            raise ValueError(
                "original_filename must not be empty"
            )

        if not content_type.strip():
            raise ValueError(
                "content_type must not be empty"
            )

        if not data:
            raise ValueError(
                "data must not be empty"
            )

        object_key = self._build_object_key(
            patient_id=patient_id,
            original_filename=original_filename,
        )

        object_uploaded = False
        database_committed = False

        try:
            storage_metadata = self.storage.upload_bytes(
                object_key=object_key,
                data=data,
                content_type=content_type,
            )

            object_uploaded = True

            report = DiagnosticReport(
                patient_id=patient_id,
                encounter_id=encounter_id,
                uploaded_by_id=uploaded_by_id,
                external_id=external_id,
                source_system=source_system,
                report_type=report_type,
                status=status,
                title=title,
                conclusion=conclusion,
                bucket_name=str(
                    storage_metadata["bucket_name"]
                ),
                object_key=str(
                    storage_metadata["object_key"]
                ),
                original_filename=original_filename,
                content_type=str(
                    storage_metadata["content_type"]
                ),
                file_size_bytes=int(
                    storage_metadata["file_size_bytes"]
                ),
                checksum_sha256=str(
                    storage_metadata["checksum_sha256"]
                ),
                issued_at=issued_at,
            )

            db.add(report)

            # Force SQL execution before commit so database
            # constraint failures are detected here.
            db.flush()

            db.commit()
            database_committed = True

            return report

        except Exception as exc:
            if not database_committed:
                db.rollback()

                if object_uploaded:
                    try:
                        self.storage.delete_object(
                            object_key
                        )

                    except Exception as cleanup_exc:
                        raise RuntimeError(
                            "Diagnostic report persistence failed "
                            "and compensating MinIO cleanup also "
                            "failed. "
                            f"Cleanup error: {cleanup_exc}"
                        ) from exc

            raise


diagnostic_report_service = DiagnosticReportService()