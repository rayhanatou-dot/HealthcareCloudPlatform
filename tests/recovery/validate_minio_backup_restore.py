from __future__ import annotations

import csv
import hashlib
import json
import shutil
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from minio import Minio
from minio.error import S3Error


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / ".env"
RECOVERY_DIR = PROJECT_ROOT / "tests" / "recovery"

RESULTS_FILE = RECOVERY_DIR / "minio_backup_restore_results.csv"
SUMMARY_FILE = RECOVERY_DIR / "minio_backup_restore_summary.txt"


def read_env_value(
    name: str,
    default: str | None = None,
) -> str:
    if ENV_FILE.exists():
        for raw_line in ENV_FILE.read_text(
            encoding="utf-8-sig"
        ).splitlines():
            line = raw_line.strip()

            if (
                not line
                or line.startswith("#")
                or "=" not in line
            ):
                continue

            key, value = line.split("=", 1)

            if key.strip() == name:
                return (
                    value.strip()
                    .strip('"')
                    .strip("'")
                )

    if default is not None:
        return default

    raise RuntimeError(
        f"Missing environment variable: {name}"
    )


def resolve_endpoint() -> str:
    endpoint = read_env_value(
        "MINIO_ENDPOINT",
        "localhost:9000",
    )

    endpoint = (
        endpoint.replace("http://", "")
        .replace("https://", "")
        .rstrip("/")
    )

    host = endpoint.split(":", 1)[0].lower()

    if host in {
        "minio",
        "healthcare_minio",
        "healthcare-minio",
    }:
        port = read_env_value(
            "MINIO_API_PORT",
            "9000",
        )
        endpoint = f"localhost:{port}"

    return endpoint


def create_client() -> Minio:
    secure = read_env_value(
        "MINIO_SECURE",
        "false",
    ).lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

    return Minio(
        endpoint=resolve_endpoint(),
        access_key=read_env_value(
            "MINIO_ROOT_USER"
        ),
        secret_key=read_env_value(
            "MINIO_ROOT_PASSWORD"
        ),
        secure=secure,
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as file_handle:
        for chunk in iter(
            lambda: file_handle.read(
                1024 * 1024
            ),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest()


def add_result(
    results: list[dict[str, Any]],
    test: str,
    expected: str,
    actual: str,
    passed: bool,
) -> None:
    results.append(
        {
            "Test": test,
            "Expected": expected,
            "Actual": actual,
            "Passed": passed,
        }
    )

    print(
        f"{test:<40} "
        f"{'PASS' if passed else 'FAIL'} "
        f"(expected {expected}, got {actual})"
    )


def safe_temp_bucket_name(
    source_bucket: str,
) -> str:
    suffix = uuid.uuid4().hex[:8]
    base = (
        source_bucket.lower()
        .replace("_", "-")
    )

    candidate = (
        f"{base}-restore-test-{suffix}"
    )

    return candidate[:63].rstrip("-")


def cleanup_bucket(
    client: Minio,
    bucket_name: str,
) -> bool:
    try:
        if not client.bucket_exists(
            bucket_name
        ):
            return True

        objects = list(
            client.list_objects(
                bucket_name,
                recursive=True,
            )
        )

        for item in objects:
            client.remove_object(
                bucket_name,
                item.object_name,
            )

        client.remove_bucket(
            bucket_name
        )

        return not client.bucket_exists(
            bucket_name
        )

    except Exception:
        return False


def main() -> int:
    RECOVERY_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    timestamp = datetime.now(
        timezone.utc
    ).strftime("%Y%m%d_%H%M%S")

    source_bucket = read_env_value(
        "MINIO_BUCKET_NAME",
        "healthcare-files",
    )
    temp_bucket = safe_temp_bucket_name(
        source_bucket
    )

    backup_root = (
        RECOVERY_DIR
        / f"minio_backup_{timestamp}"
    )
    object_dir = backup_root / "objects"
    manifest_file = (
        backup_root
        / "minio_backup_manifest.json"
    )
    object_csv = (
        backup_root
        / "minio_backup_objects.csv"
    )

    results: list[dict[str, Any]] = []
    manifest: dict[str, Any] = {
        "created_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "endpoint": resolve_endpoint(),
        "source_bucket": source_bucket,
        "temporary_restore_bucket": temp_bucket,
        "backup_directory": str(
            backup_root
        ),
        "source_object_count": 0,
        "source_total_size_bytes": 0,
        "restored_object_count": 0,
        "restored_total_size_bytes": 0,
        "objects": [],
        "temporary_bucket_removed": False,
    }

    client = create_client()
    execution_error: Exception | None = None

    try:
        print("=== MINIO PRE-FLIGHT ===")

        source_exists = client.bucket_exists(
            source_bucket
        )

        add_result(
            results,
            "Source bucket accessible",
            "present",
            (
                "present"
                if source_exists
                else "missing"
            ),
            source_exists,
        )

        if not source_exists:
            raise RuntimeError(
                "The configured MinIO bucket "
                "does not exist."
            )

        source_objects = list(
            client.list_objects(
                source_bucket,
                recursive=True,
            )
        )

        manifest["source_object_count"] = len(
            source_objects
        )
        manifest["source_total_size_bytes"] = sum(
            int(item.size or 0)
            for item in source_objects
        )

        add_result(
            results,
            "Source object inventory",
            "completed",
            f"{len(source_objects)} objects",
            True,
        )

        backup_root.mkdir(
            parents=True,
            exist_ok=False,
        )
        object_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        print("\n=== MINIO BACKUP ===")

        backed_up_objects: list[
            dict[str, Any]
        ] = []

        for position, item in enumerate(
            source_objects,
            start=1,
        ):
            stat = client.stat_object(
                source_bucket,
                item.object_name,
            )

            object_hash = hashlib.sha256(
                item.object_name.encode(
                    "utf-8"
                )
            ).hexdigest()

            local_file = (
                object_dir
                / f"{object_hash}.bin"
            )

            response = client.get_object(
                source_bucket,
                item.object_name,
            )

            try:
                with local_file.open(
                    "wb"
                ) as file_handle:
                    for chunk in response.stream(
                        1024 * 1024
                    ):
                        file_handle.write(chunk)
            finally:
                response.close()
                response.release_conn()

            local_size = local_file.stat().st_size
            checksum = sha256_file(
                local_file
            )

            record = {
                "position": position,
                "object_name": item.object_name,
                "backup_file": str(
                    local_file.relative_to(
                        backup_root
                    )
                ),
                "size_bytes": local_size,
                "sha256": checksum,
                "etag": str(
                    stat.etag or ""
                ).strip('"'),
                "content_type": (
                    stat.content_type
                    or "application/octet-stream"
                ),
                "last_modified": (
                    stat.last_modified.isoformat()
                    if stat.last_modified
                    else None
                ),
            }

            backed_up_objects.append(
                record
            )

            add_result(
                results,
                (
                    "Backup object "
                    f"{position}/{len(source_objects)}"
                ),
                f"{int(item.size or 0)} bytes",
                f"{local_size} bytes",
                local_size
                == int(item.size or 0),
            )

        manifest["objects"] = (
            backed_up_objects
        )

        manifest_file.write_text(
            json.dumps(
                manifest,
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        object_fields = [
            "position",
            "object_name",
            "backup_file",
            "size_bytes",
            "sha256",
            "etag",
            "content_type",
            "last_modified",
        ]

        with object_csv.open(
            "w",
            newline="",
            encoding="utf-8-sig",
        ) as csv_file:
            writer = csv.DictWriter(
                csv_file,
                fieldnames=object_fields,
            )
            writer.writeheader()
            writer.writerows(
                backed_up_objects
            )

        backup_file_count = len(
            list(
                object_dir.glob("*.bin")
            )
        )

        add_result(
            results,
            "Backup object count",
            str(len(source_objects)),
            str(backup_file_count),
            backup_file_count
            == len(source_objects),
        )

        backed_up_total_size = sum(
            int(record["size_bytes"])
            for record in backed_up_objects
        )

        add_result(
            results,
            "Backup total size",
            str(
                manifest[
                    "source_total_size_bytes"
                ]
            ),
            str(backed_up_total_size),
            backed_up_total_size
            == manifest[
                "source_total_size_bytes"
            ],
        )

        print("\n=== TEMPORARY MINIO RESTORE ===")

        if client.bucket_exists(
            temp_bucket
        ):
            if not cleanup_bucket(
                client,
                temp_bucket,
            ):
                raise RuntimeError(
                    "Unable to remove an existing "
                    "temporary restore bucket."
                )

        client.make_bucket(
            temp_bucket
        )

        add_result(
            results,
            "Temporary bucket creation",
            "created",
            "created",
            True,
        )

        for record in backed_up_objects:
            local_file = (
                backup_root
                / record["backup_file"]
            )

            client.fput_object(
                temp_bucket,
                record["object_name"],
                str(local_file),
                content_type=record[
                    "content_type"
                ],
            )

        restored_objects = list(
            client.list_objects(
                temp_bucket,
                recursive=True,
            )
        )

        restored_count = len(
            restored_objects
        )
        restored_total_size = sum(
            int(item.size or 0)
            for item in restored_objects
        )

        manifest[
            "restored_object_count"
        ] = restored_count
        manifest[
            "restored_total_size_bytes"
        ] = restored_total_size

        add_result(
            results,
            "Restored object count",
            str(len(backed_up_objects)),
            str(restored_count),
            restored_count
            == len(backed_up_objects),
        )

        add_result(
            results,
            "Restored total size",
            str(backed_up_total_size),
            str(restored_total_size),
            restored_total_size
            == backed_up_total_size,
        )

        restored_by_name = {
            item.object_name: item
            for item in restored_objects
        }

        verified_objects = 0

        for position, record in enumerate(
            backed_up_objects,
            start=1,
        ):
            object_name = record[
                "object_name"
            ]

            if object_name not in restored_by_name:
                add_result(
                    results,
                    (
                        "Restore integrity "
                        f"{position}/"
                        f"{len(backed_up_objects)}"
                    ),
                    "object present",
                    "object missing",
                    False,
                )
                continue

            response = client.get_object(
                temp_bucket,
                object_name,
            )
            digest = hashlib.sha256()
            restored_size = 0

            try:
                for chunk in response.stream(
                    1024 * 1024
                ):
                    digest.update(chunk)
                    restored_size += len(chunk)
            finally:
                response.close()
                response.release_conn()

            restored_hash = digest.hexdigest()
            passed = (
                restored_hash
                == record["sha256"]
                and restored_size
                == int(
                    record[
                        "size_bytes"
                    ]
                )
            )

            if passed:
                verified_objects += 1

            add_result(
                results,
                (
                    "Restore integrity "
                    f"{position}/"
                    f"{len(backed_up_objects)}"
                ),
                record["sha256"],
                restored_hash,
                passed,
            )

        add_result(
            results,
            "All restored objects verified",
            str(len(backed_up_objects)),
            str(verified_objects),
            verified_objects
            == len(backed_up_objects),
        )

    except Exception as exc:
        execution_error = exc

        print(
            f"\nMINIO RECOVERY ERROR: {exc}",
            file=sys.stderr,
        )

        add_result(
            results,
            "Validation execution",
            "successful",
            str(exc),
            False,
        )

    finally:
        print("\n=== MINIO CLEANUP ===")

        cleanup_passed = cleanup_bucket(
            client,
            temp_bucket,
        )

        manifest[
            "temporary_bucket_removed"
        ] = cleanup_passed

        add_result(
            results,
            "Temporary bucket cleanup",
            "removed",
            (
                "removed"
                if cleanup_passed
                else "not removed"
            ),
            cleanup_passed,
        )

        if backup_root.exists():
            manifest_file.write_text(
                json.dumps(
                    manifest,
                    indent=2,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

        with RESULTS_FILE.open(
            "w",
            newline="",
            encoding="utf-8-sig",
        ) as csv_file:
            writer = csv.DictWriter(
                csv_file,
                fieldnames=[
                    "Test",
                    "Expected",
                    "Actual",
                    "Passed",
                ],
            )
            writer.writeheader()
            writer.writerows(results)

    failed = [
        result
        for result in results
        if not result["Passed"]
    ]

    summary_lines = [
        "MinIO Backup and Restore Validation",
        "===================================",
        f"Endpoint: {manifest['endpoint']}",
        (
            "Source bucket: "
            f"{source_bucket}"
        ),
        (
            "Source objects: "
            f"{manifest['source_object_count']}"
        ),
        (
            "Source size: "
            f"{manifest['source_total_size_bytes']} bytes"
        ),
        (
            "Restored objects: "
            f"{manifest['restored_object_count']}"
        ),
        (
            "Restored size: "
            f"{manifest['restored_total_size_bytes']} bytes"
        ),
        f"Backup directory: {backup_root}",
        (
            "Temporary bucket removed: "
            f"{manifest['temporary_bucket_removed']}"
        ),
        f"Total checks: {len(results)}",
        (
            "Passed checks: "
            f"{len(results) - len(failed)}"
        ),
        f"Failed checks: {len(failed)}",
    ]

    SUMMARY_FILE.write_text(
        "\n".join(summary_lines) + "\n",
        encoding="utf-8",
    )

    print(
        "\n=== MINIO RECOVERY SUMMARY ==="
    )
    print("Total checks :", len(results))
    print(
        "Passed       :",
        len(results) - len(failed),
    )
    print("Failed       :", len(failed))
    print(
        "Objects      :",
        (
            f"{manifest['restored_object_count']}/"
            f"{manifest['source_object_count']}"
        ),
    )
    print(
        "Source size  :",
        manifest[
            "source_total_size_bytes"
        ],
        "bytes",
    )
    print(
        "Restored size:",
        manifest[
            "restored_total_size_bytes"
        ],
        "bytes",
    )
    print("Backup       :", backup_root)
    print("Manifest     :", manifest_file)
    print("Results CSV  :", RESULTS_FILE)
    print("Summary      :", SUMMARY_FILE)

    return (
        1
        if failed or execution_error
        else 0
    )


if __name__ == "__main__":
    sys.exit(main())
