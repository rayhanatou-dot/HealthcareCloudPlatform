from __future__ import annotations

from pathlib import Path
import re


ROOT = Path.cwd()
CONFIG_FILE = ROOT / "backend" / "app" / "core" / "config.py"
MAIN_FILE = ROOT / "backend" / "app" / "main.py"
DOCKERFILE = ROOT / "backend" / "Dockerfile"
ENV_FILE = ROOT / ".env"


CONFIG_CONTENT = '''from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "Healthcare Cloud Platform"
    APP_ENV: str = "development"
    APP_DEBUG: bool = True
    BACKEND_PORT: int = 8000

    DATABASE_URL: str = (
        "postgresql://your_postgres_user:"
        "your_postgres_password@localhost:5432/"
        "healthcare_cloud_db"
    )

    JWT_SECRET_KEY: str = "replace_with_secure_random_key"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    MINIO_ROOT_PASSWORD: str = "your_minio_password"
    MINIO_BUCKET_NAME: str = "healthcare-files"
    MINIO_SECURE: bool = False

    DOCS_ENABLED: bool = True
    CORS_ALLOWED_ORIGINS: str = (
        "http://localhost:3000,"
        "http://localhost:5173,"
        "http://localhost:8080,"
        "http://localhost:8081"
    )
    ALLOWED_HOSTS: str = (
        "localhost,"
        "127.0.0.1,"
        "backend,"
        "healthcare_backend"
    )

    model_config = SettingsConfigDict(
        env_file="../.env",
        extra="ignore",
    )

    @property
    def cors_allowed_origins(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.CORS_ALLOWED_ORIGINS.split(",")
            if origin.strip()
        ]

    @property
    def allowed_hosts(self) -> list[str]:
        return [
            host.strip()
            for host in self.ALLOWED_HOSTS.split(",")
            if host.strip()
        ]


settings = Settings()
'''


MAIN_CONTENT = '''from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.v1.router import api_router
from app.core.config import settings


is_production = settings.APP_ENV.strip().lower() == "production"
docs_enabled = settings.DOCS_ENABLED and not is_production


app = FastAPI(
    title="Healthcare Cloud Platform API",
    description=(
        "Secure, scalable, and cost-efficient healthcare "
        "data management prototype."
    ),
    version="0.1.0",
    docs_url="/docs" if docs_enabled else None,
    redoc_url="/redoc" if docs_enabled else None,
    openapi_url="/openapi.json" if docs_enabled else None,
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_credentials=True,
    allow_methods=[
        "GET",
        "POST",
        "PUT",
        "PATCH",
        "DELETE",
        "OPTIONS",
    ],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "Accept",
    ],
)


if is_production:
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=settings.allowed_hosts,
    )


@app.middleware("http")
async def add_security_headers(
    request: Request,
    call_next,
):
    response = await call_next(request)

    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = (
        "camera=(), microphone=(), geolocation=()"
    )
    response.headers["Cache-Control"] = "no-store"

    if request.url.path in {
        "/docs",
        "/redoc",
        "/openapi.json",
    }:
        response.headers["Content-Security-Policy"] = (
            "default-src 'self' https: data:; "
            "script-src 'self' https: 'unsafe-inline'; "
            "style-src 'self' https: 'unsafe-inline'; "
            "img-src 'self' https: data:; "
            "frame-ancestors 'none'; "
            "base-uri 'self'"
        )
    else:
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; "
            "frame-ancestors 'none'; "
            "base-uri 'none'; "
            "form-action 'none'"
        )

    if is_production:
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )

    return response


app.include_router(
    api_router,
    prefix="/api/v1",
)


@app.get("/")
def root():
    return {
        "message": "Healthcare Cloud Platform API is running",
        "status": "success",
    }


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "healthcare-cloud-platform",
    }
'''


def ensure_exists(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Required file not found: {path}")


def write_utf8_no_bom(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8", newline="\n")


def add_env_setting(lines: list[str], name: str, value: str) -> None:
    prefix = f"{name}="

    for index, line in enumerate(lines):
        if line.strip().startswith(prefix):
            lines[index] = f"{name}={value}"
            return

    lines.append(f"{name}={value}")


def prepare_dockerfile_patch(path: Path) -> tuple[str, bool]:
    content = path.read_text(encoding="utf-8-sig")

    if "--no-server-header" in content:
        return content, False

    updated = re.sub(
        r'("--timeout-keep-alive"\s*,\s*"5")(\s*\])',
        r'\1, "--no-server-header"\2',
        content,
        count=1,
    )

    if updated == content:
        raise RuntimeError(
            "Dockerfile CMD was not recognized. "
            "No project files were modified."
        )

    return updated, True


def main() -> None:
    for required_file in (
        CONFIG_FILE,
        MAIN_FILE,
        DOCKERFILE,
        ENV_FILE,
    ):
        ensure_exists(required_file)

    dockerfile_content, dockerfile_changed = (
        prepare_dockerfile_patch(DOCKERFILE)
    )

    env_lines = ENV_FILE.read_text(
        encoding="utf-8-sig"
    ).splitlines()

    add_env_setting(env_lines, "DOCS_ENABLED", "true")
    add_env_setting(
        env_lines,
        "CORS_ALLOWED_ORIGINS",
        (
            "http://localhost:3000,"
            "http://localhost:5173,"
            "http://localhost:8080,"
            "http://localhost:8081"
        ),
    )
    add_env_setting(
        env_lines,
        "ALLOWED_HOSTS",
        (
            "localhost,"
            "127.0.0.1,"
            "backend,"
            "healthcare_backend"
        ),
    )

    write_utf8_no_bom(CONFIG_FILE, CONFIG_CONTENT)
    write_utf8_no_bom(MAIN_FILE, MAIN_CONTENT)
    write_utf8_no_bom(
        ENV_FILE,
        "\n".join(env_lines).rstrip() + "\n",
    )

    if dockerfile_changed:
        write_utf8_no_bom(
            DOCKERFILE,
            dockerfile_content,
        )

    print("HTTP security configuration applied.")
    print(f"Updated: {CONFIG_FILE}")
    print(f"Updated: {MAIN_FILE}")
    print(f"Updated: {ENV_FILE}")
    print(
        f"Updated: {DOCKERFILE}"
        if dockerfile_changed
        else f"Already configured: {DOCKERFILE}"
    )


if __name__ == "__main__":
    main()
