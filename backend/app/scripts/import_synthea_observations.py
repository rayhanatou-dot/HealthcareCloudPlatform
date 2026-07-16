import os
from pathlib import Path

from app.db.session import SessionLocal
from app.services.ingestion.synthea_observation_importer import (
    import_synthea_observations,
)


DEFAULT_SYNTHEA_OBSERVATIONS_CSV = Path(
    os.getenv(
        "SYNTHEA_OBSERVATIONS_CSV",
        "../datasets/synthea/csv/observations.csv",
    )
)


def main():
    csv_file_path = DEFAULT_SYNTHEA_OBSERVATIONS_CSV

    print(
        "Importing Synthea observations from:",
        csv_file_path,
    )

    db = SessionLocal()

    try:
        result = import_synthea_observations(
            db=db,
            csv_file_path=csv_file_path,
        )

        print(
            "[SUCCESS] Synthea observations import completed."
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