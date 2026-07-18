import csv
import re
from pathlib import Path


RESULTS_DIR = Path("tests/performance/results")
OUTPUT_FILE = RESULTS_DIR / "performance_summary.csv"


def extract_users_from_filename(file_name: str) -> str:
    match = re.search(r"locust_(\d+)_users", file_name)

    if match:
        return match.group(1)

    return "unknown"


def find_aggregated_row(stats_file: Path) -> dict | None:
    with stats_file.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as csv_file:
        reader = csv.DictReader(csv_file)

        for row in reader:
            row_type = row.get("Type", "")
            row_name = row.get("Name", "")

            if row_name == "Aggregated" or row_type == "Aggregated":
                return row

    return None


def main():
    stats_files = sorted(
        RESULTS_DIR.glob("locust_*_stats.csv")
    )

    if not stats_files:
        print(
            "[ERROR] No Locust stats files found."
        )
        return

    summary_rows = []

    for stats_file in stats_files:
        aggregated_row = find_aggregated_row(
            stats_file
        )

        if aggregated_row is None:
            print(
                f"[SKIPPED] No Aggregated row found in {stats_file.name}"
            )
            continue

        scenario = stats_file.stem.replace(
            "_stats",
            "",
        )

        users = extract_users_from_filename(
            stats_file.name
        )

        summary_rows.append(
            {
                "Scenario": scenario,
                "Users": users,
                "Request Count": aggregated_row.get(
                    "Request Count",
                    "",
                ),
                "Failure Count": aggregated_row.get(
                    "Failure Count",
                    "",
                ),
                "Average Response Time": aggregated_row.get(
                    "Average Response Time",
                    "",
                ),
                "Median Response Time": aggregated_row.get(
                    "Median Response Time",
                    "",
                ),
                "95% Response Time": aggregated_row.get(
                    "95%",
                    "",
                ),
                "99% Response Time": aggregated_row.get(
                    "99%",
                    "",
                ),
                "Requests/s": aggregated_row.get(
                    "Requests/s",
                    "",
                ),
                "Failures/s": aggregated_row.get(
                    "Failures/s",
                    "",
                ),
            }
        )

    if not summary_rows:
        print(
            "[ERROR] No summary rows generated."
        )
        return

    fieldnames = list(
        summary_rows[0].keys()
    )

    with OUTPUT_FILE.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as output_csv:
        writer = csv.DictWriter(
            output_csv,
            fieldnames=fieldnames,
        )

        writer.writeheader()
        writer.writerows(
            summary_rows
        )

    print(
        "[SUCCESS] Performance summary created:",
        OUTPUT_FILE,
    )

    print()

    for row in summary_rows:
        print(
            row
        )


if __name__ == "__main__":
    main()