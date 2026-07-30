from __future__ import annotations

import csv
import math
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = PROJECT_ROOT / "tests" / "performance" / "results"

OUTPUT_CSV = RESULTS_DIR / "performance_consolidated_summary.csv"
OUTPUT_MD = RESULTS_DIR / "performance_consolidated_summary.md"
LATENCY_CHART = RESULTS_DIR / "performance_latency_scaling.png"
THROUGHPUT_CHART = RESULTS_DIR / "performance_throughput_scaling.png"
FAILURE_CHART = RESULTS_DIR / "performance_200_users_failure_comparison.png"


@dataclass
class ScenarioResult:
    scenario: str
    concurrent_users: int
    request_count: int
    failure_count: int
    failure_rate_pct: float
    average_response_ms: float
    median_response_ms: float
    p95_response_ms: float
    p99_response_ms: float
    requests_per_second: float
    source_file: str


SCENARIOS = [
    (
        "10 users",
        10,
        [
            "locust_10_users_stats.csv",
        ],
    ),
    (
        "50 users",
        50,
        [
            "locust_50_users_stats.csv",
        ],
    ),
    (
        "100 users",
        100,
        [
            "locust_100_users_stats.csv",
        ],
    ),
    (
        "200 users initial",
        200,
        [
            "locust_200_users_stats.csv",
        ],
    ),
    (
        "200 users optimized",
        200,
        [
            "locust_200_users_fixed_stats.csv",
        ],
    ),
]


def normalize_header(value: str) -> str:
    return re.sub(
        r"[^a-z0-9]+",
        "",
        value.strip().lower(),
    )


def parse_number(
    value: Any,
    default: float = 0.0,
) -> float:
    if value is None:
        return default

    text = str(value).strip()

    if not text:
        return default

    text = text.replace(",", "")

    try:
        return float(text)
    except ValueError:
        return default


def locate_file(
    candidates: list[str],
) -> Path | None:
    for candidate in candidates:
        path = RESULTS_DIR / candidate

        if path.exists():
            return path

    return None


def read_aggregated_row(
    path: Path,
) -> tuple[dict[str, str], dict[str, str]]:
    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as csv_file:
        reader = csv.DictReader(csv_file)
        rows = list(reader)

    if not rows:
        raise RuntimeError(
            f"No rows found in {path}"
        )

    headers = {
        normalize_header(header): header
        for header in rows[0].keys()
        if header is not None
    }

    name_header = headers.get("name")
    type_header = headers.get("type")

    aggregated = None

    for row in rows:
        name_value = (
            row.get(name_header, "")
            if name_header
            else ""
        ).strip().lower()

        type_value = (
            row.get(type_header, "")
            if type_header
            else ""
        ).strip().lower()

        if (
            name_value == "aggregated"
            or type_value == "aggregated"
        ):
            aggregated = row
            break

    if aggregated is None:
        aggregated = rows[-1]

    return aggregated, headers


def get_value(
    row: dict[str, str],
    headers: dict[str, str],
    aliases: list[str],
    default: float = 0.0,
) -> float:
    for alias in aliases:
        normalized = normalize_header(alias)

        if normalized in headers:
            return parse_number(
                row.get(
                    headers[normalized],
                    "",
                ),
                default,
            )

    return default


def load_scenario(
    scenario: str,
    users: int,
    candidates: list[str],
) -> ScenarioResult | None:
    path = locate_file(candidates)

    if path is None:
        print(
            f"SKIP: no result file found for {scenario}"
        )
        return None

    row, headers = read_aggregated_row(path)

    request_count = int(
        get_value(
            row,
            headers,
            [
                "Request Count",
                "Requests",
            ],
        )
    )

    failure_count = int(
        get_value(
            row,
            headers,
            [
                "Failure Count",
                "Failures",
            ],
        )
    )

    average_response = get_value(
        row,
        headers,
        [
            "Average Response Time",
            "Average",
        ],
    )

    median_response = get_value(
        row,
        headers,
        [
            "Median Response Time",
            "Median",
            "50%",
        ],
    )

    p95_response = get_value(
        row,
        headers,
        [
            "95%",
            "p95",
        ],
    )

    p99_response = get_value(
        row,
        headers,
        [
            "99%",
            "p99",
        ],
    )

    rps = get_value(
        row,
        headers,
        [
            "Requests/s",
            "Requests Per Second",
            "RPS",
        ],
    )

    failure_rate = (
        (failure_count / request_count) * 100
        if request_count > 0
        else 0.0
    )

    return ScenarioResult(
        scenario=scenario,
        concurrent_users=users,
        request_count=request_count,
        failure_count=failure_count,
        failure_rate_pct=round(
            failure_rate,
            4,
        ),
        average_response_ms=round(
            average_response,
            2,
        ),
        median_response_ms=round(
            median_response,
            2,
        ),
        p95_response_ms=round(
            p95_response,
            2,
        ),
        p99_response_ms=round(
            p99_response,
            2,
        ),
        requests_per_second=round(
            rps,
            2,
        ),
        source_file=path.name,
    )


def write_csv(
    results: list[ScenarioResult],
) -> None:
    with OUTPUT_CSV.open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=list(
                asdict(results[0]).keys()
            ),
        )
        writer.writeheader()

        for result in results:
            writer.writerow(
                asdict(result)
            )


def markdown_table(
    results: list[ScenarioResult],
) -> str:
    lines = [
        "| Scenario | Users | Requests | Failures | Failure rate | Avg (ms) | Median (ms) | P95 (ms) | P99 (ms) | RPS |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]

    for result in results:
        lines.append(
            "| "
            + " | ".join(
                [
                    result.scenario,
                    str(result.concurrent_users),
                    str(result.request_count),
                    str(result.failure_count),
                    f"{result.failure_rate_pct:.2f}%",
                    f"{result.average_response_ms:.2f}",
                    f"{result.median_response_ms:.2f}",
                    f"{result.p95_response_ms:.2f}",
                    f"{result.p99_response_ms:.2f}",
                    f"{result.requests_per_second:.2f}",
                ]
            )
            + " |"
        )

    return "\n".join(lines)


def find_result(
    results: list[ScenarioResult],
    scenario: str,
) -> ScenarioResult | None:
    return next(
        (
            result
            for result in results
            if result.scenario == scenario
        ),
        None,
    )


def write_markdown(
    results: list[ScenarioResult],
) -> None:
    initial = find_result(
        results,
        "200 users initial",
    )
    optimized = find_result(
        results,
        "200 users optimized",
    )

    conclusions: list[str] = []

    successful = [
        result
        for result in results
        if result.failure_count == 0
    ]

    if successful:
        max_success = max(
            successful,
            key=lambda item: (
                item.concurrent_users,
                item.requests_per_second,
            ),
        )

        conclusions.append(
            (
                f"- Maximum validated load with zero failures: "
                f"**{max_success.concurrent_users} concurrent users** "
                f"at **{max_success.requests_per_second:.2f} requests/s**."
            )
        )

    if initial and optimized:
        failure_reduction = (
            initial.failure_count
            - optimized.failure_count
        )

        rps_gain = (
            optimized.requests_per_second
            - initial.requests_per_second
        )

        conclusions.append(
            (
                f"- The optimized 200-user configuration reduced failures "
                f"from **{initial.failure_count}** to "
                f"**{optimized.failure_count}**, a reduction of "
                f"**{failure_reduction} failed requests**."
            )
        )

        conclusions.append(
            (
                f"- Throughput at 200 users increased from "
                f"**{initial.requests_per_second:.2f}** to "
                f"**{optimized.requests_per_second:.2f} requests/s**, "
                f"a gain of **{rps_gain:.2f} requests/s**."
            )
        )

        if initial.average_response_ms > 0:
            latency_change = (
                (
                    initial.average_response_ms
                    - optimized.average_response_ms
                )
                / initial.average_response_ms
                * 100
            )

            conclusions.append(
                (
                    f"- Mean response time at 200 users improved by "
                    f"approximately **{latency_change:.2f}%**."
                )
            )

    content = [
        "# Consolidated Performance Results",
        "",
        markdown_table(results),
        "",
        "## Interpretation",
        "",
        *conclusions,
        "",
        "## Evidence files",
        "",
    ]

    for result in results:
        content.append(
            f"- `{result.source_file}`"
        )

    content.extend(
        [
            "",
            "## Notes",
            "",
            "- The initial 200-user result is retained as evidence of the original connection-pool bottleneck.",
            "- The optimized 200-user result is the final scalability result.",
            "- These results describe the tested Docker environment and should not be generalized beyond the measured configuration without additional experiments.",
            "",
        ]
    )

    OUTPUT_MD.write_text(
        "\n".join(content),
        encoding="utf-8",
    )


def create_charts(
    results: list[ScenarioResult],
) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print(
            "matplotlib is not installed; charts were skipped."
        )
        return

    scalable = [
        result
        for result in results
        if result.scenario
        in {
            "10 users",
            "50 users",
            "100 users",
            "200 users optimized",
        }
    ]

    scalable.sort(
        key=lambda item: item.concurrent_users
    )

    if scalable:
        plt.figure()
        plt.plot(
            [
                item.concurrent_users
                for item in scalable
            ],
            [
                item.average_response_ms
                for item in scalable
            ],
            marker="o",
            label="Average",
        )
        plt.plot(
            [
                item.concurrent_users
                for item in scalable
            ],
            [
                item.p95_response_ms
                for item in scalable
            ],
            marker="o",
            label="P95",
        )
        plt.plot(
            [
                item.concurrent_users
                for item in scalable
            ],
            [
                item.p99_response_ms
                for item in scalable
            ],
            marker="o",
            label="P99",
        )
        plt.xlabel("Concurrent users")
        plt.ylabel("Response time (ms)")
        plt.title("Backend latency scaling")
        plt.legend()
        plt.tight_layout()
        plt.savefig(
            LATENCY_CHART,
            dpi=200,
        )
        plt.close()

        plt.figure()
        plt.plot(
            [
                item.concurrent_users
                for item in scalable
            ],
            [
                item.requests_per_second
                for item in scalable
            ],
            marker="o",
        )
        plt.xlabel("Concurrent users")
        plt.ylabel("Requests per second")
        plt.title("Backend throughput scaling")
        plt.tight_layout()
        plt.savefig(
            THROUGHPUT_CHART,
            dpi=200,
        )
        plt.close()

    initial = find_result(
        results,
        "200 users initial",
    )
    optimized = find_result(
        results,
        "200 users optimized",
    )

    if initial and optimized:
        plt.figure()
        plt.bar(
            [
                "Initial",
                "Optimized",
            ],
            [
                initial.failure_count,
                optimized.failure_count,
            ],
        )
        plt.xlabel("200-user configuration")
        plt.ylabel("Failed requests")
        plt.title(
            "Failure comparison at 200 concurrent users"
        )
        plt.tight_layout()
        plt.savefig(
            FAILURE_CHART,
            dpi=200,
        )
        plt.close()


def print_summary(
    results: list[ScenarioResult],
) -> None:
    print(
        "\n=== CONSOLIDATED PERFORMANCE SUMMARY ==="
    )

    for result in results:
        print(
            (
                f"{result.scenario:<22} "
                f"requests={result.request_count:<7} "
                f"failures={result.failure_count:<5} "
                f"avg={result.average_response_ms:<8.2f} "
                f"p95={result.p95_response_ms:<8.2f} "
                f"p99={result.p99_response_ms:<8.2f} "
                f"rps={result.requests_per_second:.2f}"
            )
        )

    print("\nOutput CSV :", OUTPUT_CSV)
    print("Output MD  :", OUTPUT_MD)

    if LATENCY_CHART.exists():
        print("Latency PNG:", LATENCY_CHART)

    if THROUGHPUT_CHART.exists():
        print(
            "RPS PNG    :",
            THROUGHPUT_CHART,
        )

    if FAILURE_CHART.exists():
        print(
            "Failure PNG:",
            FAILURE_CHART,
        )


def main() -> int:
    RESULTS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    results: list[ScenarioResult] = []

    for scenario, users, candidates in SCENARIOS:
        loaded = load_scenario(
            scenario,
            users,
            candidates,
        )

        if loaded is not None:
            results.append(loaded)

    if not results:
        raise RuntimeError(
            "No Locust statistics files were found."
        )

    write_csv(results)
    write_markdown(results)
    create_charts(results)
    print_summary(results)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
