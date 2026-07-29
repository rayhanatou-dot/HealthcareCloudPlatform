from pathlib import Path
import ast
import csv

SOURCE_DIR = Path("backend/app/api/v1/endpoints")
OUTPUT_FILE = Path("tests/security/rbac_matrix.csv")
HTTP_METHODS = {"get", "post", "put", "patch", "delete"}


def dotted_name(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = dotted_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""


def extract_roles(node):
    found = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Call) and dotted_name(child.func).endswith("require_roles"):
            for arg in child.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    found.add(arg.value)
    return found


rows = []

for source_file in sorted(SOURCE_DIR.glob("*.py")):
    tree = ast.parse(
        source_file.read_text(encoding="utf-8-sig"),
        filename=str(source_file),
    )

    router_roles = set()
    for node in tree.body:
        value = node.value if isinstance(node, (ast.Assign, ast.AnnAssign)) else None
        if isinstance(value, ast.Call) and dotted_name(value.func).endswith("APIRouter"):
            router_roles.update(extract_roles(value))

    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue

            method = dotted_name(decorator.func).split(".")[-1].lower()
            if method not in HTTP_METHODS:
                continue

            path = "/"
            if decorator.args and isinstance(decorator.args[0], ast.Constant):
                if isinstance(decorator.args[0].value, str):
                    path = decorator.args[0].value

            route_roles = extract_roles(node)
            allowed_roles = route_roles or router_roles

            rows.append(
                {
                    "Module": source_file.stem,
                    "Method": method.upper(),
                    "Path": path,
                    "Function": node.name,
                    "AllowedRoles": ", ".join(sorted(allowed_roles)),
                    "SecurityScope": (
                        "route"
                        if route_roles
                        else "router"
                        if router_roles
                        else "not_detected"
                    ),
                    "Line": node.lineno,
                }
            )

OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

with OUTPUT_FILE.open("w", newline="", encoding="utf-8-sig") as csv_file:
    writer = csv.DictWriter(
        csv_file,
        fieldnames=[
            "Module",
            "Method",
            "Path",
            "Function",
            "AllowedRoles",
            "SecurityScope",
            "Line",
        ],
    )
    writer.writeheader()
    writer.writerows(rows)

print(f"Routes exported: {len(rows)}")
print(f"File created: {OUTPUT_FILE}")
