from __future__ import annotations

import csv
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.db.session import SessionLocal
from app.models.patient import Patient
from app.models.encounter import Encounter

SOURCE_SYSTEM = "cms-de-synpuf"
BATCH_SIZE = 2000


def find_files() -> tuple[Path, Path]:
    root = PROJECT_DIR / "datasets" / "cms-de-synpuf" / "sample-1"
    beneficiaries = list(root.rglob("*Beneficiary_Summary_File_Sample_1.csv"))
    inpatient = list(root.rglob("*Inpatient_Claims_Sample_1.csv"))
    if not beneficiaries:
        raise FileNotFoundError("CMS beneficiary CSV was not found.")
    if not inpatient:
        raise FileNotFoundError("CMS inpatient claims CSV was not found.")
    return beneficiaries[0], inpatient[0]


def value(row: dict[str, str], column: str) -> str:
    return (row.get(column) or "").strip()


def parse_date(text: str):
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y%m%d").date()
    except ValueError:
        return None


def parse_datetime(text: str):
    parsed = parse_date(text)
    return datetime.combine(parsed, datetime.min.time()) if parsed else None


def gender(code: str) -> str:
    return {"1": "male", "2": "female"}.get(code, "unknown")


def upsert_patients(db, rows: list[dict]) -> None:
    if not rows:
        return
    stmt = pg_insert(Patient).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=[Patient.source_system, Patient.external_id],
        set_={
            "medical_record_number": stmt.excluded.medical_record_number,
            "first_name": stmt.excluded.first_name,
            "last_name": stmt.excluded.last_name,
            "date_of_birth": stmt.excluded.date_of_birth,
            "gender": stmt.excluded.gender,
            "state": stmt.excluded.state,
            "country": stmt.excluded.country,
            "updated_at": func.now(),
        },
    )
    db.execute(stmt)
    db.commit()


def upsert_encounters(db, rows: list[dict]) -> None:
    if not rows:
        return
    stmt = pg_insert(Encounter).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=[Encounter.source_system, Encounter.external_id],
        set_={
            "patient_id": stmt.excluded.patient_id,
            "encounter_type": stmt.excluded.encounter_type,
            "status": stmt.excluded.status,
            "start_time": stmt.excluded.start_time,
            "end_time": stmt.excluded.end_time,
            "location": stmt.excluded.location,
            "updated_at": func.now(),
        },
    )
    db.execute(stmt)
    db.commit()


def import_patients(db, path: Path) -> tuple[int, int, int]:
    existing = set(
        db.scalars(
            select(Patient.external_id).where(
                Patient.source_system == SOURCE_SYSTEM
            )
        ).all()
    )
    created = updated = skipped = processed = 0
    seen: set[str] = set()
    batch: list[dict] = []

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            processed += 1
            external_id = value(row, "DESYNPUF_ID")
            if not external_id:
                skipped += 1
                continue
            if external_id in seen:
                continue
            seen.add(external_id)

            if external_id in existing:
                updated += 1
            else:
                created += 1

            batch.append(
                {
                    "medical_record_number": f"CMS-{external_id}",
                    "external_id": external_id,
                    "source_system": SOURCE_SYSTEM,
                    "first_name": "CMS",
                    "last_name": external_id,
                    "date_of_birth": parse_date(value(row, "BENE_BIRTH_DT")),
                    "gender": gender(value(row, "BENE_SEX_IDENT_CD")),
                    "state": value(row, "SP_STATE_CODE") or None,
                    "country": "US",
                }
            )

            if len(batch) >= BATCH_SIZE:
                upsert_patients(db, batch)
                batch.clear()
                print(f"Beneficiaries processed: {processed:,}")

    upsert_patients(db, batch)
    return created, updated, skipped


def import_encounters(db, path: Path) -> tuple[int, int, int, int]:
    patient_map = dict(
        db.execute(
            select(Patient.external_id, Patient.id).where(
                Patient.source_system == SOURCE_SYSTEM
            )
        ).all()
    )
    existing = set(
        db.scalars(
            select(Encounter.external_id).where(
                Encounter.source_system == SOURCE_SYSTEM
            )
        ).all()
    )

    created = updated = missing_patient = missing_claim = processed = 0
    seen: set[str] = set()
    batch: list[dict] = []

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            processed += 1
            beneficiary_id = value(row, "DESYNPUF_ID")
            claim_id = value(row, "CLM_ID")
            segment = value(row, "SEGMENT")

            if not claim_id:
                missing_claim += 1
                continue

            patient_id = patient_map.get(beneficiary_id)
            if patient_id is None:
                missing_patient += 1
                continue

            external_id = f"{claim_id}:{segment}" if segment else claim_id
            if external_id in seen:
                continue
            seen.add(external_id)

            if external_id in existing:
                updated += 1
            else:
                created += 1

            start_time = (
                parse_datetime(value(row, "CLM_ADMSN_DT"))
                or parse_datetime(value(row, "CLM_FROM_DT"))
            )
            end_time = (
                parse_datetime(value(row, "NCH_BENE_DSCHRG_DT"))
                or parse_datetime(value(row, "CLM_THRU_DT"))
            )

            batch.append(
                {
                    "patient_id": patient_id,
                    "external_id": external_id,
                    "source_system": SOURCE_SYSTEM,
                    "encounter_type": "inpatient",
                    "status": "finished" if end_time else "in-progress",
                    "start_time": start_time,
                    "end_time": end_time,
                    "location": value(row, "PRVDR_NUM") or None,
                }
            )

            if len(batch) >= BATCH_SIZE:
                upsert_encounters(db, batch)
                batch.clear()
                print(f"Inpatient claims processed: {processed:,}")

    upsert_encounters(db, batch)
    return created, updated, missing_patient, missing_claim


def main() -> None:
    beneficiary_path, inpatient_path = find_files()
    print(f"Beneficiary file: {beneficiary_path}")
    print(f"Inpatient file: {inpatient_path}")

    db = SessionLocal()
    try:
        p_created, p_updated, p_skipped = import_patients(db, beneficiary_path)
        e_created, e_updated, e_missing_patient, e_missing_claim = (
            import_encounters(db, inpatient_path)
        )

        patient_total = db.scalar(
            select(func.count(Patient.id)).where(
                Patient.source_system == SOURCE_SYSTEM
            )
        )
        encounter_total = db.scalar(
            select(func.count(Encounter.id)).where(
                Encounter.source_system == SOURCE_SYSTEM
            )
        )

        print()
        print("CMS DE-SynPUF patient and encounter import completed")
        print(f"Patients created: {p_created:,}")
        print(f"Patients updated: {p_updated:,}")
        print(f"Patient rows skipped because ID was missing: {p_skipped:,}")
        print(f"CMS patients in database: {patient_total:,}")
        print(f"Encounters created: {e_created:,}")
        print(f"Encounters updated: {e_updated:,}")
        print(f"Claims skipped because patient was missing: {e_missing_patient:,}")
        print(f"Claims skipped because claim ID was missing: {e_missing_claim:,}")
        print(f"CMS encounters in database: {encounter_total:,}")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
