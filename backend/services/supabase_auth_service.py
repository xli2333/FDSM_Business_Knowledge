from __future__ import annotations

from functools import lru_cache

import requests

from backend.config import PREVIEW_AUTH_ENABLED, SUPABASE_ANON_KEY, SUPABASE_AUTH_ENABLED, SUPABASE_AUTH_TIMEOUT_SECONDS, SUPABASE_URL


def is_supabase_auth_enabled() -> bool:
    return SUPABASE_AUTH_ENABLED


def _extract_bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    prefix = "bearer "
    text = authorization.strip()
    if text.lower().startswith(prefix):
        token = text[len(prefix) :].strip()
        return token or None
    return None


@lru_cache(maxsize=1)
def _user_endpoint() -> str:
    return f"{SUPABASE_URL}/auth/v1/user"


def _build_debug_user(debug_user_id: str | None, debug_user_email: str | None) -> dict | None:
    if not PREVIEW_AUTH_ENABLED or not debug_user_id:
        return None
    user_id = debug_user_id.strip()
    if not user_id:
        return None
    return {
        "id": user_id,
        "email": debug_user_email.strip() if debug_user_email else None,
        "raw_user": {"debug": True},
    }


def get_authenticated_user(
    authorization: str | None,
    *,
    debug_user_id: str | None = None,
    debug_user_email: str | None = None,
) -> dict | None:
    if not is_supabase_auth_enabled():
        return _build_debug_user(debug_user_id, debug_user_email)
    access_token = _extract_bearer_token(authorization)
    if not access_token:
        return _build_debug_user(debug_user_id, debug_user_email)

    try:
        response = requests.get(
            _user_endpoint(),
            headers={
                "apikey": SUPABASE_ANON_KEY,
                "Authorization": f"Bearer {access_token}",
            },
            timeout=SUPABASE_AUTH_TIMEOUT_SECONDS,
        )
    except requests.RequestException:
        return None

    if response.status_code != 200:
        return None

    payload = response.json()
    user_id = payload.get("id")
    if not user_id:
        return None
    return {
        "id": user_id,
        "email": payload.get("email"),
        "raw_user": payload,
    }


def get_auth_status_payload(
    authorization: str | None,
    *,
    debug_user_id: str | None = None,
    debug_user_email: str | None = None,
) -> dict:
    from backend.services.membership_service import get_membership_profile
    from backend.services.user_profile_service import get_business_profile, role_home_path_for_tier

    user = get_authenticated_user(
        authorization,
        debug_user_id=debug_user_id,
        debug_user_email=debug_user_email,
    )
    membership = get_membership_profile(user)
    business_profile = get_business_profile(user, membership)
    return {
        "enabled": is_supabase_auth_enabled() or PREVIEW_AUTH_ENABLED,
        "authenticated": bool(user),
        "user": {"id": user["id"], "email": user.get("email")} if user else None,
        "auth_mode": "password" if PREVIEW_AUTH_ENABLED else "email_otp",
        "membership": membership,
        "business_profile": business_profile,
        "role_home_path": business_profile.get("role_home_path")
        or role_home_path_for_tier((membership or {}).get("tier")),
    }
