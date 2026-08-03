import csv
import hashlib
import io
import os
import uuid
from pathlib import Path
from dotenv import load_dotenv
from minio import Minio
BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR / ".env")
RESULT_FILES = [
    BASE_DIR
    / "tests"
    / "storage"
    / "minio_validation_results.csv",
    BASE_DIR
    / "tests"
    / "storage"
    / "minio_storage_results.csv",
]
def create_results():
    return [
        {
            "Test": "Bucket existence",
            "Expected": "True",
            "Actual": "Not executed",
            "Passed": False,
        },
        {
            "Test": "Bucket access",
            "Expected": "No error",
            "Actual": "Not executed",
            "Passed": False,
        },
        {
            "Test": "Object upload/download integrity",
            "Expected": "SHA-256 match",
            "Actual": "Not executed",
            "Passed": False,
        },
        {
            "Test": "Object deletion",
            "Expected": "Object absent",
            "Actual": "Not executed",
            "Passed": False,
        },
    ]
def update_result(results, index, actual, passed):
    results[index]["Actual"] = str(actual)
    results[index]["Passed"] = bool(passed)
def write_results(results):
    for result_file in RESULT_FILES:
        result_file.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        with result_file.open(
            "w",
            newline="",
            encoding="utf-8",
        ) as file_handle:
            writer = csv.DictWriter(
                file_handle,
                fieldnames=[
                    "Test",
                    "Expected",
                    "Actual",
                    "Passed",
                ],
            )
            writer.writeheader()
            writer.writerows(results)
def main():
    results = create_results()
    client = None
    bucket = os.getenv(
        "MINIO_BUCKET_NAME",
        "healthcare-files",
    )
    object_name = (
        "validation/"
        f"minio-lifecycle-{uuid.uuid4().hex}.txt"
    )
    object_uploaded = False
    deletion_completed = False
    try:
        client = Minio(
            os.getenv(
                "MINIO_ENDPOINT",
                "localhost:9000",
            ),
            access_key=os.getenv(
                "MINIO_ROOT_USER",
            ),
            secret_key=os.getenv(
                "MINIO_ROOT_PASSWORD",
            ),
            secure=False,
        )
        bucket_exists = client.bucket_exists(bucket)
        update_result(
            results,
            0,
            bucket_exists,
            bucket_exists,
        )
        if not bucket_exists:
            update_result(
                results,
                1,
                "Skipped: bucket does not exist",
                False,
            )
            update_result(
                results,
                2,
                "Skipped: bucket does not exist",
                False,
            )
            update_result(
                results,
                3,
                "Skipped: bucket does not exist",
                False,
            )
        else:
            try:
                objects = list(
                    client.list_objects(
                        bucket,
                        recursive=True,
                    )
                )
                update_result(
                    results,
                    1,
                    f"{len(objects)} objects found",
                    True,
                )
            except Exception as exception:
                update_result(
                    results,
                    1,
                    f"Access error: {exception}",
                    False,
                )
                update_result(
                    results,
                    2,
                    "Skipped: bucket access failed",
                    False,
                )
                update_result(
                    results,
                    3,
                    "Skipped: bucket access failed",
                    False,
                )
            if results[1]["Passed"]:
                test_content = (
                    b"Healthcare Cloud Platform "
                    b"MinIO lifecycle validation"
                )
                expected_hash = hashlib.sha256(
                    test_content
                ).hexdigest()
                try:
                    client.put_object(
                        bucket,
                        object_name,
                        io.BytesIO(test_content),
                        length=len(test_content),
                        content_type="text/plain",
                    )
                    object_uploaded = True
                    response = client.get_object(
                        bucket,
                        object_name,
                    )
                    try:
                        downloaded_content = response.read()
                    finally:
                        response.close()
                        response.release_conn()
                    actual_hash = hashlib.sha256(
                        downloaded_content
                    ).hexdigest()
                    integrity_passed = (
                        expected_hash == actual_hash
                    )
                    update_result(
                        results,
                        2,
                        (
                            "SHA-256 match"
                            if integrity_passed
                            else (
                                f"Expected {expected_hash}; "
                                f"received {actual_hash}"
                            )
                        ),
                        integrity_passed,
                    )
                except Exception as exception:
                    update_result(
                        results,
                        2,
                        f"Transfer error: {exception}",
                        False,
                    )
                    update_result(
                        results,
                        3,
                        "Skipped: transfer validation failed",
                        False,
                    )
                if results[2]["Passed"]:
                    try:
                        client.remove_object(
                            bucket,
                            object_name,
                        )
                        remaining_objects = list(
                            client.list_objects(
                                bucket,
                                prefix=object_name,
                                recursive=True,
                            )
                        )
                        object_absent = all(
                            item.object_name != object_name
                            for item in remaining_objects
                        )
                        deletion_completed = object_absent
                        update_result(
                            results,
                            3,
                            (
                                "Object absent"
                                if object_absent
                                else "Object still present"
                            ),
                            object_absent,
                        )
                    except Exception as exception:
                        update_result(
                            results,
                            3,
                            f"Deletion error: {exception}",
                            False,
                        )
    except Exception as exception:
        for index, result in enumerate(results):
            if result["Actual"] == "Not executed":
                update_result(
                    results,
                    index,
                    f"MinIO exception: {exception}",
                    False,
                )
    finally:
        if (
            client is not None
            and object_uploaded
            and not deletion_completed
        ):
            try:
                client.remove_object(
                    bucket,
                    object_name,
                )
            except Exception:
                pass
    write_results(results)
    failed = [
        result
        for result in results
        if not result["Passed"]
    ]
    print("=== MINIO VALIDATION SUMMARY ===")
    print("Total:", len(results))
    print("Passed:", len(results) - len(failed))
    print("Failed:", len(failed))
    for result_file in RESULT_FILES:
        print("Results:", result_file)
    if failed:
        raise SystemExit(1)
if __name__ == "__main__":
    main()
