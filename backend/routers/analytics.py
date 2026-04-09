from __future__ import annotations

from fastapi import APIRouter, Header

from backend.models.schemas import AnalyticsOverviewResponse
from backend.services.analytics_service import get_analytics_overview
from backend.services.membership_service import require_admin_profile
from backend.services.supabase_auth_service import get_authenticated_user

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


def _require_analytics_admin(
    authorization: str | None,
    debug_user_id: str | None,
    debug_user_email: str | None,
) -> None:
    user = get_authenticated_user(
        authorization,
        debug_user_id=debug_user_id,
        debug_user_email=debug_user_email,
    )
    require_admin_profile(user)


@router.get("/overview", response_model=AnalyticsOverviewResponse)
def analytics_overview(
    authorization: str | None = Header(default=None),
    x_debug_user_id: str | None = Header(default=None, alias="X-Debug-User-Id"),
    x_debug_user_email: str | None = Header(default=None, alias="X-Debug-User-Email"),
):
    _require_analytics_admin(authorization, x_debug_user_id, x_debug_user_email)
    return get_analytics_overview()
