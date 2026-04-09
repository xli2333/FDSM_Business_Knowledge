from __future__ import annotations

from fastapi import APIRouter

from backend.models.schemas import TimeMachineResponse
from backend.services.catalog_service import get_time_machine

router = APIRouter(prefix="/api", tags=["time-machine"])


@router.get("/time_machine", response_model=TimeMachineResponse)
def time_machine(date: str | None = None, language: str = "zh"):
    return get_time_machine(date, language=language)
