from __future__ import annotations

from fastapi import APIRouter

from backend.models.schemas import OrganizationDetail, OrganizationSummary
from backend.services.catalog_service import get_organization_detail, list_organizations

router = APIRouter(prefix="/api", tags=["organizations"])


@router.get("/organizations", response_model=list[OrganizationSummary])
def organizations(limit: int = 60):
    return list_organizations(limit=limit)


@router.get("/organizations/{slug}", response_model=OrganizationDetail)
def organization_detail(slug: str, page: int = 1, page_size: int = 12):
    return get_organization_detail(slug, page=page, page_size=page_size)
