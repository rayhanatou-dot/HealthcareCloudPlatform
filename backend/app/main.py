from fastapi import FastAPI
from app.api.v1.router import api_router

app = FastAPI(
    title="Healthcare Cloud Platform API",
    description="Secure, scalable, and cost-efficient healthcare data management prototype.",
    version="0.1.0"
)

app.include_router(api_router, prefix="/api/v1")


@app.get("/")
def root():
    return {
        "message": "Healthcare Cloud Platform API is running",
        "status": "success"
    }


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "healthcare-cloud-platform"
    }