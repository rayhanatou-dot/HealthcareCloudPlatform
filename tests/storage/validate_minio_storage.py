import csv
import os
from pathlib import Path

from dotenv import load_dotenv
from minio import Minio


BASE_DIR = Path(__file__).resolve().parents[2]

load_dotenv(BASE_DIR / ".env")


RESULT_FILE = (
    BASE_DIR /
    "tests" /
    "storage" /
    "minio_validation_results.csv"
)


def main():

    results = []

    try:

        client = Minio(
            "localhost:9000",
            access_key=os.getenv("MINIO_ROOT_USER"),
            secret_key=os.getenv("MINIO_ROOT_PASSWORD"),
            secure=False,
        )


        bucket = os.getenv(
            "MINIO_BUCKET_NAME",
            "healthcare-files"
        )


        exists = client.bucket_exists(bucket)


        results.append(
            {
                "Test": "Bucket existence",
                "Expected": "True",
                "Actual": str(exists),
                "Passed": exists,
            }
        )


        if exists:

            objects = list(
                client.list_objects(
                    bucket,
                    recursive=True
                )
            )

            results.append(
                {
                    "Test": "Bucket access",
                    "Expected": "No error",
                    "Actual": f"{len(objects)} objects found",
                    "Passed": True,
                }
            )


    except Exception as e:

        results.append(
            {
                "Test": "MinIO exception",
                "Expected": "No error",
                "Actual": str(e),
                "Passed": False,
            }
        )


    RESULT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )


    with open(
        RESULT_FILE,
        "w",
        newline="",
        encoding="utf-8"
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=[
                "Test",
                "Expected",
                "Actual",
                "Passed",
            ]
        )

        writer.writeheader()
        writer.writerows(results)


    failed = [
        r for r in results
        if not r["Passed"]
    ]


    print("=== MINIO VALIDATION SUMMARY ===")
    print("Total:", len(results))
    print("Failed:", len(failed))
    print("Results:", RESULT_FILE)


    if failed:
        exit(1)



if __name__ == "__main__":
    main()