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
        publish_date="2026-04-11",
        cover_image_path="/legacy-covers/legacy-cover.png",
    )
    new_editorial_article_id = _insert_article(
        title="New Editorial Cover Should Stay",
        slug="new-editorial-cover-should-stay",
        publish_date="2026-04-12",
        cover_image_path="/editorial-uploads/covers/new-cover.png",
    )

    with connection_scope() as connection:
        now = "2026-04-12T09:00:00"
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
                "2026-04-11",
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
                "2026-04-12",
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
        publish_date="2026-04-01",
    )
    new_article_id = _insert_article(
        title="Newest Column Article",
        slug="newest-column-article",
        publish_date="2026-04-10",
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
    assert preview_ids[0] == new_article_id
