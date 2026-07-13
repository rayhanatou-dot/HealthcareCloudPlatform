from datetime import datetime
from hashlib import sha256
from urllib.parse import quote

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies.rbac import require_roles
from app.db.session import get_db
from app.models.diagnostic_report import DiagnosticReport
from app.models.encounter import Encounter
from app.models.patient import Patient
from app.models.user import User
from app.schemas.diagnostic_report import (
    DiagnosticReportResponse,
)
from app.services import (
    audit_service,
    diagnostic_report_service,
    storage_service,
)


router = APIRouter(
    prefix="/diagnostic-reports",
    tags=["Diagnostic Reports"],
)


MAX_REPORT_SIZE_BYTES = 10 * 1024 * 1024


ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "text/plain",
    "image/jpeg",
    "image/png",
}


@router.post(
    "",
    response_model=DiagnosticReportResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_diagnostic_report(
    request: Request,
    patient_id: int = Form(...),
    report_type: str = Form(...),
    title: str = Form(...),
    issued_at: datetime = Form(...),
    file: UploadFile = File(...),
    encounter_id: int | None = Form(None),
    external_id: str | None = Form(None),
    source_system: str | None = Form(None),
    report_status: str = Form("final"),
    conclusion: str | None = Form(None),
    current_user: User = Depends(
        require_roles(
            "Admin",
            "Doctor",
            "Lab Staff",
        )
    ),
    db: Session = Depends(get_db),
) -> DiagnosticReportResponse:
    """
    Upload a diagnostic report to MinIO and persist
    its structured metadata in PostgreSQL.

    Access is restricted through RBAC.
    A successful upload is recorded in the audit log.
    """

    patient = db.get(
        Patient,
        patient_id,
    )

    if patient is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient not found",
        )

    if encounter_id is not None:
        encounter = db.get(
            Encounter,
            encounter_id,
        )

        if encounter is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Encounter not found",
            )

        if encounter.patient_id != patient_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Encounter does not belong "
                    "to the specified patient"
                ),
            )

    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file must have a filename",
        )

    content_type = (
        file.content_type
        or "application/octet-stream"
    )

    if content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=(
                status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
            ),
            detail=(
                "Unsupported file type. "
                f"Allowed types: "
                f"{sorted(ALLOWED_CONTENT_TYPES)}"
            ),
        )

    file_data = await file.read(
        MAX_REPORT_SIZE_BYTES + 1
    )

    if not file_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty",
        )

    if len(file_data) > MAX_REPORT_SIZE_BYTES:
        raise HTTPException(
            status_code=(
                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
            ),
            detail=(
                "File exceeds the maximum allowed "
                "size of 10 MB"
            ),
        )

    try:
        report = (
            diagnostic_report_service.create_report(
                db,
                patient_id=patient_id,
                encounter_id=encounter_id,
                uploaded_by_id=current_user.id,
                report_type=report_type,
                title=title,
                issued_at=issued_at,
                original_filename=file.filename,
                content_type=content_type,
                data=file_data,
                external_id=external_id,
                source_system=source_system,
                status=report_status,
                conclusion=conclusion,
            )
        )

        audit_service.safe_record_event(
            db,
            action="REPORT_UPLOAD",
            outcome="SUCCESS",
            user_id=current_user.id,
            resource_type="DiagnosticReport",
            resource_id=report.id,
            request=request,
            details={
                "patient_id": report.patient_id,
                "encounter_id": report.encounter_id,
                "report_type": report.report_type,
                "file_size_bytes": (
                    report.file_size_bytes
                ),
                "content_type": report.content_type,
            },
        )

        return DiagnosticReportResponse.model_validate(
            report
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Diagnostic report conflicts "
                "with an existing database record"
            ),
        ) from exc

    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "Unable to persist the diagnostic "
                "report in the storage layer"
            ),
        ) from exc

    finally:
        await file.close()


@router.get(
    "/{report_id}",
    response_model=DiagnosticReportResponse,
    status_code=status.HTTP_200_OK,
)
def get_diagnostic_report(
    report_id: int,
    request: Request,
    current_user: User = Depends(
        require_roles(
            "Admin",
            "Doctor",
            "Nurse",
            "Lab Staff",
            "Data Manager",
        )
    ),
    db: Session = Depends(get_db),
) -> DiagnosticReportResponse:
    """
    Retrieve structured diagnostic-report metadata
    from PostgreSQL.

    A successful metadata access is recorded
    in the audit log.
    """

    report = db.get(
        DiagnosticReport,
        report_id,
    )

    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Diagnostic report not found",
        )

    audit_service.safe_record_event(
        db,
        action="REPORT_READ",
        outcome="SUCCESS",
        user_id=current_user.id,
        resource_type="DiagnosticReport",
        resource_id=report.id,
        request=request,
        details={
            "patient_id": report.patient_id,
            "encounter_id": report.encounter_id,
            "report_type": report.report_type,
        },
    )

    return DiagnosticReportResponse.model_validate(
        report
    )


@router.get(
    "/{report_id}/download",
    status_code=status.HTTP_200_OK,
)
def download_diagnostic_report(
    report_id: int,
    request: Request,
    current_user: User = Depends(
        require_roles(
            "Admin",
            "Doctor",
            "Nurse",
            "Lab Staff",
        )
    ),
    db: Session = Depends(get_db),
) -> Response:
    """
    Download a diagnostic-report object through
    the FastAPI backend.

    MinIO remains private and is not exposed
    directly to the client.

    SHA-256 integrity is verified before the
    file is returned.

    A successful download is recorded
    in the audit log.
    """

    report = db.get(
        DiagnosticReport,
        report_id,
    )

    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Diagnostic report not found",
        )

    try:
        file_data = storage_service.download_bytes(
            report.object_key
        )

    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "Unable to retrieve the diagnostic "
                "report from object storage"
            ),
        ) from exc

    integrity_verified = False

    if report.checksum_sha256:
        actual_checksum = sha256(
            file_data
        ).hexdigest()

        if actual_checksum != report.checksum_sha256:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Stored diagnostic report failed "
                    "SHA-256 integrity verification"
                ),
            )

        integrity_verified = True

    filename = (
        report.original_filename
        or f"diagnostic-report-{report.id}.bin"
    )

    encoded_filename = quote(
        filename,
        safe="",
    )

    content_type = (
        report.content_type
        or "application/octet-stream"
    )

    audit_service.safe_record_event(
        db,
        action="REPORT_DOWNLOAD",
        outcome="SUCCESS",
        user_id=current_user.id,
        resource_type="DiagnosticReport",
        resource_id=report.id,
        request=request,
        details={
            "patient_id": report.patient_id,
            "encounter_id": report.encounter_id,
            "report_type": report.report_type,
            "file_size_bytes": (
                report.file_size_bytes
            ),
            "content_type": report.content_type,
            "integrity_verified": integrity_verified,
        },
    )

    return Response(
        content=file_data,
        media_type=content_type,
        headers={
            "Content-Disposition": (
                "attachment; "
                f"filename*=UTF-8''{encoded_filename}"
            ),
            "X-Content-SHA256": (
                report.checksum_sha256
                or ""
            ),
        },
    )