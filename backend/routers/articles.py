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
from backend.services.catalog_service import (
    get_article_cover_path,
    get_article_detail,
    list_articles,
    list_trending_articles,
)
from backend.services.engagement_service import get_article_engagement, record_article_view, set_article_reaction
from backend.services.membership_service import get_membership_profile
from backend.services.supabase_auth_service import get_authenticated_user
from backend.services.translation_service import get_article_translation

router = APIRouter(prefix="/api", tags=["articles"])


@router.get("/articles/latest", response_model=list[ArticleCard])
def get_latest_articles(limit: int = 12, offset: int = 0, language: str = "zh"):
    return list_articles(limit=limit, offset=offset, order_by="publish_date DESC, id DESC", language=language)


@router.get("/articles/trending", response_model=list[ArticleCard])
def get_trending_articles(limit: int = 12, offset: int = 0, window: str = "week", language: str = "zh"):
    return list_trending_articles(limit=limit, offset=offset, window=window, language=language)


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
    return {
        "id": article["id"],
        "title": article["title"],
        "source": article["source"],
        "publish_date": article["publish_date"],
        "link": article["link"],
        "summary": article.get("summary") or "",
        "summary_html": article.get("summary_html"),
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
