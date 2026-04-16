from __future__ import annotations

from fastapi import APIRouter, Header

from backend.models.schemas import (
    UserKnowledgeThemeArticleRequest,
    UserKnowledgeThemeArticleResponse,
    UserKnowledgeThemeChatRequest,
    UserKnowledgeThemeChatResponse,
    UserKnowledgeThemeCreateRequest,
    UserKnowledgeThemeDetail,
    UserKnowledgeThemeListResponse,
    UserKnowledgeThemeSummary,
    UserKnowledgeThemeUpdateRequest,
)
from backend.services.membership_service import require_paid_profile
from backend.services.supabase_auth_service import get_authenticated_user
from backend.services.user_knowledge_service import (
    chat_with_user_knowledge_theme,
    create_user_knowledge_theme,
    delete_user_knowledge_theme,
    get_user_knowledge_theme_detail,
    list_user_knowledge_themes,
    set_article_in_user_knowledge_theme,
    update_user_knowledge_theme,
)

router = APIRouter(prefix="/api/me/knowledge", tags=["user-knowledge"])


def _current_paid_user(
    authorization: str | None = None,
    x_debug_user_id: str | None = None,
    x_debug_user_email: str | None = None,
) -> tuple[dict, dict]:
    user = get_authenticated_user(
        authorization,
        debug_user_id=x_debug_user_id,
        debug_user_email=x_debug_user_email,
    )
    membership = require_paid_profile(user)
    return user, membership


@router.get("/themes", response_model=UserKnowledgeThemeListResponse)
def knowledge_theme_list(
    article_id: int | None = None,
    authorization: str | None = Header(default=None),
    x_debug_user_id: str | None = Header(default=None, alias="X-Debug-User-Id"),
    x_debug_user_email: str | None = Header(default=None, alias="X-Debug-User-Email"),
):
    user, membership = _current_paid_user(authorization, x_debug_user_id, x_debug_user_email)
    return list_user_knowledge_themes(
        user["id"],
        membership_profile=membership,
        article_id=article_id,
    )


@router.post("/themes", response_model=UserKnowledgeThemeSummary)
def knowledge_theme_create(
    payload: UserKnowledgeThemeCreateRequest,
    authorization: str | None = Header(default=None),
    x_debug_user_id: str | None = Header(default=None, alias="X-Debug-User-Id"),
    x_debug_user_email: str | None = Header(default=None, alias="X-Debug-User-Email"),
):
    user, membership = _current_paid_user(authorization, x_debug_user_id, x_debug_user_email)
    return create_user_knowledge_theme(
        user["id"],
        title=payload.title,
        description=payload.description,
        membership_profile=membership,
        initial_article_id=payload.initial_article_id,
    )


@router.get("/themes/{theme_slug}", response_model=UserKnowledgeThemeDetail)
def knowledge_theme_detail(
    theme_slug: str,
    page: int = 1,
    page_size: int = 24,
    authorization: str | None = Header(default=None),
    x_debug_user_id: str | None = Header(default=None, alias="X-Debug-User-Id"),
    x_debug_user_email: str | None = Header(default=None, alias="X-Debug-User-Email"),
):
    user, membership = _current_paid_user(authorization, x_debug_user_id, x_debug_user_email)
    return get_user_knowledge_theme_detail(
        user["id"],
        theme_slug,
        membership_profile=membership,
        page=page,
        page_size=page_size,
    )


@router.put("/themes/{theme_slug}", response_model=UserKnowledgeThemeSummary)
def knowledge_theme_update(
    theme_slug: str,
    payload: UserKnowledgeThemeUpdateRequest,
    authorization: str | None = Header(default=None),
    x_debug_user_id: str | None = Header(default=None, alias="X-Debug-User-Id"),
    x_debug_user_email: str | None = Header(default=None, alias="X-Debug-User-Email"),
):
    user, membership = _current_paid_user(authorization, x_debug_user_id, x_debug_user_email)
    return update_user_knowledge_theme(
        user["id"],
        theme_slug,
        title=payload.title,
        description=payload.description,
        title_provided="title" in payload.model_fields_set,
        description_provided="description" in payload.model_fields_set,
        membership_profile=membership,
    )


@router.delete("/themes/{theme_slug}")
def knowledge_theme_delete(
    theme_slug: str,
    authorization: str | None = Header(default=None),
    x_debug_user_id: str | None = Header(default=None, alias="X-Debug-User-Id"),
    x_debug_user_email: str | None = Header(default=None, alias="X-Debug-User-Email"),
):
    user, _ = _current_paid_user(authorization, x_debug_user_id, x_debug_user_email)
    return delete_user_knowledge_theme(user["id"], theme_slug)


@router.post("/themes/{theme_id}/articles", response_model=UserKnowledgeThemeArticleResponse)
def knowledge_theme_add_article(
    theme_id: int,
    payload: UserKnowledgeThemeArticleRequest,
    authorization: str | None = Header(default=None),
    x_debug_user_id: str | None = Header(default=None, alias="X-Debug-User-Id"),
    x_debug_user_email: str | None = Header(default=None, alias="X-Debug-User-Email"),
):
    user, _ = _current_paid_user(authorization, x_debug_user_id, x_debug_user_email)
    return set_article_in_user_knowledge_theme(
        user["id"],
        theme_id,
        payload.article_id,
        active=True,
    )


@router.delete("/themes/{theme_id}/articles/{article_id}", response_model=UserKnowledgeThemeArticleResponse)
def knowledge_theme_remove_article(
    theme_id: int,
    article_id: int,
    authorization: str | None = Header(default=None),
    x_debug_user_id: str | None = Header(default=None, alias="X-Debug-User-Id"),
    x_debug_user_email: str | None = Header(default=None, alias="X-Debug-User-Email"),
):
    user, _ = _current_paid_user(authorization, x_debug_user_id, x_debug_user_email)
    return set_article_in_user_knowledge_theme(
        user["id"],
        theme_id,
        article_id,
        active=False,
    )


@router.post("/themes/{theme_slug}/chat", response_model=UserKnowledgeThemeChatResponse)
def knowledge_theme_chat(
    theme_slug: str,
    payload: UserKnowledgeThemeChatRequest,
    authorization: str | None = Header(default=None),
    x_debug_user_id: str | None = Header(default=None, alias="X-Debug-User-Id"),
    x_debug_user_email: str | None = Header(default=None, alias="X-Debug-User-Email"),
):
    user, membership = _current_paid_user(authorization, x_debug_user_id, x_debug_user_email)
    return chat_with_user_knowledge_theme(
        user["id"],
        theme_slug,
        messages=[message.model_dump() for message in payload.messages],
        membership_profile=membership,
        language=payload.language,
        selected_article_ids=payload.selected_article_ids,
    )
