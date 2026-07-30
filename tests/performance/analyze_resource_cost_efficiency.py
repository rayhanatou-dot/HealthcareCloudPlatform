from __future__ import annotations

import csv
import json
import math
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = PROJECT_ROOT / "tests" / "performance" / "results"

PERFORMANCE_FILE = (
    RESULTS_DIR
    / "performance_consolidated_summary.csv"
)
OUTPUT_CSV = (
    RESULTS_DIR
    / "resource_cost_efficiency_summary.csv"
)
OUTPUT_MD = (
    RESULTS_DIR
    / "resource_cost_efficiency_summary.md"
)
COST_TEMPLATE = (
    RESULTS_DIR
    / "cost_input_template.csv"
)
THROUGHPUT_CHART = (
    RESULTS_DIR
    / "successful_throughput_by_load.png"
)
OPTIMIZATION_CHART = (
    RESULTS_DIR
    / "optimization_impact_200_users.png"
)
RESOURCE_CHART = (
    RESULTS_DIR
    / "resource_efficiency_by_load.png"
)


@dataclass
class EfficiencyRow:
    scenario: str
    concurrent_users: int
    request_count: int
    failure_count: int
    failure_rate_pct: float
    average_response_ms: float
    p95_response_ms: float
    p99_response_ms: float
    requests_per_second: float
    successful_requests_per_second: float
    latency_adjusted_efficiency: float
    backend_cpu_pct: float | None
    backend_memory_mib: float | None
    successful_rps_per_cpu_pct: float | None
    successful_rps_per_gib: float | None
    resource_source: str


RESOURCE_FILES = {
    "10 users": [
        "docker_stats_10_users.txt",
    ],
    "50 users": [
        "docker_stats_50_users.txt",
    ],
    "100 users": [
        "docker_stats_100_users.txt",
    ],
    "200 users optimized": [
        "docker_stats_200_users.txt",
        "docker_resource_snapshot_final.txt",
    ],
}


def parse_float(value: Any, default: float = 0.0) -> float:
    try:
        text = str(value).strip().replace(",", "")
        return float(text) if text else default
    except (TypeError, ValueError):
        return default


def parse_int(value: Any, default: int = 0) -> int:
    return int(round(parse_float(value, float(default))))


def memory_to_mib(value: float, unit: str) -> float:
    normalized = unit.lower()

    factors = {
        "b": 1 / (1024 * 1024),
        "kb": 1000 / (1024 * 1024),
        "kib": 1 / 1024,
        "mb": 1000 * 1000 / (1024 * 1024),
        "mib": 1,
        "gb": 1000 * 1000 * 1000 / (1024 * 1024),
        "gib": 1024,
        "tb": 1000 * 1000 * 1000 * 1000 / (1024 * 1024),
        "tib": 1024 * 1024,
    }

    return value * factors.get(normalized, 1)


def find_resource_file(candidates: list[str]) -> Path | None:
    for filename in candidates:
        path = RESULTS_DIR / filename

        if path.exists():
            return path

    return None


def parse_backend_resource_file(
    path: Path,
) -> tuple[float | None, float | None]:
    text = path.read_text(
        encoding="utf-8",
        errors="ignore",
    )

    lines = [
        line
        for line in text.splitlines()
        if line.strip()
    ]

    preferred_lines = [
        line
        for line in lines
        if "backend" in line.lower()
    ]

    search_lines = preferred_lines or lines

    for line in search_lines:
        cpu_match = re.search(
            r"(\d+(?:\.\d+)?)\s*%",
            line,
        )

        memory_match = re.search(
            r"(\d+(?:\.\d+)?)\s*"
            r"(B|KB|KiB|MB|MiB|GB|GiB|TB|TiB)"
            r"\s*/",
            line,
            flags=re.IGNORECASE,
        )

        cpu_value = (
            float(cpu_match.group(1))
            if cpu_match
            else None
        )

        memory_value = (
            memory_to_mib(
                float(memory_match.group(1)),
                memory_match.group(2),
            )
            if memory_match
            else None
        )

        if (
            cpu_value is not None
            or memory_value is not None
        ):
            return cpu_value, memory_value

    return None, None


def load_performance_rows() -> list[dict[str, str]]:
    if not PERFORMANCE_FILE.exists():
        raise RuntimeError(
            "Missing performance summary: "
            f"{PERFORMANCE_FILE}. "
            "Run consolidate_performance_results.py first."
        )

    with PERFORMANCE_FILE.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as csv_file:
        return list(csv.DictReader(csv_file))


def build_efficiency_rows(
    performance_rows: list[dict[str, str]],
) -> list[EfficiencyRow]:
    output: list[EfficiencyRow] = []

    for row in performance_rows:
        scenario = row.get("scenario", "").strip()
        users = parse_int(
            row.get("concurrent_users")
        )
        request_count = parse_int(
            row.get("request_count")
        )
        failure_count = parse_int(
            row.get("failure_count")
        )
        failure_rate = parse_float(
            row.get("failure_rate_pct")
        )
        average_ms = parse_float(
            row.get("average_response_ms")
        )
        p95_ms = parse_float(
            row.get("p95_response_ms")
        )
        p99_ms = parse_float(
            row.get("p99_response_ms")
        )
        rps = parse_float(
            row.get("requests_per_second")
        )

        success_fraction = max(
            0.0,
            1.0 - (failure_rate / 100.0),
        )
        successful_rps = rps * success_fraction

        latency_adjusted = (
            successful_rps
            / (1.0 + average_ms / 1000.0)
            if successful_rps >= 0
            else 0.0
        )

        resource_file = find_resource_file(
            RESOURCE_FILES.get(
                scenario,
                [],
            )
        )

        cpu_pct: float | None = None
        memory_mib: float | None = None
        resource_source = ""

        if resource_file is not None:
            cpu_pct, memory_mib = (
                parse_backend_resource_file(
                    resource_file
                )
            )
            resource_source = resource_file.name

        rps_per_cpu = (
            successful_rps / cpu_pct
            if cpu_pct is not None
            and cpu_pct > 0
            else None
        )

        rps_per_gib = (
            successful_rps
            / (memory_mib / 1024.0)
            if memory_mib is not None
            and memory_mib > 0
            else None
        )

        output.append(
            EfficiencyRow(
                scenario=scenario,
                concurrent_users=users,
                request_count=request_count,
                failure_count=failure_count,
                failure_rate_pct=round(
                    failure_rate,
                    4,
                ),
                average_response_ms=round(
                    average_ms,
                    2,
                ),
                p95_response_ms=round(
                    p95_ms,
                    2,
                ),
                p99_response_ms=round(
                    p99_ms,
                    2,
                ),
                requests_per_second=round(
                    rps,
                    2,
                ),
                successful_requests_per_second=round(
                    successful_rps,
                    2,
                ),
                latency_adjusted_efficiency=round(
                    latency_adjusted,
                    4,
                ),
                backend_cpu_pct=(
                    round(cpu_pct, 2)
                    if cpu_pct is not None
                    else None
                ),
                backend_memory_mib=(
                    round(memory_mib, 2)
                    if memory_mib is not None
                    else None
                ),
                successful_rps_per_cpu_pct=(
                    round(rps_per_cpu, 4)
                    if rps_per_cpu is not None
                    else None
                ),
                successful_rps_per_gib=(
                    round(rps_per_gib, 2)
                    if rps_per_gib is not None
                    else None
                ),
                resource_source=resource_source,
            )
        )

    return output


def write_summary_csv(
    rows: list[EfficiencyRow],
) -> None:
    fieldnames = list(
        asdict(rows[0]).keys()
    )

    with OUTPUT_CSV.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=fieldnames,
        )
        writer.writeheader()

        for row in rows:
            writer.writerow(asdict(row))


def write_cost_template(
    rows: list[EfficiencyRow],
) -> None:
    fieldnames = [
        "scenario",
        "concurrent_users",
        "monthly_infrastructure_cost_usd",
        "monthly_operations_cost_usd",
        "monthly_total_cost_usd",
        "successful_requests_per_second",
        "estimated_successful_requests_per_month",
        "cost_per_million_successful_requests_usd",
        "notes",
    ]

    seconds_per_month = 30 * 24 * 60 * 60

    with COST_TEMPLATE.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=fieldnames,
        )
        writer.writeheader()

        for row in rows:
            estimated_monthly_requests = (
                row.successful_requests_per_second
                * seconds_per_month
            )

            writer.writerow(
                {
                    "scenario": row.scenario,
                    "concurrent_users": (
                        row.concurrent_users
                    ),
                    "monthly_infrastructure_cost_usd": "",
                    "monthly_operations_cost_usd": "",
                    "monthly_total_cost_usd": "",
                    "successful_requests_per_second": (
                        row.successful_requests_per_second
                    ),
                    "estimated_successful_requests_per_month": round(
                        estimated_monthly_requests,
                        0,
                    ),
                    "cost_per_million_successful_requests_usd": "",
                    "notes": (
                        "Enter measured or quoted monthly costs. "
                        "Do not treat maximum-load RPS as continuous "
                        "production demand without a utilization model."
                    ),
                }
            )


def get_scenario(
    rows: list[EfficiencyRow],
    name: str,
) -> EfficiencyRow | None:
    return next(
        (
            row
            for row in rows
            if row.scenario == name
        ),
        None,
    )


def percentage_change(
    old: float,
    new: float,
) -> float | None:
    if old == 0:
        return None

    return (
        (new - old)
        / old
        * 100.0
    )


def markdown_value(
    value: float | None,
    decimals: int = 2,
) -> str:
    if value is None:
        return "N/A"

    return f"{value:.{decimals}f}"


def write_markdown(
    rows: list[EfficiencyRow],
) -> None:
    initial = get_scenario(
        rows,
        "200 users initial",
    )
    optimized = get_scenario(
        rows,
        "200 users optimized",
    )

    table_lines = [
        "| Scenario | Users | Failures | Failure rate | Successful RPS | Avg ms | P95 ms | P99 ms | CPU % | Memory MiB | RPS/CPU% | RPS/GiB |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]

    for row in rows:
        table_lines.append(
            "| "
            + " | ".join(
                [
                    row.scenario,
                    str(row.concurrent_users),
                    str(row.failure_count),
                    f"{row.failure_rate_pct:.2f}%",
                    f"{row.successful_requests_per_second:.2f}",
                    f"{row.average_response_ms:.2f}",
                    f"{row.p95_response_ms:.2f}",
                    f"{row.p99_response_ms:.2f}",
                    markdown_value(
                        row.backend_cpu_pct
                    ),
                    markdown_value(
                        row.backend_memory_mib
                    ),
                    markdown_value(
                        row.successful_rps_per_cpu_pct,
                        4,
                    ),
                    markdown_value(
                        row.successful_rps_per_gib
                    ),
                ]
            )
            + " |"
        )

    interpretation: list[str] = []

    zero_failure_rows = [
        row
        for row in rows
        if row.failure_count == 0
    ]

    if zero_failure_rows:
        strongest = max(
            zero_failure_rows,
            key=lambda row: (
                row.concurrent_users,
                row.successful_requests_per_second,
            ),
        )

        interpretation.append(
            (
                "- Highest validated zero-failure load: "
                f"**{strongest.concurrent_users} users**, "
                f"**{strongest.successful_requests_per_second:.2f} "
                "successful requests/s**."
            )
        )

    if initial and optimized:
        throughput_change = percentage_change(
            initial.successful_requests_per_second,
            optimized.successful_requests_per_second,
        )
        latency_change = percentage_change(
            initial.average_response_ms,
            optimized.average_response_ms,
        )

        interpretation.extend(
            [
                (
                    "- At 200 users, failed requests decreased from "
                    f"**{initial.failure_count}** to "
                    f"**{optimized.failure_count}**."
                ),
                (
                    "- Reliability-adjusted throughput changed from "
                    f"**{initial.successful_requests_per_second:.2f}** "
                    "to "
                    f"**{optimized.successful_requests_per_second:.2f} "
                    "requests/s**."
                ),
                (
                    "- Relative throughput change at 200 users: "
                    f"**{markdown_value(throughput_change)}%**."
                ),
                (
                    "- Relative mean-latency change at 200 users: "
                    f"**{markdown_value(latency_change)}%** "
                    "(a negative value indicates improvement)."
                ),
            ]
        )

    resource_rows = [
        row
        for row in rows
        if (
            row.backend_cpu_pct is not None
            or row.backend_memory_mib is not None
        )
    ]

    if resource_rows:
        interpretation.append(
            (
                "- Docker resource snapshots were available for "
                f"**{len(resource_rows)}** scenarios. "
                "RPS/CPU% and RPS/GiB are reported only where "
                "the backend container could be parsed reliably."
            )
        )
    else:
        interpretation.append(
            (
                "- Docker resource snapshots could not be parsed "
                "reliably. Monetary cost-effectiveness should not "
                "be claimed until CPU, memory, storage, network, "
                "and deployment prices are measured."
            )
        )

    content = [
        "# Resource and Cost-Efficiency Analysis",
        "",
        "## Consolidated efficiency table",
        "",
        *table_lines,
        "",
        "## Interpretation",
        "",
        *interpretation,
        "",
        "## Monetary cost model",
        "",
        "The file `cost_input_template.csv` contains the performance denominator required for a cost model. Enter verified monthly infrastructure and operations costs before calculating monetary cost-effectiveness.",
        "",
        "Recommended formula:",
        "",
        "`cost per million successful requests = monthly total cost / (estimated successful monthly requests / 1,000,000)`",
        "",
        "The maximum-load throughput measured by Locust must not automatically be treated as continuous monthly production traffic. Apply a realistic utilization factor and expected workload profile.",
        "",
        "## Thesis use",
        "",
        "- Report reliability-adjusted throughput rather than raw throughput alone.",
        "- Separate software optimization gains from hardware scaling gains.",
        "- State that financial conclusions require deployment-specific prices and utilization assumptions.",
        "- Use the initial 200-user failure as evidence of a connection-pool bottleneck and the optimized result as evidence of remediation.",
        "",
    ]

    OUTPUT_MD.write_text(
        "\n".join(content),
        encoding="utf-8",
    )


def create_charts(
    rows: list[EfficiencyRow],
) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print(
            "matplotlib is not installed; charts were skipped."
        )
        return

    ordered = [
        row
        for row in rows
        if row.scenario
        in {
            "10 users",
            "50 users",
            "100 users",
            "200 users optimized",
        }
    ]
    ordered.sort(
        key=lambda row: row.concurrent_users
    )

    if ordered:
        plt.figure()
        plt.plot(
            [
                row.concurrent_users
                for row in ordered
            ],
            [
                row.successful_requests_per_second
                for row in ordered
            ],
            marker="o",
        )
        plt.xlabel("Concurrent users")
        plt.ylabel(
            "Successful requests per second"
        )
        plt.title(
            "Reliability-adjusted throughput"
        )
        plt.tight_layout()
        plt.savefig(
            THROUGHPUT_CHART,
            dpi=200,
        )
        plt.close()

    initial = get_scenario(
        rows,
        "200 users initial",
    )
    optimized = get_scenario(
        rows,
        "200 users optimized",
    )

    if initial and optimized:
        plt.figure()
        plt.bar(
            [
                "Initial failures",
                "Optimized failures",
            ],
            [
                initial.failure_count,
                optimized.failure_count,
            ],
        )
        plt.ylabel("Failed requests")
        plt.title(
            "200-user optimization impact"
        )
        plt.tight_layout()
        plt.savefig(
            OPTIMIZATION_CHART,
            dpi=200,
        )
        plt.close()

    resource_rows = [
        row
        for row in ordered
        if row.successful_rps_per_gib
        is not None
    ]

    if resource_rows:
        plt.figure()
        plt.plot(
            [
                row.concurrent_users
                for row in resource_rows
            ],
            [
                row.successful_rps_per_gib
                for row in resource_rows
            ],
            marker="o",
        )
        plt.xlabel("Concurrent users")
        plt.ylabel(
            "Successful requests/s per GiB"
        )
        plt.title(
            "Backend memory efficiency"
        )
        plt.tight_layout()
        plt.savefig(
            RESOURCE_CHART,
            dpi=200,
        )
        plt.close()


def print_summary(
    rows: list[EfficiencyRow],
) -> None:
    print(
        "\n=== RESOURCE AND COST-EFFICIENCY SUMMARY ==="
    )

    for row in rows:
        print(
            (
                f"{row.scenario:<22} "
                f"successful_rps="
                f"{row.successful_requests_per_second:<8.2f} "
                f"failures={row.failure_count:<5} "
                f"avg_ms={row.average_response_ms:<9.2f} "
                f"cpu={markdown_value(row.backend_cpu_pct):<8} "
                f"memory_mib="
                f"{markdown_value(row.backend_memory_mib)}"
            )
        )

    print("\nSummary CSV :", OUTPUT_CSV)
    print("Summary MD  :", OUTPUT_MD)
    print("Cost input  :", COST_TEMPLATE)

    for path in (
        THROUGHPUT_CHART,
        OPTIMIZATION_CHART,
        RESOURCE_CHART,
    ):
        if path.exists():
            print("Chart       :", path)


def main() -> int:
    RESULTS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    performance_rows = load_performance_rows()
    efficiency_rows = build_efficiency_rows(
        performance_rows
    )

    if not efficiency_rows:
        raise RuntimeError(
            "No performance scenarios were loaded."
        )

    write_summary_csv(
        efficiency_rows
    )
    write_cost_template(
        efficiency_rows
    )
    write_markdown(
        efficiency_rows
    )
    create_charts(
        efficiency_rows
    )
    print_summary(
        efficiency_rows
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
