from __future__ import annotations

from backend.config import (
    ALLOW_LEGACY_SUPABASE_AUTH,
    AUTH_BACKEND,
    IS_PRODUCTION,
    PREVIEW_AUTH_ENABLED,
)
from backend.services import cas_auth_service, supabase_auth_service


def _supabase_backend_allowed() -> bool:
    return (not IS_PRODUCTION) or ALLOW_LEGACY_SUPABASE_AUTH


def _resolved_backend() -> str:
    configured = AUTH_BACKEND
    supabase_allowed = _supabase_backend_allowed()
    if configured == "auto":
        cas_enabled = cas_auth_service.is_cas_enabled()
        supabase_enabled = supabase_allowed and supabase_auth_service.is_supabase_auth_enabled()
        if cas_enabled and supabase_enabled:
            return "dual"
        if cas_enabled:
            return "cas"
        if supabase_enabled:
            return "supabase"
        if IS_PRODUCTION:
            return "cas"
        return "supabase"
    if configured in {"dual", "supabase"} and not supabase_allowed:
        return "cas"
    if configured in {"cas", "dual", "supabase"}:
        return configured
    return "cas" if IS_PRODUCTION else "supabase"


def get_authenticated_user(
    authorization: str | None,
    *,
    debug_user_id: str | None = None,
    debug_user_email: str | None = None,
) -> dict | None:
    if not PREVIEW_AUTH_ENABLED:
        debug_user_id = None
        debug_user_email = None
    backend = _resolved_backend()
    if backend == "cas":
        return cas_auth_service.get_authenticated_user(
            authorization,
            debug_user_id=debug_user_id,
            debug_user_email=debug_user_email,
        )
    if backend == "dual":
        return supabase_auth_service.get_authenticated_user(
            authorization,
            debug_user_id=debug_user_id,
            debug_user_email=debug_user_email,
        ) or cas_auth_service.get_authenticated_user(
            authorization,
            debug_user_id=debug_user_id,
            debug_user_email=debug_user_email,
        )
    return supabase_auth_service.get_authenticated_user(
        authorization,
        debug_user_id=debug_user_id,
        debug_user_email=debug_user_email,
    )


def get_auth_status_payload(
    authorization: str | None,
    *,
    debug_user_id: str | None = None,
    debug_user_email: str | None = None,
) -> dict:
    if not PREVIEW_AUTH_ENABLED:
        debug_user_id = None
        debug_user_email = None
    backend = _resolved_backend()
    if backend == "cas":
        return cas_auth_service.get_auth_status_payload(
            authorization,
            debug_user_id=debug_user_id,
            debug_user_email=debug_user_email,
        )
    if backend == "dual":
        supabase_payload = supabase_auth_service.get_auth_status_payload(
            authorization,
            debug_user_id=debug_user_id,
            debug_user_email=debug_user_email,
        )
        if supabase_payload.get("authenticated"):
            return supabase_payload
        return cas_auth_service.get_auth_status_payload(
            authorization,
            debug_user_id=debug_user_id,
            debug_user_email=debug_user_email,
        )
    return supabase_auth_service.get_auth_status_payload(
        authorization,
        debug_user_id=debug_user_id,
        debug_user_email=debug_user_email,
    )
