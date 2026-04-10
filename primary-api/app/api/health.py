from fastapi import APIRouter, HTTPException

from app.models.api import HealthResponse
from app.services.repositories import store

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    if not store.ping():
        raise HTTPException(status_code=503, detail="Database unreachable")
    return HealthResponse()
