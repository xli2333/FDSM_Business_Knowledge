from __future__ import annotations

from fastapi import APIRouter

from backend.models.schemas import TagsResponse
from backend.services.catalog_service import get_tag_articles, list_tags
from backend.services.tag_engine import generate_tags_for_articles

router = APIRouter(prefix="/api", tags=["tags"])


@router.get("/tags", response_model=TagsResponse)
def tags():
    return list_tags()


@router.get("/tags/cloud")
def tag_cloud():
    payload = list_tags()
    return payload["hot"]


@router.get("/tags/{tag_slug}/articles")
def tag_articles(tag_slug: str, page: int = 1, page_size: int = 12):
    return get_tag_articles(tag_slug, page=page, page_size=page_size)


@router.post("/tags/batch-generate")
def batch_generate_tags(limit: int = 50, regenerate: bool = False):
    return generate_tags_for_articles(limit=limit, regenerate=regenerate)
