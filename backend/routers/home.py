from __future__ import annotations

from fastapi import APIRouter

from backend.models.schemas import HomeFeedResponse
from backend.services.catalog_service import get_home_feed

router = APIRouter(prefix="/api", tags=["home"])


@router.get("/home/feed", response_model=HomeFeedResponse)
def home_feed(language: str = "zh"):
    return get_home_feed(language=language)
