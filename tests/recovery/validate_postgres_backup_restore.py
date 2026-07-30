from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / ".env"
RECOVERY_DIR = PROJECT_ROOT / "tests" / "recovery"

RESULTS_FILE = (
    RECOVERY_DIR
    / "postgres_backup_restore_results.csv"
)
MANIFEST_FILE = (
    RECOVERY_DIR
    / "postgres_backup_manifest.json"
)
SUMMARY_FILE = (
    RECOVERY_DIR
    / "postgres_backup_restore_summary.txt"
)


def read_env_value(
    name: str,
    default: str,
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

    return default


POSTGRES_USER = read_env_value(
    "POSTGRES_USER",
    "healthcare_user",
)
SOURCE_DATABASE = read_env_value(
    "POSTGRES_DB",
    "healthcare_cloud_db",
)
RESTORE_DATABASE = (
    f"{SOURCE_DATABASE}_restore_test"
)


def run_command(
    command: list[str],
    *,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    if check and completed.returncode != 0:
        message = (
            completed.stderr.strip()
            or completed.stdout.strip()
            or "Unknown command failure"
        )
        raise RuntimeError(
            f"Command failed: {' '.join(command)}\n"
            f"{message}"
        )

    return completed


def docker_compose(
    *arguments: str,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return run_command(
        [
            "docker",
            "compose",
            *arguments,
        ],
        check=check,
    )


def psql_scalar(
    database: str,
    sql: str,
) -> str:
    completed = docker_compose(
        "exec",
        "-T",
        "postgres",
        "psql",
        "-U",
        POSTGRES_USER,
        "-d",
        database,
        "-tA",
        "-P",
        "pager=off",
        "-v",
        "ON_ERROR_STOP=1",
        "-c",
        sql,
    )

    return completed.stdout.strip()


def quote_identifier(
    identifier: str,
) -> str:
    return '"' + identifier.replace(
        '"',
        '""',
    ) + '"'


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
        f"{test:<42} "
        f"{'PASS' if passed else 'FAIL'} "
        f"(expected {expected}, got {actual})"
    )


def write_outputs(
    results: list[dict[str, Any]],
    manifest: dict[str, Any],
) -> None:
    RECOVERY_DIR.mkdir(
        parents=True,
        exist_ok=True,
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

    MANIFEST_FILE.write_text(
        json.dumps(
            manifest,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    failed = [
        item
        for item in results
        if not item["Passed"]
    ]

    summary_lines = [
        "PostgreSQL Backup and Restore Validation",
        "========================================",
        f"Source database: {SOURCE_DATABASE}",
        f"Restore database: {RESTORE_DATABASE}",
        (
            "Backup file: "
            f"{manifest.get('backup_file', '')}"
        ),
        (
            "Backup size: "
            f"{manifest.get('backup_size_bytes', 0)} bytes"
        ),
        (
            "SHA-256: "
            f"{manifest.get('backup_sha256', '')}"
        ),
        (
            "Tables verified: "
            f"{manifest.get('tables_verified', 0)}"
        ),
        (
            "Tables matched: "
            f"{manifest.get('tables_matched', 0)}"
        ),
        f"Total checks: {len(results)}",
        (
            "Passed checks: "
            f"{len(results) - len(failed)}"
        ),
        f"Failed checks: {len(failed)}",
        (
            "Temporary restore database removed: "
            f"{manifest.get('restore_database_removed', False)}"
        ),
    ]

    SUMMARY_FILE.write_text(
        "\n".join(summary_lines) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    RECOVERY_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    timestamp = datetime.now(
        timezone.utc
    ).strftime("%Y%m%d_%H%M%S")

    container_dump = (
        f"/tmp/{SOURCE_DATABASE}_{timestamp}.dump"
    )
    host_dump = (
        RECOVERY_DIR
        / f"{SOURCE_DATABASE}_{timestamp}.dump"
    )

    results: list[dict[str, Any]] = []
    manifest: dict[str, Any] = {
        "created_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "source_database": SOURCE_DATABASE,
        "restore_database": RESTORE_DATABASE,
        "postgres_user": POSTGRES_USER,
        "backup_file": str(host_dump),
        "backup_size_bytes": 0,
        "backup_sha256": "",
        "public_table_count": 0,
        "constraint_count": 0,
        "index_count": 0,
        "tables_verified": 0,
        "tables_matched": 0,
        "mismatched_tables": [],
        "restore_database_removed": False,
    }

    container_id = ""
    restore_created = False
    execution_error: Exception | None = None

    try:
        print("=== PRE-FLIGHT ===")

        container_id = docker_compose(
            "ps",
            "-q",
            "postgres",
        ).stdout.strip()

        container_running = bool(
            container_id
        )

        add_result(
            results,
            "PostgreSQL container",
            "running",
            (
                "running"
                if container_running
                else "not running"
            ),
            container_running,
        )

        if not container_running:
            raise RuntimeError(
                "PostgreSQL container is not running."
            )

        source_table_count = int(
            psql_scalar(
                SOURCE_DATABASE,
                (
                    "SELECT COUNT(*) "
                    "FROM pg_tables "
                    "WHERE schemaname = 'public';"
                ),
            )
        )
        source_constraint_count = int(
            psql_scalar(
                SOURCE_DATABASE,
                (
                    "SELECT COUNT(*) "
                    "FROM pg_constraint "
                    "WHERE connamespace = "
                    "'public'::regnamespace;"
                ),
            )
        )
        source_index_count = int(
            psql_scalar(
                SOURCE_DATABASE,
                (
                    "SELECT COUNT(*) "
                    "FROM pg_indexes "
                    "WHERE schemaname = 'public';"
                ),
            )
        )

        manifest["public_table_count"] = (
            source_table_count
        )
        manifest["constraint_count"] = (
            source_constraint_count
        )
        manifest["index_count"] = (
            source_index_count
        )

        print("\n=== CONSISTENT LOGICAL BACKUP ===")

        docker_compose(
            "exec",
            "-T",
            "postgres",
            "pg_dump",
            "-U",
            POSTGRES_USER,
            "-d",
            SOURCE_DATABASE,
            "--format=custom",
            "--compress=6",
            "--no-owner",
            "--no-privileges",
            f"--file={container_dump}",
        )

        run_command(
            [
                "docker",
                "cp",
                f"{container_id}:{container_dump}",
                str(host_dump),
            ]
        )

        backup_exists = host_dump.exists()
        backup_size = (
            host_dump.stat().st_size
            if backup_exists
            else 0
        )

        manifest["backup_size_bytes"] = (
            backup_size
        )

        add_result(
            results,
            "Backup file created",
            "non-empty file",
            f"{backup_size} bytes",
            backup_exists and backup_size > 0,
        )

        if not backup_exists or backup_size <= 0:
            raise RuntimeError(
                "Backup file is missing or empty."
            )

        digest = hashlib.sha256()

        with host_dump.open("rb") as backup_file:
            for chunk in iter(
                lambda: backup_file.read(
                    1024 * 1024
                ),
                b"",
            ):
                digest.update(chunk)

        backup_hash = digest.hexdigest()
        manifest["backup_sha256"] = backup_hash

        add_result(
            results,
            "Backup SHA-256",
            "64 hexadecimal characters",
            backup_hash,
            (
                len(backup_hash) == 64
                and all(
                    character
                    in "0123456789abcdef"
                    for character in backup_hash
                )
            ),
        )

        archive_check = docker_compose(
            "exec",
            "-T",
            "postgres",
            "pg_restore",
            "--list",
            container_dump,
            check=False,
        )

        archive_readable = (
            archive_check.returncode == 0
        )

        add_result(
            results,
            "Archive readability",
            "readable pg_restore archive",
            (
                "readable"
                if archive_readable
                else "unreadable"
            ),
            archive_readable,
        )

        if not archive_readable:
            raise RuntimeError(
                "The pg_restore archive is unreadable."
            )

        print("\n=== TEMPORARY RESTORE ===")

        docker_compose(
            "exec",
            "-T",
            "postgres",
            "psql",
            "-U",
            POSTGRES_USER,
            "-d",
            "postgres",
            "-v",
            "ON_ERROR_STOP=1",
            "-c",
            (
                "SELECT pg_terminate_backend(pid) "
                "FROM pg_stat_activity "
                f"WHERE datname = '{RESTORE_DATABASE}' "
                "AND pid <> pg_backend_pid();"
            ),
            check=False,
        )

        docker_compose(
            "exec",
            "-T",
            "postgres",
            "dropdb",
            "-U",
            POSTGRES_USER,
            "--if-exists",
            RESTORE_DATABASE,
        )

        docker_compose(
            "exec",
            "-T",
            "postgres",
            "createdb",
            "-U",
            POSTGRES_USER,
            RESTORE_DATABASE,
        )
        restore_created = True

        docker_compose(
            "exec",
            "-T",
            "postgres",
            "pg_restore",
            "-U",
            POSTGRES_USER,
            "-d",
            RESTORE_DATABASE,
            "--no-owner",
            "--no-privileges",
            "--exit-on-error",
            container_dump,
        )

        add_result(
            results,
            "Temporary restore",
            "successful",
            "successful",
            True,
        )

        restored_table_count = int(
            psql_scalar(
                RESTORE_DATABASE,
                (
                    "SELECT COUNT(*) "
                    "FROM pg_tables "
                    "WHERE schemaname = 'public';"
                ),
            )
        )

        add_result(
            results,
            "Public table count",
            str(source_table_count),
            str(restored_table_count),
            (
                source_table_count
                == restored_table_count
            ),
        )

        restored_constraint_count = int(
            psql_scalar(
                RESTORE_DATABASE,
                (
                    "SELECT COUNT(*) "
                    "FROM pg_constraint "
                    "WHERE connamespace = "
                    "'public'::regnamespace;"
                ),
            )
        )

        add_result(
            results,
            "Constraint count",
            str(source_constraint_count),
            str(restored_constraint_count),
            (
                source_constraint_count
                == restored_constraint_count
            ),
        )

        restored_index_count = int(
            psql_scalar(
                RESTORE_DATABASE,
                (
                    "SELECT COUNT(*) "
                    "FROM pg_indexes "
                    "WHERE schemaname = 'public';"
                ),
            )
        )

        add_result(
            results,
            "Index count",
            str(source_index_count),
            str(restored_index_count),
            (
                source_index_count
                == restored_index_count
            ),
        )

        print("\n=== EXACT TABLE ROW COUNTS ===")

        table_output = psql_scalar(
            SOURCE_DATABASE,
            (
                "SELECT tablename "
                "FROM pg_tables "
                "WHERE schemaname = 'public' "
                "ORDER BY tablename;"
            ),
        )

        table_names = [
            line.strip()
            for line in table_output.splitlines()
            if line.strip()
        ]

        matched_tables = 0
        mismatched_tables: list[str] = []

        for table_name in table_names:
            qualified_table = (
                "public."
                + quote_identifier(table_name)
            )

            source_count = int(
                psql_scalar(
                    SOURCE_DATABASE,
                    (
                        "SELECT COUNT(*) FROM "
                        f"{qualified_table};"
                    ),
                )
            )
            restored_count = int(
                psql_scalar(
                    RESTORE_DATABASE,
                    (
                        "SELECT COUNT(*) FROM "
                        f"{qualified_table};"
                    ),
                )
            )

            passed = (
                source_count == restored_count
            )

            if passed:
                matched_tables += 1
            else:
                mismatched_tables.append(
                    (
                        f"{table_name}: "
                        f"{source_count} != "
                        f"{restored_count}"
                    )
                )

            add_result(
                results,
                f"Rows: {table_name}",
                str(source_count),
                str(restored_count),
                passed,
            )

        manifest["tables_verified"] = len(
            table_names
        )
        manifest["tables_matched"] = (
            matched_tables
        )
        manifest["mismatched_tables"] = (
            mismatched_tables
        )

    except Exception as exc:
        execution_error = exc
        print(
            f"\nRECOVERY VALIDATION ERROR: {exc}",
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
        print("\n=== CLEANUP ===")

        if restore_created:
            docker_compose(
                "exec",
                "-T",
                "postgres",
                "psql",
                "-U",
                POSTGRES_USER,
                "-d",
                "postgres",
                "-v",
                "ON_ERROR_STOP=1",
                "-c",
                (
                    "SELECT pg_terminate_backend(pid) "
                    "FROM pg_stat_activity "
                    f"WHERE datname = '{RESTORE_DATABASE}' "
                    "AND pid <> pg_backend_pid();"
                ),
                check=False,
            )

            drop_result = docker_compose(
                "exec",
                "-T",
                "postgres",
                "dropdb",
                "-U",
                POSTGRES_USER,
                "--if-exists",
                RESTORE_DATABASE,
                check=False,
            )

            restore_removed = (
                drop_result.returncode == 0
            )
        else:
            restore_removed = True

        manifest[
            "restore_database_removed"
        ] = restore_removed

        add_result(
            results,
            "Temporary database cleanup",
            "removed",
            (
                "removed"
                if restore_removed
                else "not removed"
            ),
            restore_removed,
        )

        if container_id:
            docker_compose(
                "exec",
                "-T",
                "postgres",
                "rm",
                "-f",
                container_dump,
                check=False,
            )

        write_outputs(
            results,
            manifest,
        )

    failed = [
        result
        for result in results
        if not result["Passed"]
    ]

    print(
        "\n=== POSTGRESQL RECOVERY SUMMARY ==="
    )
    print("Total checks :", len(results))
    print(
        "Passed       :",
        len(results) - len(failed),
    )
    print("Failed       :", len(failed))
    print(
        "Tables       :",
        (
            f"{manifest['tables_matched']}/"
            f"{manifest['tables_verified']}"
        ),
    )
    print("Backup       :", host_dump)
    print(
        "SHA-256      :",
        manifest["backup_sha256"],
    )
    print("Results CSV  :", RESULTS_FILE)
    print("Manifest     :", MANIFEST_FILE)
    print("Summary      :", SUMMARY_FILE)

    return (
        1
        if failed or execution_error
        else 0
    )


if __name__ == "__main__":
    sys.exit(main())
