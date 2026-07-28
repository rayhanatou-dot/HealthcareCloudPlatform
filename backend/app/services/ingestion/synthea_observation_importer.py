import csv
import hashlib
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.encounter import Encounter
from app.models.observation import Observation
from app.models.patient import Patient


SYNTHEA_SOURCE_SYSTEM = "synthea"


def clean_optional_string(value: str | None):

    if value is None:
        return None

    value = value.strip()

    if not value:
        return None

    return value


def parse_optional_datetime(value: str | None):

    value = clean_optional_string(value)

    if value is None:
        return None

    normalized_value = value.replace(
        "Z",
        "+00:00"
    )

    parsed_datetime = datetime.fromisoformat(
        normalized_value
    )

    if parsed_datetime.tzinfo is not None:

        parsed_datetime = (
            parsed_datetime
            .astimezone(timezone.utc)
            .replace(tzinfo=None)
        )

    return parsed_datetime


def parse_optional_float(value: str | None):

    value = clean_optional_string(value)

    if value is None:
        return None

    try:
        return float(value)

    except ValueError:
        return None


def build_observation_external_id(row: dict):

    raw_identifier = "|".join(
        [
            clean_optional_string(row.get("DATE")) or "",
            clean_optional_string(row.get("PATIENT")) or "",
            clean_optional_string(row.get("ENCOUNTER")) or "",
            clean_optional_string(row.get("CODE")) or "",
            clean_optional_string(row.get("DESCRIPTION")) or "",
            clean_optional_string(row.get("VALUE")) or "",
            clean_optional_string(row.get("UNITS")) or "",
        ]
    )

    digest = hashlib.sha256(
        raw_identifier.encode("utf-8")
    ).hexdigest()

    return (
        f"synthea-observation-{digest}"
    )


def find_patient_by_synthea_id(
    db: Session,
    synthea_patient_id: str,
):

    statement = select(Patient).where(
        Patient.source_system == SYNTHEA_SOURCE_SYSTEM,
        Patient.external_id == synthea_patient_id,
    )

    return db.scalar(statement)


def find_encounter_by_synthea_id(
    db: Session,
    synthea_encounter_id: str | None,
):

    synthea_encounter_id = clean_optional_string(
        synthea_encounter_id
    )

    if synthea_encounter_id is None:
        return None

    statement = select(Encounter).where(
        Encounter.source_system == SYNTHEA_SOURCE_SYSTEM,
        Encounter.external_id == synthea_encounter_id,
    )

    return db.scalar(statement)


def find_existing_observation(
    db: Session,
    external_id: str,
):

    statement = select(Observation).where(
        Observation.source_system == SYNTHEA_SOURCE_SYSTEM,
        Observation.external_id == external_id,
    )

    return db.scalar(statement)


def create_or_update_observation(
    db: Session,
    row: dict,
):

    synthea_patient_id = clean_optional_string(
        row.get("PATIENT")
    )

    if synthea_patient_id is None:
        return None, False, "missing_patient_id"


    patient = find_patient_by_synthea_id(
        db,
        synthea_patient_id
    )


    if patient is None:
        return None, False, "patient_not_found"


    observed_at = parse_optional_datetime(
        row.get("DATE")
    )


    if observed_at is None:
        return None, False, "missing_observation_date"


    observation_code = clean_optional_string(
        row.get("CODE")
    )

    display_name = clean_optional_string(
        row.get("DESCRIPTION")
    )


    if observation_code is None:
        return None, False, "missing_observation_code"


    if display_name is None:
        return None, False, "missing_description"



    encounter = find_encounter_by_synthea_id(
        db,
        row.get("ENCOUNTER")
    )


    raw_value = clean_optional_string(
        row.get("VALUE")
    )


    value_numeric = parse_optional_float(
        raw_value
    )


    value_text = None

    if value_numeric is None:
        value_text = raw_value



    external_id = build_observation_external_id(
        row
    )


    existing = find_existing_observation(
        db,
        external_id
    )


    observation_data = {

        "patient_id": patient.id,

        "encounter_id":
            encounter.id
            if encounter
            else None,

        "external_id": external_id,

        "source_system":
            SYNTHEA_SOURCE_SYSTEM,

        "category":
            clean_optional_string(
                row.get("CATEGORY")
            )
            or "laboratory",

        "code":
            observation_code,

        "code_system":
            clean_optional_string(
                row.get("SYSTEM")
            )
            or "LOINC",

        "display_name":
            display_name,

        "value_numeric":
            value_numeric,

        "value_text":
            value_text,

        "unit":
            clean_optional_string(
                row.get("UNITS")
            ),

        "reference_range":
            None,

        "status":
            "final",

        "observed_at":
            observed_at,

        "issued_at":
            observed_at,
    }


    if existing:

        for key, value in observation_data.items():

            setattr(
                existing,
                key,
                value
            )

        return existing, False, None



    observation = Observation(
        **observation_data
    )

    db.add(observation)

    return observation, True, None



def import_synthea_observations(
    db: Session,
    csv_file_path: Path,
):

    created_count = 0
    updated_count = 0
    skipped_count = 0

    skip_reasons = {}

    batch_size = 1000

    processed_count = 0

    seen_external_ids = set()



    with csv_file_path.open(
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as file:


        reader = csv.DictReader(file)



        for row in reader:


            external_id = (
                build_observation_external_id(row)
            )


            if external_id in seen_external_ids:

                skipped_count += 1

                skip_reasons[
                    "duplicate_in_csv"
                ] = (
                    skip_reasons.get(
                        "duplicate_in_csv",
                        0
                    )
                    + 1
                )

                continue



            seen_external_ids.add(
                external_id
            )



            _, created, reason = (
                create_or_update_observation(
                    db,
                    row
                )
            )


            processed_count += 1



            if reason:

                skipped_count += 1

                skip_reasons[reason] = (
                    skip_reasons.get(reason, 0)
                    + 1
                )

                continue



            if created:
                created_count += 1
            else:
                updated_count += 1



            if processed_count % batch_size == 0:

                db.commit()

                db.expire_all()

                seen_external_ids.clear()

                print(
                    f"Processed {processed_count} observations..."
                )



    db.commit()



    return {

        "created": created_count,

        "updated": updated_count,

        "skipped": skipped_count,

        "skip_reasons": skip_reasons

    }



# ==========================================================
# Standalone execution
# ==========================================================


if __name__ == "__main__":

    from app.db.session import SessionLocal


    csv_path = (

        Path(__file__)
        .resolve()
        .parents[4]

        / "datasets"
        / "synthea"
        / "csv"
        / "observations.csv"

    )


    print(
        f"Loading Synthea observations file: {csv_path}"
    )


    db = SessionLocal()


    try:

        result = import_synthea_observations(
            db,
            csv_path
        )


        print(
            "Synthea observation import completed"
        )


        print(result)


    finally:

        db.close()