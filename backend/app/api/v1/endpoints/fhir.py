from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
)

from sqlalchemy.orm import Session

from app.db.session import get_db

from app.api.dependencies.rbac import require_roles

from app.models.patient import Patient
from app.models.encounter import Encounter
from app.models.observation import Observation
from app.models.prescription import Prescription


router = APIRouter(
    prefix="/fhir",
    tags=["FHIR"],
    dependencies=[
        Depends(
            require_roles(
                "Admin",
                "Doctor",
                "Nurse",
                "Pharmacist",
                "Data Manager",
            )
        )
    ],
)


# =====================================================
# FHIR Resource Helper Functions
# =====================================================


def patient_resource(patient):

    return {

        "resourceType": "Patient",

        "id":
            str(patient.id),

        "identifier":
            [
                {
                    "system":
                        patient.source_system,

                    "value":
                        patient.external_id,
                }
            ],

        "name":
            [
                {
                    "family":
                        patient.last_name,

                    "given":
                        [
                            patient.first_name
                        ],
                }
            ],

        "gender":
            patient.gender,

        "birthDate":
            (
                patient.date_of_birth.isoformat()
                if patient.date_of_birth
                else None
            ),

    }



def encounter_resource(encounter):

    return {

        "resourceType":
            "Encounter",

        "id":
            str(encounter.id),

        "status":
            encounter.status,

        "subject":
            {
                "reference":
                    f"Patient/{encounter.patient_id}"
            },

    }



def observation_resource(obs):

    data = {

        "resourceType":
            "Observation",

        "id":
            str(obs.id),

        "status":
            obs.status,

        "subject":
            {
                "reference":
                    f"Patient/{obs.patient_id}"
            },

        "code":
            {

                "coding":
                    [
                        {
                            "system":
                                obs.code_system,

                            "code":
                                obs.code,
                        }
                    ],

                "text":
                    obs.display_name,

            },

    }


    if obs.value_numeric is not None:

        data["valueQuantity"] = {

            "value":
                float(
                    obs.value_numeric
                ),

            "unit":
                obs.unit,

        }


    elif obs.value_text:

        data["valueString"] = (
            obs.value_text
        )


    return data



def medication_resource(rx):

    return {

        "resourceType":
            "MedicationRequest",

        "id":
            str(rx.id),

        "status":
            rx.status,

        "subject":
            {
                "reference":
                    f"Patient/{rx.patient_id}"
            },

        "medicationCodeableConcept":
            {

                "text":
                    rx.medication_name

            },

        "authoredOn":
            (
                rx.authored_at.isoformat()
                if rx.authored_at
                else None
            ),

    }



# =====================================================
# CapabilityStatement
# =====================================================


@router.get(
    "/metadata"
)
def metadata():

    return {

        "resourceType":
            "CapabilityStatement",

        "status":
            "active",

        "kind":
            "instance",

        "software":
            {

                "name":
                    "Healthcare Cloud Platform",

                "version":
                    "1.0",

            },

        "format":
            [
                "json"
            ],

    }



# =====================================================
# Patient Search
# =====================================================


@router.get(
    "/Patient"
)
def search_patient(

    name: str | None = None,

    _count: int = Query(
        20,
        le=100
    ),

    db: Session = Depends(get_db),

):

    query = db.query(
        Patient
    )


    if name:

        query = query.filter(

            Patient.first_name.ilike(
                f"%{name}%"
            )

            |

            Patient.last_name.ilike(
                f"%{name}%"
            )

        )


    patients = (

        query
        .limit(_count)
        .all()

    )


    return {

        "resourceType":
            "Bundle",

        "type":
            "searchset",

        "total":
            len(patients),

        "entry":
            [

                {

                    "resource":
                        patient_resource(
                            patient
                        )

                }

                for patient in patients

            ],

    }



# =====================================================
# Patient Read
# =====================================================


@router.get(
    "/Patient/{patient_id}"
)
def get_patient(

    patient_id: int,

    db: Session = Depends(get_db),

):

    patient = (

        db.query(
            Patient
        )

        .filter(
            Patient.id == patient_id
        )

        .first()

    )


    if not patient:

        raise HTTPException(

            status_code=404,

            detail="Patient not found"

        )


    return patient_resource(
        patient
    )
# =====================================================
# Patient Everything
# =====================================================


@router.get(
    "/Patient/{patient_id}/$everything"
)
def everything(

    patient_id: int,

    db: Session = Depends(get_db),

):

    patient = (

        db.query(
            Patient
        )

        .filter(
            Patient.id == patient_id
        )

        .first()

    )


    if not patient:

        raise HTTPException(

            status_code=404,

            detail="Patient not found"

        )


    resources = [

        {

            "resource":

                patient_resource(
                    patient
                )

        }

    ]


    encounters = (

        db.query(
            Encounter
        )

        .filter(
            Encounter.patient_id == patient_id
        )

        .all()

    )


    for encounter in encounters:

        resources.append(

            {

                "resource":

                    encounter_resource(
                        encounter
                    )

            }

        )



    observations = (

        db.query(
            Observation
        )

        .filter(
            Observation.patient_id == patient_id
        )

        .all()

    )


    for observation in observations:

        resources.append(

            {

                "resource":

                    observation_resource(
                        observation
                    )

            }

        )



    prescriptions = (

        db.query(
            Prescription
        )

        .filter(
            Prescription.patient_id == patient_id
        )

        .all()

    )


    for prescription in prescriptions:

        resources.append(

            {

                "resource":

                    medication_resource(
                        prescription
                    )

            }

        )



    return {

        "resourceType":

            "Bundle",

        "type":

            "collection",

        "total":

            len(resources),

        "entry":

            resources,

    }



# =====================================================
# Encounter Read
# =====================================================


@router.get(
    "/Encounter/{encounter_id}"
)
def get_encounter(

    encounter_id: int,

    db: Session = Depends(get_db),

):

    encounter = (

        db.query(
            Encounter
        )

        .filter(
            Encounter.id == encounter_id
        )

        .first()

    )


    if not encounter:

        raise HTTPException(

            status_code=404,

            detail="Encounter not found"

        )


    return encounter_resource(
        encounter
    )



# =====================================================
# Observation Search
# =====================================================


@router.get(
    "/Observation"
)
def search_observation(

    patient: int | None = None,

    code: str | None = None,

    _count: int = Query(
        20,
        le=100
    ),

    db: Session = Depends(get_db),

):

    query = db.query(
        Observation
    )


    if patient:

        query = query.filter(

            Observation.patient_id == patient

        )


    if code:

        query = query.filter(

            Observation.code == code

        )


    observations = (

        query

        .limit(_count)

        .all()

    )


    return {

        "resourceType":

            "Bundle",

        "type":

            "searchset",

        "total":

            len(observations),

        "entry":

            [

                {

                    "resource":

                        observation_resource(
                            observation
                        )

                }

                for observation in observations

            ],

    }



# =====================================================
# Observation Read
# =====================================================


@router.get(
    "/Observation/{observation_id}"
)
def get_observation(

    observation_id: int,

    db: Session = Depends(get_db),

):

    observation = (

        db.query(
            Observation
        )

        .filter(

            Observation.id == observation_id

        )

        .first()

    )


    if not observation:

        raise HTTPException(

            status_code=404,

            detail="Observation not found"

        )


    return observation_resource(
        observation
    )



# =====================================================
# MedicationRequest Read
# =====================================================


@router.get(
    "/MedicationRequest/{prescription_id}"
)
def get_medication(

    prescription_id: int,

    db: Session = Depends(get_db),

):

    prescription = (

        db.query(
            Prescription
        )

        .filter(

            Prescription.id == prescription_id

        )

        .first()

    )


    if not prescription:

        raise HTTPException(

            status_code=404,

            detail="MedicationRequest not found"

        )


    return medication_resource(
        prescription
    )