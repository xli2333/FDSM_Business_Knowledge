from __future__ import annotations

from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile

from backend.models.schemas import (
    AdminContentEntity,
    EditorialArticleCreate,
    EditorialArticleDetail,
    EditorialArticleSummary,
    EditorialAiImportRequest,
    EditorialAutoFormatRequest,
    EditorialAiOutputDetail,
    EditorialDashboardResponse,
    EditorialDeleteResponse,
    EditorialArticleUpdate,
    EditorialHtmlResponse,
    EditorialPublishResponse,
    EditorialSourceArticleSummary,
    EditorialUploadResponse,
    EditorialWorkflowRequest,
)
from backend.services.membership_service import require_admin_profile
from backend.services.supabase_auth_service import get_authenticated_user
from backend.services.editorial_service import (
    create_editorial_article,
    create_editorial_from_upload,
    auto_format_editorial_article,
    generate_editorial_summary,
    generate_editorial_translation,
    generate_editorial_tags,
    get_editorial_dashboard,
    get_editorial_article,
    get_editorial_source_ai_output,
    list_editorial_topic_candidates,
    import_editorial_ai_draft,
    list_editorial_articles,
    list_editorial_source_articles,
    delete_editorial_article,
    publish_editorial_article,
    reopen_published_article_to_editorial_draft_box,
    render_editorial_html,
    upload_editorial_cover_image,
    update_editorial_workflow,
    update_editorial_article,
)

router = APIRouter(prefix="/api/editorial", tags=["editorial"])


def _require_editorial_admin(
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


@router.get("/dashboard", response_model=EditorialDashboardResponse)
def editorial_dashboard(
    limit: int = 6,
    authorization: str | None = Header(default=None),
    x_debug_user_id: str | None = Header(default=None, alias="X-Debug-User-Id"),
    x_debug_user_email: str | None = Header(default=None, alias="X-Debug-User-Email"),
):
    _require_editorial_admin(authorization, x_debug_user_id, x_debug_user_email)
    return get_editorial_dashboard(limit=limit)


@router.get("/articles", response_model=list[EditorialArticleSummary])
def editorial_articles(
    limit: int = 40,
    status: str | None = None,
    workflow_status: str | None = None,
    draft_box_state: str | None = "active",
    authorization: str | None = Header(default=None),
    x_debug_user_id: str | None = Header(default=None, alias="X-Debug-User-Id"),
    x_debug_user_email: str | None = Header(default=None, alias="X-Debug-User-Email"),
):
    _require_editorial_admin(authorization, x_debug_user_id, x_debug_user_email)
    return list_editorial_articles(
        limit=limit,
        status=status,
        workflow_status=workflow_status,
        draft_box_state=draft_box_state,
    )


@router.get("/source-articles", response_model=list[EditorialSourceArticleSummary])
def editorial_source_articles(
    query: str = "",
    limit: int = 12,
    authorization: str | None = Header(default=None),
    x_debug_user_id: str | None = Header(default=None, alias="X-Debug-User-Id"),
    x_debug_user_email: str | None = Header(default=None, alias="X-Debug-User-Email"),
):
    _require_editorial_admin(authorization, x_debug_user_id, x_debug_user_email)
    return list_editorial_source_articles(query=query, limit=limit)


@router.get("/source-articles/{article_id}/ai-output", response_model=EditorialAiOutputDetail)
def editorial_source_ai_output(
    article_id: int,
    authorization: str | None = Header(default=None),
    x_debug_user_id: str | None = Header(default=None, alias="X-Debug-User-Id"),
    x_debug_user_email: str | None = Header(default=None, alias="X-Debug-User-Email"),
):
    _require_editorial_admin(authorization, x_debug_user_id, x_debug_user_email)
    return get_editorial_source_ai_output(article_id)


@router.get("/topics", response_model=list[AdminContentEntity])
def editorial_topics(
    query: str = "",
    limit: int = 12,
    authorization: str | None = Header(default=None),
    x_debug_user_id: str | None = Header(default=None, alias="X-Debug-User-Id"),
    x_debug_user_email: str | None = Header(default=None, alias="X-Debug-User-Email"),
):
    _require_editorial_admin(authorization, x_debug_user_id, x_debug_user_email)
    return list_editorial_topic_candidates(query=query, limit=limit)


@router.post("/source-articles/{article_id}/import-ai", response_model=EditorialArticleDetail)
def editorial_source_import_ai(
    article_id: int,
    payload: EditorialAiImportRequest,
    authorization: str | None = Header(default=None),
    x_debug_user_id: str | None = Header(default=None, alias="X-Debug-User-Id"),
    x_debug_user_email: str | None = Header(default=None, alias="X-Debug-User-Email"),
):
    _require_editorial_admin(authorization, x_debug_user_id, x_debug_user_email)
    return import_editorial_ai_draft(article_id, payload.model_dump())


@router.post("/source-articles/{article_id}/reopen-draft", response_model=EditorialArticleDetail)
def editorial_source_reopen_draft(
    article_id: int,
    authorization: str | None = Header(default=None),
    x_debug_user_id: str | None = Header(default=None, alias="X-Debug-User-Id"),
    x_debug_user_email: str | None = Header(default=None, alias="X-Debug-User-Email"),
):
    _require_editorial_admin(authorization, x_debug_user_id, x_debug_user_email)
    return reopen_published_article_to_editorial_draft_box(article_id)


@router.post("/articles", response_model=EditorialArticleDetail)
def editorial_article_create(
    payload: EditorialArticleCreate,
    authorization: str | None = Header(default=None),
    x_debug_user_id: str | None = Header(default=None, alias="X-Debug-User-Id"),
    x_debug_user_email: str | None = Header(default=None, alias="X-Debug-User-Email"),
):
    _require_editorial_admin(authorization, x_debug_user_id, x_debug_user_email)
    return create_editorial_article(payload.model_dump())


@router.post("/upload", response_model=EditorialUploadResponse)
async def editorial_upload(
    usage: str = Form("source"),
    editorial_id: int | None = Form(default=None),
    file: UploadFile = File(...),
    authorization: str | None = Header(default=None),
    x_debug_user_id: str | None = Header(default=None, alias="X-Debug-User-Id"),
    x_debug_user_email: str | None = Header(default=None, alias="X-Debug-User-Email"),
):
    _require_editorial_admin(authorization, x_debug_user_id, x_debug_user_email)
    if usage == "cover":
        if editorial_id is None:
            raise HTTPException(status_code=400, detail="Editorial draft id is required for cover uploads")
        return await upload_editorial_cover_image(
            editorial_id=editorial_id,
            upload_file=file,
            filename=file.filename or "cover-image.bin",
            content_type=file.content_type,
        )
    if usage != "source":
        raise HTTPException(status_code=400, detail="Unsupported editorial upload usage")
    content = await file.read()
    article = create_editorial_from_upload(file.filename or "uploaded.md", content)
    return {
        "filename": file.filename or "uploaded.md",
        "usage": "source",
        "url": None,
        "article": article,
    }


@router.get("/articles/{editorial_id}", response_model=EditorialArticleDetail)
def editorial_article_detail(
    editorial_id: int,
    authorization: str | None = Header(default=None),
    x_debug_user_id: str | None = Header(default=None, alias="X-Debug-User-Id"),
    x_debug_user_email: str | None = Header(default=None, alias="X-Debug-User-Email"),
):
    _require_editorial_admin(authorization, x_debug_user_id, x_debug_user_email)
    return get_editorial_article(editorial_id)


@router.put("/articles/{editorial_id}", response_model=EditorialArticleDetail)
def editorial_article_update(
    editorial_id: int,
    payload: EditorialArticleUpdate,
    authorization: str | None = Header(default=None),
    x_debug_user_id: str | None = Header(default=None, alias="X-Debug-User-Id"),
    x_debug_user_email: str | None = Header(default=None, alias="X-Debug-User-Email"),
):
    _require_editorial_admin(authorization, x_debug_user_id, x_debug_user_email)
    return update_editorial_article(editorial_id, payload.model_dump(exclude_unset=True))


@router.delete("/articles/{editorial_id}", response_model=EditorialDeleteResponse)
def editorial_article_delete(
    editorial_id: int,
    authorization: str | None = Header(default=None),
    x_debug_user_id: str | None = Header(default=None, alias="X-Debug-User-Id"),
    x_debug_user_email: str | None = Header(default=None, alias="X-Debug-User-Email"),
):
    _require_editorial_admin(authorization, x_debug_user_id, x_debug_user_email)
    return delete_editorial_article(editorial_id)


@router.post("/articles/{editorial_id}/auto-format", response_model=EditorialArticleDetail)
def editorial_article_auto_format(
    editorial_id: int,
    payload: EditorialAutoFormatRequest,
    authorization: str | None = Header(default=None),
    x_debug_user_id: str | None = Header(default=None, alias="X-Debug-User-Id"),
    x_debug_user_email: str | None = Header(default=None, alias="X-Debug-User-Email"),
):
    _require_editorial_admin(authorization, x_debug_user_id, x_debug_user_email)
    return auto_format_editorial_article(editorial_id, payload.model_dump(exclude_unset=True))


@router.post("/articles/{editorial_id}/autotag", response_model=EditorialArticleDetail)
def editorial_article_autotag(
    editorial_id: int,
    authorization: str | None = Header(default=None),
    x_debug_user_id: str | None = Header(default=None, alias="X-Debug-User-Id"),
    x_debug_user_email: str | None = Header(default=None, alias="X-Debug-User-Email"),
):
    _require_editorial_admin(authorization, x_debug_user_id, x_debug_user_email)
    return generate_editorial_tags(editorial_id)


@router.post("/articles/{editorial_id}/auto-summary", response_model=EditorialArticleDetail)
def editorial_article_auto_summary(
    editorial_id: int,
    authorization: str | None = Header(default=None),
    x_debug_user_id: str | None = Header(default=None, alias="X-Debug-User-Id"),
    x_debug_user_email: str | None = Header(default=None, alias="X-Debug-User-Email"),
):
    _require_editorial_admin(authorization, x_debug_user_id, x_debug_user_email)
    return generate_editorial_summary(editorial_id)


@router.post("/articles/{editorial_id}/auto-translate", response_model=EditorialArticleDetail)
def editorial_article_auto_translate(
    editorial_id: int,
    authorization: str | None = Header(default=None),
    x_debug_user_id: str | None = Header(default=None, alias="X-Debug-User-Id"),
    x_debug_user_email: str | None = Header(default=None, alias="X-Debug-User-Email"),
):
    _require_editorial_admin(authorization, x_debug_user_id, x_debug_user_email)
    return generate_editorial_translation(editorial_id)


@router.post("/articles/{editorial_id}/workflow", response_model=EditorialArticleDetail)
def editorial_article_workflow(
    editorial_id: int,
    payload: EditorialWorkflowRequest,
    authorization: str | None = Header(default=None),
    x_debug_user_id: str | None = Header(default=None, alias="X-Debug-User-Id"),
    x_debug_user_email: str | None = Header(default=None, alias="X-Debug-User-Email"),
):
    _require_editorial_admin(authorization, x_debug_user_id, x_debug_user_email)
    return update_editorial_workflow(editorial_id, payload.model_dump())


@router.post("/articles/{editorial_id}/render-html", response_model=EditorialHtmlResponse)
def editorial_article_render(
    editorial_id: int,
    authorization: str | None = Header(default=None),
    x_debug_user_id: str | None = Header(default=None, alias="X-Debug-User-Id"),
    x_debug_user_email: str | None = Header(default=None, alias="X-Debug-User-Email"),
):
    _require_editorial_admin(authorization, x_debug_user_id, x_debug_user_email)
    return render_editorial_html(editorial_id)


@router.get("/articles/{editorial_id}/export")
def editorial_article_export(
    editorial_id: int,
    variant: str = "web",
    authorization: str | None = Header(default=None),
    x_debug_user_id: str | None = Header(default=None, alias="X-Debug-User-Id"),
    x_debug_user_email: str | None = Header(default=None, alias="X-Debug-User-Email"),
):
    _require_editorial_admin(authorization, x_debug_user_id, x_debug_user_email)
    del editorial_id, variant
    raise HTTPException(status_code=410, detail="Editorial HTML export has been removed from the workbench")


@router.post("/articles/{editorial_id}/publish", response_model=EditorialPublishResponse)
def editorial_article_publish(
    editorial_id: int,
    authorization: str | None = Header(default=None),
    x_debug_user_id: str | None = Header(default=None, alias="X-Debug-User-Id"),
    x_debug_user_email: str | None = Header(default=None, alias="X-Debug-User-Email"),
):
    _require_editorial_admin(authorization, x_debug_user_id, x_debug_user_email)
    return publish_editorial_article(editorial_id)
