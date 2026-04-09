from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import PlainTextResponse

from backend.models.schemas import (
    CommerceOverviewResponse,
    DemoRequestIn,
    DemoRequestResponse,
    DemoRequestSummary,
)
from backend.services.membership_service import require_admin_profile
from backend.services.supabase_auth_service import get_authenticated_user
from backend.services.commerce_service import (
    create_demo_request,
    export_demo_requests_csv,
    get_commerce_overview,
    list_demo_requests,
)

router = APIRouter(prefix="/api/commerce", tags=["commerce"])


@router.get("/overview", response_model=CommerceOverviewResponse)
def commerce_overview():
    return get_commerce_overview()


@router.post("/demo-request", response_model=DemoRequestResponse)
def demo_request(payload: DemoRequestIn):
    if "@" not in payload.email:
        raise HTTPException(status_code=400, detail="Invalid email")
    return create_demo_request(payload.model_dump())


@router.get("/demo-requests", response_model=list[DemoRequestSummary])
def demo_requests(
    limit: int = 50,
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
    return list_demo_requests(limit=limit)


@router.get("/demo-requests/export")
def demo_requests_export(
    limit: int = 200,
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
    csv_content = export_demo_requests_csv(limit=limit)
    headers = {"Content-Disposition": 'attachment; filename="demo_requests.csv"'}
    return PlainTextResponse(csv_content, headers=headers, media_type="text/csv; charset=utf-8")
