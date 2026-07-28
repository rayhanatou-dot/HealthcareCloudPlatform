from __future__ import annotations

import csv
import gzip
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import func, insert, select


BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


from app.db.session import SessionLocal
from app.models.encounter import Encounter
from app.models.observation import Observation
from app.models.patient import Patient


SOURCE_SYSTEM = "mimic-iv-demo"
CODE_SYSTEM = "urn:mimic-iv:itemid"
BATCH_SIZE = 2000


def locate_hosp_directory() -> Path:
    """Locate the MIMIC-IV Demo hospital directory."""

    dataset_root = (
        PROJECT_DIR
        / "datasets"
        / "mimic-iv-demo"
    )

    matches = list(
        dataset_root.rglob("hosp/labevents.csv.gz")
    )

    if not matches:
        raise FileNotFoundError(
            "MIMIC labevents.csv.gz was not found."
        )

    return matches[0].parent


def clean_value(
    row: dict[str, str],
    column: str,
) -> str:
    """Return a normalized CSV value."""

    return (row.get(column) or "").strip()


def parse_datetime(value: str) -> datetime | None:
    """Parse a MIMIC datetime value."""

    if not value:
        return None

    return datetime.strptime(
        value,
        "%Y-%m-%d %H:%M:%S",
    )


def parse_float(value: str) -> float | None:
    """Convert a numeric text value into a float."""

    if not value:
        return None

    try:
        return float(value)
    except ValueError:
        return None


def build_reference_range(
    lower: str,
    upper: str,
) -> str | None:
    """Build a readable laboratory reference range."""

    if lower and upper:
        return f"{lower} - {upper}"

    if lower:
        return f">= {lower}"

    if upper:
        return f"<= {upper}"

    return None


def load_lab_dictionary(
    dictionary_path: Path,
) -> dict[str, str]:
    """Load MIMIC laboratory item descriptions."""

    lab_dictionary: dict[str, str] = {}

    with gzip.open(
        dictionary_path,
        mode="rt",
        encoding="utf-8",
        newline="",
    ) as csv_file:
        reader = csv.DictReader(csv_file)

        for row in reader:
            item_id = clean_value(
                row,
                "itemid",
            )

            label = clean_value(
                row,
                "label",
            )

            if item_id:
                lab_dictionary[item_id] = (
                    label
                    or f"MIMIC laboratory item {item_id}"
                )

    return lab_dictionary


def flush_batch(
    db,
    records: list[dict],
) -> None:
    """Insert one batch of observations."""

    if not records:
        return

    db.execute(
        insert(Observation),
        records,
    )

    db.commit()


def main() -> None:
    """Import MIMIC-IV Demo laboratory observations."""

    hosp_directory = locate_hosp_directory()

    labevents_path = (
        hosp_directory
        / "labevents.csv.gz"
    )

    dictionary_path = (
        hosp_directory
        / "d_labitems.csv.gz"
    )

    if not dictionary_path.exists():
        raise FileNotFoundError(
            f"Laboratory dictionary not found: "
            f"{dictionary_path}"
        )

    lab_dictionary = load_lab_dictionary(
        dictionary_path
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
            str(external_id): database_id
            for external_id, database_id
            in encounter_rows
        }

        if not patient_map:
            raise RuntimeError(
                "No MIMIC patients were found. "
                "Import patients first."
            )

        existing_external_ids = set(
            db.scalars(
                select(
                    Observation.external_id
                ).where(
                    Observation.source_system
                    == SOURCE_SYSTEM
                )
            ).all()
        )

        print(f"Hospital directory: {hosp_directory}")
        print(
            f"Lab dictionary entries: "
            f"{len(lab_dictionary):,}"
        )
        print(
            f"MIMIC patients available: "
            f"{len(patient_map):,}"
        )
        print(
            f"MIMIC encounters available: "
            f"{len(encounter_map):,}"
        )
        print(
            f"Existing MIMIC observations: "
            f"{len(existing_external_ids):,}"
        )

        processed = 0
        imported = 0
        skipped_existing = 0
        skipped_missing_patient = 0
        skipped_missing_identifier = 0
        unmatched_encounter = 0
        missing_lab_description = 0
        non_numeric_values = 0

        batch: list[dict] = []

        with gzip.open(
            labevents_path,
            mode="rt",
            encoding="utf-8",
            newline="",
        ) as csv_file:
            reader = csv.DictReader(csv_file)

            for row in reader:
                processed += 1

                lab_event_id = clean_value(
                    row,
                    "labevent_id",
                )

                subject_id = clean_value(
                    row,
                    "subject_id",
                )

                admission_id = clean_value(
                    row,
                    "hadm_id",
                )

                item_id = clean_value(
                    row,
                    "itemid",
                )

                if not lab_event_id or not item_id:
                    skipped_missing_identifier += 1
                    continue

                external_id = (
                    f"mimic-lab-{lab_event_id}"
                )

                if external_id in existing_external_ids:
                    skipped_existing += 1
                    continue

                patient_id = patient_map.get(
                    subject_id
                )

                if patient_id is None:
                    skipped_missing_patient += 1
                    continue

                encounter_id = None

                if admission_id:
                    encounter_id = encounter_map.get(
                        admission_id
                    )

                    if encounter_id is None:
                        unmatched_encounter += 1

                display_name = lab_dictionary.get(
                    item_id
                )

                if not display_name:
                    display_name = (
                        f"MIMIC laboratory item {item_id}"
                    )
                    missing_lab_description += 1

                value_text = clean_value(
                    row,
                    "value",
                )

                numeric_text = clean_value(
                    row,
                    "valuenum",
                )

                value_numeric = parse_float(
                    numeric_text
                )

                if numeric_text and value_numeric is None:
                    non_numeric_values += 1

                lower_range = clean_value(
                    row,
                    "ref_range_lower",
                )

                upper_range = clean_value(
                    row,
                    "ref_range_upper",
                )

                batch.append(
                    {
                        "patient_id": patient_id,
                        "encounter_id": encounter_id,
                        "external_id": external_id,
                        "source_system": SOURCE_SYSTEM,
                        "category": "laboratory",
                        "code": item_id,
                        "code_system": CODE_SYSTEM,
                        "display_name": display_name,
                        "value_numeric": value_numeric,
                        "value_text": value_text or None,
                        "unit": (
                            clean_value(
                                row,
                                "valueuom",
                            )
                            or None
                        ),
                        "reference_range": (
                            build_reference_range(
                                lower_range,
                                upper_range,
                            )
                        ),
                        "status": "final",
                        "observed_at": parse_datetime(
                            clean_value(
                                row,
                                "charttime",
                            )
                        ),
                        "issued_at": parse_datetime(
                            clean_value(
                                row,
                                "storetime",
                            )
                        ),
                    }
                )

                existing_external_ids.add(
                    external_id
                )

                imported += 1

                if len(batch) >= BATCH_SIZE:
                    flush_batch(
                        db,
                        batch,
                    )

                    batch.clear()

                    print(
                        f"Processed: {processed:,} | "
                        f"Imported: {imported:,}"
                    )

            flush_batch(
                db,
                batch,
            )

        database_total = db.scalar(
            select(
                func.count(Observation.id)
            ).where(
                Observation.source_system
                == SOURCE_SYSTEM
            )
        )

        print()
        print("MIMIC laboratory import completed")
        print(f"Rows processed: {processed:,}")
        print(f"Rows imported: {imported:,}")
        print(
            f"Existing rows skipped: "
            f"{skipped_existing:,}"
        )
        print(
            "Skipped because patient was missing: "
            f"{skipped_missing_patient:,}"
        )
        print(
            "Skipped because identifier was missing: "
            f"{skipped_missing_identifier:,}"
        )
        print(
            "Rows without a matching encounter: "
            f"{unmatched_encounter:,}"
        )
        print(
            "Rows without a laboratory description: "
            f"{missing_lab_description:,}"
        )
        print(
            "Invalid numeric values: "
            f"{non_numeric_values:,}"
        )
        print(
            "MIMIC observations in database: "
            f"{database_total:,}"
        )

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


if __name__ == "__main__":
    main()
