import csv
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.encounter import Encounter
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

    normalized_value = value.replace("Z", "+00:00")

    parsed_datetime = datetime.fromisoformat(normalized_value)

    if parsed_datetime.tzinfo is not None:
        parsed_datetime = (
            parsed_datetime.astimezone(timezone.utc)
            .replace(tzinfo=None)
        )

    return parsed_datetime


def find_patient_by_synthea_id(
    db: Session,
    synthea_patient_id: str,
):
    statement = select(Patient).where(
        Patient.source_system == SYNTHEA_SOURCE_SYSTEM,
        Patient.external_id == synthea_patient_id,
    )

    return db.scalar(statement)


def find_existing_encounter(
    db: Session,
    synthea_encounter_id: str,
):
    statement = select(Encounter).where(
        Encounter.source_system == SYNTHEA_SOURCE_SYSTEM,
        Encounter.external_id == synthea_encounter_id,
    )

    return db.scalar(statement)


def determine_status(stop_time):
    if stop_time is None:
        return "in-progress"

    return "finished"


def create_or_update_encounter(
    db: Session,
    row: dict,
) -> tuple[Encounter | None, bool, str | None]:
    synthea_encounter_id = clean_optional_string(
        row.get("Id")
    )

    synthea_patient_id = clean_optional_string(
        row.get("PATIENT")
    )

    if synthea_encounter_id is None:
        return None, False, "missing_encounter_id"

    if synthea_patient_id is None:
        return None, False, "missing_patient_id"

    patient = find_patient_by_synthea_id(
        db=db,
        synthea_patient_id=synthea_patient_id,
    )

    if patient is None:
        return None, False, "patient_not_found"

    start_time = parse_optional_datetime(
        row.get("START")
    )

    end_time = parse_optional_datetime(
        row.get("STOP")
    )

    if start_time is None:
        return None, False, "missing_start_time"

    existing_encounter = find_existing_encounter(
        db=db,
        synthea_encounter_id=synthea_encounter_id,
    )

    encounter_data = {
        "patient_id": patient.id,
        "external_id": synthea_encounter_id,
        "source_system": SYNTHEA_SOURCE_SYSTEM,
        "encounter_type": clean_optional_string(
            row.get("ENCOUNTERCLASS")
        ),
        "status": determine_status(
            end_time
        ),
        "start_time": start_time,
        "end_time": end_time,
        "location": clean_optional_string(
            row.get("ORGANIZATION")
        ),
    }

    if existing_encounter is not None:
        for field_name, field_value in encounter_data.items():
            setattr(
                existing_encounter,
                field_name,
                field_value,
            )

        return existing_encounter, False, None

    encounter = Encounter(
        **encounter_data
    )

    db.add(encounter)

    return encounter, True, None


def import_synthea_encounters(
    db: Session,
    csv_file_path: Path,
) -> dict:
    if not csv_file_path.exists():
        raise FileNotFoundError(
            f"File not found: {csv_file_path}"
        )

    created_count = 0
    updated_count = 0
    skipped_count = 0
    skip_reasons: dict[str, int] = {}

    with csv_file_path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as csv_file:
        reader = csv.DictReader(csv_file)

        for row in reader:
            _, created, skip_reason = create_or_update_encounter(
                db=db,
                row=row,
            )

            if skip_reason is not None:
                skipped_count += 1
                skip_reasons[skip_reason] = (
                    skip_reasons.get(skip_reason, 0) + 1
                )
                continue

            if created:
                created_count += 1
            else:
                updated_count += 1

    db.commit()

    return {
        "created": created_count,
        "updated": updated_count,
        "skipped": skipped_count,
        "skip_reasons": skip_reasons,
    }