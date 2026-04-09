from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException

from backend.models.schemas import SearchRequest, SearchResponse
from backend.services.rag_engine import search_articles, suggest
from backend.services.membership_service import get_membership_profile
from backend.services.supabase_auth_service import get_authenticated_user

router = APIRouter(prefix="/api", tags=["search"])


@router.post("/search", response_model=SearchResponse)
def search(
    request: SearchRequest,
    authorization: str | None = Header(default=None),
    x_debug_user_id: str | None = Header(default=None, alias="X-Debug-User-Id"),
    x_debug_user_email: str | None = Header(default=None, alias="X-Debug-User-Email"),
):
    mode = (request.mode or "smart").strip().lower()
    if mode != "exact":
        user = get_authenticated_user(
            authorization,
            debug_user_id=x_debug_user_id,
            debug_user_email=x_debug_user_email,
        )
        if not user:
            raise HTTPException(status_code=401, detail="Login required for smart search")
        membership = get_membership_profile(user)
        if not membership.get("can_access_paid"):
            raise HTTPException(status_code=403, detail="Paid membership required for smart search")
    return search_articles(
        request.query,
        mode=mode,
        language=request.language,
        filters=request.filters,
        sort=request.sort,
        page=request.page,
        page_size=request.page_size,
    )


@router.get("/suggest")
def search_suggest(query: str = "", language: str = "zh"):
    return suggest(query, language=language)
