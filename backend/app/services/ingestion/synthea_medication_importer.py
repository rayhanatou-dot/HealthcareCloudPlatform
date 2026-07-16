import csv
import hashlib
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.encounter import Encounter
from app.models.patient import Patient
from app.models.prescription import Prescription
from app.models.user import User


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


def parse_optional_date(value: str | None):
    parsed_datetime = parse_optional_datetime(value)

    if parsed_datetime is None:
        return None

    return parsed_datetime.date()


def build_prescription_external_id(row: dict) -> str:
    raw_identifier = "|".join(
        [
            clean_optional_string(row.get("START")) or "",
            clean_optional_string(row.get("STOP")) or "",
            clean_optional_string(row.get("PATIENT")) or "",
            clean_optional_string(row.get("ENCOUNTER")) or "",
            clean_optional_string(row.get("CODE")) or "",
            clean_optional_string(row.get("DESCRIPTION")) or "",
        ]
    )

    digest = hashlib.sha256(
        raw_identifier.encode("utf-8")
    ).hexdigest()[:24]

    return f"synthea-medication-{digest}"


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


def find_default_prescriber(db: Session):
    statement = select(User).where(
        User.username == "demo_doctor",
    )

    user = db.scalar(statement)

    if user is not None:
        return user

    fallback_statement = select(User).where(
        User.is_active.is_(True),
    ).limit(1)

    return db.scalar(fallback_statement)


def find_existing_prescription(
    db: Session,
    external_id: str,
):
    statement = select(Prescription).where(
        Prescription.source_system == SYNTHEA_SOURCE_SYSTEM,
        Prescription.external_id == external_id,
    )

    return db.scalar(statement)


def determine_status(stop_date):
    if stop_date is None:
        return "active"

    return "completed"


def create_or_update_prescription(
    db: Session,
    row: dict,
    default_prescriber: User | None,
) -> tuple[Prescription | None, bool, str | None]:
    synthea_patient_id = clean_optional_string(
        row.get("PATIENT")
    )

    if synthea_patient_id is None:
        return None, False, "missing_patient_id"

    patient = find_patient_by_synthea_id(
        db=db,
        synthea_patient_id=synthea_patient_id,
    )

    if patient is None:
        return None, False, "patient_not_found"

    medication_code = clean_optional_string(
        row.get("CODE")
    )

    medication_name = clean_optional_string(
        row.get("DESCRIPTION")
    )

    if medication_code is None:
        return None, False, "missing_medication_code"

    if medication_name is None:
        return None, False, "missing_medication_name"

    authored_at = parse_optional_datetime(
        row.get("START")
    )

    start_date = parse_optional_date(
        row.get("START")
    )

    end_date = parse_optional_date(
        row.get("STOP")
    )

    if authored_at is None:
        return None, False, "missing_start_time"

    encounter = find_encounter_by_synthea_id(
        db=db,
        synthea_encounter_id=row.get("ENCOUNTER"),
    )

    external_id = build_prescription_external_id(
        row=row
    )

    existing_prescription = find_existing_prescription(
        db=db,
        external_id=external_id,
    )

    prescription_data = {
        "patient_id": patient.id,
        "encounter_id": encounter.id if encounter is not None else None,
        "prescriber_id": (
            default_prescriber.id
            if default_prescriber is not None
            else None
        ),
        "external_id": external_id,
        "source_system": SYNTHEA_SOURCE_SYSTEM,
        "medication_code": medication_code,
        "code_system": "RxNorm",
        "medication_name": medication_name,
        "dosage_amount": None,
        "dosage_unit": None,
        "frequency": None,
        "route": None,
        "instructions": clean_optional_string(
            row.get("REASONDESCRIPTION")
        ),
        "status": determine_status(
            end_date
        ),
        "authored_at": authored_at,
        "start_date": start_date,
        "end_date": end_date,
    }

    if existing_prescription is not None:
        for field_name, field_value in prescription_data.items():
            setattr(
                existing_prescription,
                field_name,
                field_value,
            )

        return existing_prescription, False, None

    prescription = Prescription(
        **prescription_data
    )

    db.add(prescription)

    return prescription, True, None


def import_synthea_medications(
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

    default_prescriber = find_default_prescriber(
        db=db
    )

    with csv_file_path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as csv_file:
        reader = csv.DictReader(csv_file)

        for row in reader:
            _, created, skip_reason = create_or_update_prescription(
                db=db,
                row=row,
                default_prescriber=default_prescriber,
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