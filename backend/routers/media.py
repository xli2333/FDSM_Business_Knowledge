from __future__ import annotations

from fastapi import APIRouter, File, Form, Header, UploadFile

from backend.models.schemas import (
    MediaAdminListResponse,
    MediaHubResponse,
    MediaItemCreate,
    MediaItemDetail,
    MediaPublicDetail,
    MediaItemUpdate,
    MediaUploadResponse,
)
from backend.services.media_service import (
    create_media_item,
    delete_media_item,
    generate_media_copy,
    get_admin_media_item,
    get_media_item_detail,
    list_admin_media_items,
    list_media_items,
    open_published_media_edit_draft,
    publish_media_item,
    rewrite_media_chapters,
    update_media_item,
    upload_media_asset,
)
from backend.services.membership_service import get_membership_profile, require_admin_profile
from backend.services.supabase_auth_service import get_authenticated_user

router = APIRouter(prefix="/api/media", tags=["media"])


def _require_media_admin(
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


@router.get("/admin/items", response_model=MediaAdminListResponse)
def media_admin_list(
    kind: str | None = None,
    status: str | None = None,
    workflow_status: str | None = None,
    draft_box_state: str | None = "active",
    limit: int = 60,
    authorization: str | None = Header(default=None),
    x_debug_user_id: str | None = Header(default=None, alias="X-Debug-User-Id"),
    x_debug_user_email: str | None = Header(default=None, alias="X-Debug-User-Email"),
):
    _require_media_admin(authorization, x_debug_user_id, x_debug_user_email)
    return list_admin_media_items(
        kind=kind,
        status=status,
        workflow_status=workflow_status,
        draft_box_state=draft_box_state,
        limit=limit,
    )


@router.post("/admin/published-items/{media_item_id}/edit-draft", response_model=MediaItemDetail)
def media_admin_edit_published_item(
    media_item_id: int,
    authorization: str | None = Header(default=None),
    x_debug_user_id: str | None = Header(default=None, alias="X-Debug-User-Id"),
    x_debug_user_email: str | None = Header(default=None, alias="X-Debug-User-Email"),
):
    _require_media_admin(authorization, x_debug_user_id, x_debug_user_email)
    return open_published_media_edit_draft(media_item_id)


@router.get("/admin/items/{media_id}", response_model=MediaItemDetail)
def media_admin_detail(
    media_id: int,
    authorization: str | None = Header(default=None),
    x_debug_user_id: str | None = Header(default=None, alias="X-Debug-User-Id"),
    x_debug_user_email: str | None = Header(default=None, alias="X-Debug-User-Email"),
):
    _require_media_admin(authorization, x_debug_user_id, x_debug_user_email)
    return get_admin_media_item(media_id)


@router.post("/admin/items", response_model=MediaItemDetail)
def media_admin_create(
    payload: MediaItemCreate,
    authorization: str | None = Header(default=None),
    x_debug_user_id: str | None = Header(default=None, alias="X-Debug-User-Id"),
    x_debug_user_email: str | None = Header(default=None, alias="X-Debug-User-Email"),
):
    _require_media_admin(authorization, x_debug_user_id, x_debug_user_email)
    return create_media_item(payload.model_dump())


@router.put("/admin/items/{media_id}", response_model=MediaItemDetail)
def media_admin_update(
    media_id: int,
    payload: MediaItemUpdate,
    authorization: str | None = Header(default=None),
    x_debug_user_id: str | None = Header(default=None, alias="X-Debug-User-Id"),
    x_debug_user_email: str | None = Header(default=None, alias="X-Debug-User-Email"),
):
    _require_media_admin(authorization, x_debug_user_id, x_debug_user_email)
    return update_media_item(media_id, payload.model_dump(exclude_unset=True))


@router.delete("/admin/items/{media_id}")
def media_admin_delete(
    media_id: int,
    authorization: str | None = Header(default=None),
    x_debug_user_id: str | None = Header(default=None, alias="X-Debug-User-Id"),
    x_debug_user_email: str | None = Header(default=None, alias="X-Debug-User-Email"),
):
    _require_media_admin(authorization, x_debug_user_id, x_debug_user_email)
    return delete_media_item(media_id)


@router.post("/admin/items/{media_id}/generate-copy", response_model=MediaItemDetail)
def media_admin_generate_copy(
    media_id: int,
    authorization: str | None = Header(default=None),
    x_debug_user_id: str | None = Header(default=None, alias="X-Debug-User-Id"),
    x_debug_user_email: str | None = Header(default=None, alias="X-Debug-User-Email"),
):
    _require_media_admin(authorization, x_debug_user_id, x_debug_user_email)
    return generate_media_copy(media_id)


@router.post("/admin/items/{media_id}/rewrite-chapters", response_model=MediaItemDetail)
def media_admin_rewrite_chapters(
    media_id: int,
    authorization: str | None = Header(default=None),
    x_debug_user_id: str | None = Header(default=None, alias="X-Debug-User-Id"),
    x_debug_user_email: str | None = Header(default=None, alias="X-Debug-User-Email"),
):
    _require_media_admin(authorization, x_debug_user_id, x_debug_user_email)
    return rewrite_media_chapters(media_id)


@router.post("/admin/items/{media_id}/publish", response_model=MediaItemDetail)
def media_admin_publish(
    media_id: int,
    authorization: str | None = Header(default=None),
    x_debug_user_id: str | None = Header(default=None, alias="X-Debug-User-Id"),
    x_debug_user_email: str | None = Header(default=None, alias="X-Debug-User-Email"),
):
    _require_media_admin(authorization, x_debug_user_id, x_debug_user_email)
    return publish_media_item(media_id)


@router.post("/admin/upload", response_model=MediaUploadResponse)
async def media_admin_upload(
    kind: str = Form(...),
    usage: str = Form("media"),
    draft_id: int | None = Form(default=None),
    duration_seconds: int | None = Form(default=None),
    file: UploadFile = File(...),
    authorization: str | None = Header(default=None),
    x_debug_user_id: str | None = Header(default=None, alias="X-Debug-User-Id"),
    x_debug_user_email: str | None = Header(default=None, alias="X-Debug-User-Email"),
):
    _require_media_admin(authorization, x_debug_user_id, x_debug_user_email)
    return await upload_media_asset(
        kind=kind,
        usage=usage,
        upload_file=file,
        filename=file.filename or f"{kind}.bin",
        content_type=file.content_type,
        draft_id=draft_id,
        duration_seconds=duration_seconds,
    )


@router.get("/{kind}/{slug}", response_model=MediaPublicDetail)
def media_public_detail(
    kind: str,
    slug: str,
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
    return get_media_item_detail(kind, slug, membership)


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
