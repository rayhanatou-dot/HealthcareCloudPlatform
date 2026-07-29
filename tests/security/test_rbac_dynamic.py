from __future__ import annotations

import csv
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


BASE_URL = os.getenv("RBAC_TEST_BASE_URL", "http://localhost:8000").rstrip("/")
ENV_FILE = Path(".env")
OUTPUT_FILE = Path("tests/security/rbac_dynamic_results.csv")

USERS = {
    "Admin": "demo_admin",
    "Doctor": "demo_doctor",
    "Nurse": "demo_nurse",
    "Lab Staff": "demo_lab_staff",
    "Pharmacist": "demo_pharmacist",
    "Data Manager": "demo_data_manager",
}

TESTS = [
    {
        "name": "FHIR Condition read",
        "method": "GET",
        "path": "/api/v1/fhir/Condition/1",
        "allowed_roles": {"Admin", "Doctor", "Nurse", "Data Manager"},
    },
    {
        "name": "FHIR Patient read",
        "method": "GET",
        "path": "/api/v1/fhir/Patient/1192",
        "allowed_roles": {
            "Admin",
            "Doctor",
            "Nurse",
            "Pharmacist",
            "Data Manager",
        },
    },
    {
        "name": "Clinical Patient read",
        "method": "GET",
        "path": "/api/v1/patients/1192",
        "allowed_roles": {
            "Admin",
            "Doctor",
            "Nurse",
            "Lab Staff",
            "Data Manager",
        },
    },
]


def read_env_value(name: str) -> str:
    if not ENV_FILE.exists():
        raise RuntimeError(f"Environment file not found: {ENV_FILE}")

    for raw_line in ENV_FILE.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()

        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)

        if key.strip() == name:
            return value.strip().strip('"').strip("'")

    raise RuntimeError(f"Missing environment variable: {name}")


def perform_request(
    method: str,
    path: str,
    token: str | None = None,
    body: bytes | None = None,
    content_type: str | None = None,
) -> tuple[int, str]:
    headers = {"Accept": "application/json"}

    if token:
        headers["Authorization"] = f"Bearer {token}"

    if content_type:
        headers["Content-Type"] = content_type

    request = urllib.request.Request(
        url=f"{BASE_URL}{path}",
        data=body,
        headers=headers,
        method=method,
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            response_body = response.read().decode("utf-8", errors="replace")
            return response.status, response_body

    except urllib.error.HTTPError as error:
        response_body = error.read().decode("utf-8", errors="replace")
        return error.code, response_body


def login(username: str, password: str) -> str:
    body = urllib.parse.urlencode(
        {
            "username": username,
            "password": password,
        }
    ).encode("utf-8")

    status, response_body = perform_request(
        method="POST",
        path="/api/v1/auth/login",
        body=body,
        content_type="application/x-www-form-urlencoded",
    )

    if status != 200:
        raise RuntimeError(
            f"Login failed for {username}: HTTP {status} {response_body[:200]}"
        )

    payload = json.loads(response_body)
    token = payload.get("access_token")

    if not token:
        raise RuntimeError(f"No access token returned for {username}")

    return token


def main() -> int:
    password = read_env_value("DEMO_ADMIN_PASSWORD")
    tokens: dict[str, str] = {}
    rows: list[dict[str, object]] = []

    print("Authenticating demo accounts...")

    for role, username in USERS.items():
        token = login(username, password)
        tokens[role] = token
        print(f"  {role:<13} {username:<20} OK")

    print("\nRunning RBAC tests...")

    for test in TESTS:
        no_token_status, _ = perform_request(
            method=test["method"],
            path=test["path"],
        )

        no_token_passed = no_token_status == 401

        rows.append(
            {
                "Test": test["name"],
                "Endpoint": test["path"],
                "Role": "Unauthenticated",
                "Username": "",
                "ExpectedStatus": 401,
                "ActualStatus": no_token_status,
                "Passed": no_token_passed,
            }
        )

        print(
            f"  {test['name']} | Unauthenticated | "
            f"expected 401, got {no_token_status} | "
            f"{'PASS' if no_token_passed else 'FAIL'}"
        )

        for role, username in USERS.items():
            expected_status = 200 if role in test["allowed_roles"] else 403
            actual_status, _ = perform_request(
                method=test["method"],
                path=test["path"],
                token=tokens[role],
            )
            passed = actual_status == expected_status

            rows.append(
                {
                    "Test": test["name"],
                    "Endpoint": test["path"],
                    "Role": role,
                    "Username": username,
                    "ExpectedStatus": expected_status,
                    "ActualStatus": actual_status,
                    "Passed": passed,
                }
            )

            print(
                f"  {test['name']} | {role:<13} | "
                f"expected {expected_status}, got {actual_status} | "
                f"{'PASS' if passed else 'FAIL'}"
            )

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    with OUTPUT_FILE.open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=[
                "Test",
                "Endpoint",
                "Role",
                "Username",
                "ExpectedStatus",
                "ActualStatus",
                "Passed",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    passed_count = sum(bool(row["Passed"]) for row in rows)
    failed_count = len(rows) - passed_count

    print("\n=== RBAC DYNAMIC TEST SUMMARY ===")
    print(f"Total checks : {len(rows)}")
    print(f"Passed       : {passed_count}")
    print(f"Failed       : {failed_count}")
    print(f"Results file : {OUTPUT_FILE}")

    if failed_count:
        print("\nFailed checks:")

        for row in rows:
            if not row["Passed"]:
                print(
                    f"  {row['Test']} | {row['Role']} | "
                    f"expected {row['ExpectedStatus']}, "
                    f"got {row['ActualStatus']}"
                )

        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
