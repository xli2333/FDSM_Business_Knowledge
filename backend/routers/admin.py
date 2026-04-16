from __future__ import annotations

from fastapi import APIRouter, Header

from backend.models.schemas import (
    AdminContentEntity,
    AdminContentOperationsResponse,
    AdminOverviewResponse,
    AdminContentSectionUpdateRequest,
    AdminTrendingConfig,
    AdminTrendingConfigUpdateRequest,
    BillingOrdersResponse,
    MembershipListResponse,
    MembershipSummary,
    MembershipUpdateRequest,
    RagAdminOverviewResponse,
)
from backend.services.billing_service import list_billing_orders
from backend.services.content_operations_service import (
    get_content_operations_state,
    search_content_operation_candidates,
    update_content_operations_section,
    update_trending_config as save_trending_config,
)
from backend.services.membership_service import list_memberships, require_admin_profile, update_membership
from backend.services.rag_admin_service import get_rag_admin_overview
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


@router.get("/content-ops", response_model=AdminContentOperationsResponse)
def admin_content_operations(
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
    return get_content_operations_state()


@router.get("/rag", response_model=RagAdminOverviewResponse)
def admin_rag_overview(
    asset_limit: int = 12,
    job_limit: int = 12,
    event_limit: int = 8,
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
    return get_rag_admin_overview(
        asset_limit=asset_limit,
        job_limit=job_limit,
        event_limit=event_limit,
    )


@router.get("/content-ops/candidates", response_model=list[AdminContentEntity])
def admin_content_operation_candidates(
    entity_type: str,
    query: str = "",
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
    require_admin_profile(user)
    return search_content_operation_candidates(entity_type, query=query, limit=limit)


@router.put("/content-ops/sections/{slot_key}", response_model=AdminContentOperationsResponse)
def admin_update_content_operations_section(
    slot_key: str,
    payload: AdminContentSectionUpdateRequest,
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
    return update_content_operations_section(slot_key, [item.model_dump() for item in payload.items])


@router.put("/content-ops/trending", response_model=AdminTrendingConfig)
def admin_update_trending_config(
    payload: AdminTrendingConfigUpdateRequest,
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
    return save_trending_config(payload.model_dump())
