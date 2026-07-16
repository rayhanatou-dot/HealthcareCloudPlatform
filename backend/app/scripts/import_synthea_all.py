import os
from pathlib import Path

from app.db.session import SessionLocal
from app.services.ingestion.synthea_patient_importer import (
    import_synthea_patients,
)
from app.services.ingestion.synthea_encounter_importer import (
    import_synthea_encounters,
)
from app.services.ingestion.synthea_observation_importer import (
    import_synthea_observations,
)
from app.services.ingestion.synthea_medication_importer import (
    import_synthea_medications,
)


DEFAULT_SYNTHEA_CSV_DIR = Path(
    os.getenv(
        "SYNTHEA_CSV_DIR",
        "../datasets/synthea/csv",
    )
)


def print_result(
    name: str,
    result: dict,
):
    print()
    print(f"[{name}]")
    print("Created:", result.get("created", 0))
    print("Updated:", result.get("updated", 0))
    print("Skipped:", result.get("skipped", 0))

    if "skip_reasons" in result:
        print("Skip reasons:", result["skip_reasons"])


def main():
    csv_dir = DEFAULT_SYNTHEA_CSV_DIR

    patients_csv = csv_dir / "patients.csv"
    encounters_csv = csv_dir / "encounters.csv"
    observations_csv = csv_dir / "observations.csv"
    medications_csv = csv_dir / "medications.csv"

    print("Synthea CSV directory:", csv_dir)
    print("Patients CSV:", patients_csv)
    print("Encounters CSV:", encounters_csv)
    print("Observations CSV:", observations_csv)
    print("Medications CSV:", medications_csv)

    db = SessionLocal()

    try:
        print()
        print("Starting Synthea import pipeline...")

        patient_result = import_synthea_patients(
            db=db,
            csv_file_path=patients_csv,
        )

        print_result(
            name="PATIENTS",
            result=patient_result,
        )

        encounter_result = import_synthea_encounters(
            db=db,
            csv_file_path=encounters_csv,
        )

        print_result(
            name="ENCOUNTERS",
            result=encounter_result,
        )

        observation_result = import_synthea_observations(
            db=db,
            csv_file_path=observations_csv,
        )

        print_result(
            name="OBSERVATIONS",
            result=observation_result,
        )

        medication_result = import_synthea_medications(
            db=db,
            csv_file_path=medications_csv,
        )

        print_result(
            name="MEDICATIONS / PRESCRIPTIONS",
            result=medication_result,
        )

        print()
        print("[SUCCESS] Full Synthea import pipeline completed.")

    finally:
        db.close()


if __name__ == "__main__":
    main()