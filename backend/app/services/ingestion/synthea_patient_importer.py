import csv
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.patient import Patient


SYNTHEA_SOURCE_SYSTEM = "synthea"


def parse_optional_date(
    value: str | None,
):
    if value is None:
        return None

    value = value.strip()

    if not value:
        return None

    return datetime.fromisoformat(value).date()


def clean_optional_string(
    value: str | None,
):
    if value is None:
        return None

    value = value.strip()

    if not value:
        return None

    return value


def build_medical_record_number(
    synthea_patient_id: str,
) -> str:
    return f"SYNTHEA-{synthea_patient_id}"


def map_gender(
    value: str | None,
):
    value = clean_optional_string(value)

    if value is None:
        return None

    gender_map = {
        "M": "male",
        "F": "female",
    }

    return gender_map.get(
        value.upper(),
        value,
    )


def find_existing_patient(
    db: Session,
    synthea_patient_id: str,
):
    statement = select(Patient).where(
        Patient.source_system == SYNTHEA_SOURCE_SYSTEM,
        Patient.external_id == synthea_patient_id,
    )

    return db.scalar(statement)


def create_or_update_patient(
    db: Session,
    row: dict,
) -> tuple[Patient, bool]:
    synthea_patient_id = row["Id"].strip()

    existing_patient = find_existing_patient(
        db=db,
        synthea_patient_id=synthea_patient_id,
    )

    patient_data = {
        "medical_record_number": build_medical_record_number(
            synthea_patient_id
        ),
        "external_id": synthea_patient_id,
        "source_system": SYNTHEA_SOURCE_SYSTEM,
        "first_name": row["FIRST"].strip(),
        "last_name": row["LAST"].strip(),
        "date_of_birth": parse_optional_date(
            row.get("BIRTHDATE")
        ),
        "gender": map_gender(
            row.get("GENDER")
        ),
        "phone": clean_optional_string(
            row.get("PHONE")
        ),
        "email": clean_optional_string(
            row.get("EMAIL")
        ),
        "address_line": clean_optional_string(
            row.get("ADDRESS")
        ),
        "city": clean_optional_string(
            row.get("CITY")
        ),
        "state": clean_optional_string(
            row.get("STATE")
        ),
        "postal_code": clean_optional_string(
            row.get("ZIP")
        ),
        "country": clean_optional_string(
            row.get("COUNTRY")
        ),
    }

    if existing_patient is not None:
        for field_name, field_value in patient_data.items():
            setattr(
                existing_patient,
                field_name,
                field_value,
            )

        return existing_patient, False

    patient = Patient(
        **patient_data
    )

    db.add(patient)

    return patient, True


def import_synthea_patients(
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

    with csv_file_path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as csv_file:
        reader = csv.DictReader(csv_file)

        for row in reader:
            synthea_patient_id = clean_optional_string(
                row.get("Id")
            )

            first_name = clean_optional_string(
                row.get("FIRST")
            )

            last_name = clean_optional_string(
                row.get("LAST")
            )

            if (
                synthea_patient_id is None
                or first_name is None
                or last_name is None
            ):
                skipped_count += 1
                continue

            _, created = create_or_update_patient(
                db=db,
                row=row,
            )

            if created:
                created_count += 1
            else:
                updated_count += 1

    db.commit()

    return {
        "created": created_count,
        "updated": updated_count,
        "skipped": skipped_count,
    }