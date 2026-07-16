import os
from pathlib import Path

from app.db.session import SessionLocal
from app.services.ingestion.synthea_encounter_importer import (
    import_synthea_encounters,
)


DEFAULT_SYNTHEA_ENCOUNTERS_CSV = Path(
    os.getenv(
        "SYNTHEA_ENCOUNTERS_CSV",
        "../datasets/synthea/csv/encounters.csv",
    )
)


def main():
    csv_file_path = DEFAULT_SYNTHEA_ENCOUNTERS_CSV

    print(
        "Importing Synthea encounters from:",
        csv_file_path,
    )

    db = SessionLocal()

    try:
        result = import_synthea_encounters(
            db=db,
            csv_file_path=csv_file_path,
        )

        print(
            "[SUCCESS] Synthea encounters import completed."
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