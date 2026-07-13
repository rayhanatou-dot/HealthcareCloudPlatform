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
from app.models.patient import Patient
from app.models.user import User
from app.schemas.encounter import (
    EncounterCreate,
    EncounterListResponse,
    EncounterResponse,
    EncounterUpdate,
)
from app.services.audit_service import audit_service
from app.services.encounter_service import encounter_service


encounters_router = APIRouter(
    prefix="/encounters",
    tags=["Encounters"],
)


@encounters_router.post(
    "",
    response_model=EncounterResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_encounter(
    payload: EncounterCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(
            "Admin",
            "Doctor",
            "Nurse",
            "Data Manager",
        )
    ),
):
    patient = db.get(
        Patient,
        payload.patient_id,
    )

    if patient is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient not found",
        )

    try:
        encounter = encounter_service.create_encounter(
            db=db,
            encounter_data=payload.model_dump(),
        )

    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Encounter conflicts with an existing record"
            ),
        )

    audit_service.safe_record_event(
        db=db,
        action="ENCOUNTER_CREATE",
        outcome="SUCCESS",
        user_id=current_user.id,
        resource_type="Encounter",
        resource_id=str(encounter.id),
        request=request,
        details={
            "patient_id": encounter.patient_id,
            "encounter_type": encounter.encounter_type,
        },
    )

    return encounter


@encounters_router.get(
    "",
    response_model=EncounterListResponse,
)
def list_encounters(
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
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(
            "Admin",
            "Doctor",
            "Nurse",
            "Lab Staff",
            "Data Manager",
        )
    ),
):
    if patient_id is not None:
        patient = db.get(
            Patient,
            patient_id,
        )

        if patient is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Patient not found",
            )

    total, encounters = (
        encounter_service.list_encounters(
            db=db,
            skip=skip,
            limit=limit,
            patient_id=patient_id,
        )
    )

    audit_service.safe_record_event(
        db=db,
        action="ENCOUNTER_LIST",
        outcome="SUCCESS",
        user_id=current_user.id,
        resource_type="Encounter",
        resource_id=(
            str(patient_id)
            if patient_id is not None
            else None
        ),
        request=request,
        details={
            "skip": skip,
            "limit": limit,
            "patient_id": patient_id,
            "returned_count": len(encounters),
            "total": total,
        },
    )

    return EncounterListResponse(
        total=total,
        skip=skip,
        limit=limit,
        items=encounters,
    )


@encounters_router.get(
    "/{encounter_id}",
    response_model=EncounterResponse,
)
def get_encounter(
    encounter_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(
            "Admin",
            "Doctor",
            "Nurse",
            "Lab Staff",
            "Data Manager",
        )
    ),
):
    encounter = encounter_service.get_encounter(
        db=db,
        encounter_id=encounter_id,
    )

    if encounter is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Encounter not found",
        )

    audit_service.safe_record_event(
        db=db,
        action="ENCOUNTER_READ",
        outcome="SUCCESS",
        user_id=current_user.id,
        resource_type="Encounter",
        resource_id=str(encounter.id),
        request=request,
        details={
            "patient_id": encounter.patient_id,
        },
    )

    return encounter


@encounters_router.patch(
    "/{encounter_id}",
    response_model=EncounterResponse,
)
def update_encounter(
    encounter_id: int,
    payload: EncounterUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(
            "Admin",
            "Doctor",
            "Nurse",
            "Data Manager",
        )
    ),
):
    encounter = encounter_service.get_encounter(
        db=db,
        encounter_id=encounter_id,
    )

    if encounter is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Encounter not found",
        )

    update_data = payload.model_dump(
        exclude_unset=True
    )

    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No update fields supplied",
        )

    final_start_time = update_data.get(
        "start_time",
        encounter.start_time,
    )

    final_end_time = update_data.get(
        "end_time",
        encounter.end_time,
    )

    if (
        final_end_time is not None
        and final_end_time < final_start_time
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "end_time cannot be earlier than start_time"
            ),
        )

    try:
        updated_encounter = (
            encounter_service.update_encounter(
                db=db,
                encounter=encounter,
                update_data=update_data,
            )
        )

    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Encounter update conflicts with an "
                "existing record"
            ),
        )

    audit_service.safe_record_event(
        db=db,
        action="ENCOUNTER_UPDATE",
        outcome="SUCCESS",
        user_id=current_user.id,
        resource_type="Encounter",
        resource_id=str(updated_encounter.id),
        request=request,
        details={
            "patient_id": updated_encounter.patient_id,
            "updated_fields": sorted(
                update_data.keys()
            ),
        },
    )

    return updated_encounter