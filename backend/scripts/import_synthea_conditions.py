from __future__ import annotations

import csv
import hashlib
import sys
from datetime import datetime, timezone
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


CSV_PATH = (
    PROJECT_DIR
    / "datasets"
    / "synthea"
    / "csv"
    / "conditions.csv"
)

SOURCE_SYSTEM = "synthea"
DEFAULT_CODE_SYSTEM = "http://snomed.info/sct"
BATCH_SIZE = 1000


def clean_value(row: dict[str, str], column: str) -> str:
    """Return a normalized CSV value."""

    return (row.get(column) or "").strip()


def parse_datetime(value: str) -> datetime | None:
    """Convert a Synthea date or datetime into a UTC datetime."""

    value = value.strip()

    if not value:
        return None

    normalized_value = value.replace("Z", "+00:00")
    parsed_value = datetime.fromisoformat(normalized_value)

    if parsed_value.tzinfo is None:
        parsed_value = parsed_value.replace(
            tzinfo=timezone.utc
        )

    return parsed_value


def create_external_id(row: dict[str, str]) -> str:
    """Create a stable identifier for idempotent imports."""

    source_value = "|".join(
        [
            clean_value(row, "PATIENT"),
            clean_value(row, "ENCOUNTER"),
            clean_value(row, "CODE"),
            clean_value(row, "DESCRIPTION"),
            clean_value(row, "START"),
            clean_value(row, "STOP"),
        ]
    )

    return hashlib.sha256(
        source_value.encode("utf-8")
    ).hexdigest()


def flush_batch(db, records: list[dict]) -> None:
    """Insert or update one batch of conditions."""

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
            "abatement_at": (
                statement.excluded.abatement_at
            ),
            "recorded_at": statement.excluded.recorded_at,
            "updated_at": func.now(),
        },
    )

    db.execute(statement)
    db.commit()


def main() -> None:
    """Import Synthea conditions into PostgreSQL."""

    if not CSV_PATH.exists():
        raise FileNotFoundError(
            f"CSV file not found: {CSV_PATH}"
        )

    db = SessionLocal()

    try:
        patient_rows = db.execute(
            select(
                Patient.external_id,
                Patient.id,
            ).where(
                Patient.external_id.is_not(None)
            )
        ).all()

        encounter_rows = db.execute(
            select(
                Encounter.external_id,
                Encounter.id,
            ).where(
                Encounter.external_id.is_not(None)
            )
        ).all()

        patient_map = {
            str(external_id): database_id
            for external_id, database_id in patient_rows
        }

        encounter_map = {
            str(external_id): database_id
            for external_id, database_id in encounter_rows
        }

        print(f"CSV file: {CSV_PATH}")
        print(f"Patients available: {len(patient_map):,}")
        print(f"Encounters available: {len(encounter_map):,}")

        processed = 0
        accepted = 0
        skipped_missing_patient = 0
        skipped_missing_code = 0
        unmatched_encounter = 0
        batch: list[dict] = []

        with CSV_PATH.open(
            mode="r",
            encoding="utf-8-sig",
            newline="",
        ) as csv_file:
            reader = csv.DictReader(csv_file)

            available_columns = set(
                reader.fieldnames or []
            )

            required_columns = {
                "PATIENT",
                "CODE",
            }

            missing_columns = (
                required_columns - available_columns
            )

            if missing_columns:
                raise RuntimeError(
                    "Missing required CSV columns: "
                    + ", ".join(sorted(missing_columns))
                )

            print(
                "CSV columns: "
                + ", ".join(reader.fieldnames or [])
            )

            for row in reader:
                processed += 1

                patient_external_id = clean_value(
                    row,
                    "PATIENT",
                )

                encounter_external_id = clean_value(
                    row,
                    "ENCOUNTER",
                )

                code = clean_value(
                    row,
                    "CODE",
                )

                patient_id = patient_map.get(
                    patient_external_id
                )

                if patient_id is None:
                    skipped_missing_patient += 1
                    continue

                if not code:
                    skipped_missing_code += 1
                    continue

                encounter_id = encounter_map.get(
                    encounter_external_id
                )

                if (
                    encounter_external_id
                    and encounter_id is None
                ):
                    unmatched_encounter += 1

                onset_at = parse_datetime(
                    clean_value(row, "START")
                )

                abatement_at = parse_datetime(
                    clean_value(row, "STOP")
                )

                code_system = (
                    clean_value(row, "SYSTEM")
                    or DEFAULT_CODE_SYSTEM
                )

                batch.append(
                    {
                        "patient_id": patient_id,
                        "encounter_id": encounter_id,
                        "external_id": create_external_id(row),
                        "source_system": SOURCE_SYSTEM,
                        "code": code,
                        "code_system": code_system,
                        "display_name": (
                            clean_value(
                                row,
                                "DESCRIPTION",
                            )
                            or None
                        ),
                        "clinical_status": (
                            "resolved"
                            if abatement_at is not None
                            else "active"
                        ),
                        "verification_status": "confirmed",
                        "onset_at": onset_at,
                        "abatement_at": abatement_at,
                        "recorded_at": onset_at,
                    }
                )

                accepted += 1

                if len(batch) >= BATCH_SIZE:
                    flush_batch(db, batch)
                    batch.clear()

                    print(
                        f"Processed: {processed:,} | "
                        f"Accepted: {accepted:,}"
                    )

            flush_batch(db, batch)

        database_total = db.scalar(
            select(
                func.count(Condition.id)
            ).where(
                Condition.source_system
                == SOURCE_SYSTEM
            )
        )

        print()
        print("Import completed")
        print(f"Rows processed: {processed:,}")
        print(
            "Rows imported or updated: "
            f"{accepted:,}"
        )
        print(
            "Skipped because patient was not found: "
            f"{skipped_missing_patient:,}"
        )
        print(
            "Skipped because code was missing: "
            f"{skipped_missing_code:,}"
        )
        print(
            "Rows without a matching encounter: "
            f"{unmatched_encounter:,}"
        )
        print(
            "Synthea conditions in database: "
            f"{database_total:,}"
        )

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


if __name__ == "__main__":
    main()
