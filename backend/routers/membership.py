from __future__ import annotations

from fastapi import APIRouter, Header

from backend.models.schemas import MembershipProfile
from backend.services.membership_service import get_membership_profile
from backend.services.supabase_auth_service import get_authenticated_user

router = APIRouter(prefix="/api/membership", tags=["membership"])


@router.get("/me", response_model=MembershipProfile)
def membership_me(
    authorization: str | None = Header(default=None),
    x_debug_user_id: str | None = Header(default=None, alias="X-Debug-User-Id"),
    x_debug_user_email: str | None = Header(default=None, alias="X-Debug-User-Email"),
):
    user = get_authenticated_user(
        authorization,
        debug_user_id=x_debug_user_id,
        debug_user_email=x_debug_user_email,
    )
    return get_membership_profile(user)
