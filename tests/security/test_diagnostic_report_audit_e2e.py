from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
E2E_TEST = (
    PROJECT_ROOT
    / "tests"
    / "storage"
    / "test_diagnostic_report_e2e.py"
)
OUTPUT_DIR = PROJECT_ROOT / "tests" / "security"
AUDIT_ROWS_JSON = OUTPUT_DIR / "diagnostic_report_audit_rows.json"
AUDIT_ROWS_CSV = OUTPUT_DIR / "diagnostic_report_audit_rows.csv"
RESULTS_CSV = OUTPUT_DIR / "diagnostic_report_audit_results.csv"

POSTGRES_USER = "healthcare_user"
POSTGRES_DB = "healthcare_cloud_db"


def run_command(
    command: list[str],
    *,
    capture: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=capture,
        check=False,
    )


def psql_scalar(sql: str) -> str:
    completed = run_command(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "postgres",
            "psql",
            "-U",
            POSTGRES_USER,
            "-d",
            POSTGRES_DB,
            "-tA",
            "-P",
            "pager=off",
            "-c",
            sql,
        ]
    )

    if completed.returncode != 0:
        raise RuntimeError(
            "PostgreSQL command failed:\n"
            + completed.stderr.strip()
        )

    return completed.stdout.strip()


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

    state = "PASS" if passed else "FAIL"
    print(
        f"{test:<38} {state} "
        f"(expected {expected}, got {actual})"
    )


def action_value(row: dict[str, Any]) -> str:
    for key in (
        "action",
        "event_type",
        "operation",
        "activity",
        "event",
    ):
        value = row.get(key)

        if value is not None:
            return str(value)

    return ""


def flatten_value(value: Any) -> str:
    if value is None:
        return ""

    if isinstance(value, (dict, list)):
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
        )

    return str(value)


def main() -> int:
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    if not E2E_TEST.exists():
        raise RuntimeError(
            f"Missing E2E test: {E2E_TEST}"
        )

    before_audit_id_text = psql_scalar(
        "SELECT COALESCE(MAX(id), 0) "
        "FROM audit_logs;"
    )
    before_audit_id = int(
        before_audit_id_text or "0"
    )

    before_report_count = int(
        psql_scalar(
            "SELECT COUNT(*) "
            "FROM diagnostic_reports;"
        )
    )

    print("=== RUNNING DIAGNOSTIC REPORT E2E ===")

    e2e = run_command(
        [
            sys.executable,
            str(E2E_TEST),
        ]
    )

    if e2e.stdout:
        print(e2e.stdout)

    if e2e.stderr:
        print(
            e2e.stderr,
            file=sys.stderr,
        )

    after_report_count = int(
        psql_scalar(
            "SELECT COUNT(*) "
            "FROM diagnostic_reports;"
        )
    )

    audit_json_text = psql_scalar(
        "SELECT COALESCE("
        "json_agg(row_to_json(t)), "
        "'[]'::json"
        ") "
        "FROM ("
        "SELECT * "
        "FROM audit_logs "
        f"WHERE id > {before_audit_id} "
        "ORDER BY id"
        ") AS t;"
    )

    audit_rows = json.loads(
        audit_json_text or "[]"
    )

    AUDIT_ROWS_JSON.write_text(
        json.dumps(
            audit_rows,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    all_columns = sorted(
        {
            key
            for row in audit_rows
            for key in row.keys()
        }
    )

    with AUDIT_ROWS_CSV.open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as csv_file:
        if all_columns:
            writer = csv.DictWriter(
                csv_file,
                fieldnames=all_columns,
            )
            writer.writeheader()

            for row in audit_rows:
                writer.writerow(
                    {
                        key: flatten_value(
                            row.get(key)
                        )
                        for key in all_columns
                    }
                )
        else:
            csv_file.write(
                "message\nNo new audit rows\n"
            )

    serialized_rows = json.dumps(
        audit_rows,
        ensure_ascii=False,
    ).lower()

    detected_actions = sorted(
        {
            action_value(row)
            for row in audit_rows
            if action_value(row)
        }
    )

    results: list[dict[str, Any]] = []

    add_result(
        results,
        "Diagnostic report E2E test",
        "exit code 0",
        f"exit code {e2e.returncode}",
        e2e.returncode == 0,
    )

    add_result(
        results,
        "New audit records",
        "at least 1",
        str(len(audit_rows)),
        len(audit_rows) >= 1,
    )

    has_login_success = (
        "login_success" in serialized_rows
        or "login success" in serialized_rows
    )

    add_result(
        results,
        "Successful login audit",
        "present",
        (
            "present"
            if has_login_success
            else "missing"
        ),
        has_login_success,
    )

    has_access_denied = any(
        token in serialized_rows
        for token in (
            "access_denied",
            "access denied",
            '"status_code": 403',
            '"status": 403',
        )
    )

    add_result(
        results,
        "Denied access audit",
        "present",
        (
            "present"
            if has_access_denied
            else "missing"
        ),
        has_access_denied,
    )

    has_diagnostic_report = (
        "diagnostic_report" in serialized_rows
        or "diagnostic-report" in serialized_rows
        or "diagnostic report" in serialized_rows
        or "diagnostic_reports" in serialized_rows
    )

    add_result(
        results,
        "Diagnostic report audit context",
        "present",
        (
            "present"
            if has_diagnostic_report
            else "missing"
        ),
        has_diagnostic_report,
    )

    has_read_or_download = any(
        token in serialized_rows
        for token in (
            "download",
            "_read",
            " read",
            '"method": "get"',
            '"http_method": "get"',
        )
    )

    add_result(
        results,
        "Read or download audit",
        "present",
        (
            "present"
            if has_read_or_download
            else "missing"
        ),
        has_read_or_download,
    )

    add_result(
        results,
        "Diagnostic report cleanup",
        str(before_report_count),
        str(after_report_count),
        before_report_count
        == after_report_count,
    )

    with RESULTS_CSV.open(
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

    print("\n=== NEW AUDIT ACTIONS ===")

    if detected_actions:
        for action in detected_actions:
            print(action)
    else:
        print(
            "No action/event column was detected."
        )

    print(
        "\n=== DIAGNOSTIC REPORT AUDIT SUMMARY ==="
    )
    print("Total checks :", len(results))
    print(
        "Passed       :",
        len(results) - len(failed),
    )
    print("Failed       :", len(failed))
    print("Audit rows   :", AUDIT_ROWS_JSON)
    print("Audit CSV    :", AUDIT_ROWS_CSV)
    print("Results CSV  :", RESULTS_CSV)

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
