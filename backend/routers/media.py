from __future__ import annotations

from fastapi import APIRouter, File, Form, Header, UploadFile

from backend.models.schemas import MediaAdminListResponse, MediaHubResponse, MediaItemCreate, MediaItemDetail, MediaItemUpdate, MediaUploadResponse
from backend.services.media_service import create_media_item, get_admin_media_item, list_admin_media_items, list_media_items, update_media_item, upload_media_asset
from backend.services.membership_service import get_membership_profile, require_admin_profile
from backend.services.supabase_auth_service import get_authenticated_user

router = APIRouter(prefix="/api/media", tags=["media"])


@router.get("/admin/items", response_model=MediaAdminListResponse)
def media_admin_list(
    kind: str | None = None,
    status: str | None = None,
    limit: int = 60,
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
    return list_admin_media_items(kind=kind, status=status, limit=limit)


@router.get("/admin/items/{media_id}", response_model=MediaItemDetail)
def media_admin_detail(
    media_id: int,
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
    return get_admin_media_item(media_id)


@router.post("/admin/items", response_model=MediaItemDetail)
def media_admin_create(
    payload: MediaItemCreate,
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
    return create_media_item(payload.model_dump())


@router.put("/admin/items/{media_id}", response_model=MediaItemDetail)
def media_admin_update(
    media_id: int,
    payload: MediaItemUpdate,
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
    return update_media_item(media_id, payload.model_dump(exclude_unset=True))


@router.post("/admin/upload", response_model=MediaUploadResponse)
async def media_admin_upload(
    kind: str = Form(...),
    usage: str = Form("media"),
    file: UploadFile = File(...),
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
    raw_bytes = await file.read()
    return upload_media_asset(
        kind=kind,
        usage=usage,
        filename=file.filename or f"{kind}.bin",
        raw_bytes=raw_bytes,
        content_type=file.content_type,
    )


@router.get("/{kind}", response_model=MediaHubResponse)
def media_hub(
    kind: str,
    limit: int = 24,
    authorization: str | None = Header(default=None),
    x_debug_user_id: str | None = Header(default=None, alias="X-Debug-User-Id"),
    x_debug_user_email: str | None = Header(default=None, alias="X-Debug-User-Email"),
):
    user = get_authenticated_user(
        authorization,
        debug_user_id=x_debug_user_id,
        debug_user_email=x_debug_user_email,
    )
    membership = get_membership_profile(user)
    return list_media_items(kind, membership, limit=limit)
