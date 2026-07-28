from __future__ import annotations

import csv
import gzip
import sys
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert


BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


from app.db.session import SessionLocal
from app.models.condition import Condition
from app.models.encounter import Encounter
from app.models.patient import Patient


SOURCE_SYSTEM = "mimic-iv-demo"
BATCH_SIZE = 1000


def locate_hosp_directory() -> Path:
    """Locate the extracted MIMIC-IV Demo hospital directory."""

    dataset_root = (
        PROJECT_DIR
        / "datasets"
        / "mimic-iv-demo"
    )

    matches = list(
        dataset_root.rglob("hosp/diagnoses_icd.csv.gz")
    )

    if not matches:
        raise FileNotFoundError(
            "MIMIC diagnoses_icd.csv.gz was not found."
        )

    return matches[0].parent


def clean_value(
    row: dict[str, str],
    column: str,
) -> str:
    """Return a normalized CSV value."""

    return (row.get(column) or "").strip()


def get_code_system(
    icd_version: str,
) -> str:
    """Return the corresponding ICD coding system."""

    if icd_version == "9":
        return "http://hl7.org/fhir/sid/icd-9-cm"

    if icd_version == "10":
        return "http://hl7.org/fhir/sid/icd-10-cm"

    return "urn:oid:unknown-icd-system"


def create_external_id(
    admission_id: str,
    sequence_number: str,
    icd_code: str,
    icd_version: str,
) -> str:
    """Create a stable identifier for one diagnosis."""

    return (
        f"{admission_id}:"
        f"{sequence_number}:"
        f"{icd_version}:"
        f"{icd_code}"
    )


def load_diagnosis_dictionary(
    dictionary_path: Path,
) -> dict[tuple[str, str], str]:
    """Load ICD descriptions indexed by code and version."""

    diagnosis_dictionary: dict[
        tuple[str, str],
        str,
    ] = {}

    with gzip.open(
        dictionary_path,
        mode="rt",
        encoding="utf-8",
        newline="",
    ) as csv_file:
        reader = csv.DictReader(csv_file)

        for row in reader:
            code = clean_value(
                row,
                "icd_code",
            )

            version = clean_value(
                row,
                "icd_version",
            )

            title = clean_value(
                row,
                "long_title",
            )

            if code and version:
                diagnosis_dictionary[
                    (code, version)
                ] = title

    return diagnosis_dictionary


def flush_batch(
    db,
    records: list[dict],
) -> None:
    """Insert or update one diagnosis batch."""

    if not records:
        return

    statement = postgresql_insert(
        Condition
    ).values(records)

    statement = statement.on_conflict_do_update(
        index_elements=[
            Condition.source_system,
            Condition.external_id,
        ],
        set_={
            "patient_id": statement.excluded.patient_id,
            "encounter_id": statement.excluded.encounter_id,
            "code": statement.excluded.code,
            "code_system": statement.excluded.code_system,
            "display_name": statement.excluded.display_name,
            "clinical_status": (
                statement.excluded.clinical_status
            ),
            "verification_status": (
                statement.excluded.verification_status
            ),
            "onset_at": statement.excluded.onset_at,
            "abatement_at": statement.excluded.abatement_at,
            "recorded_at": statement.excluded.recorded_at,
            "updated_at": func.now(),
        },
    )

    db.execute(statement)
    db.commit()


def main() -> None:
    """Import MIMIC-IV Demo ICD diagnoses."""

    hosp_directory = locate_hosp_directory()

    diagnoses_path = (
        hosp_directory
        / "diagnoses_icd.csv.gz"
    )

    dictionary_path = (
        hosp_directory
        / "d_icd_diagnoses.csv.gz"
    )

    if not dictionary_path.exists():
        raise FileNotFoundError(
            f"ICD dictionary not found: {dictionary_path}"
        )

    diagnosis_dictionary = (
        load_diagnosis_dictionary(
            dictionary_path
        )
    )

    db = SessionLocal()

    try:
        patient_rows = db.execute(
            select(
                Patient.external_id,
                Patient.id,
            ).where(
                Patient.source_system
                == SOURCE_SYSTEM
            )
        ).all()

        encounter_rows = db.execute(
            select(
                Encounter.external_id,
                Encounter.id,
                Encounter.patient_id,
                Encounter.start_time,
            ).where(
                Encounter.source_system
                == SOURCE_SYSTEM
            )
        ).all()

        patient_map = {
            str(external_id): database_id
            for external_id, database_id
            in patient_rows
        }

        encounter_map = {
            str(external_id): {
                "id": database_id,
                "patient_id": patient_id,
                "start_time": start_time,
            }
            for (
                external_id,
                database_id,
                patient_id,
                start_time,
            ) in encounter_rows
        }

        print(f"Hospital directory: {hosp_directory}")
        print(
            f"ICD dictionary entries: "
            f"{len(diagnosis_dictionary):,}"
        )
        print(
            f"MIMIC patients available: "
            f"{len(patient_map):,}"
        )
        print(
            f"MIMIC encounters available: "
            f"{len(encounter_map):,}"
        )

        processed = 0
        accepted = 0
        skipped_missing_patient = 0
        skipped_missing_encounter = 0
        skipped_missing_code = 0
        missing_description = 0
        batch: list[dict] = []

        with gzip.open(
            diagnoses_path,
            mode="rt",
            encoding="utf-8",
            newline="",
        ) as csv_file:
            reader = csv.DictReader(csv_file)

            for row in reader:
                processed += 1

                subject_id = clean_value(
                    row,
                    "subject_id",
                )

                admission_id = clean_value(
                    row,
                    "hadm_id",
                )

                sequence_number = clean_value(
                    row,
                    "seq_num",
                )

                icd_code = clean_value(
                    row,
                    "icd_code",
                )

                icd_version = clean_value(
                    row,
                    "icd_version",
                )

                patient_id = patient_map.get(
                    subject_id
                )

                if patient_id is None:
                    skipped_missing_patient += 1
                    continue

                encounter_data = encounter_map.get(
                    admission_id
                )

                if encounter_data is None:
                    skipped_missing_encounter += 1
                    continue

                if not icd_code:
                    skipped_missing_code += 1
                    continue

                description = (
                    diagnosis_dictionary.get(
                        (
                            icd_code,
                            icd_version,
                        )
                    )
                )

                if not description:
                    missing_description += 1

                batch.append(
                    {
                        "patient_id": patient_id,
                        "encounter_id": (
                            encounter_data["id"]
                        ),
                        "external_id": (
                            create_external_id(
                                admission_id,
                                sequence_number,
                                icd_code,
                                icd_version,
                            )
                        ),
                        "source_system": SOURCE_SYSTEM,
                        "code": icd_code,
                        "code_system": get_code_system(
                            icd_version
                        ),
                        "display_name": description,
                        "clinical_status": "active",
                        "verification_status": "confirmed",
                        "onset_at": (
                            encounter_data["start_time"]
                        ),
                        "abatement_at": None,
                        "recorded_at": (
                            encounter_data["start_time"]
                        ),
                    }
                )

                accepted += 1

                if len(batch) >= BATCH_SIZE:
                    flush_batch(
                        db,
                        batch,
                    )

                    batch.clear()

                    print(
                        f"Processed: {processed:,} | "
                        f"Accepted: {accepted:,}"
                    )

            flush_batch(
                db,
                batch,
            )

        database_total = db.scalar(
            select(
                func.count(Condition.id)
            ).where(
                Condition.source_system
                == SOURCE_SYSTEM
            )
        )

        print()
        print("MIMIC diagnosis import completed")
        print(f"Rows processed: {processed:,}")
        print(
            f"Rows imported or updated: "
            f"{accepted:,}"
        )
        print(
            "Skipped because patient was missing: "
            f"{skipped_missing_patient:,}"
        )
        print(
            "Skipped because encounter was missing: "
            f"{skipped_missing_encounter:,}"
        )
        print(
            "Skipped because ICD code was missing: "
            f"{skipped_missing_code:,}"
        )
        print(
            "Rows without ICD description: "
            f"{missing_description:,}"
        )
        print(
            "MIMIC conditions in database: "
            f"{database_total:,}"
        )

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


if __name__ == "__main__":
    main()
