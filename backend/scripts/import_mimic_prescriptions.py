from __future__ import annotations

import csv
import gzip
import hashlib
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
from app.models.patient import Patient
from app.models.prescription import Prescription


SOURCE_SYSTEM = "mimic-iv-demo"
BATCH_SIZE = 1000


def locate_hosp_directory() -> Path:
    """Locate the MIMIC-IV Demo hospital directory."""

    dataset_root = (
        PROJECT_DIR
        / "datasets"
        / "mimic-iv-demo"
    )

    matches = list(
        dataset_root.rglob(
            "hosp/prescriptions.csv.gz"
        )
    )

    if not matches:
        raise FileNotFoundError(
            "MIMIC prescriptions.csv.gz was not found."
        )

    return matches[0].parent


def clean_value(
    row: dict[str, str],
    column: str,
) -> str:
    """Return a normalized CSV value."""

    return (row.get(column) or "").strip()


def parse_datetime(
    value: str,
) -> datetime | None:
    """Parse a MIMIC datetime value."""

    if not value:
        return None

    return datetime.strptime(
        value,
        "%Y-%m-%d %H:%M:%S",
    )


def parse_float(
    value: str,
) -> float | None:
    """Convert one numeric dose into a float."""

    if not value:
        return None

    normalized_value = (
        value
        .replace(",", "")
        .strip()
    )

    try:
        return float(normalized_value)
    except ValueError:
        return None


def create_external_id(
    row: dict[str, str],
) -> str:
    """Create a stable prescription identifier."""

    identity_fields = [
        clean_value(row, "subject_id"),
        clean_value(row, "hadm_id"),
        clean_value(row, "pharmacy_id"),
        clean_value(row, "poe_id"),
        clean_value(row, "poe_seq"),
        clean_value(row, "drug"),
        clean_value(row, "starttime"),
        clean_value(row, "stoptime"),
        clean_value(row, "route"),
        clean_value(row, "dose_val_rx"),
        clean_value(row, "dose_unit_rx"),
    ]

    identity_text = "|".join(identity_fields)

    return hashlib.sha256(
        identity_text.encode("utf-8")
    ).hexdigest()


def get_medication_code(
    row: dict[str, str],
) -> tuple[str, str]:
    """Select the best available medication code."""

    ndc = clean_value(row, "ndc")

    if ndc and ndc != "0":
        return (
            ndc,
            "http://hl7.org/fhir/sid/ndc",
        )

    formulary_code = clean_value(
        row,
        "formulary_drug_cd",
    )

    if formulary_code:
        return (
            formulary_code,
            "urn:mimic-iv:formulary-drug-code",
        )

    gsn = clean_value(row, "gsn")

    if gsn:
        return (
            gsn,
            "urn:mimic-iv:gsn",
        )

    drug_name = clean_value(row, "drug")

    generated_code = hashlib.sha256(
        drug_name.lower().encode("utf-8")
    ).hexdigest()[:24]

    return (
        f"drug-{generated_code}",
        "urn:mimic-iv:drug-name",
    )


def build_frequency(
    row: dict[str, str],
) -> str | None:
    """Build a readable prescription frequency."""

    doses_per_day = clean_value(
        row,
        "doses_per_24_hrs",
    )

    if not doses_per_day:
        return None

    return f"{doses_per_day} doses per 24 hours"


def build_instructions(
    row: dict[str, str],
) -> str | None:
    """Preserve relevant source prescription details."""

    instruction_parts: list[str] = []

    dose_value = clean_value(
        row,
        "dose_val_rx",
    )

    dose_unit = clean_value(
        row,
        "dose_unit_rx",
    )

    if dose_value:
        dose_text = f"Original dose: {dose_value}"

        if dose_unit:
            dose_text += f" {dose_unit}"

        instruction_parts.append(dose_text)

    product_strength = clean_value(
        row,
        "prod_strength",
    )

    if product_strength:
        instruction_parts.append(
            f"Product strength: {product_strength}"
        )

    prescription_form = clean_value(
        row,
        "form_rx",
    )

    if prescription_form:
        instruction_parts.append(
            f"Prescription form: {prescription_form}"
        )

    dispensed_value = clean_value(
        row,
        "form_val_disp",
    )

    dispensed_unit = clean_value(
        row,
        "form_unit_disp",
    )

    if dispensed_value:
        dispensed_text = (
            f"Dispensed form: {dispensed_value}"
        )

        if dispensed_unit:
            dispensed_text += f" {dispensed_unit}"

        instruction_parts.append(dispensed_text)

    drug_type = clean_value(
        row,
        "drug_type",
    )

    if drug_type:
        instruction_parts.append(
            f"Drug type: {drug_type}"
        )

    if not instruction_parts:
        return None

    return "; ".join(instruction_parts)


def flush_batch(
    db,
    records: list[dict],
) -> None:
    """Insert one batch of prescriptions."""

    if not records:
        return

    db.execute(
        insert(Prescription),
        records,
    )

    db.commit()


def main() -> None:
    """Import MIMIC-IV Demo prescriptions."""

    hosp_directory = locate_hosp_directory()

    prescriptions_path = (
        hosp_directory
        / "prescriptions.csv.gz"
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
                    Prescription.external_id
                ).where(
                    Prescription.source_system
                    == SOURCE_SYSTEM
                )
            ).all()
        )

        print(f"Hospital directory: {hosp_directory}")
        print(
            f"MIMIC patients available: "
            f"{len(patient_map):,}"
        )
        print(
            f"MIMIC encounters available: "
            f"{len(encounter_map):,}"
        )
        print(
            f"Existing MIMIC prescriptions: "
            f"{len(existing_external_ids):,}"
        )

        processed = 0
        imported = 0
        skipped_existing = 0
        skipped_missing_patient = 0
        skipped_missing_drug = 0
        unmatched_encounter = 0
        non_numeric_dose = 0
        batch: list[dict] = []

        with gzip.open(
            prescriptions_path,
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

                drug_name = clean_value(
                    row,
                    "drug",
                )

                if not drug_name:
                    skipped_missing_drug += 1
                    continue

                patient_id = patient_map.get(
                    subject_id
                )

                if patient_id is None:
                    skipped_missing_patient += 1
                    continue

                external_id = create_external_id(
                    row
                )

                if external_id in existing_external_ids:
                    skipped_existing += 1
                    continue

                encounter_id = None

                if admission_id:
                    encounter_id = encounter_map.get(
                        admission_id
                    )

                    if encounter_id is None:
                        unmatched_encounter += 1

                medication_code, code_system = (
                    get_medication_code(row)
                )

                dose_value_text = clean_value(
                    row,
                    "dose_val_rx",
                )

                dosage_amount = parse_float(
                    dose_value_text
                )

                if (
                    dose_value_text
                    and dosage_amount is None
                ):
                    non_numeric_dose += 1

                start_time = parse_datetime(
                    clean_value(
                        row,
                        "starttime",
                    )
                )

                end_time = parse_datetime(
                    clean_value(
                        row,
                        "stoptime",
                    )
                )

                batch.append(
                    {
                        "patient_id": patient_id,
                        "encounter_id": encounter_id,
                        "prescriber_id": None,
                        "external_id": external_id,
                        "source_system": SOURCE_SYSTEM,
                        "medication_code": medication_code,
                        "code_system": code_system,
                        "medication_name": drug_name,
                        "dosage_amount": dosage_amount,
                        "dosage_unit": (
                            clean_value(
                                row,
                                "dose_unit_rx",
                            )
                            or None
                        ),
                        "frequency": build_frequency(
                            row
                        ),
                        "route": (
                            clean_value(
                                row,
                                "route",
                            )
                            or None
                        ),
                        "instructions": (
                            build_instructions(row)
                        ),
                        "status": (
                            "completed"
                            if end_time is not None
                            else "active"
                        ),
                        "authored_at": start_time,
                        "start_date": start_time,
                        "end_date": end_time,
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
                func.count(Prescription.id)
            ).where(
                Prescription.source_system
                == SOURCE_SYSTEM
            )
        )

        print()
        print("MIMIC prescription import completed")
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
            "Skipped because drug name was missing: "
            f"{skipped_missing_drug:,}"
        )
        print(
            "Rows without a matching encounter: "
            f"{unmatched_encounter:,}"
        )
        print(
            "Rows with non-numeric dosage values: "
            f"{non_numeric_dose:,}"
        )
        print(
            "MIMIC prescriptions in database: "
            f"{database_total:,}"
        )

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


if __name__ == "__main__":
    main()
