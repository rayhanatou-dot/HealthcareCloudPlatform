from __future__ import annotations

import csv
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


BASE_URL = os.getenv("JWT_TEST_BASE_URL", "http://localhost:8000").rstrip("/")
ENV_FILE = Path(".env")
OUTPUT_FILE = Path("tests/security/jwt_security_results.csv")


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
    authorization_header: str | None = None,
    body: bytes | None = None,
    content_type: str | None = None,
) -> tuple[int, str]:
    headers = {"Accept": "application/json"}

    if token:
        headers["Authorization"] = f"Bearer {token}"

    if authorization_header:
        headers["Authorization"] = authorization_header

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


def login(username: str, password: str) -> tuple[int, str]:
    body = urllib.parse.urlencode(
        {
            "username": username,
            "password": password,
        }
    ).encode("utf-8")

    return perform_request(
        method="POST",
        path="/api/v1/auth/login",
        body=body,
        content_type="application/x-www-form-urlencoded",
    )


def mutate_token(token: str) -> str:
    parts = token.split(".")

    if len(parts) != 3 or not parts[2]:
        return f"{token}x"

    signature = parts[2]
    replacement = "A" if signature[0] != "A" else "B"
    parts[2] = replacement + signature[1:]
    return ".".join(parts)


def add_result(
    rows: list[dict[str, object]],
    test_name: str,
    expected_status: int,
    actual_status: int,
) -> None:
    passed = expected_status == actual_status

    rows.append(
        {
            "Test": test_name,
            "ExpectedStatus": expected_status,
            "ActualStatus": actual_status,
            "Passed": passed,
        }
    )

    print(
        f"{test_name:<34} expected {expected_status}, "
        f"got {actual_status} | {'PASS' if passed else 'FAIL'}"
    )


def main() -> int:
    username = "demo_admin"
    password = read_env_value("DEMO_ADMIN_PASSWORD")
    rows: list[dict[str, object]] = []

    print("Running JWT and authentication security tests...\n")

    valid_status, valid_body = login(username, password)
    add_result(rows, "Valid login", 200, valid_status)

    if valid_status != 200:
        print("\nValid login failed. Remaining token tests cannot run.")
        return 1

    token = json.loads(valid_body).get("access_token")

    if not token:
        raise RuntimeError("Valid login did not return an access token.")

    invalid_password_status, _ = login(
        username,
        f"{password}-invalid",
    )
    add_result(
        rows,
        "Invalid password",
        401,
        invalid_password_status,
    )

    unknown_user_status, _ = login(
        "user_that_does_not_exist",
        password,
    )
    add_result(
        rows,
        "Unknown username",
        401,
        unknown_user_status,
    )

    valid_token_status, _ = perform_request(
        method="GET",
        path="/api/v1/auth/me",
        token=token,
    )
    add_result(
        rows,
        "Valid JWT on protected endpoint",
        200,
        valid_token_status,
    )

    missing_token_status, _ = perform_request(
        method="GET",
        path="/api/v1/auth/me",
    )
    add_result(
        rows,
        "Missing JWT",
        401,
        missing_token_status,
    )

    malformed_token_status, _ = perform_request(
        method="GET",
        path="/api/v1/auth/me",
        token="not-a-valid-jwt",
    )
    add_result(
        rows,
        "Malformed JWT",
        401,
        malformed_token_status,
    )

    tampered_token_status, _ = perform_request(
        method="GET",
        path="/api/v1/auth/me",
        token=mutate_token(token),
    )
    add_result(
        rows,
        "Tampered JWT signature",
        401,
        tampered_token_status,
    )

    wrong_scheme_status, _ = perform_request(
        method="GET",
        path="/api/v1/auth/me",
        authorization_header=f"Basic {token}",
    )
    add_result(
        rows,
        "Wrong authorization scheme",
        401,
        wrong_scheme_status,
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
                "ExpectedStatus",
                "ActualStatus",
                "Passed",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    passed_count = sum(bool(row["Passed"]) for row in rows)
    failed_count = len(rows) - passed_count

    print("\n=== JWT SECURITY TEST SUMMARY ===")
    print(f"Total checks : {len(rows)}")
    print(f"Passed       : {passed_count}")
    print(f"Failed       : {failed_count}")
    print(f"Results file : {OUTPUT_FILE}")

    return 1 if failed_count else 0


if __name__ == "__main__":
    sys.exit(main())
