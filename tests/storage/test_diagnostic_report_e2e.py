from __future__ import annotations

import ast
import csv
import hashlib
import json
import re
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from minio import Minio


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / ".env"
ENDPOINT_FILE = (
    PROJECT_ROOT
    / "backend"
    / "app"
    / "api"
    / "v1"
    / "endpoints"
    / "diagnostic_reports.py"
)
RESULT_FILE = (
    PROJECT_ROOT
    / "tests"
    / "storage"
    / "diagnostic_report_e2e_results.csv"
)

BASE_URL = "http://localhost:8000"


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


POSTGRES_USER = read_env_value(
    "POSTGRES_USER",
    "healthcare_user",
)
POSTGRES_DB = read_env_value(
    "POSTGRES_DB",
    "healthcare_cloud_db",
)


def psql_scalar(sql: str) -> str:
    completed = subprocess.run(
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
            "-c",
            sql,
        ],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    if completed.returncode != 0:
        raise RuntimeError(
            "PostgreSQL command failed: "
            + completed.stderr.strip()
        )

    return completed.stdout.strip()


def login(
    username: str,
    password: str,
) -> str:
    response = requests.post(
        f"{BASE_URL}/api/v1/auth/login",
        data={
            "username": username,
            "password": password,
        },
        timeout=30,
    )

    if response.status_code != 200:
        raise RuntimeError(
            f"Login failed for {username}: "
            f"HTTP {response.status_code} "
            f"{response.text[:300]}"
        )

    token = response.json().get("access_token")

    if not token:
        raise RuntimeError(
            f"No access token returned for {username}."
        )

    return token


def resolve_ref(
    schema: dict[str, Any],
    document: dict[str, Any],
) -> dict[str, Any]:
    current = schema

    while "$ref" in current:
        target: Any = document

        for part in current["$ref"].lstrip("#/").split("/"):
            target = target[part]

        current = target

    return current


def schema_variants(
    schema: dict[str, Any],
    document: dict[str, Any],
) -> list[dict[str, Any]]:
    resolved = resolve_ref(schema, document)
    variants = [resolved]

    for keyword in ("allOf", "anyOf", "oneOf"):
        for child in resolved.get(keyword, []):
            variants.extend(
                schema_variants(
                    child,
                    document,
                )
            )

    return variants


def schema_is_binary(
    schema: dict[str, Any],
    document: dict[str, Any],
) -> bool:
    for variant in schema_variants(
        schema,
        document,
    ):
        if variant.get("format") == "binary":
            return True

        if variant.get("contentEncoding") in {
            "binary",
            "base64",
        }:
            return True

        if (
            variant.get("type") == "string"
            and "file" in str(
                variant.get("title", "")
            ).lower()
        ):
            return True

    return False


def flattened_properties(
    schema: dict[str, Any],
    document: dict[str, Any],
) -> tuple[
    dict[str, dict[str, Any]],
    set[str],
]:
    properties: dict[str, dict[str, Any]] = {}
    required: set[str] = set()

    for variant in schema_variants(
        schema,
        document,
    ):
        properties.update(
            variant.get("properties", {})
        )
        required.update(
            variant.get("required", [])
        )

    return properties, required


def dotted_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id

    if isinstance(node, ast.Attribute):
        parent = dotted_name(node.value)
        return (
            f"{parent}.{node.attr}"
            if parent
            else node.attr
        )

    return ""


def source_file_field() -> str | None:
    tree = ast.parse(
        ENDPOINT_FILE.read_text(
            encoding="utf-8-sig"
        ),
        filename=str(ENDPOINT_FILE),
    )

    for node in ast.walk(tree):
        if not isinstance(
            node,
            (
                ast.FunctionDef,
                ast.AsyncFunctionDef,
            ),
        ):
            continue

        defaults = list(node.args.defaults)
        defaults.extend(
            default
            for default in node.args.kw_defaults
            if default is not None
        )

        positional_names = [
            argument.arg
            for argument in node.args.args
        ]

        positional_default_names = positional_names[
            len(positional_names) - len(node.args.defaults):
        ]

        keyword_default_names = [
            argument.arg
            for argument in node.args.kwonlyargs
        ]

        default_pairs = list(
            zip(
                positional_default_names,
                node.args.defaults,
            )
        )
        default_pairs.extend(
            (
                name,
                default,
            )
            for name, default in zip(
                keyword_default_names,
                node.args.kw_defaults,
            )
            if default is not None
        )

        for name, default in default_pairs:
            if (
                isinstance(default, ast.Call)
                and dotted_name(
                    default.func
                ).endswith("File")
            ):
                return name

        all_arguments = (
            list(node.args.args)
            + list(node.args.kwonlyargs)
        )

        for argument in all_arguments:
            annotation = dotted_name(
                argument.annotation
            )

            if annotation.endswith("UploadFile"):
                return argument.arg

    return None


def choose_file_field(
    properties: dict[str, dict[str, Any]],
    document: dict[str, Any],
) -> str:
    binary_fields = [
        name
        for name, definition in properties.items()
        if schema_is_binary(
            definition,
            document,
        )
    ]

    if len(binary_fields) == 1:
        return binary_fields[0]

    source_candidate = source_file_field()

    if (
        source_candidate
        and source_candidate in properties
    ):
        return source_candidate

    name_candidates = [
        name
        for name in properties
        if any(
            token in name.lower()
            for token in (
                "file",
                "upload",
                "attachment",
                "document",
            )
        )
    ]

    if len(name_candidates) == 1:
        return name_candidates[0]

    raise RuntimeError(
        "Unable to identify the upload field. "
        f"OpenAPI properties: {sorted(properties)}; "
        f"binary candidates: {binary_fields}; "
        f"source candidate: {source_candidate}"
    )


def find_routes(
    openapi: dict[str, Any],
) -> tuple[
    str,
    dict[str, Any],
    str,
    str,
]:
    create_routes: list[
        tuple[str, dict[str, Any]]
    ] = []
    detail_routes: list[str] = []
    download_routes: list[str] = []

    for path, operations in openapi["paths"].items():
        lowered = path.lower()

        if (
            "diagnostic" not in lowered
            or "report" not in lowered
        ):
            continue

        if "post" in operations:
            create_routes.append(
                (
                    path,
                    operations["post"],
                )
            )

        if "get" not in operations:
            continue

        if "download" in lowered:
            download_routes.append(path)

        elif "{" in path:
            detail_routes.append(path)

    if len(create_routes) != 1:
        raise RuntimeError(
            "Expected one diagnostic-report POST route, "
            f"found {[path for path, _ in create_routes]}."
        )

    if not detail_routes:
        raise RuntimeError(
            "Diagnostic-report detail route not found."
        )

    if not download_routes:
        raise RuntimeError(
            "Diagnostic-report download route not found."
        )

    return (
        create_routes[0][0],
        create_routes[0][1],
        detail_routes[0],
        download_routes[0],
    )


def request_schema(
    operation: dict[str, Any],
    openapi: dict[str, Any],
) -> tuple[
    str,
    dict[str, Any],
]:
    content = operation.get(
        "requestBody",
        {},
    ).get(
        "content",
        {},
    )

    preferred_types = (
        "multipart/form-data",
        "application/x-www-form-urlencoded",
        "application/json",
    )

    for content_type in preferred_types:
        if content_type in content:
            return (
                content_type,
                resolve_ref(
                    content[content_type]["schema"],
                    openapi,
                ),
            )

    if content:
        content_type, definition = next(
            iter(content.items())
        )

        return (
            content_type,
            resolve_ref(
                definition["schema"],
                openapi,
            ),
        )

    raise RuntimeError(
        "The upload route has no request-body schema."
    )


def schema_value(
    field_name: str,
    schema: dict[str, Any],
    patient_id: int,
    encounter_id: str,
    suffix: str,
) -> str:
    variants = schema_variants(
        schema,
        openapi={},
    ) if False else [schema]

    enum_values = schema.get("enum")

    if enum_values:
        return str(enum_values[0])

    field_type = schema.get("type")
    field_format = schema.get("format")
    lowered = field_name.lower()

    known = {
        "patient_id": str(patient_id),
        "encounter_id": encounter_id,
        "report_type": "laboratory",
        "title": "Diagnostic report E2E validation",
        "issued_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "status": "final",
        "conclusion": (
            "Automated end-to-end storage validation."
        ),
        "external_id": (
            f"diagnostic-e2e-{suffix}"
        ),
        "source_system": "validation",
    }

    if lowered in known:
        return known[lowered]

    if field_format == "date-time":
        return datetime.now(
            timezone.utc
        ).isoformat()

    if field_type in {"integer", "number"}:
        return "1"

    if field_type == "boolean":
        return "true"

    return f"validation-{suffix}"


def replace_identifier(
    template: str,
    identifier: int,
) -> str:
    return re.sub(
        r"\{[^}]+\}",
        str(identifier),
        template,
    )


def response_identifier(
    payload: Any,
) -> int:
    if isinstance(payload, dict):
        if isinstance(payload.get("id"), int):
            return payload["id"]

        if (
            isinstance(payload.get("id"), str)
            and payload["id"].isdigit()
        ):
            return int(payload["id"])

        for value in payload.values():
            try:
                return response_identifier(value)
            except ValueError:
                pass

    raise ValueError(
        "No diagnostic-report ID found "
        "in the response."
    )


def minio_client() -> Minio:
    endpoint = read_env_value(
        "MINIO_ENDPOINT",
        "localhost:9000",
    )

    if endpoint.startswith("minio:"):
        endpoint = (
            "localhost:"
            + endpoint.split(":", 1)[1]
        )

    return Minio(
        endpoint,
        access_key=read_env_value(
            "MINIO_ROOT_USER"
        ),
        secret_key=read_env_value(
            "MINIO_ROOT_PASSWORD"
        ),
        secure=read_env_value(
            "MINIO_SECURE",
            "false",
        ).lower()
        in {"1", "true", "yes"},
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
        f"{test:<34} "
        f"{'PASS' if passed else 'FAIL'} "
        f"(expected {expected}, got {actual})"
    )


def main() -> int:
    global openapi

    results: list[dict[str, Any]] = []
    created_id: int | None = None
    bucket_name: str | None = None
    object_key: str | None = None

    original_count = int(
        psql_scalar(
            "SELECT COUNT(*) FROM diagnostic_reports;"
        )
    )

    password = read_env_value(
        "DEMO_ADMIN_PASSWORD"
    )

    admin_token = login(
        "demo_admin",
        password,
    )
    pharmacist_token = login(
        "demo_pharmacist",
        password,
    )

    openapi_response = requests.get(
        f"{BASE_URL}/openapi.json",
        timeout=30,
    )

    if openapi_response.status_code != 200:
        raise RuntimeError(
            "OpenAPI is unavailable. "
            "Use development mode for this test."
        )

    openapi = openapi_response.json()

    (
        create_path,
        create_operation,
        detail_template,
        download_template,
    ) = find_routes(openapi)

    content_type, body_schema = request_schema(
        create_operation,
        openapi,
    )

    properties, required_fields = (
        flattened_properties(
            body_schema,
            openapi,
        )
    )

    file_field = choose_file_field(
        properties,
        openapi,
    )

    patient_id = int(
        psql_scalar(
            "SELECT p.id "
            "FROM patients p "
            "JOIN encounters e "
            "ON e.patient_id = p.id "
            "GROUP BY p.id "
            "ORDER BY p.id "
            "LIMIT 1;"
        )
    )

    encounter_id = psql_scalar(
        "SELECT id FROM encounters "
        f"WHERE patient_id = {patient_id} "
        "ORDER BY id LIMIT 1;"
    )

    suffix = uuid.uuid4().hex
    original_bytes = (
        b"Healthcare Cloud Platform diagnostic "
        b"report end-to-end validation.\n"
    )
    original_hash = hashlib.sha256(
        original_bytes
    ).hexdigest()

    form_data: dict[str, str] = {}

    for name, definition in properties.items():
        if name == file_field:
            continue

        resolved = resolve_ref(
            definition,
            openapi,
        )

        if (
            name in required_fields
            or name
            in {
                "patient_id",
                "encounter_id",
                "report_type",
                "title",
                "issued_at",
                "status",
                "conclusion",
                "external_id",
                "source_system",
            }
        ):
            form_data[name] = schema_value(
                name,
                resolved,
                patient_id,
                encounter_id,
                suffix,
            )

    print("=== DISCOVERED API INTERFACE ===")
    print("Create route  :", create_path)
    print("Content type  :", content_type)
    print("File field    :", file_field)
    print(
        "Form fields   :",
        ", ".join(sorted(form_data)),
    )
    print()

    try:
        response = requests.post(
            f"{BASE_URL}{create_path}",
            headers={
                "Authorization": (
                    f"Bearer {admin_token}"
                )
            },
            data=form_data,
            files={
                file_field: (
                    "diagnostic-e2e-validation.txt",
                    original_bytes,
                    "text/plain",
                )
            },
            timeout=60,
        )

        upload_ok = response.status_code in {
            200,
            201,
        }

        add_result(
            results,
            "Authorized report upload",
            "200 or 201",
            str(response.status_code),
            upload_ok,
        )

        if not upload_ok:
            print(response.text[:1500])
            raise RuntimeError(
                "Diagnostic-report upload failed."
            )

        created_id = response_identifier(
            response.json()
        )

        detail_path = replace_identifier(
            detail_template,
            created_id,
        )
        download_path = replace_identifier(
            download_template,
            created_id,
        )

        metadata_response = requests.get(
            f"{BASE_URL}{detail_path}",
            headers={
                "Authorization": (
                    f"Bearer {admin_token}"
                )
            },
            timeout=30,
        )

        add_result(
            results,
            "Authorized metadata read",
            "200",
            str(metadata_response.status_code),
            metadata_response.status_code == 200,
        )

        record = psql_scalar(
            "SELECT "
            "bucket_name || E'\\t' || "
            "object_key || E'\\t' || "
            "COALESCE(checksum_sha256, '') || E'\\t' || "
            "COALESCE(file_size_bytes::text, '') "
            "FROM diagnostic_reports "
            f"WHERE id = {created_id};"
        )

        parts = record.split("\t")

        if len(parts) != 4:
            raise RuntimeError(
                "Unable to parse the PostgreSQL record."
            )

        (
            bucket_name,
            object_key,
            database_hash,
            database_size,
        ) = parts

        add_result(
            results,
            "PostgreSQL metadata row",
            "present",
            "present" if record else "missing",
            bool(record),
        )
        add_result(
            results,
            "Database checksum",
            original_hash,
            database_hash,
            database_hash == original_hash,
        )
        add_result(
            results,
            "Database file size",
            str(len(original_bytes)),
            database_size,
            database_size == str(
                len(original_bytes)
            ),
        )

        client = minio_client()
        object_response = client.get_object(
            bucket_name,
            object_key,
        )

        try:
            stored_bytes = object_response.read()
        finally:
            object_response.close()
            object_response.release_conn()

        stored_hash = hashlib.sha256(
            stored_bytes
        ).hexdigest()

        add_result(
            results,
            "MinIO object integrity",
            original_hash,
            stored_hash,
            stored_hash == original_hash,
        )

        download_response = requests.get(
            f"{BASE_URL}{download_path}",
            headers={
                "Authorization": (
                    f"Bearer {admin_token}"
                )
            },
            timeout=30,
        )

        add_result(
            results,
            "Authorized file download",
            "200 and matching bytes",
            (
                f"{download_response.status_code} "
                f"and {'matching' if download_response.content == original_bytes else 'different'}"
            ),
            (
                download_response.status_code == 200
                and download_response.content
                == original_bytes
            ),
        )

        no_token_response = requests.get(
            f"{BASE_URL}{download_path}",
            timeout=30,
        )

        add_result(
            results,
            "Download without JWT",
            "401",
            str(no_token_response.status_code),
            no_token_response.status_code == 401,
        )

        pharmacist_response = requests.get(
            f"{BASE_URL}{download_path}",
            headers={
                "Authorization": (
                    f"Bearer {pharmacist_token}"
                )
            },
            timeout=30,
        )

        add_result(
            results,
            "Pharmacist download denied",
            "403",
            str(pharmacist_response.status_code),
            pharmacist_response.status_code == 403,
        )

    finally:
        if bucket_name and object_key:
            try:
                minio_client().remove_object(
                    bucket_name,
                    object_key,
                )
            except Exception as exc:
                print(
                    "Warning: MinIO cleanup failed:",
                    exc,
                )

        if created_id is not None:
            psql_scalar(
                "DELETE FROM diagnostic_reports "
                f"WHERE id = {created_id} "
                "RETURNING id;"
            )

    final_count = int(
        psql_scalar(
            "SELECT COUNT(*) FROM diagnostic_reports;"
        )
    )

    add_result(
        results,
        "Post-test cleanup",
        str(original_count),
        str(final_count),
        final_count == original_count,
    )

    RESULT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with RESULT_FILE.open(
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

    print(
        "\n=== DIAGNOSTIC REPORT E2E SUMMARY ==="
    )
    print("Total checks :", len(results))
    print(
        "Passed       :",
        len(results) - len(failed),
    )
    print("Failed       :", len(failed))
    print("Results file :", RESULT_FILE)

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
