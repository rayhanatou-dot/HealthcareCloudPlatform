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
from app.models.encounter import Encounter
from app.models.patient import Patient
from app.models.user import User
from app.schemas.prescription import (
    PrescriptionCreate,
    PrescriptionListResponse,
    PrescriptionResponse,
    PrescriptionUpdate,
)
from app.services.audit_service import audit_service
from app.services.prescription_service import prescription_service


prescriptions_router = APIRouter(
    prefix="/prescriptions",
    tags=["Prescriptions"],
)


def validate_patient_exists(
    db: Session,
    patient_id: int,
) -> Patient:
    patient = db.get(
        Patient,
        patient_id,
    )

    if patient is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient not found",
        )

    return patient


def validate_encounter_belongs_to_patient(
    db: Session,
    encounter_id: int | None,
    patient_id: int,
) -> Encounter | None:
    if encounter_id is None:
        return None

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
                "Encounter does not belong to the "
                "specified patient"
            ),
        )

    return encounter


def validate_prescriber_exists(
    db: Session,
    prescriber_id: int,
) -> User:
    prescriber = db.get(
        User,
        prescriber_id,
    )

    if prescriber is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prescriber not found",
        )

    if not prescriber.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Prescriber account is inactive",
        )

    return prescriber


@prescriptions_router.post(
    "",
    response_model=PrescriptionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_prescription(
    payload: PrescriptionCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(
            "Admin",
            "Doctor",
        )
    ),
):
    validate_patient_exists(
        db=db,
        patient_id=payload.patient_id,
    )

    validate_encounter_belongs_to_patient(
        db=db,
        encounter_id=payload.encounter_id,
        patient_id=payload.patient_id,
    )

    validate_prescriber_exists(
        db=db,
        prescriber_id=payload.prescriber_id,
    )

    try:
        prescription = prescription_service.create_prescription(
            db=db,
            prescription_data=payload.model_dump(),
        )

    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Prescription conflicts with an existing record"
            ),
        )

    audit_service.safe_record_event(
        db=db,
        action="PRESCRIPTION_CREATE",
        outcome="SUCCESS",
        user_id=current_user.id,
        resource_type="Prescription",
        resource_id=str(prescription.id),
        request=request,
        details={
            "patient_id": prescription.patient_id,
            "encounter_id": prescription.encounter_id,
            "prescriber_id": prescription.prescriber_id,
            "medication_name": prescription.medication_name,
            "dosage_amount": (
                str(prescription.dosage_amount)
                if prescription.dosage_amount is not None
                else None
            ),
            "dosage_unit": prescription.dosage_unit,
            "status": prescription.status,
        },
    )

    return prescription


@prescriptions_router.get(
    "",
    response_model=PrescriptionListResponse,
)
def list_prescriptions(
    request: Request,
    skip: int = Query(
        default=0,
        ge=0,
    ),
    limit: int = Query(
        default=100,
        ge=1,
        le=500,
    ),
    patient_id: int | None = Query(
        default=None,
        gt=0,
    ),
    encounter_id: int | None = Query(
        default=None,
        gt=0,
    ),
    prescriber_id: int | None = Query(
        default=None,
        gt=0,
    ),
    prescription_status: str | None = Query(
        default=None,
        max_length=50,
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(
            "Admin",
            "Doctor",
            "Nurse",
            "Pharmacist",
            "Data Manager",
        )
    ),
):
    if patient_id is not None:
        validate_patient_exists(
            db=db,
            patient_id=patient_id,
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

        if (
            patient_id is not None
            and encounter.patient_id != patient_id
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Encounter does not belong to the "
                    "specified patient"
                ),
            )

    if prescriber_id is not None:
        validate_prescriber_exists(
            db=db,
            prescriber_id=prescriber_id,
        )

    total, prescriptions = (
        prescription_service.list_prescriptions(
            db=db,
            skip=skip,
            limit=limit,
            patient_id=patient_id,
            encounter_id=encounter_id,
            prescriber_id=prescriber_id,
            status=prescription_status,
        )
    )

    audit_service.safe_record_event(
        db=db,
        action="PRESCRIPTION_LIST",
        outcome="SUCCESS",
        user_id=current_user.id,
        resource_type="Prescription",
        resource_id=None,
        request=request,
        details={
            "skip": skip,
            "limit": limit,
            "patient_id": patient_id,
            "encounter_id": encounter_id,
            "prescriber_id": prescriber_id,
            "status": prescription_status,
            "returned_count": len(prescriptions),
            "total": total,
        },
    )

    return PrescriptionListResponse(
        total=total,
        skip=skip,
        limit=limit,
        items=prescriptions,
    )


@prescriptions_router.get(
    "/{prescription_id}",
    response_model=PrescriptionResponse,
)
def get_prescription(
    prescription_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(
            "Admin",
            "Doctor",
            "Nurse",
            "Pharmacist",
            "Data Manager",
        )
    ),
):
    prescription = prescription_service.get_prescription(
        db=db,
        prescription_id=prescription_id,
    )

    if prescription is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prescription not found",
        )

    audit_service.safe_record_event(
        db=db,
        action="PRESCRIPTION_READ",
        outcome="SUCCESS",
        user_id=current_user.id,
        resource_type="Prescription",
        resource_id=str(prescription.id),
        request=request,
        details={
            "patient_id": prescription.patient_id,
            "encounter_id": prescription.encounter_id,
            "prescriber_id": prescription.prescriber_id,
        },
    )

    return prescription


@prescriptions_router.patch(
    "/{prescription_id}",
    response_model=PrescriptionResponse,
)
def update_prescription(
    prescription_id: int,
    payload: PrescriptionUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(
            "Admin",
            "Doctor",
            "Pharmacist",
        )
    ),
):
    prescription = prescription_service.get_prescription(
        db=db,
        prescription_id=prescription_id,
    )

    if prescription is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prescription not found",
        )

    update_data = payload.model_dump(
        exclude_unset=True
    )

    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No update fields supplied",
        )

    if "encounter_id" in update_data:
        validate_encounter_belongs_to_patient(
            db=db,
            encounter_id=update_data["encounter_id"],
            patient_id=prescription.patient_id,
        )

    if "prescriber_id" in update_data:
        validate_prescriber_exists(
            db=db,
            prescriber_id=update_data["prescriber_id"],
        )

    final_start_date = update_data.get(
        "start_date",
        prescription.start_date,
    )

    final_end_date = update_data.get(
        "end_date",
        prescription.end_date,
    )

    if (
        final_start_date is not None
        and final_end_date is not None
        and final_end_date < final_start_date
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="end_date cannot be earlier than start_date",
        )

    final_dosage_amount = update_data.get(
        "dosage_amount",
        prescription.dosage_amount,
    )

    final_dosage_unit = update_data.get(
        "dosage_unit",
        prescription.dosage_unit,
    )

    if (
        final_dosage_amount is not None
        and final_dosage_unit is None
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "dosage_unit must be supplied when dosage_amount "
                "is provided"
            ),
        )

    try:
        updated_prescription = (
            prescription_service.update_prescription(
                db=db,
                prescription=prescription,
                update_data=update_data,
            )
        )

    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Prescription update conflicts with an "
                "existing record"
            ),
        )

    audit_service.safe_record_event(
        db=db,
        action="PRESCRIPTION_UPDATE",
        outcome="SUCCESS",
        user_id=current_user.id,
        resource_type="Prescription",
        resource_id=str(updated_prescription.id),
        request=request,
        details={
            "patient_id": updated_prescription.patient_id,
            "encounter_id": updated_prescription.encounter_id,
            "prescriber_id": updated_prescription.prescriber_id,
            "updated_fields": sorted(
                update_data.keys()
            ),
        },
    )

    return updated_prescription