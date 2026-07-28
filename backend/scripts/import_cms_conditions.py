from __future__ import annotations

import csv
import sys
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert


BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


from app.db.session import SessionLocal
from app.models.condition import Condition
from app.models.encounter import Encounter
from app.models.patient import Patient


SOURCE_SYSTEM = "cms-de-synpuf"
CODE_SYSTEM = "http://hl7.org/fhir/sid/icd-9-cm"
BATCH_SIZE = 2000


def locate_inpatient_file() -> Path:
    """Locate the CMS DE-SynPUF inpatient claims CSV."""

    root = (
        PROJECT_DIR
        / "datasets"
        / "cms-de-synpuf"
        / "sample-1"
    )

    matches = list(
        root.rglob(
            "*Inpatient_Claims_Sample_1.csv"
        )
    )

    if not matches:
        raise FileNotFoundError(
            "CMS inpatient claims CSV was not found."
        )

    return matches[0]


def clean_value(
    row: dict[str, str],
    column: str,
) -> str:
    """Return a normalized CSV value."""

    return (row.get(column) or "").strip()


def claim_external_id(
    claim_id: str,
    segment: str,
) -> str:
    """Build the encounter external ID used by the CMS importer."""

    if segment:
        return f"{claim_id}:{segment}"

    return claim_id


def condition_external_id(
    encounter_external_id: str,
    diagnosis_type: str,
    position: int,
    code: str,
) -> str:
    """Build a stable identifier for one claim diagnosis."""

    return (
        f"{encounter_external_id}:"
        f"{diagnosis_type}:"
        f"{position}:"
        f"{code}"
    )


def flush_batch(
    db,
    records: list[dict],
) -> None:
    """Insert or update one batch of CMS conditions."""

    if not records:
        return

    statement = pg_insert(
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
    """Import CMS inpatient ICD-9 diagnoses into conditions."""

    inpatient_path = locate_inpatient_file()

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
                Encounter.end_time,
            ).where(
                Encounter.source_system
                == SOURCE_SYSTEM
            )
        ).all()

        patient_map = {
            str(external_id): patient_id
            for external_id, patient_id
            in patient_rows
        }

        encounter_map = {
            str(external_id): {
                "id": encounter_id,
                "patient_id": patient_id,
                "start_time": start_time,
                "end_time": end_time,
            }
            for (
                external_id,
                encounter_id,
                patient_id,
                start_time,
                end_time,
            ) in encounter_rows
        }

        if not patient_map:
            raise RuntimeError(
                "No CMS patients were found. "
                "Import CMS patients first."
            )

        if not encounter_map:
            raise RuntimeError(
                "No CMS encounters were found. "
                "Import CMS encounters first."
            )

        print(f"Inpatient file: {inpatient_path}")
        print(
            f"CMS patients available: "
            f"{len(patient_map):,}"
        )
        print(
            f"CMS encounters available: "
            f"{len(encounter_map):,}"
        )

        processed_claims = 0
        accepted_conditions = 0
        skipped_missing_patient = 0
        skipped_missing_encounter = 0
        skipped_missing_claim = 0
        empty_diagnosis_slots = 0
        batch: list[dict] = []

        diagnosis_columns = [
            (
                "ADMTNG_ICD9_DGNS_CD",
                "admitting",
                0,
            )
        ]

        diagnosis_columns.extend(
            (
                f"ICD9_DGNS_CD_{position}",
                "diagnosis",
                position,
            )
            for position in range(1, 11)
        )

        with inpatient_path.open(
            mode="r",
            encoding="utf-8-sig",
            newline="",
        ) as csv_file:
            reader = csv.DictReader(csv_file)

            for row in reader:
                processed_claims += 1

                beneficiary_id = clean_value(
                    row,
                    "DESYNPUF_ID",
                )

                claim_id = clean_value(
                    row,
                    "CLM_ID",
                )

                segment = clean_value(
                    row,
                    "SEGMENT",
                )

                if not claim_id:
                    skipped_missing_claim += 1
                    continue

                patient_id = patient_map.get(
                    beneficiary_id
                )

                if patient_id is None:
                    skipped_missing_patient += 1
                    continue

                encounter_external_id = (
                    claim_external_id(
                        claim_id,
                        segment,
                    )
                )

                encounter = encounter_map.get(
                    encounter_external_id
                )

                if encounter is None:
                    skipped_missing_encounter += 1
                    continue

                for (
                    column,
                    diagnosis_type,
                    position,
                ) in diagnosis_columns:
                    code = clean_value(
                        row,
                        column,
                    )

                    if not code:
                        empty_diagnosis_slots += 1
                        continue

                    batch.append(
                        {
                            "patient_id": patient_id,
                            "encounter_id": (
                                encounter["id"]
                            ),
                            "external_id": (
                                condition_external_id(
                                    encounter_external_id,
                                    diagnosis_type,
                                    position,
                                    code,
                                )
                            ),
                            "source_system": SOURCE_SYSTEM,
                            "code": code,
                            "code_system": CODE_SYSTEM,
                            "display_name": (
                                f"ICD-9-CM {code}"
                            ),
                            "clinical_status": (
                                "resolved"
                                if encounter["end_time"]
                                is not None
                                else "active"
                            ),
                            "verification_status": "confirmed",
                            "onset_at": (
                                encounter["start_time"]
                            ),
                            "abatement_at": (
                                encounter["end_time"]
                            ),
                            "recorded_at": (
                                encounter["start_time"]
                            ),
                        }
                    )

                    accepted_conditions += 1

                    if len(batch) >= BATCH_SIZE:
                        flush_batch(
                            db,
                            batch,
                        )

                        batch.clear()

                if (
                    processed_claims % 5000
                    == 0
                ):
                    print(
                        f"Claims processed: "
                        f"{processed_claims:,} | "
                        f"Conditions accepted: "
                        f"{accepted_conditions:,}"
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
        print("CMS diagnosis import completed")
        print(
            f"Claims processed: "
            f"{processed_claims:,}"
        )
        print(
            f"Conditions imported or updated: "
            f"{accepted_conditions:,}"
        )
        print(
            "Claims skipped because patient "
            f"was missing: "
            f"{skipped_missing_patient:,}"
        )
        print(
            "Claims skipped because encounter "
            f"was missing: "
            f"{skipped_missing_encounter:,}"
        )
        print(
            "Claims skipped because claim ID "
            f"was missing: "
            f"{skipped_missing_claim:,}"
        )
        print(
            f"Empty diagnosis slots: "
            f"{empty_diagnosis_slots:,}"
        )
        print(
            f"CMS conditions in database: "
            f"{database_total:,}"
        )

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


if __name__ == "__main__":
    main()
