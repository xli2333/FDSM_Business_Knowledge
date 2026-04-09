from __future__ import annotations

from fastapi import APIRouter, Header

from backend.models.schemas import (
    BillingCheckoutIntentRequest,
    BillingCheckoutIntentResponse,
    BillingMeResponse,
    BillingPlansResponse,
)
from backend.services.billing_service import create_checkout_intent, get_billing_profile, list_billing_plans
from backend.services.supabase_auth_service import get_authenticated_user

router = APIRouter(prefix="/api/billing", tags=["billing"])


@router.get("/plans", response_model=BillingPlansResponse)
def billing_plans(language: str = "zh"):
    return list_billing_plans(language=language)


@router.get("/me", response_model=BillingMeResponse)
def billing_me(
    language: str = "zh",
    authorization: str | None = Header(default=None),
    x_debug_user_id: str | None = Header(default=None, alias="X-Debug-User-Id"),
    x_debug_user_email: str | None = Header(default=None, alias="X-Debug-User-Email"),
):
    user = get_authenticated_user(
        authorization,
        debug_user_id=x_debug_user_id,
        debug_user_email=x_debug_user_email,
    )
    return get_billing_profile(user, language=language)


@router.post("/checkout-intent", response_model=BillingCheckoutIntentResponse)
def billing_checkout_intent(
    payload: BillingCheckoutIntentRequest,
    authorization: str | None = Header(default=None),
    x_debug_user_id: str | None = Header(default=None, alias="X-Debug-User-Id"),
    x_debug_user_email: str | None = Header(default=None, alias="X-Debug-User-Email"),
):
    user = get_authenticated_user(
        authorization,
        debug_user_id=x_debug_user_id,
        debug_user_email=x_debug_user_email,
    )
    return create_checkout_intent(
        user,
        plan_code=payload.plan_code,
        success_url=payload.success_url,
        cancel_url=payload.cancel_url,
    )
