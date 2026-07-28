from fastapi import APIRouter

from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.endpoints.diagnostic_reports import (
    router as diagnostic_reports_router,
)
from app.api.v1.endpoints.encounters import encounters_router
from app.api.v1.endpoints.observations import observations_router
from app.api.v1.endpoints.patients import router as patients_router
from app.api.v1.endpoints.prescriptions import prescriptions_router
from app.api.v1.endpoints.fhir import router as fhir_router


api_router = APIRouter()


api_router.include_router(auth_router)
api_router.include_router(patients_router)
api_router.include_router(encounters_router)
api_router.include_router(observations_router)
api_router.include_router(prescriptions_router)
api_router.include_router(diagnostic_reports_router)
api_router.include_router(fhir_router)