from __future__ import annotations

import os
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("DEV_AUTH_ENABLED", "1")
os.environ.setdefault("ADMIN_EMAILS", "admin@example.com")
os.environ.setdefault("PAYMENTS_ENABLED", "0")
os.environ.setdefault("PAYMENT_PROVIDER", "mock")

from backend.database import SQLITE_DB_PATH
from backend.main import app
from backend.services.ai_service import is_ai_enabled


def main() -> None:
    client = TestClient(app)
    ai_enabled = is_ai_enabled()
    run_suffix = datetime.now().strftime("%H%M%S")
    member_user_id = f"member-smoke-{run_suffix}"
    member_email = f"member.{run_suffix}@example.com"
    member_headers = {
        "X-Debug-User-Id": member_user_id,
        "X-Debug-User-Email": member_email,
    }
    free_seed_headers = {
        "X-Debug-User-Id": "mock-free-member",
        "X-Debug-User-Email": "reader@example.com",
    }
    paid_seed_headers = {
        "X-Debug-User-Id": "mock-paid-member",
        "X-Debug-User-Email": "paid@example.com",
    }
    admin_headers = {
        "X-Debug-User-Id": "mock-admin",
        "X-Debug-User-Email": "admin@example.com",
    }

    health = client.get("/").json()
    home = client.get("/api/home/feed").json()
    tags_payload = client.get("/api/tags").json()
    columns_payload = client.get("/api/columns").json()
    organizations_payload = client.get("/api/organizations?limit=20").json()
    topics_payload = client.get("/api/topics", headers=paid_seed_headers).json()
    search = client.post(
        "/api/search",
        json={
            "query": "AI",
            "mode": "smart",
            "sort": "relevance",
            "page": 1,
            "page_size": 5,
        },
    ).json()
    analytics = client.get("/api/analytics/overview", headers=admin_headers).json()
    chat = client.post(
        "/api/chat",
        json={
            "messages": [{"role": "user", "content": "/summarize AI"}],
            "mode": "precise",
        },
    ).json()
    overview = client.get("/api/commerce/overview").json()
    demo_request = client.post(
        "/api/commerce/demo-request",
        json={
            "name": "Smoke Tester",
            "organization": "FDSM QA",
            "role": "QA Engineer",
            "email": "qa@example.com",
            "phone": "123456789",
            "use_case": "商业化与支付骨架验收",
            "message": "验证线索、会员、支付、内容后台工作流和发布流程",
        },
    ).json()
    demo_requests_unauthorized = client.get("/api/commerce/demo-requests?limit=10")
    demo_requests = client.get("/api/commerce/demo-requests?limit=10", headers=admin_headers).json()
    demo_export = client.get("/api/commerce/demo-requests/export?limit=10", headers=admin_headers)

    billing_plans = client.get("/api/billing/plans").json()
    billing_guest = client.get("/api/billing/me").json()
    billing_checkout_unauthorized = client.post(
        "/api/billing/checkout-intent",
        json={"plan_code": "paid_member_monthly"},
    )
    billing_checkout_member = client.post(
        "/api/billing/checkout-intent",
        headers=member_headers,
        json={
            "plan_code": "paid_member_monthly",
            "success_url": "http://127.0.0.1:4173/membership",
            "cancel_url": "http://127.0.0.1:4173/membership",
        },
    ).json()
    billing_member = client.get("/api/billing/me", headers=member_headers).json()
    admin_orders_unauthorized = client.get("/api/admin/billing/orders")
    admin_orders = client.get("/api/admin/billing/orders?limit=20", headers=admin_headers).json()

    follow_tag_slug = (tags_payload.get("hot") or [{}])[0].get("slug")
    follow_column_slug = (columns_payload or [{}])[0].get("slug")
    organization_slug = (organizations_payload or [{}])[0].get("slug")
    follow_topic_slug = (topics_payload or [{}])[0].get("slug")
    follows_unauthorized = client.get("/api/follows")
    follow_tag = client.post(
        "/api/follows",
        headers=member_headers,
        json={"entity_type": "tag", "entity_slug": follow_tag_slug, "active": True},
    ).json()
    follow_column = client.post(
        "/api/follows",
        headers=member_headers,
        json={"entity_type": "column", "entity_slug": follow_column_slug, "active": True},
    ).json()
    follow_topic = client.post(
        "/api/follows",
        headers=member_headers,
        json={"entity_type": "topic", "entity_slug": follow_topic_slug, "active": True},
    ).json()
    follow_list = client.get("/api/follows", headers=member_headers).json()
    follow_watchlist = client.get("/api/follows/watchlist?limit=12", headers=member_headers).json()
    unfollow_topic = client.post(
        "/api/follows",
        headers=member_headers,
        json={"entity_type": "topic", "entity_slug": follow_topic_slug, "active": False},
    ).json()
    organization_detail = client.get(f"/api/organizations/{organization_slug}?page=1&page_size=6").json()

    media_admin_unauthorized = client.get("/api/media/admin/items?limit=2")
    media_admin_create = client.post(
        "/api/media/admin/items",
        headers=admin_headers,
        json={
            "kind": "audio",
            "title": "Round18 Smoke Audio Episode",
            "summary": "Media studio smoke item used to verify program management and chapter metadata.",
            "speaker": "Smoke Studio",
            "series_name": "Smoke Audio Series",
            "episode_number": 3,
            "publish_date": "2026-03-24",
            "duration_seconds": 980,
            "visibility": "member",
            "status": "published",
            "media_url": "https://example.com/audio/full",
            "preview_url": "https://example.com/audio/preview",
            "source_url": "https://example.com/audio/source",
            "transcript_markdown": "## Transcript\n\nThis is a smoke transcript.",
            "body_markdown": "Media studio smoke description.",
            "chapters": [
                {"title": "Opening", "timestamp_label": "00:00", "timestamp_seconds": 0},
                {"title": "Key Insight", "timestamp_label": "03:20", "timestamp_seconds": 200},
            ],
        },
    ).json()
    media_admin_id = media_admin_create["id"]
    media_admin_update = client.put(
        f"/api/media/admin/items/{media_admin_id}",
        headers=admin_headers,
        json={
            "summary": "Updated smoke media summary",
            "episode_number": 4,
            "transcript_markdown": "## Transcript\n\nUpdated smoke transcript.",
        },
    ).json()
    media_admin_list = client.get("/api/media/admin/items?limit=20&kind=audio", headers=admin_headers).json()
    media_admin_detail = client.get(f"/api/media/admin/items/{media_admin_id}", headers=admin_headers).json()

    scheduled_publish_at = (datetime.now() + timedelta(hours=2)).replace(microsecond=0).isoformat()
    editorial_unauthorized = client.get("/api/editorial/dashboard")
    editorial_create = client.post(
        "/api/editorial/articles",
        headers=admin_headers,
        json={
            "title": "Round17 Smoke Editorial",
            "author": "Smoke Bot",
            "organization": "FDSM QA",
            "publish_date": "2026-03-24",
            "primary_column_slug": "insights",
            "access_level": "paid",
            "content_markdown": "# Round17 Smoke Editorial\n\nThis draft verifies workflow transitions, HTML rendering, paywall publication, and billing readiness.",
        },
    ).json()
    editorial_id = editorial_create["id"]
    editorial_submit_review = client.post(
        f"/api/editorial/articles/{editorial_id}/workflow",
        headers=admin_headers,
        json={"action": "submit_review", "review_note": "Need editor review"},
    ).json()
    editorial_approve = client.post(
        f"/api/editorial/articles/{editorial_id}/workflow",
        headers=admin_headers,
        json={"action": "approve", "review_note": "Approved by editor"},
    ).json()
    editorial_schedule = client.post(
        f"/api/editorial/articles/{editorial_id}/workflow",
        headers=admin_headers,
        json={
            "action": "schedule",
            "review_note": "Schedule for evening release",
            "scheduled_publish_at": scheduled_publish_at,
        },
    ).json()
    editorial_autotag = client.post(f"/api/editorial/articles/{editorial_id}/autotag", headers=admin_headers).json()
    editorial_render = client.post(f"/api/editorial/articles/{editorial_id}/render-html", headers=admin_headers).json()
    editorial_export = client.get(f"/api/editorial/articles/{editorial_id}/export?variant=web", headers=admin_headers)
    editorial_publish = client.post(f"/api/editorial/articles/{editorial_id}/publish", headers=admin_headers).json()
    public_article_id = editorial_publish["article_id"]
    editorial_detail_after_publish = client.get(f"/api/editorial/articles/{editorial_id}", headers=admin_headers).json()
    editorial_dashboard = client.get("/api/editorial/dashboard?limit=6", headers=admin_headers).json()

    auth_status = client.get("/api/auth/status").json()
    membership_guest = client.get("/api/membership/me").json()
    membership_member_before = client.get("/api/membership/me", headers=member_headers).json()
    guest_dashboard = client.get("/api/me/dashboard").json()
    free_seed_dashboard = client.get("/api/me/dashboard", headers=free_seed_headers).json()
    paid_seed_dashboard = client.get("/api/me/dashboard", headers=paid_seed_headers).json()
    admin_overview = client.get("/api/admin/overview", headers=admin_headers).json()

    guest_paid_article = client.get(
        f"/api/article/{public_article_id}",
        headers={"X-Visitor-Id": "visitor-smoke-a"},
    ).json()
    repeated_public_editorial = client.get(
        f"/api/article/{public_article_id}",
        headers={"X-Visitor-Id": "visitor-smoke-a"},
    ).json()
    second_visitor_public_editorial = client.get(
        f"/api/article/{public_article_id}",
        headers={"X-Visitor-Id": "visitor-smoke-b"},
    ).json()
    free_member_paid_article = client.get(
        f"/api/article/{public_article_id}",
        headers={**member_headers, "X-Visitor-Id": "visitor-smoke-member"},
    ).json()
    guest_paid_summary = client.get(f"/api/summarize_article/{public_article_id}").json()
    guest_translation_response = (
        client.get(
            f"/api/article/{public_article_id}/translation?lang=en",
            headers={"X-Visitor-Id": "visitor-smoke-a"},
        )
        if ai_enabled
        else client.get(f"/api/article/{public_article_id}/translation?lang=en")
    )
    guest_translation = guest_translation_response.json()
    guest_translation_cached = (
        client.get(
            f"/api/article/{public_article_id}/translation?lang=en",
            headers={"X-Visitor-Id": "visitor-smoke-a"},
        ).json()
        if ai_enabled
        else None
    )

    if not guest_paid_summary.get("summary_html"):
        raise AssertionError("Expected persisted or fast-rendered summary_html for article summary response.")
    if guest_translation_response.status_code == 200 and isinstance(guest_translation, dict) and not guest_translation.get("summary_html"):
        raise AssertionError("Expected fast-rendered summary_html for translation response.")

    admin_memberships_unauthorized = client.get("/api/admin/memberships")
    admin_memberships = client.get("/api/admin/memberships?limit=20", headers=admin_headers).json()
    admin_upgrade = client.put(
        f"/api/admin/memberships/{member_user_id}",
        headers=admin_headers,
        json={
            "email": member_email,
            "tier": "paid_member",
            "status": "active",
            "note": "Smoke upgraded to paid member",
            "expires_at": "2026-12-31",
        },
    ).json()
    membership_member_after = client.get("/api/membership/me", headers=member_headers).json()
    paid_member_article = client.get(
        f"/api/article/{public_article_id}",
        headers={**member_headers, "X-Visitor-Id": "visitor-smoke-paid"},
    ).json()
    paid_translation_response = (
        client.get(
            f"/api/article/{public_article_id}/translation?lang=en",
            headers={**member_headers, "X-Visitor-Id": "visitor-smoke-paid"},
        )
        if ai_enabled
        else None
    )
    paid_translation = paid_translation_response.json() if paid_translation_response is not None else None

    audio_guest = client.get("/api/media/audio?limit=6").json()
    audio_paid = client.get("/api/media/audio?limit=6", headers=member_headers).json()
    my_library = client.get("/api/me/library?limit=5")
    unauthorized_reaction = client.post(
        f"/api/article/{public_article_id}/reaction",
        json={"reaction_type": "like", "active": True},
    )

    sitemap = client.get("/sitemap.xml")
    rss = client.get("/rss.xml")
    robots = client.get("/robots.txt")

    with sqlite3.connect(SQLITE_DB_PATH) as connection:
        lead_row = connection.execute(
            """
            SELECT id, organization, use_case, status
            FROM demo_requests
            WHERE id = ?
            """,
            (demo_request["id"],),
        ).fetchone()
        editorial_row = connection.execute(
            """
            SELECT id, article_id, status, workflow_status, scheduled_publish_at
            FROM editorial_articles
            WHERE id = ?
            """,
            (editorial_id,),
        ).fetchone()
        article_row = connection.execute(
            """
            SELECT id, access_level
            FROM articles
            WHERE id = ?
            """,
            (public_article_id,),
        ).fetchone()
        membership_row = connection.execute(
            """
            SELECT user_id, email, tier, status
            FROM user_memberships
            WHERE user_id = ?
            """,
            (member_user_id,),
        ).fetchone()
        order_row = connection.execute(
            """
            SELECT plan_code, status, payment_provider
            FROM billing_orders
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (member_user_id,),
        ).fetchone()
        checkout_row = connection.execute(
            """
            SELECT plan_code, status, payment_provider
            FROM billing_checkout_intents
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (member_user_id,),
        ).fetchone()
        translation_row = connection.execute(
            """
            SELECT article_id, target_lang, model
            FROM article_translations
            WHERE article_id = ?
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (public_article_id,),
        ).fetchone()

    summary = {
        "health": health,
        "home_sections": {
            "editors_picks": len(home.get("editors_picks", [])),
            "trending": len(home.get("trending", [])),
            "latest": len(home.get("latest", [])),
        },
        "search_total": search.get("total"),
        "analytics": {
            "metrics": len(analytics.get("metrics", [])),
            "trend_points": len(analytics.get("views_trend", [])),
            "top_viewed": len(analytics.get("top_viewed", [])),
        },
        "chat_sources": len(chat.get("sources", [])),
        "commerce": {
            "metrics": len(overview.get("metrics", [])),
            "faiss_ready": overview.get("faiss_ready"),
            "ai_ready": overview.get("ai_ready"),
            "lead_count": overview.get("lead_count"),
        },
        "demo_request": {
            "api_id": demo_request.get("id"),
            "db_row": list(lead_row) if lead_row else None,
        },
        "demo_requests": {
            "unauthorized_status": demo_requests_unauthorized.status_code,
            "count": len(demo_requests),
            "latest_id": demo_requests[0]["id"] if demo_requests else None,
            "csv_head": demo_export.text.splitlines()[:2],
        },
        "billing": {
            "plans": len(billing_plans.get("items", [])),
            "payments_enabled": billing_plans.get("payments_enabled"),
            "guest_membership_tier": billing_guest.get("membership", {}).get("tier"),
            "checkout_unauthorized_status": billing_checkout_unauthorized.status_code,
            "checkout_status": billing_checkout_member.get("status"),
            "checkout_message": billing_checkout_member.get("message"),
            "member_recent_orders": len(billing_member.get("recent_orders", [])),
            "admin_orders_unauthorized_status": admin_orders_unauthorized.status_code,
            "admin_orders_total": admin_orders.get("total"),
            "db_order_row": list(order_row) if order_row else None,
            "db_checkout_row": list(checkout_row) if checkout_row else None,
        },
        "follows": {
            "unauthorized_status": follows_unauthorized.status_code,
            "tag_active": follow_tag.get("active"),
            "column_active": follow_column.get("active"),
            "topic_active": follow_topic.get("active"),
            "list_total": follow_list.get("total"),
            "watchlist_total": follow_watchlist.get("total"),
            "watchlist_first_match": (follow_watchlist.get("items") or [{}])[0].get("matched_entities"),
            "unfollow_topic_active": unfollow_topic.get("active"),
        },
        "organizations": {
            "total": len(organizations_payload),
            "first_slug": organization_slug,
            "detail_name": organization_detail.get("name"),
            "detail_article_count": organization_detail.get("article_count"),
        },
        "editorial": {
            "editorial_id": editorial_id,
            "submit_review_status": editorial_submit_review.get("workflow_status"),
            "approve_status": editorial_approve.get("workflow_status"),
            "schedule_status": editorial_schedule.get("workflow_status"),
            "scheduled_publish_at": editorial_schedule.get("scheduled_publish_at"),
            "tag_count": len(editorial_autotag.get("tags", [])),
            "rendered": bool(editorial_render.get("html_web")) and bool(editorial_render.get("html_wechat")),
            "export_ok": editorial_export.status_code == 200 and "<!doctype html>" in editorial_export.text[:80].lower(),
            "dashboard_pending_review": editorial_dashboard.get("pending_review_count"),
            "dashboard_scheduled": editorial_dashboard.get("scheduled_count"),
            "published_article_id": public_article_id,
            "detail_after_publish_workflow": editorial_detail_after_publish.get("workflow_status"),
            "access_level": guest_paid_article.get("access", {}).get("access_level"),
            "guest_locked": guest_paid_article.get("access", {}).get("locked"),
            "free_member_locked": free_member_paid_article.get("access", {}).get("locked"),
            "paid_member_locked": paid_member_article.get("access", {}).get("locked"),
            "guest_preview_length": len(guest_paid_article.get("content", "")),
            "paid_member_content_length": len(paid_member_article.get("content", "")),
            "summary_preview_length": len(guest_paid_summary.get("summary", "")),
            "summary_html_length": len(guest_paid_summary.get("summary_html", "")),
            "translation": {
                "ai_enabled": ai_enabled,
                "guest_status": guest_translation_response.status_code,
                "guest_cached": guest_translation_cached.get("cached") if guest_translation_cached else None,
                "guest_scope": guest_translation.get("content_scope") if isinstance(guest_translation, dict) else None,
                "guest_model": guest_translation.get("model") if isinstance(guest_translation, dict) else None,
                "guest_title_sample": (guest_translation.get("title") or "")[:60] if isinstance(guest_translation, dict) else None,
                "guest_summary_html_length": len(guest_translation.get("summary_html", "")) if isinstance(guest_translation, dict) else 0,
                "paid_status": paid_translation_response.status_code if paid_translation_response is not None else None,
                "paid_scope": paid_translation.get("content_scope") if isinstance(paid_translation, dict) else None,
                "paid_content_length": len(paid_translation.get("content", "")) if isinstance(paid_translation, dict) else 0,
                "db_row": list(translation_row) if translation_row else None,
            },
            "deduped_views": {
                "first": guest_paid_article.get("engagement", {}).get("views"),
                "repeat_same_visitor": repeated_public_editorial.get("engagement", {}).get("views"),
                "second_visitor": second_visitor_public_editorial.get("engagement", {}).get("views"),
            },
            "unauthorized_reaction_status": unauthorized_reaction.status_code,
            "db_row": list(editorial_row) if editorial_row else None,
            "article_row": list(article_row) if article_row else None,
        },
        "auth": auth_status,
        "dashboards": {
            "guest_tier": guest_dashboard.get("business_profile", {}).get("tier"),
            "guest_home_path": guest_dashboard.get("business_profile", {}).get("role_home_path"),
            "free_seed_display_name": free_seed_dashboard.get("business_profile", {}).get("display_name"),
            "free_seed_quick_links": len(free_seed_dashboard.get("quick_links", [])),
            "paid_seed_access_level": paid_seed_dashboard.get("asset_summary", {}).get("unlocked_access_level"),
            "paid_seed_media_count": paid_seed_dashboard.get("asset_summary", {}).get("accessible_media_count"),
            "admin_metrics": len(admin_overview.get("metrics", [])),
            "admin_audits": len(admin_overview.get("recent_audits", [])),
        },
        "membership": {
            "guest_tier": membership_guest.get("tier"),
            "member_tier_before_upgrade": membership_member_before.get("tier"),
            "member_tier_after_upgrade": membership_member_after.get("tier"),
            "admin_unauthorized_status": admin_memberships_unauthorized.status_code,
            "admin_list_total": admin_memberships.get("total"),
            "admin_upgrade_tier": admin_upgrade.get("tier"),
            "db_row": list(membership_row) if membership_row else None,
        },
        "media": {
            "admin_unauthorized_status": media_admin_unauthorized.status_code,
            "admin_created_id": media_admin_id,
            "admin_updated_episode": media_admin_update.get("episode_number"),
            "admin_list_total": media_admin_list.get("total"),
            "admin_detail_series": media_admin_detail.get("series_name"),
            "admin_detail_chapter_count": len(media_admin_detail.get("chapters", [])),
            "audio_total": audio_guest.get("total"),
            "audio_first_series": audio_guest.get("items", [{}])[0].get("series_name") if audio_guest.get("items") else None,
            "guest_audio_accessible": sum(1 for item in audio_guest.get("items", []) if item.get("accessible")),
            "guest_audio_locked": sum(1 for item in audio_guest.get("items", []) if not item.get("accessible")),
            "paid_audio_accessible": sum(1 for item in audio_paid.get("items", []) if item.get("accessible")),
            "paid_audio_locked": sum(1 for item in audio_paid.get("items", []) if not item.get("accessible")),
        },
        "me": {
            "library_unauthorized_status": my_library.status_code,
        },
        "admin": {
            "overview_metrics": len(admin_overview.get("metrics", [])),
            "overview_role_counts": len(admin_overview.get("role_counts", [])),
            "mock_accounts": len(admin_overview.get("mock_accounts", [])),
        },
        "editorial_admin": {
            "unauthorized_status": editorial_unauthorized.status_code,
        },
        "publishing": {
            "sitemap_ok": sitemap.status_code == 200 and "<urlset" in sitemap.text,
            "rss_ok": rss.status_code == 200 and "<rss" in rss.text,
            "robots_ok": robots.status_code == 200 and "Sitemap:" in robots.text,
        },
    }
    print(summary)


if __name__ == "__main__":
    main()
