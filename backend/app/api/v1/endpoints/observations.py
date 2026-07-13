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
from app.schemas.observation import (
    ObservationCreate,
    ObservationListResponse,
    ObservationResponse,
    ObservationUpdate,
)
from app.services.audit_service import audit_service
from app.services.observation_service import observation_service


observations_router = APIRouter(
    prefix="/observations",
    tags=["Observations"],
)


@observations_router.post(
    "",
    response_model=ObservationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_observation(
    payload: ObservationCreate,
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
    patient = db.get(
        Patient,
        payload.patient_id,
    )

    if patient is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient not found",
        )

    if payload.encounter_id is not None:
        encounter = db.get(
            Encounter,
            payload.encounter_id,
        )

        if encounter is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Encounter not found",
            )

        if encounter.patient_id != payload.patient_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Encounter does not belong to the "
                    "specified patient"
                ),
            )

    try:
        observation = observation_service.create_observation(
            db=db,
            observation_data=payload.model_dump(),
        )

    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Observation conflicts with an existing record"
            ),
        )

    audit_service.safe_record_event(
        db=db,
        action="OBSERVATION_CREATE",
        outcome="SUCCESS",
        user_id=current_user.id,
        resource_type="Observation",
        resource_id=str(observation.id),
        request=request,
        details={
            "patient_id": observation.patient_id,
            "encounter_id": observation.encounter_id,
            "category": observation.category,
            "code": observation.code,
        },
    )

    return observation


@observations_router.get(
    "",
    response_model=ObservationListResponse,
)
def list_observations(
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

    total, observations = (
        observation_service.list_observations(
            db=db,
            skip=skip,
            limit=limit,
            patient_id=patient_id,
            encounter_id=encounter_id,
        )
    )

    audit_service.safe_record_event(
        db=db,
        action="OBSERVATION_LIST",
        outcome="SUCCESS",
        user_id=current_user.id,
        resource_type="Observation",
        resource_id=None,
        request=request,
        details={
            "skip": skip,
            "limit": limit,
            "patient_id": patient_id,
            "encounter_id": encounter_id,
            "returned_count": len(observations),
            "total": total,
        },
    )

    return ObservationListResponse(
        total=total,
        skip=skip,
        limit=limit,
        items=observations,
    )


@observations_router.get(
    "/{observation_id}",
    response_model=ObservationResponse,
)
def get_observation(
    observation_id: int,
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
    observation = observation_service.get_observation(
        db=db,
        observation_id=observation_id,
    )

    if observation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Observation not found",
        )

    audit_service.safe_record_event(
        db=db,
        action="OBSERVATION_READ",
        outcome="SUCCESS",
        user_id=current_user.id,
        resource_type="Observation",
        resource_id=str(observation.id),
        request=request,
        details={
            "patient_id": observation.patient_id,
            "encounter_id": observation.encounter_id,
        },
    )

    return observation


@observations_router.patch(
    "/{observation_id}",
    response_model=ObservationResponse,
)
def update_observation(
    observation_id: int,
    payload: ObservationUpdate,
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
    observation = observation_service.get_observation(
        db=db,
        observation_id=observation_id,
    )

    if observation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Observation not found",
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
        new_encounter_id = update_data["encounter_id"]

        if new_encounter_id is not None:
            encounter = db.get(
                Encounter,
                new_encounter_id,
            )

            if encounter is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Encounter not found",
                )

            if encounter.patient_id != observation.patient_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "Encounter does not belong to the "
                        "observation patient"
                    ),
                )

    final_numeric = update_data.get(
        "value_numeric",
        observation.value_numeric,
    )

    final_text = update_data.get(
        "value_text",
        observation.value_text,
    )

    if (
        final_numeric is None
        and final_text is None
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Either value_numeric or value_text "
                "must be supplied"
            ),
        )

    try:
        updated_observation = (
            observation_service.update_observation(
                db=db,
                observation=observation,
                update_data=update_data,
            )
        )

    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Observation update conflicts with an "
                "existing record"
            ),
        )

    audit_service.safe_record_event(
        db=db,
        action="OBSERVATION_UPDATE",
        outcome="SUCCESS",
        user_id=current_user.id,
        resource_type="Observation",
        resource_id=str(updated_observation.id),
        request=request,
        details={
            "patient_id": updated_observation.patient_id,
            "encounter_id": updated_observation.encounter_id,
            "updated_fields": sorted(
                update_data.keys()
            ),
        },
    )

    return updated_observation