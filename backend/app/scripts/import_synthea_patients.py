import os
from pathlib import Path

from app.db.session import SessionLocal
from app.services.ingestion.synthea_patient_importer import (
    import_synthea_patients,
)


DEFAULT_SYNTHEA_PATIENTS_CSV = Path(
    os.getenv(
        "SYNTHEA_PATIENTS_CSV",
        "../datasets/synthea/csv/patients.csv",
    )
)


def main():
    csv_file_path = DEFAULT_SYNTHEA_PATIENTS_CSV

    print(
        "Importing Synthea patients from:",
        csv_file_path,
    )

    db = SessionLocal()

    try:
        result = import_synthea_patients(
            db=db,
            csv_file_path=csv_file_path,
        )

        print(
            "[SUCCESS] Synthea patients import completed."
        )

        print(
            "Created:",
            result["created"],
        )

        print(
            "Updated:",
            result["updated"],
        )

        print(
            "Skipped:",
            result["skipped"],
        )

    finally:
        db.close()


if __name__ == "__main__":
    main()