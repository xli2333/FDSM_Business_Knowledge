from __future__ import annotations

from fastapi import APIRouter, Header

from backend.models.schemas import TopicDetail, TopicSummary
from backend.services.catalog_service import (
    get_topic_detail,
    get_topic_insights,
    get_topic_timeline,
    increment_topic_view_count_by_slug,
    list_topics,
)
from backend.services.membership_service import require_paid_profile
from backend.services.supabase_auth_service import get_authenticated_user
from backend.services.topic_engine import auto_generate_topics

router = APIRouter(prefix="/api", tags=["topics"])


def _require_topic_access(
    authorization: str | None = None,
    x_debug_user_id: str | None = None,
    x_debug_user_email: str | None = None,
):
    user = get_authenticated_user(
        authorization,
        debug_user_id=x_debug_user_id,
        debug_user_email=x_debug_user_email,
    )
    return require_paid_profile(user)


@router.get("/topics", response_model=list[TopicSummary])
def topics(
    authorization: str | None = Header(default=None),
    x_debug_user_id: str | None = Header(default=None, alias="X-Debug-User-Id"),
    x_debug_user_email: str | None = Header(default=None, alias="X-Debug-User-Email"),
):
    _require_topic_access(authorization, x_debug_user_id, x_debug_user_email)
    return list_topics()


@router.get("/topics/{slug}", response_model=TopicDetail)
def topic_detail(
    slug: str,
    page: int = 1,
    page_size: int = 12,
    authorization: str | None = Header(default=None),
    x_debug_user_id: str | None = Header(default=None, alias="X-Debug-User-Id"),
    x_debug_user_email: str | None = Header(default=None, alias="X-Debug-User-Email"),
):
    _require_topic_access(authorization, x_debug_user_id, x_debug_user_email)
    if page == 1:
        increment_topic_view_count_by_slug(slug)
    return get_topic_detail(slug, page=page, page_size=page_size)


@router.get("/topics/{topic_id}/timeline")
def topic_timeline(
    topic_id: int,
    authorization: str | None = Header(default=None),
    x_debug_user_id: str | None = Header(default=None, alias="X-Debug-User-Id"),
    x_debug_user_email: str | None = Header(default=None, alias="X-Debug-User-Email"),
):
    _require_topic_access(authorization, x_debug_user_id, x_debug_user_email)
    return get_topic_timeline(topic_id)


@router.get("/topics/{topic_id}/insights")
def topic_insights(
    topic_id: int,
    authorization: str | None = Header(default=None),
    x_debug_user_id: str | None = Header(default=None, alias="X-Debug-User-Id"),
    x_debug_user_email: str | None = Header(default=None, alias="X-Debug-User-Email"),
):
    _require_topic_access(authorization, x_debug_user_id, x_debug_user_email)
    return get_topic_insights(topic_id)


@router.post("/topics/auto-generate")
def generate_topics(limit: int = 6):
    return auto_generate_topics(limit=limit)
