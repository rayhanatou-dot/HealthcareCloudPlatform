from fastapi import FastAPI, Request
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
