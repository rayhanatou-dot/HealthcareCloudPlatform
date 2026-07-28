import csv
import os
from pathlib import Path


DEFAULT_SYNTHEA_CSV_DIR = Path(
    os.getenv(
        "SYNTHEA_CSV_DIR",
        "/datasets/synthea/csv",
    )
)


EXPECTED_FILES = {
    "patients.csv": [
        "Id",
        "FIRST",
        "LAST",
        "BIRTHDATE",
        "GENDER",
    ],
    "encounters.csv": [
        "Id",
        "PATIENT",
        "START",
        "ENCOUNTERCLASS",
    ],
    "observations.csv": [
        "DATE",
        "PATIENT",
        "CODE",
        "DESCRIPTION",
        "VALUE",
        "UNITS",
    ],
    "medications.csv": [
        "START",
        "PATIENT",
        "CODE",
        "DESCRIPTION",
    ],
}


def count_data_rows(
    file_path: Path,
) -> int:
    with file_path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as csv_file:
        row_count = sum(
            1 for _ in csv_file
        )

    return max(
        row_count - 1,
        0,
    )


def read_headers(
    file_path: Path,
) -> list[str]:
    with file_path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as csv_file:
        reader = csv.reader(
            csv_file
        )

        try:
            return next(reader)

        except StopIteration:
            return []


def check_file(
    csv_dir: Path,
    file_name: str,
    required_headers: list[str],
) -> bool:
    file_path = csv_dir / file_name

    if not file_path.exists():
        print(
            f"[MISSING] {file_name}"
        )
        return False

    headers = read_headers(
        file_path
    )

    missing_headers = [
        header
        for header in required_headers
        if header not in headers
    ]

    row_count = count_data_rows(
        file_path
    )

    if missing_headers:
        print(
            f"[INVALID] {file_name}"
        )
        print(
            f"          Missing headers: {missing_headers}"
        )
        print(
            f"          Found headers: {headers}"
        )
        return False

    print(
        f"[OK] {file_name} | rows={row_count}"
    )

    return True


def main():
    csv_dir = DEFAULT_SYNTHEA_CSV_DIR

    print(
        "Synthea CSV directory:",
        csv_dir,
    )

    if not csv_dir.exists():
        print(
            "[ERROR] Directory does not exist."
        )
        return

    all_ok = True

    for file_name, required_headers in EXPECTED_FILES.items():
        file_ok = check_file(
            csv_dir=csv_dir,
            file_name=file_name,
            required_headers=required_headers,
        )

        all_ok = all_ok and file_ok

    if all_ok:
        print(
            "[SUCCESS] All required Synthea CSV files are ready."
        )
    else:
        print(
            "[FAILED] Some Synthea CSV files are missing or invalid."
        )


if __name__ == "__main__":
    main()