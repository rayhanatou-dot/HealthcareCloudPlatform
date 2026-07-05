from fastapi import APIRouter

api_router = APIRouter()


@api_router.get("/status")
def api_status():
    return {
        "api_version": "v1",
        "status": "active"
    }