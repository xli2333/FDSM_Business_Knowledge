from __future__ import annotations

from fastapi import APIRouter, Header

from backend.models.schemas import FollowListResponse, FollowRequest, FollowToggleResponse, WatchlistResponse
from backend.services.follow_service import get_watchlist, list_follows, toggle_follow
from backend.services.supabase_auth_service import get_authenticated_user

router = APIRouter(prefix="/api/follows", tags=["follows"])


def _resolve_user(
    authorization: str | None,
    x_debug_user_id: str | None,
    x_debug_user_email: str | None,
):
    return get_authenticated_user(
        authorization,
        debug_user_id=x_debug_user_id,
        debug_user_email=x_debug_user_email,
    )


@router.get("", response_model=FollowListResponse)
def follows_list(
    authorization: str | None = Header(default=None),
    x_debug_user_id: str | None = Header(default=None, alias="X-Debug-User-Id"),
    x_debug_user_email: str | None = Header(default=None, alias="X-Debug-User-Email"),
):
    user = _resolve_user(authorization, x_debug_user_id, x_debug_user_email)
    return list_follows(user)


@router.post("", response_model=FollowToggleResponse)
def follows_toggle(
    payload: FollowRequest,
    authorization: str | None = Header(default=None),
    x_debug_user_id: str | None = Header(default=None, alias="X-Debug-User-Id"),
    x_debug_user_email: str | None = Header(default=None, alias="X-Debug-User-Email"),
):
    user = _resolve_user(authorization, x_debug_user_id, x_debug_user_email)
    return toggle_follow(
        user,
        entity_type=payload.entity_type,
        entity_slug=payload.entity_slug,
        active=payload.active,
    )


@router.get("/watchlist", response_model=WatchlistResponse)
def follows_watchlist(
    limit: int = 24,
    entity_type: str | None = None,
    entity_slug: str | None = None,
    authorization: str | None = Header(default=None),
    x_debug_user_id: str | None = Header(default=None, alias="X-Debug-User-Id"),
    x_debug_user_email: str | None = Header(default=None, alias="X-Debug-User-Email"),
):
    user = _resolve_user(authorization, x_debug_user_id, x_debug_user_email)
    return get_watchlist(user, limit=limit, entity_type=entity_type, entity_slug=entity_slug)
