from __future__ import annotations

import csv
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = PROJECT_ROOT / "tests" / "final_validation"
OUTPUT_CSV = OUTPUT_DIR / "final_validation_matrix.csv"
OUTPUT_MD = OUTPUT_DIR / "final_validation_matrix.md"
OUTPUT_TXT = OUTPUT_DIR / "final_project_status.txt"


@dataclass
class ValidationItem:
    domain: str
    validation: str
    status: str
    passed_checks: int | None
    total_checks: int | None
    evidence: str
    note: str


def first_existing(candidates: Iterable[Path]) -> Path | None:
    for path in candidates:
        if path.exists():
            return path
    return None


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def bool_value(value: str) -> bool | None:
    normalized = str(value).strip().lower()

    if normalized in {"true", "1", "yes", "pass", "passed"}:
        return True

    if normalized in {"false", "0", "no", "fail", "failed"}:
        return False

    return None


def summarize_boolean_csv(path: Path) -> tuple[int, int] | None:
    rows = read_csv(path)

    if not rows:
        return None

    candidate_columns = [
        "Passed",
        "passed",
        "PASS",
        "Success",
        "success",
        "Valid",
        "valid",
    ]

    column = next(
        (
            name
            for name in candidate_columns
            if name in rows[0]
        ),
        None,
    )

    if column is None:
        return None

    parsed = [
        bool_value(row.get(column, ""))
        for row in rows
    ]
    parsed = [
        value
        for value in parsed
        if value is not None
    ]

    if not parsed:
        return None

    return sum(parsed), len(parsed)


def add_boolean_validation(
    items: list[ValidationItem],
    domain: str,
    validation: str,
    candidates: list[Path],
    expected_total: int | None = None,
    note: str = "",
) -> None:
    path = first_existing(candidates)

    if path is None:
        items.append(
            ValidationItem(
                domain=domain,
                validation=validation,
                status="PENDING",
                passed_checks=None,
                total_checks=expected_total,
                evidence="",
                note="Evidence file not found.",
            )
        )
        return

    summary = summarize_boolean_csv(path)

    if summary is None:
        items.append(
            ValidationItem(
                domain=domain,
                validation=validation,
                status="REVIEW",
                passed_checks=None,
                total_checks=expected_total,
                evidence=str(path.relative_to(PROJECT_ROOT)),
                note="Evidence exists but its pass/fail column could not be parsed.",
            )
        )
        return

    passed, total = summary
    status = "PASS" if passed == total else "FAIL"

    items.append(
        ValidationItem(
            domain=domain,
            validation=validation,
            status=status,
            passed_checks=passed,
            total_checks=total,
            evidence=str(path.relative_to(PROJECT_ROOT)),
            note=note,
        )
    )


def add_performance_validation(
    items: list[ValidationItem],
) -> None:
    path = PROJECT_ROOT / (
        "tests/performance/results/"
        "performance_consolidated_summary.csv"
    )

    if not path.exists():
        items.append(
            ValidationItem(
                domain="Performance",
                validation="Optimized 200-user load",
                status="PENDING",
                passed_checks=None,
                total_checks=1,
                evidence="",
                note="Consolidated performance summary not found.",
            )
        )
        return

    rows = read_csv(path)
    optimized = next(
        (
            row
            for row in rows
            if row.get("scenario", "").strip()
            == "200 users optimized"
        ),
        None,
    )

    if optimized is None:
        items.append(
            ValidationItem(
                domain="Performance",
                validation="Optimized 200-user load",
                status="REVIEW",
                passed_checks=None,
                total_checks=1,
                evidence=str(path.relative_to(PROJECT_ROOT)),
                note="The optimized 200-user scenario is missing.",
            )
        )
        return

    failures = int(
        float(
            optimized.get(
                "failure_count",
                "0",
            )
            or 0
        )
    )
    rps = optimized.get(
        "requests_per_second",
        "",
    )
    p95 = optimized.get(
        "p95_response_ms",
        "",
    )

    items.append(
        ValidationItem(
            domain="Performance",
            validation="Optimized 200-user load",
            status="PASS" if failures == 0 else "FAIL",
            passed_checks=1 if failures == 0 else 0,
            total_checks=1,
            evidence=str(path.relative_to(PROJECT_ROOT)),
            note=(
                f"Failures={failures}; "
                f"RPS={rps}; "
                f"P95={p95} ms."
            ),
        )
    )


def write_outputs(
    items: list[ValidationItem],
) -> None:
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    with OUTPUT_CSV.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(
                asdict(items[0]).keys()
            ),
        )
        writer.writeheader()

        for item in items:
            writer.writerow(asdict(item))

    totals = {
        "PASS": sum(
            item.status == "PASS"
            for item in items
        ),
        "FAIL": sum(
            item.status == "FAIL"
            for item in items
        ),
        "PENDING": sum(
            item.status == "PENDING"
            for item in items
        ),
        "REVIEW": sum(
            item.status == "REVIEW"
            for item in items
        ),
    }

    table = [
        "| Domain | Validation | Status | Checks | Evidence | Note |",
        "|---|---|---:|---:|---|---|",
    ]

    for item in items:
        checks = (
            f"{item.passed_checks}/{item.total_checks}"
            if item.passed_checks is not None
            and item.total_checks is not None
            else (
                f"?/{item.total_checks}"
                if item.total_checks is not None
                else "N/A"
            )
        )

        table.append(
            "| "
            + " | ".join(
                [
                    item.domain,
                    item.validation,
                    item.status,
                    checks,
                    item.evidence or "Not found",
                    item.note,
                ]
            )
            + " |"
        )

    markdown = [
        "# Final Validation Matrix",
        "",
        *table,
        "",
        "## Status summary",
        "",
        f"- PASS: {totals['PASS']}",
        f"- FAIL: {totals['FAIL']}",
        f"- PENDING: {totals['PENDING']}",
        f"- REVIEW: {totals['REVIEW']}",
        "",
        "A production-readiness claim is justified only when no item is marked FAIL, PENDING, or REVIEW.",
        "",
    ]

    OUTPUT_MD.write_text(
        "\n".join(markdown),
        encoding="utf-8",
    )

    overall = (
        "PASS"
        if totals["FAIL"] == 0
        and totals["PENDING"] == 0
        and totals["REVIEW"] == 0
        else "INCOMPLETE"
    )

    text = [
        "FINAL PROJECT VALIDATION STATUS",
        f"Overall status: {overall}",
        f"PASS: {totals['PASS']}",
        f"FAIL: {totals['FAIL']}",
        f"PENDING: {totals['PENDING']}",
        f"REVIEW: {totals['REVIEW']}",
        "",
        f"CSV: {OUTPUT_CSV}",
        f"Markdown: {OUTPUT_MD}",
    ]

    OUTPUT_TXT.write_text(
        "\n".join(text),
        encoding="utf-8",
    )


def main() -> int:
    items: list[ValidationItem] = []

    add_boolean_validation(
        items,
        "Security",
        "Production HTTP security",
        [
            PROJECT_ROOT
            / "tests/security/production_security_results.csv",
        ],
        expected_total=17,
    )

    add_boolean_validation(
        items,
        "Security",
        "Diagnostic report strict audit",
        [
            PROJECT_ROOT
            / "tests/security/diagnostic_report_audit_strict_results.csv",
            PROJECT_ROOT
            / "tests/security/diagnostic_report_audit_results.csv",
        ],
        expected_total=9,
    )

    add_boolean_validation(
        items,
        "Storage",
        "Diagnostic report end-to-end storage",
        [
            PROJECT_ROOT
            / "tests/storage/diagnostic_report_e2e_results.csv",
            PROJECT_ROOT
            / "tests/storage/diagnostic_report_storage_results.csv",
        ],
        expected_total=10,
    )

    add_boolean_validation(
        items,
        "Storage",
        "MinIO service lifecycle",
        [
            PROJECT_ROOT
            / "tests/storage/storage_service_validation_results.csv",
            PROJECT_ROOT
            / "tests/storage/minio_storage_results.csv",
        ],
        expected_total=4,
    )

    add_boolean_validation(
        items,
        "Disaster recovery",
        "PostgreSQL backup and restore",
        [
            PROJECT_ROOT
            / "tests/recovery/postgres_backup_restore_results.csv",
        ],
        expected_total=19,
    )

    add_boolean_validation(
        items,
        "Disaster recovery",
        "MinIO backup and restore",
        [
            PROJECT_ROOT
            / "tests/recovery/minio_backup_restore_results.csv",
        ],
        expected_total=23,
    )

    add_performance_validation(items)
    write_outputs(items)

    print("=== FINAL VALIDATION MATRIX ===")

    for item in items:
        checks = (
            f"{item.passed_checks}/{item.total_checks}"
            if item.passed_checks is not None
            and item.total_checks is not None
            else "N/A"
        )

        print(
            f"{item.domain:<20} "
            f"{item.validation:<42} "
            f"{item.status:<10} "
            f"{checks}"
        )

    print("\nOutput CSV :", OUTPUT_CSV)
    print("Output MD  :", OUTPUT_MD)
    print("Status TXT :", OUTPUT_TXT)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
