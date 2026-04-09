from __future__ import annotations

from fastapi import APIRouter, Header

from backend.models.schemas import (
    AdminOverviewResponse,
    BillingOrdersResponse,
    MembershipListResponse,
    MembershipSummary,
    MembershipUpdateRequest,
)
from backend.services.billing_service import list_billing_orders
from backend.services.membership_service import list_memberships, require_admin_profile, update_membership
from backend.services.supabase_auth_service import get_authenticated_user
from backend.services.user_profile_service import get_admin_overview

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/overview", response_model=AdminOverviewResponse)
def admin_overview(
    authorization: str | None = Header(default=None),
    x_debug_user_id: str | None = Header(default=None, alias="X-Debug-User-Id"),
    x_debug_user_email: str | None = Header(default=None, alias="X-Debug-User-Email"),
):
    user = get_authenticated_user(
        authorization,
        debug_user_id=x_debug_user_id,
        debug_user_email=x_debug_user_email,
    )
    require_admin_profile(user)
    return get_admin_overview()


@router.get("/memberships", response_model=MembershipListResponse)
def admin_memberships(
    limit: int = 100,
    query: str = "",
    authorization: str | None = Header(default=None),
    x_debug_user_id: str | None = Header(default=None, alias="X-Debug-User-Id"),
    x_debug_user_email: str | None = Header(default=None, alias="X-Debug-User-Email"),
):
    user = get_authenticated_user(
        authorization,
        debug_user_id=x_debug_user_id,
        debug_user_email=x_debug_user_email,
    )
    require_admin_profile(user)
    return list_memberships(limit=limit, query=query)


@router.put("/memberships/{user_id}", response_model=MembershipSummary)
def admin_update_membership(
    user_id: str,
    payload: MembershipUpdateRequest,
    authorization: str | None = Header(default=None),
    x_debug_user_id: str | None = Header(default=None, alias="X-Debug-User-Id"),
    x_debug_user_email: str | None = Header(default=None, alias="X-Debug-User-Email"),
):
    user = get_authenticated_user(
        authorization,
        debug_user_id=x_debug_user_id,
        debug_user_email=x_debug_user_email,
    )
    require_admin_profile(user)
    return update_membership(
        user_id,
        email=payload.email,
        tier=payload.tier,
        status=payload.status,
        note=payload.note,
        expires_at=payload.expires_at,
        actor_user=user,
    )


@router.get("/billing/orders", response_model=BillingOrdersResponse)
def admin_billing_orders(
    limit: int = 100,
    query: str = "",
    authorization: str | None = Header(default=None),
    x_debug_user_id: str | None = Header(default=None, alias="X-Debug-User-Id"),
    x_debug_user_email: str | None = Header(default=None, alias="X-Debug-User-Email"),
):
    user = get_authenticated_user(
        authorization,
        debug_user_id=x_debug_user_id,
        debug_user_email=x_debug_user_email,
    )
    require_admin_profile(user)
    return list_billing_orders(limit=limit, query=query)
