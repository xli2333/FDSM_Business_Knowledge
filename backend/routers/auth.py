from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, status

from backend.models.schemas import AuthLoginResponse, AuthPasswordLoginRequest, AuthStatusResponse
from backend.services.membership_service import get_membership_profile
from backend.services.supabase_auth_service import get_auth_status_payload
from backend.services.user_profile_service import authenticate_preview_account, get_business_profile, role_home_path_for_tier

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/status", response_model=AuthStatusResponse)
def auth_status(
    authorization: str | None = Header(default=None),
    x_debug_user_id: str | None = Header(default=None, alias="X-Debug-User-Id"),
    x_debug_user_email: str | None = Header(default=None, alias="X-Debug-User-Email"),
):
    return get_auth_status_payload(
        authorization,
        debug_user_id=x_debug_user_id,
        debug_user_email=x_debug_user_email,
    )


@router.post("/login", response_model=AuthLoginResponse)
def auth_login(payload: AuthPasswordLoginRequest):
    account = authenticate_preview_account(payload.email, payload.password)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    user = {
        "id": account["user_id"],
        "email": account["email"],
    }
    membership = get_membership_profile(user)
    business_profile = get_business_profile(user, membership)
    return {
        "authenticated": True,
        "auth_mode": "password",
        "user": {"id": user["id"], "email": user["email"]},
        "membership": membership,
        "business_profile": business_profile,
        "role_home_path": business_profile.get("role_home_path")
        or role_home_path_for_tier((membership or {}).get("tier")),
    }
