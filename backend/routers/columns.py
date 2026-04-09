from __future__ import annotations

from fastapi import APIRouter

from backend.models.schemas import ColumnSummary
from backend.services.catalog_service import get_column_articles, list_columns

router = APIRouter(prefix="/api", tags=["columns"])


@router.get("/columns", response_model=list[ColumnSummary])
def columns():
    return list_columns()


@router.get("/columns/{slug}/articles")
def column_articles(slug: str, page: int = 1, page_size: int = 12):
    return get_column_articles(slug, page=page, page_size=page_size)
