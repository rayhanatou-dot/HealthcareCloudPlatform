import csv
import hashlib

from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.patient import Patient
from app.models.encounter import Encounter
from app.models.prescription import Prescription


SYNTHEA_SOURCE_SYSTEM = "synthea"



def clean_optional_string(value):

    if value is None:
        return None

    value = value.strip()

    if value == "":
        return None

    return value



def parse_optional_datetime(value):

    value = clean_optional_string(value)

    if value is None:
        return None


    value = value.replace(
        "Z",
        "+00:00"
    )


    dt = datetime.fromisoformat(value)


    if dt.tzinfo:

        dt = (
            dt
            .astimezone(timezone.utc)
            .replace(tzinfo=None)
        )


    return dt



def parse_optional_date(value):

    dt = parse_optional_datetime(value)

    if dt is None:
        return None

    return dt.date()



def build_medication_external_id(row):

    raw = "|".join(
        [
            clean_optional_string(row.get("START")) or "",
            clean_optional_string(row.get("PATIENT")) or "",
            clean_optional_string(row.get("ENCOUNTER")) or "",
            clean_optional_string(row.get("CODE")) or "",
            clean_optional_string(row.get("DESCRIPTION")) or "",
        ]
    )


    digest = hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()


    return (
        f"synthea-medication-{digest}"
    )



def find_patient(
    db,
    synthea_id
):

    stmt = select(Patient).where(
        Patient.source_system == SYNTHEA_SOURCE_SYSTEM,
        Patient.external_id == synthea_id
    )

    return db.scalar(stmt)



def find_encounter(
    db,
    synthea_id
):

    if not synthea_id:
        return None


    stmt = select(Encounter).where(
        Encounter.source_system == SYNTHEA_SOURCE_SYSTEM,
        Encounter.external_id == synthea_id
    )


    return db.scalar(stmt)



def find_existing(
    db,
    external_id
):

    stmt = select(Prescription).where(
        Prescription.source_system == SYNTHEA_SOURCE_SYSTEM,
        Prescription.external_id == external_id
    )


    return db.scalar(stmt)



def create_or_update_medication(
    db,
    row
):

    patient_id = clean_optional_string(
        row.get("PATIENT")
    )


    if patient_id is None:

        return False, "missing_patient"



    patient = find_patient(
        db,
        patient_id
    )


    if patient is None:

        return False, "patient_not_found"



    encounter = find_encounter(
        db,
        row.get("ENCOUNTER")
    )



    external_id = build_medication_external_id(
        row
    )



    existing = find_existing(
        db,
        external_id
    )



    start_date = parse_optional_date(
        row.get("START")
    )


    end_date = parse_optional_date(
        row.get("STOP")
    )



    reason = clean_optional_string(
        row.get("REASONDESCRIPTION")
    )



    status = (
        "finished"
        if end_date
        else "active"
    )



    data = {

        "patient_id": patient.id,

        "encounter_id":
            encounter.id
            if encounter
            else None,

        "external_id": external_id,

        "source_system":
            SYNTHEA_SOURCE_SYSTEM,

        "medication_code":
            clean_optional_string(
                row.get("CODE")
            ),

        "code_system":
            "RxNorm",

        "medication_name":
            row.get("DESCRIPTION"),

        "instructions":
            reason,

        "status":
            status,

        "authored_at":
            parse_optional_datetime(
                row.get("START")
            ),

        "start_date":
            start_date,

        "end_date":
            end_date,

    }



    if existing:

        for key,value in data.items():

            setattr(
                existing,
                key,
                value
            )


        return False, None



    prescription = Prescription(
        **data
    )


    db.add(
        prescription
    )


    return True, None




def import_synthea_medications(
    db,
    csv_file_path
):

    created = 0
    updated = 0
    skipped = 0

    reasons = {}

    batch_size = 1000

    processed = 0

    seen_ids = set()



    with csv_file_path.open(
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as file:


        reader = csv.DictReader(file)



        for row in reader:


            ext_id = build_medication_external_id(
                row
            )


            if ext_id in seen_ids:

                skipped += 1

                continue


            seen_ids.add(ext_id)



            is_created, reason = (
                create_or_update_medication(
                    db,
                    row
                )
            )


            processed += 1



            if reason:

                skipped += 1

                reasons[reason] = (
                    reasons.get(reason,0)+1
                )

                continue



            if is_created:

                created += 1

            else:

                updated += 1



            if processed % batch_size == 0:

                db.commit()

                seen_ids.clear()

                print(
                    f"Processed {processed} medications..."
                )



    db.commit()


    return {

        "created": created,

        "updated": updated,

        "skipped": skipped,

        "skip_reasons": reasons

    }




if __name__ == "__main__":


    from app.db.session import SessionLocal



    csv_path = (

        Path(__file__)
        .resolve()
        .parents[4]

        / "datasets"
        / "synthea"
        / "csv"
        / "medications.csv"

    )



    print(
        f"Loading Synthea medications file: {csv_path}"
    )


    db = SessionLocal()



    try:


        result = import_synthea_medications(
            db,
            csv_path
        )


        print(
            "Synthea medication import completed"
        )


        print(result)



    finally:

        db.close()