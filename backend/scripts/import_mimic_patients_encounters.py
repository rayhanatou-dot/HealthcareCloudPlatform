from __future__ import annotations

import csv
import gzip
import sys
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import func, select


BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


from app.db.session import SessionLocal
from app.models.encounter import Encounter
from app.models.patient import Patient


SOURCE_SYSTEM = "mimic-iv-demo"


def locate_hosp_directory() -> Path:
    """Locate the extracted MIMIC-IV Demo hospital directory."""

    dataset_root = (
        PROJECT_DIR
        / "datasets"
        / "mimic-iv-demo"
    )

    patient_files = list(
        dataset_root.rglob("hosp/patients.csv.gz")
    )

    if not patient_files:
        raise FileNotFoundError(
            "MIMIC-IV Demo patients.csv.gz was not found."
        )

    return patient_files[0].parent


def clean_value(
    row: dict[str, str],
    column: str,
) -> str:
    """Return one normalized CSV value."""

    return (row.get(column) or "").strip()


def parse_datetime(value: str) -> datetime | None:
    """Parse a MIMIC datetime value."""

    value = value.strip()

    if not value:
        return None

    return datetime.strptime(
        value,
        "%Y-%m-%d %H:%M:%S",
    )


def estimate_date_of_birth(
    anchor_year_value: str,
    anchor_age_value: str,
) -> date | None:
    """Estimate birth year from MIMIC anchor values."""

    try:
        anchor_year = int(anchor_year_value)
        anchor_age = int(anchor_age_value)
    except (TypeError, ValueError):
        return None

    estimated_year = anchor_year - anchor_age

    if estimated_year < 1:
        return None

    return date(
        estimated_year,
        1,
        1,
    )


def normalize_gender(value: str) -> str:
    """Convert MIMIC gender codes into readable values."""

    normalized_value = value.strip().upper()

    if normalized_value == "F":
        return "female"

    if normalized_value == "M":
        return "male"

    return "unknown"


def normalize_encounter_type(value: str) -> str:
    """Normalize the MIMIC admission type."""

    normalized_value = value.strip().lower()

    if not normalized_value:
        return "inpatient"

    return normalized_value.replace(
        " ",
        "-",
    )


def import_patients(
    db,
    patients_path: Path,
) -> tuple[dict[str, int], int, int]:
    """Import or update MIMIC patients."""

    existing_patients = db.scalars(
        select(Patient).where(
            Patient.source_system == SOURCE_SYSTEM
        )
    ).all()

    patient_by_external_id = {
        str(patient.external_id): patient
        for patient in existing_patients
    }

    patient_id_map: dict[str, int] = {}

    created = 0
    updated = 0

    with gzip.open(
        patients_path,
        mode="rt",
        encoding="utf-8",
        newline="",
    ) as csv_file:
        reader = csv.DictReader(csv_file)

        for row in reader:
            subject_id = clean_value(
                row,
                "subject_id",
            )

            if not subject_id:
                continue

            patient = patient_by_external_id.get(
                subject_id
            )

            estimated_birth_date = (
                estimate_date_of_birth(
                    clean_value(row, "anchor_year"),
                    clean_value(row, "anchor_age"),
                )
            )

            if patient is None:
                patient = Patient(
                    medical_record_number=(
                        f"MIMIC-{subject_id}"
                    ),
                    external_id=subject_id,
                    source_system=SOURCE_SYSTEM,
                    first_name="MIMIC",
                    last_name=subject_id,
                    date_of_birth=estimated_birth_date,
                    gender=normalize_gender(
                        clean_value(row, "gender")
                    ),
                    country="US",
                )

                db.add(patient)
                db.flush()

                patient_by_external_id[
                    subject_id
                ] = patient

                created += 1

            else:
                patient.medical_record_number = (
                    f"MIMIC-{subject_id}"
                )
                patient.first_name = "MIMIC"
                patient.last_name = subject_id
                patient.date_of_birth = (
                    estimated_birth_date
                )
                patient.gender = normalize_gender(
                    clean_value(row, "gender")
                )
                patient.country = "US"

                updated += 1

            patient_id_map[subject_id] = patient.id

    return patient_id_map, created, updated


def import_encounters(
    db,
    admissions_path: Path,
    patient_id_map: dict[str, int],
) -> tuple[int, int, int]:
    """Import or update MIMIC hospital admissions."""

    existing_encounters = db.scalars(
        select(Encounter).where(
            Encounter.source_system == SOURCE_SYSTEM
        )
    ).all()

    encounter_by_external_id = {
        str(encounter.external_id): encounter
        for encounter in existing_encounters
    }

    created = 0
    updated = 0
    skipped = 0

    with gzip.open(
        admissions_path,
        mode="rt",
        encoding="utf-8",
        newline="",
    ) as csv_file:
        reader = csv.DictReader(csv_file)

        for row in reader:
            subject_id = clean_value(
                row,
                "subject_id",
            )

            admission_id = clean_value(
                row,
                "hadm_id",
            )

            patient_id = patient_id_map.get(
                subject_id
            )

            if not admission_id or patient_id is None:
                skipped += 1
                continue

            start_time = parse_datetime(
                clean_value(row, "admittime")
            )

            end_time = parse_datetime(
                clean_value(row, "dischtime")
            )

            encounter_status = (
                "finished"
                if end_time is not None
                else "in-progress"
            )

            encounter = (
                encounter_by_external_id.get(
                    admission_id
                )
            )

            if encounter is None:
                encounter = Encounter(
                    patient_id=patient_id,
                    external_id=admission_id,
                    source_system=SOURCE_SYSTEM,
                    encounter_type=(
                        normalize_encounter_type(
                            clean_value(
                                row,
                                "admission_type",
                            )
                        )
                    ),
                    status=encounter_status,
                    start_time=start_time,
                    end_time=end_time,
                    location=(
                        clean_value(
                            row,
                            "admission_location",
                        )
                        or None
                    ),
                )

                db.add(encounter)

                encounter_by_external_id[
                    admission_id
                ] = encounter

                created += 1

            else:
                encounter.patient_id = patient_id
                encounter.encounter_type = (
                    normalize_encounter_type(
                        clean_value(
                            row,
                            "admission_type",
                        )
                    )
                )
                encounter.status = encounter_status
                encounter.start_time = start_time
                encounter.end_time = end_time
                encounter.location = (
                    clean_value(
                        row,
                        "admission_location",
                    )
                    or None
                )

                updated += 1

    return created, updated, skipped


def main() -> None:
    """Import MIMIC-IV Demo patients and admissions."""

    hosp_directory = locate_hosp_directory()

    patients_path = (
        hosp_directory
        / "patients.csv.gz"
    )

    admissions_path = (
        hosp_directory
        / "admissions.csv.gz"
    )

    if not admissions_path.exists():
        raise FileNotFoundError(
            f"Admissions file not found: {admissions_path}"
        )

    print(f"Hospital directory: {hosp_directory}")

    db = SessionLocal()

    try:
        (
            patient_id_map,
            patients_created,
            patients_updated,
        ) = import_patients(
            db,
            patients_path,
        )

        (
            encounters_created,
            encounters_updated,
            encounters_skipped,
        ) = import_encounters(
            db,
            admissions_path,
            patient_id_map,
        )

        db.commit()

        patient_total = db.scalar(
            select(
                func.count(Patient.id)
            ).where(
                Patient.source_system
                == SOURCE_SYSTEM
            )
        )

        encounter_total = db.scalar(
            select(
                func.count(Encounter.id)
            ).where(
                Encounter.source_system
                == SOURCE_SYSTEM
            )
        )

        print()
        print("MIMIC-IV Demo import completed")
        print(
            f"Patients created: {patients_created:,}"
        )
        print(
            f"Patients updated: {patients_updated:,}"
        )
        print(
            f"MIMIC patients in database: "
            f"{patient_total:,}"
        )
        print(
            f"Encounters created: "
            f"{encounters_created:,}"
        )
        print(
            f"Encounters updated: "
            f"{encounters_updated:,}"
        )
        print(
            f"Encounters skipped: "
            f"{encounters_skipped:,}"
        )
        print(
            f"MIMIC encounters in database: "
            f"{encounter_total:,}"
        )

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


if __name__ == "__main__":
    main()
