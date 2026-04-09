from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException

from backend.models.schemas import UserDashboardResponse, UserLibraryResponse
from backend.services.membership_service import get_membership_profile
from backend.services.supabase_auth_service import get_authenticated_user
from backend.services.user_profile_service import get_user_dashboard
from backend.services.user_activity_service import get_user_library

router = APIRouter(prefix="/api/me", tags=["me"])


@router.get("/dashboard", response_model=UserDashboardResponse)
def my_dashboard(
    authorization: str | None = Header(default=None),
    x_debug_user_id: str | None = Header(default=None, alias="X-Debug-User-Id"),
    x_debug_user_email: str | None = Header(default=None, alias="X-Debug-User-Email"),
):
    user = get_authenticated_user(
        authorization,
        debug_user_id=x_debug_user_id,
        debug_user_email=x_debug_user_email,
    )
    return get_user_dashboard(user, get_membership_profile(user))


@router.get("/library", response_model=UserLibraryResponse)
def my_library(
    limit: int = 12,
    authorization: str | None = Header(default=None),
    x_debug_user_id: str | None = Header(default=None, alias="X-Debug-User-Id"),
    x_debug_user_email: str | None = Header(default=None, alias="X-Debug-User-Email"),
):
    user = get_authenticated_user(
        authorization,
        debug_user_id=x_debug_user_id,
        debug_user_email=x_debug_user_email,
    )
    if not user:
        raise HTTPException(status_code=401, detail="Login required")
    return get_user_library(user["id"], limit=limit)
