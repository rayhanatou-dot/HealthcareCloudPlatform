from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    status,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies.rbac import require_roles
from app.db.session import get_db
from app.models.user import User
from app.schemas.patient import (
    PatientCreate,
    PatientListResponse,
    PatientResponse,
    PatientUpdate,
)
from app.services import (
    audit_service,
    patient_service,
)


router = APIRouter(
    prefix="/patients",
    tags=["Patients"],
)


@router.post(
    "",
    response_model=PatientResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_patient(
    payload: PatientCreate,
    request: Request,
    current_user: User = Depends(
        require_roles(
            "Admin",
            "Nurse",
            "Data Manager",
        )
    ),
    db: Session = Depends(get_db),
) -> PatientResponse:
    """
    Register a new patient.

    Access is restricted through RBAC.
    """

    try:
        patient = patient_service.create_patient(
            db,
            patient_data=payload.model_dump(),
        )

    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Patient conflicts with an existing "
                "medical record or external identifier"
            ),
        ) from exc

    audit_service.safe_record_event(
        db,
        action="PATIENT_CREATE",
        outcome="SUCCESS",
        user_id=current_user.id,
        resource_type="Patient",
        resource_id=patient.id,
        request=request,
        details={
            "medical_record_number": (
                patient.medical_record_number
            ),
            "source_system": (
                patient.source_system
            ),
        },
    )

    return PatientResponse.model_validate(
        patient
    )


@router.get(
    "",
    response_model=PatientListResponse,
    status_code=status.HTTP_200_OK,
)
def list_patients(
    request: Request,
    skip: int = Query(
        default=0,
        ge=0,
    ),
    limit: int = Query(
        default=50,
        ge=1,
        le=200,
    ),
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
) -> PatientListResponse:
    """
    Retrieve a paginated patient collection.
    """

    patients, total = (
        patient_service.list_patients(
            db,
            skip=skip,
            limit=limit,
        )
    )

    audit_service.safe_record_event(
        db,
        action="PATIENT_LIST",
        outcome="SUCCESS",
        user_id=current_user.id,
        resource_type="Patient",
        request=request,
        details={
            "skip": skip,
            "limit": limit,
            "returned_count": len(patients),
            "total": total,
        },
    )

    return PatientListResponse(
        total=total,
        skip=skip,
        limit=limit,
        items=[
            PatientResponse.model_validate(
                patient
            )
            for patient in patients
        ],
    )


@router.get(
    "/{patient_id}",
    response_model=PatientResponse,
    status_code=status.HTTP_200_OK,
)
def get_patient(
    patient_id: int,
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
) -> PatientResponse:
    """
    Retrieve one patient by identifier.
    """

    patient = patient_service.get_patient(
        db,
        patient_id=patient_id,
    )

    if patient is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient not found",
        )

    audit_service.safe_record_event(
        db,
        action="PATIENT_READ",
        outcome="SUCCESS",
        user_id=current_user.id,
        resource_type="Patient",
        resource_id=patient.id,
        request=request,
        details={
            "medical_record_number": (
                patient.medical_record_number
            ),
        },
    )

    return PatientResponse.model_validate(
        patient
    )


@router.patch(
    "/{patient_id}",
    response_model=PatientResponse,
    status_code=status.HTTP_200_OK,
)
def update_patient(
    patient_id: int,
    payload: PatientUpdate,
    request: Request,
    current_user: User = Depends(
        require_roles(
            "Admin",
            "Nurse",
            "Data Manager",
        )
    ),
    db: Session = Depends(get_db),
) -> PatientResponse:
    """
    Partially update an existing patient.
    """

    patient = patient_service.get_patient(
        db,
        patient_id=patient_id,
    )

    if patient is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient not found",
        )

    update_data = payload.model_dump(
        exclude_unset=True
    )

    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No patient fields supplied for update",
        )

    try:
        patient = patient_service.update_patient(
            db,
            patient=patient,
            update_data=update_data,
        )

    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Updated patient data conflicts with "
                "an existing database record"
            ),
        ) from exc

    audit_service.safe_record_event(
        db,
        action="PATIENT_UPDATE",
        outcome="SUCCESS",
        user_id=current_user.id,
        resource_type="Patient",
        resource_id=patient.id,
        request=request,
        details={
            "updated_fields": sorted(
                update_data.keys()
            ),
        },
    )

    return PatientResponse.model_validate(
        patient
    )