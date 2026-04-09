from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import FileResponse

from backend.models.schemas import (
    ArticleCard,
    ArticleDetail,
    ArticleEngagement,
    ArticleTranslationResponse,
    ReactionRequest,
)
from backend.services import ai_service
from backend.services.article_ai_output_service import get_article_ai_output_detail
from backend.services.display_markdown_service import normalize_summary_display_markdown
from backend.services.catalog_service import (
    get_article_cover_path,
    get_article_detail,
    list_articles,
)
from backend.services.engagement_service import get_article_engagement, record_article_view, set_article_reaction
from backend.services.membership_service import get_membership_profile
from backend.services.summary_preview_service import is_summary_preview_html, render_summary_preview_html
from backend.services.supabase_auth_service import get_authenticated_user
from backend.services.translation_service import get_article_translation

router = APIRouter(prefix="/api", tags=["articles"])


@router.get("/articles/latest", response_model=list[ArticleCard])
def get_latest_articles(limit: int = 12, offset: int = 0, language: str = "zh"):
    return list_articles(limit=limit, offset=offset, order_by="publish_date DESC, id DESC", language=language)


@router.get("/articles/trending", response_model=list[ArticleCard])
def get_trending_articles(limit: int = 12, offset: int = 0):
    return list_articles(
        limit=limit,
        offset=offset,
        order_by="""
        (
            COALESCE(view_count, 0)
            + 4 * (
                SELECT COUNT(*)
                FROM article_reactions ar
                WHERE ar.article_id = articles.id
                  AND ar.reaction_type = 'like'
                  AND ar.is_active = 1
            )
            + 6 * (
                SELECT COUNT(*)
                FROM article_reactions ar
                WHERE ar.article_id = articles.id
                  AND ar.reaction_type = 'bookmark'
                  AND ar.is_active = 1
            )
        ) DESC,
        publish_date DESC
        """,
    )


@router.get("/article/{article_id}", response_model=ArticleDetail)
def read_article(
    article_id: int,
    x_visitor_id: str | None = Header(default=None, alias="X-Visitor-Id"),
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
    record_article_view(
        article_id,
        x_visitor_id,
        user_id=user["id"] if user else None,
        source="article-detail",
    )
    return get_article_detail(
        article_id,
        current_user_id=user["id"] if user else None,
        membership_profile=membership,
    )


@router.get("/article/{article_id}/cover")
def read_article_cover(article_id: int):
    return FileResponse(get_article_cover_path(article_id))


@router.get("/article/{article_id}/translation", response_model=ArticleTranslationResponse)
def read_article_translation(
    article_id: int,
    lang: str = "en",
    authorization: str | None = Header(default=None),
    x_debug_user_id: str | None = Header(default=None, alias="X-Debug-User-Id"),
    x_debug_user_email: str | None = Header(default=None, alias="X-Debug-User-Email"),
):
    user = get_authenticated_user(
        authorization,
        debug_user_id=x_debug_user_id,
        debug_user_email=x_debug_user_email,
    )
    try:
        return get_article_translation(
            article_id,
            target_lang=lang,
            current_user_id=user["id"] if user else None,
            membership_profile=get_membership_profile(user),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/summarize_article/{article_id}")
def summarize_article(
    article_id: int,
    authorization: str | None = Header(default=None),
    x_debug_user_id: str | None = Header(default=None, alias="X-Debug-User-Id"),
    x_debug_user_email: str | None = Header(default=None, alias="X-Debug-User-Email"),
):
    user = get_authenticated_user(
        authorization,
        debug_user_id=x_debug_user_id,
        debug_user_email=x_debug_user_email,
    )
    article = get_article_detail(
        article_id,
        current_user_id=user["id"] if user else None,
        membership_profile=get_membership_profile(user),
    )
    ai_output = get_article_ai_output_detail(article_id)
    summary = (
        ai_output.get("summary_zh")
        if ai_output.get("summary_ready") and ai_output.get("source_hash_matches_current")
        else ai_service.build_extractive_summary(article["content"])
    )
    summary = normalize_summary_display_markdown(summary, "zh")
    stored_summary_html = ai_output.get("summary_html_zh") if ai_output.get("source_hash_matches_current") else None
    summary_html = stored_summary_html if is_summary_preview_html(stored_summary_html) else render_summary_preview_html(summary, language="zh")
    return {
        "id": article["id"],
        "title": article["title"],
        "source": article["source"],
        "publish_date": article["publish_date"],
        "link": article["link"],
        "summary": summary,
        "summary_html": summary_html,
    }


@router.get("/article/{article_id}/engagement", response_model=ArticleEngagement)
def read_article_engagement(
    article_id: int,
    authorization: str | None = Header(default=None),
    x_debug_user_id: str | None = Header(default=None, alias="X-Debug-User-Id"),
    x_debug_user_email: str | None = Header(default=None, alias="X-Debug-User-Email"),
):
    user = get_authenticated_user(
        authorization,
        debug_user_id=x_debug_user_id,
        debug_user_email=x_debug_user_email,
    )
    return get_article_engagement(article_id, user_id=user["id"] if user else None)


@router.post("/article/{article_id}/reaction", response_model=ArticleEngagement)
def update_article_reaction(
    article_id: int,
    payload: ReactionRequest,
    authorization: str | None = Header(default=None),
    x_debug_user_id: str | None = Header(default=None, alias="X-Debug-User-Id"),
    x_debug_user_email: str | None = Header(default=None, alias="X-Debug-User-Email"),
):
    user = get_authenticated_user(
        authorization,
        debug_user_id=x_debug_user_id,
        debug_user_email=x_debug_user_email,
    )
    if not user:
        raise HTTPException(status_code=401, detail="Login required")
    return set_article_reaction(
        article_id,
        user_id=user["id"],
        reaction_type=payload.reaction_type,
        active=payload.active,
    )
