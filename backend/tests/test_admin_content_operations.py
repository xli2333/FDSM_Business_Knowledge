from __future__ import annotations

import shutil
import tempfile
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import backend.database as database_module
from backend.database import connection_scope, ensure_runtime_tables
from backend.main import app
from backend.routers import admin as admin_router
from backend.routers import editorial as editorial_router
from backend.routers import topics as topics_router
from backend.services import ai_service, editorial_service
from backend.services.article_ai_output_service import build_current_article_source_hash

SOURCE_DB_PATH = Path(__file__).resolve().parents[2] / "fudan_knowledge_base.db"


def _allow_admin_access(monkeypatch):
    admin_user = {"id": "admin-content-ops", "email": "admin@example.com"}
    monkeypatch.setattr(
        admin_router,
        "get_authenticated_user",
        lambda authorization, debug_user_id=None, debug_user_email=None: admin_user,
    )
    monkeypatch.setattr(admin_router, "require_admin_profile", lambda user: {"is_admin": True})
    monkeypatch.setattr(
        editorial_router,
        "get_authenticated_user",
        lambda authorization, debug_user_id=None, debug_user_email=None: admin_user,
    )
    monkeypatch.setattr(editorial_router, "require_admin_profile", lambda user: {"is_admin": True})
    monkeypatch.setattr(
        editorial_service,
        "sync_article_for_rag",
        lambda article_id, trigger_source="manual", force=False: {
            "job": None,
            "version": None,
            "skipped": True,
            "article_id": article_id,
            "trigger_source": trigger_source,
            "force": force,
        },
    )
    monkeypatch.setattr(
        editorial_service,
        "render_fudan_wechat",
        lambda item, timeout_seconds=60.0: {
            "previewHtml": f"<div><h1>{item.get('title') or 'Editorial'}</h1><p>Rendered for test.</p></div>",
            "contentHtml": f"<div><h1>{item.get('title') or 'Editorial'}</h1><p>Rendered for test.</p></div>",
            "renderPlan": {"layout": "test"},
            "metadata": {"engine": "test"},
            "warnings": [],
        },
    )
    monkeypatch.setattr(
        ai_service,
        "translate_editorial_assets_to_english",
        lambda title, excerpt, summary_markdown, content_markdown: {
            "title": f"{title} EN",
            "excerpt": excerpt or "English excerpt",
            "summary": summary_markdown or "English summary",
            "content": content_markdown or "English content",
            "model": "gemini-3-flash-preview",
        },
    )
    monkeypatch.setattr(
        topics_router,
        "get_authenticated_user",
        lambda authorization, debug_user_id=None, debug_user_email=None: admin_user,
    )
    monkeypatch.setattr(topics_router, "require_paid_profile", lambda user: {"can_access_paid": True})


@pytest.fixture()
def client(monkeypatch):
    temp_dir = Path(tempfile.mkdtemp(prefix="fdsm_content_ops_"))
    db_path = temp_dir / "fudan_knowledge_base.db"
    if SOURCE_DB_PATH.exists():
        shutil.copy2(SOURCE_DB_PATH, db_path)
    monkeypatch.setattr(database_module, "SQLITE_DB_PATH", db_path)
    ensure_runtime_tables()
    _allow_admin_access(monkeypatch)
    yield TestClient(app)
    shutil.rmtree(temp_dir, ignore_errors=True)


def _insert_article(
    *,
    title: str,
    slug: str,
    publish_date: str,
    excerpt: str = "Summary",
    content: str = "first paragraph\n\nsecond paragraph",
    cover_image_path: str | None = None,
) -> int:
    with connection_scope() as connection:
        article_id = int(connection.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM articles").fetchone()[0])
        now = f"{publish_date}T09:00:00"
        connection.execute(
            """
            INSERT INTO articles (
                id, doc_id, slug, relative_path, source, source_mode, title, publish_date, link,
                content, excerpt, main_topic, article_type, series_or_column, primary_org_name,
                tag_text, people_text, org_text, search_text, word_count, cover_image_path,
                access_level, view_count, is_featured, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, 'editorial', 'cms', ?, ?, NULL, ?, ?, 'Topic Governance', 'insight', 'Editorial',
                    'Fudan Business Knowledge', '', '', 'Fudan Business Knowledge', ?, ?, ?,
                    'public', 0, 0, ?, ?)
            """,
            (
                article_id,
                f"test-doc-{article_id}",
                slug,
                f"editorial/{slug}.md",
                title,
                publish_date,
                content,
                excerpt,
                f"{title} {excerpt} {content}",
                max(1, len(content.replace("\n", ""))),
                cover_image_path,
                now,
                now,
            ),
        )
        connection.commit()
    return article_id


def _ensure_column_mapping(article_id: int, column_slug: str = "insights") -> None:
    with connection_scope() as connection:
        column_row = connection.execute("SELECT id FROM columns WHERE slug = ?", (column_slug,)).fetchone()
        assert column_row is not None
        connection.execute(
            "INSERT OR REPLACE INTO article_columns (article_id, column_id, is_featured, sort_order) VALUES (?, ?, 1, 0)",
            (article_id, int(column_row["id"])),
        )
        connection.commit()


def _set_column_mapping(article_id: int, *, column_slug: str = "insights", is_featured: int = 0, sort_order: int = 0) -> None:
    with connection_scope() as connection:
        column_row = connection.execute("SELECT id FROM columns WHERE slug = ?", (column_slug,)).fetchone()
        assert column_row is not None
        connection.execute(
            "DELETE FROM article_columns WHERE article_id = ? AND column_id = ?",
            (article_id, int(column_row["id"])),
        )
        connection.execute(
            "INSERT INTO article_columns (article_id, column_id, is_featured, sort_order) VALUES (?, ?, ?, ?)",
            (article_id, int(column_row["id"]), is_featured, sort_order),
        )
        connection.commit()


def _insert_article_translation(
    article_id: int,
    *,
    title: str,
    excerpt: str,
    summary: str | None = None,
    content: str | None = None,
) -> None:
    with connection_scope() as connection:
        article_row = connection.execute(
            """
            SELECT id, title, excerpt, main_topic, content, COALESCE(access_level, 'public') AS access_level
            FROM articles
            WHERE id = ?
            """,
            (article_id,),
        ).fetchone()
        assert article_row is not None
        source_hash = build_current_article_source_hash(article_row)
        timestamp = f"{date.today().isoformat()}T10:00:00"
        connection.execute(
            """
            INSERT OR REPLACE INTO article_translations (
                article_id, target_lang, source_hash, title, excerpt, summary, content, model, created_at, updated_at
            )
            VALUES (?, 'en', ?, ?, ?, ?, ?, 'gemini-2.0-flash', ?, ?)
            """,
            (
                article_id,
                source_hash,
                title,
                excerpt,
                summary or excerpt,
                content or excerpt,
                timestamp,
                timestamp,
            ),
        )
        connection.commit()


def _ensure_topic(title: str, slug: str) -> int:
    with connection_scope() as connection:
        existing = connection.execute("SELECT id FROM topics WHERE slug = ?", (slug,)).fetchone()
        if existing is not None:
            return int(existing["id"])
        topic_id = int(connection.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM topics").fetchone()[0])
        now = date.today().isoformat()
        connection.execute(
            """
            INSERT INTO topics (
                id, title, slug, description, cover_image, cover_article_id, type, auto_rules,
                status, created_at, updated_at, view_count
            )
            VALUES (?, ?, ?, ?, NULL, NULL, 'editorial', NULL, 'published', ?, ?, 0)
            """,
            (topic_id, title, slug, f"{title} description", now, now),
        )
        connection.commit()
    return topic_id


def _ensure_tag(name: str, slug: str) -> None:
    with connection_scope() as connection:
        existing = connection.execute("SELECT id FROM tags WHERE slug = ?", (slug,)).fetchone()
        if existing is None:
            connection.execute(
                """
                INSERT INTO tags (name, slug, category, description, color, article_count)
                VALUES (?, ?, 'topic', NULL, '#0d0783', 0)
                """,
                (name, slug),
            )
            connection.commit()


def _insert_view_events(article_id: int, target_date: date, count: int) -> None:
    timestamp = f"{target_date.isoformat()}T08:00:00"
    with connection_scope() as connection:
        for index in range(count):
            connection.execute(
                """
                INSERT OR IGNORE INTO article_view_events (
                    article_id, visitor_id, user_id, view_date, source, created_at
                )
                VALUES (?, ?, NULL, ?, 'test', ?)
                """,
                (article_id, f"viewer-{article_id}-{target_date.isoformat()}-{index}", target_date.isoformat(), timestamp),
            )
        connection.commit()


def test_editorial_selected_topics_publish_into_topic_articles(client):
    topic_a = _ensure_topic("Genomics Governance", "genomics-governance")
    topic_b = _ensure_topic("Privacy Crisis", "privacy-crisis")

    create_response = client.post(
        "/api/editorial/articles",
        json={
            "title": "Topic Selection Draft",
            "source_markdown": "first paragraph\n\nsecond paragraph",
            "content_markdown": "first paragraph\n\nsecond paragraph",
            "primary_column_slug": "insights",
            "primary_column_manual": True,
            "tags": [
                {
                    "name": "Data Governance",
                    "slug": "topic-data-governance",
                    "category": "topic",
                    "confidence": 0.9,
                }
            ],
            "selected_topic_ids": [topic_a, topic_b],
            "final_html": "<!doctype html><html><body><h1>Topic Selection Draft</h1><p>Final html body.</p></body></html>",
        },
    )
    assert create_response.status_code == 200
    created_payload = create_response.json()
    editorial_id = int(created_payload["id"])
    assert created_payload["selected_topic_ids"] == [topic_a, topic_b]
    assert [item["id"] for item in created_payload["topic_candidates"][:2]] == [topic_a, topic_b]

    publish_response = client.post(f"/api/editorial/articles/{editorial_id}/publish")
    assert publish_response.status_code == 200
    publish_payload = publish_response.json()
    article_id = int(publish_payload["article_id"])
    assert [item["id"] for item in publish_payload["selected_topics"]] == [topic_a, topic_b]

    with connection_scope() as connection:
        topic_rows = connection.execute(
            "SELECT topic_id, sort_order FROM topic_articles WHERE article_id = ? ORDER BY sort_order ASC",
            (article_id,),
        ).fetchall()
    assert [(int(row["topic_id"]), int(row["sort_order"])) for row in topic_rows] == [(topic_a, 0), (topic_b, 1)]

    update_response = client.put(
        f"/api/editorial/articles/{editorial_id}",
        json={
            "selected_topic_ids": [topic_b],
            "final_html": "<!doctype html><html><body><h1>Topic Selection Draft</h1><p>Republished html body.</p></body></html>",
        },
    )
    assert update_response.status_code == 200

    republish_response = client.post(f"/api/editorial/articles/{editorial_id}/publish")
    assert republish_response.status_code == 200
    republish_payload = republish_response.json()
    assert [item["id"] for item in republish_payload["selected_topics"]] == [topic_b]

    with connection_scope() as connection:
        republished_rows = connection.execute(
            "SELECT topic_id, sort_order FROM topic_articles WHERE article_id = ? ORDER BY sort_order ASC",
            (article_id,),
        ).fetchall()
    assert [(int(row["topic_id"]), int(row["sort_order"])) for row in republished_rows] == [(topic_b, 0)]


def test_legacy_cover_images_fall_back_to_default_card_cover_until_new_editorial_publish(client):
    legacy_article_id = _insert_article(
        title="Legacy Cover Should Hide",
        slug="legacy-cover-should-hide",
        publish_date="9999-04-11",
        cover_image_path="/legacy-covers/legacy-cover.png",
    )
    new_editorial_article_id = _insert_article(
        title="New Editorial Cover Should Stay",
        slug="new-editorial-cover-should-stay",
        publish_date="9999-04-12",
        cover_image_path="/editorial-uploads/covers/new-cover.png",
    )

    with connection_scope() as connection:
        now = "9999-04-12T09:00:00"
        connection.execute(
            """
            INSERT INTO editorial_articles (
                article_id,
                source_article_id,
                slug,
                title,
                publish_date,
                cover_image_url,
                source_markdown,
                content_markdown,
                plain_text_content,
                excerpt,
                status,
                draft_box_state,
                workflow_status,
                created_at,
                updated_at,
                published_at
            )
            VALUES (?, ?, ?, ?, ?, ?, 'legacy source', 'legacy content', 'legacy content', 'legacy excerpt',
                    'published', 'archived', 'published', ?, ?, ?)
            """,
            (
                legacy_article_id,
                legacy_article_id,
                    "legacy-cover-should-hide-editorial",
                    "Legacy Cover Should Hide",
                    "9999-04-11",
                "/editorial-uploads/covers/legacy-cover.png",
                now,
                now,
                now,
            ),
        )
        connection.execute(
            """
            INSERT INTO editorial_articles (
                article_id,
                source_article_id,
                slug,
                title,
                publish_date,
                cover_image_url,
                source_markdown,
                content_markdown,
                plain_text_content,
                excerpt,
                status,
                draft_box_state,
                workflow_status,
                created_at,
                updated_at,
                published_at
            )
            VALUES (?, NULL, ?, ?, ?, ?, 'new source', 'new content', 'new content', 'new excerpt',
                    'published', 'archived', 'published', ?, ?, ?)
            """,
            (
                new_editorial_article_id,
                    "new-editorial-cover-should-stay",
                    "New Editorial Cover Should Stay",
                    "9999-04-12",
                "/editorial-uploads/covers/new-cover.png",
                now,
                now,
                now,
            ),
        )
        connection.commit()

    latest_response = client.get("/api/articles/latest?limit=20&offset=0&language=zh")
    assert latest_response.status_code == 200
    cards = {item["id"]: item for item in latest_response.json()}

    assert cards[legacy_article_id]["cover_url"] is None
    assert cards[new_editorial_article_id]["cover_url"] == f"/api/article/{new_editorial_article_id}/cover"


def test_admin_content_operations_drive_home_feed_sections(client):
    hero_article_id = _insert_article(title="Hero Configured Article", slug="hero-configured-article", publish_date="2099-01-01")
    pick_article_id = _insert_article(title="Editor Pick Article", slug="editor-pick-article", publish_date="2099-01-02")
    _ensure_column_mapping(hero_article_id, "insights")
    _ensure_column_mapping(pick_article_id, "insights")
    _ensure_tag("Configured Quick Tag", "configured-quick-tag")
    configured_topic_id = _ensure_topic("Configured Topic", "configured-topic")

    state_response = client.get("/api/admin/content-ops")
    assert state_response.status_code == 200
    assert any(section["slot_key"] == "hero" for section in state_response.json()["sections"])

    assert client.put(
        "/api/admin/content-ops/sections/hero",
        json={"items": [{"entity_type": "article", "id": hero_article_id, "slug": "hero-configured-article", "title": "Hero Configured Article"}]},
    ).status_code == 200
    assert client.put(
        "/api/admin/content-ops/sections/editors_picks",
        json={"items": [{"entity_type": "article", "id": pick_article_id, "slug": "editor-pick-article", "title": "Editor Pick Article"}]},
    ).status_code == 200
    assert client.put(
        "/api/admin/content-ops/sections/quick_tags",
        json={"items": [{"entity_type": "tag", "slug": "configured-quick-tag", "title": "Configured Quick Tag"}]},
    ).status_code == 200
    assert client.put(
        "/api/admin/content-ops/sections/topic_starters",
        json={"items": [{"entity_type": "topic", "id": configured_topic_id, "slug": "configured-topic", "title": "Configured Topic"}]},
    ).status_code == 200
    assert client.put(
        "/api/admin/content-ops/sections/column_navigation",
        json={"items": [{"entity_type": "column", "slug": "insights", "title": "深度洞察"}]},
    ).status_code == 200
    assert client.put(
        "/api/admin/content-ops/sections/topic_square",
        json={"items": [{"entity_type": "topic", "id": configured_topic_id, "slug": "configured-topic", "title": "Configured Topic"}]},
    ).status_code == 200

    feed_response = client.get("/api/home/feed?language=zh")
    assert feed_response.status_code == 200
    payload = feed_response.json()
    assert payload["hero"]["id"] == hero_article_id
    assert payload["editors_picks"][0]["id"] == pick_article_id
    assert payload["quick_tags"][0]["slug"] == "configured-quick-tag"
    assert payload["topic_starters"][0]["slug"] == "configured-topic"
    assert payload["column_previews"][0]["column"]["slug"] == "insights"
    assert payload["topic_square"][0]["slug"] == "configured-topic"


def test_admin_content_operations_support_independent_english_homepage_distribution(client):
    zh_hero_article_id = _insert_article(
        title="中文首页头条",
        slug="zh-homepage-hero",
        publish_date="2099-02-01",
        excerpt="中文首页头条摘要。",
    )
    en_hero_article_id = _insert_article(
        title="英文版候选中文原文",
        slug="en-homepage-hero-source",
        publish_date="2099-02-02",
        excerpt="这篇文章会被翻译成英文头条。",
    )
    _ensure_column_mapping(zh_hero_article_id, "insights")
    _ensure_column_mapping(en_hero_article_id, "insights")
    _insert_article_translation(
        en_hero_article_id,
        title="English Homepage Hero",
        excerpt="English homepage hero excerpt.",
        content="English homepage hero body.",
    )

    zh_update = client.put(
        "/api/admin/content-ops/sections/hero",
        json={"items": [{"entity_type": "article", "id": zh_hero_article_id, "slug": "zh-homepage-hero", "title": "中文首页头条"}]},
    )
    assert zh_update.status_code == 200
    assert zh_update.json()["language"] == "zh"

    en_update = client.put(
        "/api/admin/content-ops/sections/hero?language=en",
        json={"items": [{"entity_type": "article", "id": en_hero_article_id, "slug": "en-homepage-hero-source", "title": "English Homepage Hero"}]},
    )
    assert en_update.status_code == 200
    assert en_update.json()["language"] == "en"

    zh_state = client.get("/api/admin/content-ops?language=zh")
    en_state = client.get("/api/admin/content-ops?language=en")
    assert zh_state.status_code == 200
    assert en_state.status_code == 200
    assert zh_state.json()["sections"][0]["items"][0]["id"] == zh_hero_article_id
    assert en_state.json()["sections"][0]["items"][0]["id"] == en_hero_article_id
    assert en_state.json()["sections"][0]["items"][0]["title"] == "English Homepage Hero"

    zh_feed = client.get("/api/home/feed?language=zh")
    en_feed = client.get("/api/home/feed?language=en")
    assert zh_feed.status_code == 200
    assert en_feed.status_code == 200
    assert zh_feed.json()["hero"]["id"] == zh_hero_article_id
    assert en_feed.json()["hero"]["id"] == en_hero_article_id
    assert en_feed.json()["hero"]["title"] == "English Homepage Hero"


def test_admin_content_operation_article_candidates_filter_and_localize_for_english(client):
    translated_article_id = _insert_article(
        title="中文 GPU 原文",
        slug="gpu-english-candidate-source",
        publish_date="2099-03-02",
        excerpt="这篇文章具备英文资产。",
    )
    untranslated_article_id = _insert_article(
        title="未翻译中文文章",
        slug="zh-only-admin-candidate",
        publish_date="2099-03-01",
        excerpt="这篇文章没有英文资产。",
    )
    _insert_article_translation(
        translated_article_id,
        title="GPU Candidate",
        excerpt="English candidate excerpt.",
        content="English candidate body.",
    )

    response = client.get("/api/admin/content-ops/candidates?entity_type=article&language=en&limit=20")
    assert response.status_code == 200
    payload = response.json()

    assert any(item["id"] == translated_article_id and item["title"] == "GPU Candidate" for item in payload)
    assert all(item["id"] != untranslated_article_id for item in payload)


def test_admin_column_article_collection_manages_public_section_membership_and_order(client):
    first_article_id = _insert_article(
        title="Admin Section First",
        slug="admin-section-first",
        publish_date="2099-05-01",
    )
    second_article_id = _insert_article(
        title="Admin Section Second",
        slug="admin-section-second",
        publish_date="2099-05-02",
    )

    update_response = client.put(
        "/api/admin/content-ops/columns/case-decisions/articles",
        json={
            "items": [
                {"entity_type": "article", "id": second_article_id, "slug": "admin-section-second", "title": "Admin Section Second"},
                {"entity_type": "article", "id": first_article_id, "slug": "admin-section-first", "title": "Admin Section First"},
            ]
        },
    )
    assert update_response.status_code == 200
    assert [item["id"] for item in update_response.json()["items"]] == [second_article_id, first_article_id]

    public_response = client.get("/api/columns/case-decisions/articles?page=1&page_size=5")
    assert public_response.status_code == 200
    public_ids = [item["id"] for item in public_response.json()["items"]]
    assert public_ids[:2] == [second_article_id, first_article_id]

    remove_response = client.put(
        "/api/admin/content-ops/columns/case-decisions/articles",
        json={"items": [{"entity_type": "article", "id": first_article_id, "slug": "admin-section-first", "title": "Admin Section First"}]},
    )
    assert remove_response.status_code == 200
    assert [item["id"] for item in remove_response.json()["items"]] == [first_article_id]

    after_remove_response = client.get("/api/columns/case-decisions/articles?page=1&page_size=5")
    assert after_remove_response.status_code == 200
    after_remove_ids = [item["id"] for item in after_remove_response.json()["items"]]
    assert first_article_id in after_remove_ids
    assert second_article_id not in after_remove_ids


def test_admin_topic_article_collection_manages_topic_page_membership_and_order(client):
    _ensure_topic("Admin Managed Topic", "admin-managed-topic")
    first_article_id = _insert_article(
        title="Admin Topic First",
        slug="admin-topic-first",
        publish_date="2099-06-01",
    )
    second_article_id = _insert_article(
        title="Admin Topic Second",
        slug="admin-topic-second",
        publish_date="2099-06-02",
    )

    update_response = client.put(
        "/api/admin/content-ops/topics/admin-managed-topic/articles",
        json={
            "items": [
                {"entity_type": "article", "id": second_article_id, "slug": "admin-topic-second", "title": "Admin Topic Second"},
                {"entity_type": "article", "id": first_article_id, "slug": "admin-topic-first", "title": "Admin Topic First"},
            ]
        },
    )
    assert update_response.status_code == 200
    assert [item["id"] for item in update_response.json()["items"]] == [second_article_id, first_article_id]

    topic_response = client.get("/api/topics/admin-managed-topic?page=1&page_size=5")
    assert topic_response.status_code == 200
    topic_ids = [item["id"] for item in topic_response.json()["articles"]]
    assert topic_ids[:2] == [second_article_id, first_article_id]

    remove_response = client.put(
        "/api/admin/content-ops/topics/admin-managed-topic/articles",
        json={"items": [{"entity_type": "article", "id": first_article_id, "slug": "admin-topic-first", "title": "Admin Topic First"}]},
    )
    assert remove_response.status_code == 200
    assert [item["id"] for item in remove_response.json()["items"]] == [first_article_id]

    after_remove_response = client.get("/api/topics/admin-managed-topic?page=1&page_size=5")
    assert after_remove_response.status_code == 200
    after_remove_ids = [item["id"] for item in after_remove_response.json()["articles"]]
    assert first_article_id in after_remove_ids
    assert second_article_id not in after_remove_ids


def test_admin_column_candidates_only_return_six_public_sections(client):
    with connection_scope() as connection:
        connection.execute(
            """
            INSERT OR IGNORE INTO columns (name, slug, description, icon, sort_order, accent_color)
            VALUES ('Legacy Column', 'legacy-column', 'Old hidden column', 'Archive', 999, '#666666')
            """
        )
        connection.commit()

    response = client.get("/api/admin/content-ops/candidates?entity_type=column&limit=20")
    assert response.status_code == 200
    slugs = [item["slug"] for item in response.json()]
    assert "legacy-column" not in slugs
    assert slugs == ["deans-view", "case-decisions", "industry", "insights", "research", "fudan-classroom"]


def test_latest_and_trending_respect_new_ordering(client):
    today = date.today()
    recent_article_id = _insert_article(
        title="Latest Order Recent",
        slug="latest-order-recent",
        publish_date=(today + timedelta(days=1)).isoformat(),
    )
    older_article_id = _insert_article(
        title="Latest Order Older",
        slug="latest-order-older",
        publish_date=today.isoformat(),
    )
    monthly_hot_article_id = _insert_article(
        title="Monthly Hot Article",
        slug="monthly-hot-article",
        publish_date=(today - timedelta(days=20)).isoformat(),
    )
    weekly_hot_article_id = _insert_article(
        title="Weekly Hot Article",
        slug="weekly-hot-article",
        publish_date=(today - timedelta(days=7)).isoformat(),
    )

    latest_response = client.get("/api/articles/latest?limit=2&offset=0&language=zh")
    assert latest_response.status_code == 200
    latest_ids = [item["id"] for item in latest_response.json()]
    assert recent_article_id in latest_ids[:1]
    assert older_article_id in latest_ids[:2]

    _insert_view_events(monthly_hot_article_id, today - timedelta(days=15), 800)
    _insert_view_events(weekly_hot_article_id, today, 400)

    week_response = client.get("/api/articles/trending?limit=2&offset=0&window=week&language=zh")
    assert week_response.status_code == 200
    assert week_response.json()[0]["id"] == weekly_hot_article_id

    month_response = client.get("/api/articles/trending?limit=2&offset=0&window=month&language=zh")
    assert month_response.status_code == 200
    assert month_response.json()[0]["id"] == monthly_hot_article_id


def test_column_pages_and_home_previews_put_newer_articles_ahead_of_old_featured_items(client):
    old_featured_article_id = _insert_article(
        title="Old Featured Column Article",
        slug="old-featured-column-article",
        publish_date="9999-04-01",
    )
    new_article_id = _insert_article(
        title="Newest Column Article",
        slug="newest-column-article",
        publish_date="9999-04-10",
    )

    _set_column_mapping(old_featured_article_id, column_slug="insights", is_featured=1, sort_order=0)
    _set_column_mapping(new_article_id, column_slug="insights", is_featured=0, sort_order=0)

    assert client.put(
        "/api/admin/content-ops/sections/column_navigation",
        json={"items": [{"entity_type": "column", "slug": "insights", "title": "深度洞察"}]},
    ).status_code == 200

    column_response = client.get("/api/columns/insights/articles?page=1&page_size=5")
    assert column_response.status_code == 200
    column_ids = [item["id"] for item in column_response.json()["items"]]
    assert new_article_id in column_ids
    assert old_featured_article_id in column_ids
    assert column_ids.index(new_article_id) < column_ids.index(old_featured_article_id)

    home_response = client.get("/api/home/feed?language=zh")
    assert home_response.status_code == 200
    preview_ids = [item["id"] for item in home_response.json()["column_previews"][0]["items"]]
    assert new_article_id in preview_ids


def test_column_articles_endpoint_returns_english_payload_for_english_entry(client):
    translated_article_id = _insert_article(
        title="算力账本的悖论：GPU折旧年限与AI价值瀑布的财务博弈",
        slug="gpu-depreciation-reset-zh",
        publish_date="9999-04-16",
        excerpt="这篇文章讨论 GPU 折旧年限变化带来的财务影响。",
    )
    untranslated_article_id = _insert_article(
        title="中文专栏文章",
        slug="column-zh-only-article",
        publish_date="9999-04-15",
        excerpt="这篇文章还没有生成英文资产。",
    )

    _set_column_mapping(translated_article_id, column_slug="insights", is_featured=0, sort_order=0)
    _set_column_mapping(untranslated_article_id, column_slug="insights", is_featured=0, sort_order=1)
    _insert_article_translation(
        translated_article_id,
        title="GPU Depreciation Reset",
        excerpt="A finance read on how GPU depreciation changes AI infrastructure economics.",
        content="GPU depreciation reset English body.",
    )

    response = client.get("/api/columns/insights/articles?page=1&page_size=10&language=en")
    assert response.status_code == 200
    payload = response.json()

    assert payload["column"]["name"] == "Hot Briefing"
    assert payload["column"]["description"] == "Business hotspots explained through data, facts, and management judgment."
    assert payload["total"] >= 1
    assert all(item["id"] != untranslated_article_id for item in payload["items"])
    assert any(item["id"] == translated_article_id for item in payload["items"])

    translated_item = next(item for item in payload["items"] if item["id"] == translated_article_id)
    assert translated_item["title"] == "GPU Depreciation Reset"
    assert translated_item["excerpt"] == "A finance read on how GPU depreciation changes AI infrastructure economics."
