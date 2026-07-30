from __future__ import annotations

import csv
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / ".env"
SECURITY_DIR = PROJECT_ROOT / "tests" / "security"
RESULTS_FILE = SECURITY_DIR / "production_security_results.csv"
SUMMARY_FILE = SECURITY_DIR / "production_security_summary.txt"
BACKUP_FILE = SECURITY_DIR / ".env.production_validation.backup"

BASE_URL = "http://localhost:8000"


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
            f"Command failed: {' '.join(command)}\n{message}"
        )

    return completed


def read_env_lines() -> list[str]:
    if not ENV_FILE.exists():
        raise RuntimeError(
            f"Environment file not found: {ENV_FILE}"
        )

    return ENV_FILE.read_text(
        encoding="utf-8-sig"
    ).splitlines()


def parse_env(lines: list[str]) -> dict[str, str]:
    values: dict[str, str] = {}

    for raw_line in lines:
        line = raw_line.strip()

        if (
            not line
            or line.startswith("#")
            or "=" not in line
        ):
            continue

        key, value = line.split("=", 1)

        if key.strip() not in values:
            values[key.strip()] = (
                value.strip()
                .strip('"')
                .strip("'")
            )

    return values


def set_env_value(
    lines: list[str],
    key: str,
    value: str,
) -> list[str]:
    pattern = re.compile(
        rf"^\s*{re.escape(key)}\s*="
    )
    output: list[str] = []
    replaced = False

    for line in lines:
        if pattern.match(line):
            if not replaced:
                output.append(f"{key}={value}")
                replaced = True
            continue

        output.append(line)

    if not replaced:
        output.append(f"{key}={value}")

    return output


def detect_environment_key() -> str:
    config_file = (
        PROJECT_ROOT
        / "backend"
        / "app"
        / "core"
        / "config.py"
    )

    candidates = (
        "APP_ENV",
        "ENVIRONMENT",
        "APP_ENVIRONMENT",
        "ENV",
    )

    if config_file.exists():
        text = config_file.read_text(
            encoding="utf-8-sig"
        )

        for candidate in candidates:
            if re.search(
                rf"\b{re.escape(candidate)}\b",
                text,
            ):
                return candidate

    current_env = parse_env(read_env_lines())

    for candidate in candidates:
        if candidate in current_env:
            return candidate

    return "APP_ENV"


def parse_list_value(
    raw_value: str | None,
    default: list[str],
) -> list[str]:
    if not raw_value:
        return default

    value = raw_value.strip()

    try:
        parsed = json.loads(value)

        if isinstance(parsed, list):
            return [
                str(item)
                for item in parsed
                if str(item).strip()
            ]
    except json.JSONDecodeError:
        pass

    return [
        item.strip()
        for item in value.split(",")
        if item.strip()
    ] or default


def wait_for_backend(
    timeout_seconds: int = 90,
) -> requests.Response:
    deadline = time.time() + timeout_seconds
    last_error: Exception | None = None

    while time.time() < deadline:
        try:
            response = requests.get(
                f"{BASE_URL}/health",
                timeout=5,
            )

            if response.status_code == 200:
                return response

        except requests.RequestException as exc:
            last_error = exc

        time.sleep(3)

    raise RuntimeError(
        "Backend health endpoint did not become ready."
        + (
            f" Last error: {last_error}"
            if last_error
            else ""
        )
    )


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
        f"{test:<38} "
        f"{'PASS' if passed else 'FAIL'} "
        f"(expected {expected}, got {actual})"
    )


def header_value(
    response: requests.Response,
    name: str,
) -> str:
    return response.headers.get(
        name,
        "",
    ).strip()


def recreate_backend() -> None:
    run_command(
        [
            "docker",
            "compose",
            "up",
            "-d",
            "--force-recreate",
            "backend",
        ]
    )


def main() -> int:
    SECURITY_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    original_bytes = ENV_FILE.read_bytes()
    BACKUP_FILE.write_bytes(original_bytes)

    original_lines = read_env_lines()
    original_values = parse_env(original_lines)

    environment_key = detect_environment_key()

    allowed_origins = parse_list_value(
        original_values.get(
            "CORS_ALLOWED_ORIGINS"
        ),
        [
            "http://localhost:3000",
            "http://localhost:5173",
        ],
    )

    trusted_origin = next(
        (
            origin
            for origin in allowed_origins
            if origin.startswith("http")
        ),
        "http://localhost:3000",
    )
    untrusted_origin = "https://untrusted.example"

    allowed_hosts = parse_list_value(
        original_values.get("ALLOWED_HOSTS"),
        [
            "localhost",
            "127.0.0.1",
            "testserver",
        ],
    )

    trusted_host = next(
        (
            host
            for host in allowed_hosts
            if host not in {"*", ""}
        ),
        "localhost",
    )

    production_lines = list(original_lines)
    production_lines = set_env_value(
        production_lines,
        environment_key,
        "production",
    )
    production_lines = set_env_value(
        production_lines,
        "DOCS_ENABLED",
        "false",
    )

    ENV_FILE.write_text(
        "\n".join(production_lines) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    results: list[dict[str, Any]] = []
    execution_error: Exception | None = None
    restored = False

    try:
        print("=== PRODUCTION BACKEND STARTUP ===")
        print(
            "Environment key:",
            environment_key,
        )

        recreate_backend()
        health = wait_for_backend()

        add_result(
            results,
            "Backend health",
            "HTTP 200",
            f"HTTP {health.status_code}",
            health.status_code == 200,
        )

        print("\n=== SECURITY HEADERS ===")

        required_exact_headers = {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "no-referrer",
        }

        for name, expected in required_exact_headers.items():
            actual = header_value(
                health,
                name,
            )

            add_result(
                results,
                name,
                expected,
                actual or "missing",
                actual.lower()
                == expected.lower(),
            )

        for name in (
            "Content-Security-Policy",
            "Permissions-Policy",
            "Strict-Transport-Security",
        ):
            actual = header_value(
                health,
                name,
            )

            add_result(
                results,
                name,
                "present",
                actual or "missing",
                bool(actual),
            )

        cache_control = header_value(
            health,
            "Cache-Control",
        )

        add_result(
            results,
            "Cache-Control",
            "contains no-store",
            cache_control or "missing",
            "no-store"
            in cache_control.lower(),
        )

        server_header = header_value(
            health,
            "Server",
        )

        add_result(
            results,
            "Server disclosure",
            "uvicorn not disclosed",
            server_header or "absent",
            "uvicorn"
            not in server_header.lower(),
        )

        print("\n=== PRODUCTION DOCUMENTATION ===")

        for path in (
            "/docs",
            "/redoc",
            "/openapi.json",
        ):
            response = requests.get(
                f"{BASE_URL}{path}",
                timeout=15,
            )

            add_result(
                results,
                f"Production route {path}",
                "HTTP 404",
                f"HTTP {response.status_code}",
                response.status_code == 404,
            )

        print("\n=== CORS VALIDATION ===")

        trusted_preflight = requests.options(
            f"{BASE_URL}/health",
            headers={
                "Origin": trusted_origin,
                "Access-Control-Request-Method": "GET",
            },
            timeout=15,
        )

        trusted_allow_origin = header_value(
            trusted_preflight,
            "Access-Control-Allow-Origin",
        )

        add_result(
            results,
            "Trusted CORS origin",
            trusted_origin,
            trusted_allow_origin or "missing",
            trusted_allow_origin
            == trusted_origin,
        )

        untrusted_preflight = requests.options(
            f"{BASE_URL}/health",
            headers={
                "Origin": untrusted_origin,
                "Access-Control-Request-Method": "GET",
            },
            timeout=15,
        )

        untrusted_allow_origin = header_value(
            untrusted_preflight,
            "Access-Control-Allow-Origin",
        )

        add_result(
            results,
            "Untrusted CORS origin",
            "not allowed",
            (
                untrusted_allow_origin
                or "not allowed"
            ),
            not untrusted_allow_origin,
        )

        print("\n=== TRUSTED HOST VALIDATION ===")

        trusted_host_response = requests.get(
            f"{BASE_URL}/health",
            headers={
                "Host": trusted_host,
            },
            timeout=15,
        )

        add_result(
            results,
            "Trusted Host",
            "HTTP 200",
            f"HTTP {trusted_host_response.status_code}",
            trusted_host_response.status_code
            == 200,
        )

        invalid_host_response = requests.get(
            f"{BASE_URL}/health",
            headers={
                "Host": "evil.example",
            },
            timeout=15,
        )

        add_result(
            results,
            "Untrusted Host",
            "HTTP 400",
            f"HTTP {invalid_host_response.status_code}",
            invalid_host_response.status_code
            == 400,
        )

    except Exception as exc:
        execution_error = exc

        print(
            f"\nPRODUCTION SECURITY ERROR: {exc}",
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
        print("\n=== RESTORING DEVELOPMENT CONFIGURATION ===")

        ENV_FILE.write_bytes(original_bytes)

        try:
            recreate_backend()
            restored_health = wait_for_backend()
            restored = (
                restored_health.status_code == 200
            )
        except Exception as restore_error:
            print(
                f"RESTORE ERROR: {restore_error}",
                file=sys.stderr,
            )
            restored = False

        add_result(
            results,
            "Development configuration restored",
            "healthy",
            (
                "healthy"
                if restored
                else "not healthy"
            ),
            restored,
        )

        if BACKUP_FILE.exists():
            BACKUP_FILE.unlink()

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
        "Production HTTP Security Validation",
        "===================================",
        f"Environment key: {environment_key}",
        f"Trusted origin: {trusted_origin}",
        f"Trusted host: {trusted_host}",
        f"Total checks: {len(results)}",
        (
            "Passed checks: "
            f"{len(results) - len(failed)}"
        ),
        f"Failed checks: {len(failed)}",
        (
            "Development configuration restored: "
            f"{restored}"
        ),
    ]

    SUMMARY_FILE.write_text(
        "\n".join(summary_lines) + "\n",
        encoding="utf-8",
    )

    print(
        "\n=== PRODUCTION SECURITY SUMMARY ==="
    )
    print("Total checks :", len(results))
    print(
        "Passed       :",
        len(results) - len(failed),
    )
    print("Failed       :", len(failed))
    print(
        "Dev restored :",
        restored,
    )
    print("Results CSV  :", RESULTS_FILE)
    print("Summary      :", SUMMARY_FILE)

    return (
        1
        if failed or execution_error
        else 0
    )


if __name__ == "__main__":
    sys.exit(main())
