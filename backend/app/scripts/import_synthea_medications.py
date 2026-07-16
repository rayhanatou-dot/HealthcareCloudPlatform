import os
from pathlib import Path

from app.db.session import SessionLocal
from app.services.ingestion.synthea_medication_importer import (
    import_synthea_medications,
)


DEFAULT_SYNTHEA_MEDICATIONS_CSV = Path(
    os.getenv(
        "SYNTHEA_MEDICATIONS_CSV",
        "../datasets/synthea/csv/medications.csv",
    )
)


def main():
    csv_file_path = DEFAULT_SYNTHEA_MEDICATIONS_CSV

    print(
        "Importing Synthea medications from:",
        csv_file_path,
    )

    db = SessionLocal()

    try:
        result = import_synthea_medications(
            db=db,
            csv_file_path=csv_file_path,
        )

        print(
            "[SUCCESS] Synthea medications import completed."
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

        print(
            "Skip reasons:",
            result["skip_reasons"],
        )

    finally:
        db.close()


if __name__ == "__main__":
    main()