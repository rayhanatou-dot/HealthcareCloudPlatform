from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
)
from sqlalchemy.orm import Session

from app.api.dependencies.rbac import require_roles
from app.db.session import get_db
from app.models.condition import Condition


router = APIRouter(
    prefix="/fhir",
    tags=["FHIR"],
    dependencies=[
        Depends(
            require_roles(
                "Admin",
                "Doctor",
                "Nurse",
                "Data Manager",
            )
        )
    ],
)


def condition_to_fhir(condition: Condition) -> dict:
    """Convert a database condition into a FHIR-inspired resource."""

    resource = {
        "resourceType": "Condition",
        "id": str(condition.id),
        "clinicalStatus": {
            "coding": [
                {
                    "system": (
                        "http://terminology.hl7.org/"
                        "CodeSystem/condition-clinical"
                    ),
                    "code": condition.clinical_status,
                }
            ]
        },
        "code": {
            "coding": [
                {
                    "system": condition.code_system,
                    "code": condition.code,
                    "display": condition.display_name,
                }
            ],
            "text": condition.display_name,
        },
        "subject": {
            "reference": f"Patient/{condition.patient_id}",
        },
    }

    if condition.verification_status:
        resource["verificationStatus"] = {
            "coding": [
                {
                    "system": (
                        "http://terminology.hl7.org/"
                        "CodeSystem/condition-ver-status"
                    ),
                    "code": condition.verification_status,
                }
            ]
        }

    if condition.encounter_id is not None:
        resource["encounter"] = {
            "reference": f"Encounter/{condition.encounter_id}",
        }

    if condition.onset_at is not None:
        resource["onsetDateTime"] = condition.onset_at.isoformat()

    if condition.abatement_at is not None:
        resource["abatementDateTime"] = (
            condition.abatement_at.isoformat()
        )

    if condition.recorded_at is not None:
        resource["recordedDate"] = condition.recorded_at.isoformat()

    return resource


@router.get("/Condition")
def search_fhir_conditions(
    patient: int | None = None,
    code: str | None = None,
    clinical_status: str | None = None,
    _count: int = Query(
        default=20,
        ge=1,
        le=100,
    ),
    db: Session = Depends(get_db),
) -> dict:
    """Search FHIR Condition resources."""

    query = db.query(Condition)

    if patient is not None:
        query = query.filter(
            Condition.patient_id == patient
        )

    if code:
        query = query.filter(
            Condition.code == code
        )

    if clinical_status:
        query = query.filter(
            Condition.clinical_status == clinical_status
        )

    total = query.count()

    conditions = (
        query
        .order_by(Condition.id)
        .limit(_count)
        .all()
    )

    return {
        "resourceType": "Bundle",
        "type": "searchset",
        "total": total,
        "entry": [
            {
                "fullUrl": f"Condition/{condition.id}",
                "resource": condition_to_fhir(condition),
            }
            for condition in conditions
        ],
    }


@router.get("/Condition/{condition_id}")
def get_fhir_condition(
    condition_id: int,
    db: Session = Depends(get_db),
) -> dict:
    """Read one FHIR Condition resource."""

    condition = (
        db.query(Condition)
        .filter(
            Condition.id == condition_id
        )
        .first()
    )

    if condition is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Condition not found",
        )

    return condition_to_fhir(condition)
