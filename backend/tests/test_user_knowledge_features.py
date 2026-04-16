from __future__ import annotations

import re
import shutil
import tempfile
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import backend.database as database_module
from backend.database import connection_scope, ensure_runtime_tables
from backend.main import app
from backend.routers import me as me_router
from backend.routers import user_knowledge as user_knowledge_router
from backend.services import ai_service, rag_engine, user_knowledge_service
from backend.services.chat_markdown_service import normalize_chat_answer_markdown
from backend.services.engagement_service import set_article_reaction
from backend.services import knowledge_embedding_service, knowledge_ingestion_service, knowledge_retrieval_service
from backend.services.knowledge_ingestion_service import (
    get_current_version,
    process_pending_ingestion_jobs,
    queue_article_ingestion,
    sync_article_for_rag,
    sync_public_articles_for_rag,
)
from backend.services.knowledge_retrieval_service import RetrievalScope, retrieve_scope_context

SOURCE_DB_PATH = Path(__file__).resolve().parents[2] / "fudan_knowledge_base.db"


def _mock_get_authenticated_user(authorization, debug_user_id=None, debug_user_email=None):
    return {
        "id": debug_user_id or "paid-user",
        "email": debug_user_email or "paid@example.com",
    }


def _mock_require_paid_profile(user):
    if str(user.get("id") or "").startswith("free"):
        raise HTTPException(status_code=403, detail="Paid membership required")
    return {
        "tier": "paid_member",
        "tier_label": "Paid Member",
        "status": "active",
        "status_label": "Active",
        "is_authenticated": True,
        "is_admin": False,
        "can_access_member": True,
        "can_access_paid": True,
        "user_id": user["id"],
        "email": user.get("email"),
        "benefits": [],
    }


@pytest.fixture()
def client(monkeypatch):
    temp_dir = Path(tempfile.mkdtemp(prefix="fdsm_user_knowledge_"))
    db_path = temp_dir / "fudan_knowledge_base.db"
    if SOURCE_DB_PATH.exists():
        shutil.copy2(SOURCE_DB_PATH, db_path)
    monkeypatch.setattr(database_module, "SQLITE_DB_PATH", db_path)
    ensure_runtime_tables()
    monkeypatch.setattr(user_knowledge_router, "get_authenticated_user", _mock_get_authenticated_user)
    monkeypatch.setattr(user_knowledge_router, "require_paid_profile", _mock_require_paid_profile)
    monkeypatch.setattr(me_router, "get_authenticated_user", _mock_get_authenticated_user)
    monkeypatch.setattr(knowledge_embedding_service, "is_chunk_embedding_enabled", lambda: False)
    monkeypatch.setattr(knowledge_ingestion_service, "is_chunk_embedding_enabled", lambda: False)
    monkeypatch.setattr(knowledge_retrieval_service, "is_chunk_embedding_enabled", lambda: False)
    yield TestClient(app)
    shutil.rmtree(temp_dir, ignore_errors=True)


def _insert_article(*, title: str, slug: str, publish_date: str, excerpt: str, content: str) -> int:
    with connection_scope() as connection:
        article_id = int(connection.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM articles").fetchone()[0])
        timestamp = f"{publish_date}T09:00:00"
        connection.execute(
            """
            INSERT INTO articles (
                id, doc_id, slug, relative_path, source, source_mode, title, publish_date, link,
                content, excerpt, main_topic, article_type, series_or_column, primary_org_name,
                tag_text, people_text, org_text, search_text, word_count, cover_image_path,
                access_level, view_count, is_featured, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, 'editorial', 'cms', ?, ?, NULL, ?, ?, 'Knowledge Theme', 'insight',
                    'Editorial', 'Fudan Business Knowledge', '', '', 'Fudan Business Knowledge',
                    ?, ?, NULL, 'public', 0, 0, ?, ?)
            """,
            (
                article_id,
                f"user-knowledge-{article_id}",
                slug,
                f"editorial/{slug}.md",
                title,
                publish_date,
                content,
                excerpt,
                f"{title} {excerpt} {content}",
                max(1, len(content.replace("\n", ""))),
                timestamp,
                timestamp,
            ),
        )
        connection.commit()
    return article_id


def _headers(user_id: str, email: str) -> dict[str, str]:
    return {
        "X-Debug-User-Id": user_id,
        "X-Debug-User-Email": email,
    }


def test_paid_member_can_create_theme_with_initial_article_and_list_it(client):
    article_id = _insert_article(
        title="AI Governance Filing",
        slug="ai-governance-filing",
        publish_date="2026-04-15",
        excerpt="Explain how AI governance shifts from compliance to operating system design.",
        content="AI governance moved from policy text to operating model. The filing explains budgets, decision loops, and board oversight.",
    )

    create_response = client.post(
        "/api/me/knowledge/themes",
        headers=_headers("paid-user-one", "paid1@example.com"),
        json={
            "title": "AI Knowledge Theme",
            "description": "Track AI governance and operating-model decisions.",
            "initial_article_id": article_id,
        },
    )
    assert create_response.status_code == 200
    created = create_response.json()
    assert created["title"] == "AI Knowledge Theme"
    assert created["article_count"] == 1
    assert created["preview_articles"][0]["id"] == article_id

    list_response = client.get(
        f"/api/me/knowledge/themes?article_id={article_id}",
        headers=_headers("paid-user-one", "paid1@example.com"),
    )
    assert list_response.status_code == 200
    payload = list_response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["contains_article"] is True

    detail_response = client.get(
        f"/api/me/knowledge/themes/{created['slug']}",
        headers=_headers("paid-user-one", "paid1@example.com"),
    )
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["article_count"] == 1
    assert detail["articles"][0]["id"] == article_id


def test_free_member_is_blocked_from_knowledge_endpoints(client):
    response = client.get(
        "/api/me/knowledge/themes",
        headers=_headers("free-user-one", "reader@example.com"),
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Paid membership required"


def test_themes_are_scoped_by_user(client):
    article_id = _insert_article(
        title="Robotics Supply Chain Memo",
        slug="robotics-supply-chain-memo",
        publish_date="2026-04-14",
        excerpt="Trace supplier concentration risk inside robotics manufacturing.",
        content="The memo studies supplier concentration, capex pacing, and how procurement changes under demand volatility.",
    )

    create_response = client.post(
        "/api/me/knowledge/themes",
        headers=_headers("paid-user-alpha", "alpha@example.com"),
        json={
            "title": "Robotics Supply Chain",
            "initial_article_id": article_id,
        },
    )
    assert create_response.status_code == 200
    created = create_response.json()

    other_user_list = client.get(
        "/api/me/knowledge/themes",
        headers=_headers("paid-user-beta", "beta@example.com"),
    )
    assert other_user_list.status_code == 200
    assert other_user_list.json()["items"] == []

    other_user_detail = client.get(
        f"/api/me/knowledge/themes/{created['slug']}",
        headers=_headers("paid-user-beta", "beta@example.com"),
    )
    assert other_user_detail.status_code == 404


def test_paid_member_can_add_and_remove_article_from_theme(client):
    article_id = _insert_article(
        title="Consumer Platform Renewal",
        slug="consumer-platform-renewal",
        publish_date="2026-04-13",
        excerpt="How a consumer platform resets growth through product restructuring.",
        content="The company rebuilt pricing, channel design, and retention operations to reset growth quality.",
    )

    create_response = client.post(
        "/api/me/knowledge/themes",
        headers=_headers("paid-user-gamma", "gamma@example.com"),
        json={"title": "Platform Reset"},
    )
    theme = create_response.json()
    assert theme["article_count"] == 0

    add_response = client.post(
        f"/api/me/knowledge/themes/{theme['id']}/articles",
        headers=_headers("paid-user-gamma", "gamma@example.com"),
        json={"article_id": article_id},
    )
    assert add_response.status_code == 200
    assert add_response.json()["active"] is True
    assert add_response.json()["article_count"] == 1

    remove_response = client.delete(
        f"/api/me/knowledge/themes/{theme['id']}/articles/{article_id}",
        headers=_headers("paid-user-gamma", "gamma@example.com"),
    )
    assert remove_response.status_code == 200
    assert remove_response.json()["active"] is False
    assert remove_response.json()["article_count"] == 0


def test_paid_member_can_clear_theme_description_via_update(client):
    article_id = _insert_article(
        title="Theme Description Reset",
        slug="theme-description-reset",
        publish_date="2026-04-13",
        excerpt="Test that a theme description can be explicitly cleared.",
        content="The article exists only to seed a theme so description updates can be validated.",
    )

    create_response = client.post(
        "/api/me/knowledge/themes",
        headers=_headers("paid-user-clear-description", "cleardesc@example.com"),
        json={
            "title": "Description Reset Theme",
            "description": "This description should be cleared later.",
            "initial_article_id": article_id,
        },
    )
    assert create_response.status_code == 200
    created = create_response.json()
    assert created["description"] == "This description should be cleared later."

    update_response = client.put(
        f"/api/me/knowledge/themes/{created['slug']}",
        headers=_headers("paid-user-clear-description", "cleardesc@example.com"),
        json={
            "title": "Description Reset Theme",
            "description": None,
        },
    )
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["description"] is None

    detail_response = client.get(
        f"/api/me/knowledge/themes/{created['slug']}",
        headers=_headers("paid-user-clear-description", "cleardesc@example.com"),
    )
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["description"] is None


def test_theme_chat_only_searches_inside_current_theme(client, monkeypatch):
    inside_article_id = _insert_article(
        title="Inside Theme Article",
        slug="inside-theme-article",
        publish_date="2026-04-12",
        excerpt="This article belongs to the user theme.",
        content="The theme article explains AI budgeting, board review, and capital allocation within the chosen topic.",
    )
    second_inside_article_id = _insert_article(
        title="Second Theme Article",
        slug="second-theme-article",
        publish_date="2026-04-10",
        excerpt="This article also belongs to the user theme.",
        content="The second theme article explains execution cadence, product packaging, and margin protection.",
    )
    outside_article_id = _insert_article(
        title="Outside Theme Article",
        slug="outside-theme-article",
        publish_date="2026-04-11",
        excerpt="This article should not be visible to the theme assistant.",
        content="This article discusses an unrelated retail pricing problem and should stay outside the theme search scope.",
    )

    create_response = client.post(
        "/api/me/knowledge/themes",
        headers=_headers("paid-user-chat", "chat@example.com"),
        json={
            "title": "AI Decision Theme",
            "initial_article_id": inside_article_id,
        },
    )
    created = create_response.json()

    add_response = client.post(
        f"/api/me/knowledge/themes/{created['id']}/articles",
        headers=_headers("paid-user-chat", "chat@example.com"),
        json={"article_id": second_inside_article_id},
    )
    assert add_response.status_code == 200

    observed_allowed_ids: list[int] = []

    def _fake_retrieve_scope_context(query, *, scope, **kwargs):
        observed_allowed_ids[:] = list(scope.article_ids or [])
        assert outside_article_id not in observed_allowed_ids
        return {
            "sources": [
                {
                    "id": second_inside_article_id,
                    "title": "Second Theme Article",
                    "publish_date": "2026-04-10",
                    "score": 9.8,
                    "excerpt": "This article also belongs to the user theme.",
                    "slug": "second-theme-article",
                    "article_type": "insight",
                    "main_topic": "Knowledge Theme",
                    "access_level": "public",
                }
            ],
            "chunk_hits": [
                {
                    "article_id": second_inside_article_id,
                    "title": "Second Theme Article",
                    "publish_date": "2026-04-10",
                    "heading": "Second Theme Article",
                    "content": "The second theme article explains execution cadence, product packaging, and margin protection.",
                    "score": 9.8,
                }
            ],
            "context_blocks": "context",
            "provider": "local_chunk",
        }

    monkeypatch.setattr(user_knowledge_service, "retrieve_scope_context", _fake_retrieve_scope_context)
    monkeypatch.setattr(ai_service, "is_ai_enabled", lambda: False)

    chat_response = client.post(
        f"/api/me/knowledge/themes/{created['slug']}/chat",
        headers=_headers("paid-user-chat", "chat@example.com"),
        json={
            "language": "en",
            "messages": [{"role": "user", "content": "Summarize only the selected article."}],
            "selected_article_ids": [second_inside_article_id],
        },
    )
    assert chat_response.status_code == 200
    payload = chat_response.json()
    assert observed_allowed_ids == [second_inside_article_id]
    assert [item["id"] for item in payload["sources"]] == [second_inside_article_id]
    assert "Outside Theme Article" not in payload["answer"]


def test_theme_chat_requires_selected_articles_when_selection_is_empty(client, monkeypatch):
    inside_article_id = _insert_article(
        title="Selected Theme Article",
        slug="selected-theme-article",
        publish_date="2026-04-09",
        excerpt="This article belongs to the selected theme.",
        content="The theme article explains customer concentration, retention mechanics, and pricing discipline.",
    )

    create_response = client.post(
        "/api/me/knowledge/themes",
        headers=_headers("paid-user-chat-two", "chat2@example.com"),
        json={
            "title": "Selected Article Theme",
            "initial_article_id": inside_article_id,
        },
    )
    created = create_response.json()

    chat_response = client.post(
        f"/api/me/knowledge/themes/{created['slug']}/chat",
        headers=_headers("paid-user-chat-two", "chat2@example.com"),
        json={
            "language": "en",
            "messages": [{"role": "user", "content": "Summarize this theme."}],
            "selected_article_ids": [],
        },
    )
    assert chat_response.status_code == 200
    payload = chat_response.json()
    assert "No article is selected" in payload["answer"]
    assert payload["sources"] == []


def test_theme_chat_history_ignores_old_assistant_answers_and_normalizes_markdown(client, monkeypatch):
    article_id = _insert_article(
        title="Markdown Scope Article",
        slug="markdown-scope-article",
        publish_date="2026-04-08",
        excerpt="This article belongs to the selected theme.",
        content="The article discusses AI productization, platform APIs, and human-AI collaboration workflows.",
    )

    create_response = client.post(
        "/api/me/knowledge/themes",
        headers=_headers("paid-user-chat-three", "chat3@example.com"),
        json={
            "title": "Markdown Repair Theme",
            "initial_article_id": article_id,
        },
    )
    created = create_response.json()

    monkeypatch.setattr(
        user_knowledge_service,
        "retrieve_scope_context",
        lambda *args, **kwargs: {
            "sources": [
                {
                    "id": article_id,
                    "title": "Markdown Scope Article",
                    "publish_date": "2026-04-08",
                    "score": 9.5,
                    "excerpt": "This article belongs to the selected theme.",
                    "slug": "markdown-scope-article",
                    "article_type": "insight",
                    "main_topic": "Knowledge Theme",
                    "access_level": "public",
                }
            ],
            "chunk_hits": [
                {
                    "article_id": article_id,
                    "title": "Markdown Scope Article",
                    "publish_date": "2026-04-08",
                    "heading": "Markdown Scope Article",
                    "content": "The article discusses AI productization, platform APIs, and human-AI collaboration workflows.",
                    "score": 9.5,
                }
            ],
            "context_blocks": "context",
            "provider": "local_chunk",
        },
    )

    captured_history = {}

    def _fake_answer(question, history, context_blocks, response_language="auto"):
        captured_history["question"] = question
        captured_history["history"] = history
        captured_history["context_blocks"] = context_blocks
        captured_history["response_language"] = response_language
        return "Broken **marker starts here, and keep ***right focus**. It may become *human-AI co-creation* over time."

    monkeypatch.setattr(ai_service, "is_ai_enabled", lambda: True)
    monkeypatch.setattr(ai_service, "answer_with_sources", _fake_answer)

    chat_response = client.post(
        f"/api/me/knowledge/themes/{created['slug']}/chat",
        headers=_headers("paid-user-chat-three", "chat3@example.com"),
        json={
            "language": "en",
            "messages": [
                {"role": "user", "content": "Please outline this theme first."},
                {"role": "assistant", "content": "An older answer mentioned another article and should not leak back in."},
                {"role": "user", "content": "Summarize only the article I just selected."},
            ],
            "selected_article_ids": [article_id],
        },
    )
    assert chat_response.status_code == 200
    payload = chat_response.json()
    assert captured_history["history"] == "user: Please outline this theme first."
    assert "older answer" not in captured_history["history"]
    assert "Broken marker starts here" in payload["answer"]
    assert "**right focus**" in payload["answer"]
    assert "**human-AI co-creation**" in payload["answer"]
    assert "***" not in payload["answer"]
    assert payload["answer"].count("**") == 4


def test_normalize_chat_answer_markdown_repairs_label_and_entity_emphasis():
    raw = (
        "1. 核心主题与关注对象\n\n"
        "- *提出一个体创造力： 研究表明，生成式AI能显著提升个体作者的创作水准。\n"
        "- 《重新定义护城河：AI变革中的于英涛与新华三》：聚焦于**新华三集团（H3C）**及其掌舵人于英涛。\n"
        "- *人机共创：* 未来的文学创作可能演变为“人机共创”。\n"
    )

    normalized = normalize_chat_answer_markdown(raw)

    assert "**提出一个体创造力：**" in normalized
    assert "**新华三集团（H3C）**" in normalized
    assert "**人机共创：**" in normalized
    assert not re.search(r"(?<!\*)\*提出一个体创造力", normalized)
    assert "于**新华三集团（H3C）** 及其" in normalized


def test_sync_article_for_rag_creates_current_version_and_chunks(client):
    article_id = _insert_article(
        title="AI Operations Ledger",
        slug="ai-operations-ledger",
        publish_date="2026-04-07",
        excerpt="Trace AI operations with budget gates and delivery checkpoints.",
        content=(
            "背景\n\n"
            "企业开始把 AI 预算、模型调用和组织流程绑到同一套经营机制里。\n\n"
            "判断\n\n"
            "第一，管理层开始用预算闸门约束 AI 试点。第二，产品团队把调用成本、迭代节奏和交付节点写入季度经营表。"
        ),
    )

    payload = sync_article_for_rag(article_id, trigger_source="test_case")
    version = get_current_version(article_id)

    assert payload["version"]["status"] == "ready"
    assert payload["version"]["chunk_count"] >= 2
    assert version is not None
    assert version["status"] == "ready"

    with connection_scope() as connection:
        rows = connection.execute(
            "SELECT heading, content FROM article_chunks WHERE article_id = ? ORDER BY chunk_index ASC",
            (article_id,),
        ).fetchall()
    assert len(rows) >= 2
    assert any("背景" in str(row["heading"] or "") for row in rows)


def test_bookmark_sync_writes_formal_saved_relationship_and_library_profile(client):
    article_id = _insert_article(
        title="Capital Allocation Notes",
        slug="capital-allocation-notes",
        publish_date="2026-04-06",
        excerpt="Track capital allocation with tighter operating discipline.",
        content="The article explains capital pacing, operating leverage, and how management teams sequence investment decisions.",
    )

    set_article_reaction(article_id, "paid-user-library", "bookmark", True)

    with connection_scope() as connection:
        saved_row = connection.execute(
            "SELECT is_active FROM user_saved_articles WHERE user_id = ? AND article_id = ?",
            ("paid-user-library", article_id),
        ).fetchone()
        profile_row = connection.execute(
            "SELECT saved_count, summary_text FROM user_library_profiles WHERE user_id = ?",
            ("paid-user-library",),
        ).fetchone()

    assert saved_row is not None
    assert int(saved_row["is_active"]) == 1
    assert profile_row is not None
    assert int(profile_row["saved_count"]) == 1
    assert "已收藏 1 篇文章" in str(profile_row["summary_text"] or "")


def test_retrieve_scope_context_supports_my_library_scope(client):
    inside_article_id = _insert_article(
        title="Library Scope Article",
        slug="library-scope-article",
        publish_date="2026-04-05",
        excerpt="This article should stay inside the user's library scope.",
        content="The library article covers pricing discipline, margin defense, and management cadence in a volatile market.",
    )
    outside_article_id = _insert_article(
        title="Outside Library Scope",
        slug="outside-library-scope",
        publish_date="2026-04-04",
        excerpt="This article should not appear in the user's library scope.",
        content="The outside article discusses a different talent-management problem and should not show up for pricing queries.",
    )

    set_article_reaction(inside_article_id, "paid-user-library-scope", "bookmark", True)
    sync_article_for_rag(inside_article_id, trigger_source="test_case")
    sync_article_for_rag(outside_article_id, trigger_source="test_case")

    payload = retrieve_scope_context(
        "pricing discipline",
        scope=RetrievalScope(scope_type="my_library", user_id="paid-user-library-scope"),
        page_size=5,
        language="en",
    )

    assert payload["selected_article_ids"] == [inside_article_id]
    assert [item["id"] for item in payload["sources"]] == [inside_article_id]
    assert all(int(item["article_id"]) == inside_article_id for item in payload["chunk_hits"])


def test_my_library_chat_uses_only_saved_articles(client, monkeypatch):
    inside_article_id = _insert_article(
        title="Saved Library Brief",
        slug="saved-library-brief",
        publish_date="2026-04-03",
        excerpt="This article belongs to the saved library scope.",
        content="The saved article covers AI pricing discipline, cost control, and management review cadence.",
    )
    outside_article_id = _insert_article(
        title="Unsaved Library Brief",
        slug="unsaved-library-brief",
        publish_date="2026-04-02",
        excerpt="This article should stay outside the saved library scope.",
        content="The unsaved article covers a different HR topic and should not appear in library answers.",
    )

    set_article_reaction(inside_article_id, "paid-user-library-chat", "bookmark", True)
    sync_article_for_rag(inside_article_id, trigger_source="test_case")
    sync_article_for_rag(outside_article_id, trigger_source="test_case")
    monkeypatch.setattr(ai_service, "is_ai_enabled", lambda: False)

    response = client.post(
        "/api/me/library/chat",
        headers=_headers("paid-user-library-chat", "library-chat@example.com"),
        json={
            "language": "en",
            "messages": [{"role": "user", "content": "Summarize my saved library."}],
            "selected_article_ids": [inside_article_id],
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert [item["id"] for item in payload["sources"]] == [inside_article_id]
    assert "Unsaved Library Brief" not in payload["answer"]


def test_public_search_returns_chunk_ranked_results(client):
    strong_article_id = _insert_article(
        title="Pricing Discipline Memo",
        slug="pricing-discipline-memo",
        publish_date="2026-04-01",
        excerpt="Discuss pricing discipline and margin defense.",
        content="This memo focuses on pricing discipline, margin defense, and how management teams protect contribution profit.",
    )
    weak_article_id = _insert_article(
        title="Talent Retention Memo",
        slug="talent-retention-memo",
        publish_date="2026-03-31",
        excerpt="Discuss talent retention and organization design.",
        content="This memo focuses on talent retention, manager coaching, and organization design.",
    )

    sync_article_for_rag(strong_article_id, trigger_source="test_case")
    sync_article_for_rag(weak_article_id, trigger_source="test_case")

    payload = rag_engine.search_articles("pricing discipline", language="en", page=1, page_size=5)

    assert payload["items"]
    assert payload["items"][0]["id"] == strong_article_id
    assert all(item["id"] != weak_article_id or item["score"] <= payload["items"][0]["score"] for item in payload["items"])


def test_public_chat_uses_chunk_context_for_new_article(client, monkeypatch):
    article_id = _insert_article(
        title="GPU Depreciation Waterfall",
        slug="gpu-depreciation-waterfall",
        publish_date="2026-04-16",
        excerpt="Track how GPU depreciation assumptions affect AI value capture.",
        content=(
            "This article explains how GPU depreciation schedules, AI infrastructure utilization, "
            "and value waterfall assumptions reshape cloud margins and capital allocation."
        ),
    )
    sync_article_for_rag(article_id, trigger_source="test_public_chat", force=True)

    captured: dict[str, str] = {}

    monkeypatch.setattr(ai_service, "is_ai_enabled", lambda: True)

    def _fake_answer_with_sources(question, history, context_blocks, response_language="auto"):
        captured["question"] = question
        captured["context_blocks"] = context_blocks
        captured["response_language"] = response_language
        return context_blocks

    monkeypatch.setattr(ai_service, "answer_with_sources", _fake_answer_with_sources)

    response = client.post(
        "/api/chat",
        json={
            "language": "en",
            "messages": [{"role": "user", "content": "Show me the recent GPU article."}],
        },
    )
    assert response.status_code == 200
    payload = response.json()

    assert payload["sources"]
    assert payload["sources"][0]["id"] == article_id
    assert "Chunk:" in captured["context_blocks"]
    assert "GPU depreciation schedules" in captured["context_blocks"]


def test_public_chat_brief_command_uses_chunk_context(client, monkeypatch):
    article_id = _insert_article(
        title="GPU Asset Strategy Memo",
        slug="gpu-asset-strategy-memo",
        publish_date="2026-04-16",
        excerpt="A memo on GPU asset planning and AI capital discipline.",
        content=(
            "The memo covers GPU asset planning, depreciation resets, chip refresh timing, "
            "and how CFO teams defend AI investment returns."
        ),
    )
    sync_article_for_rag(article_id, trigger_source="test_public_brief", force=True)

    captured: dict[str, str] = {}

    monkeypatch.setattr(ai_service, "is_ai_enabled", lambda: True)

    def _fake_answer_with_sources(question, history, context_blocks, response_language="auto"):
        captured["question"] = question
        captured["context_blocks"] = context_blocks
        return "ok"

    monkeypatch.setattr(ai_service, "answer_with_sources", _fake_answer_with_sources)

    response = client.post(
        "/api/chat",
        json={
            "language": "en",
            "messages": [{"role": "user", "content": "/brief GPU asset strategy"}],
        },
    )
    assert response.status_code == 200
    payload = response.json()

    assert payload["sources"]
    assert payload["sources"][0]["id"] == article_id
    assert "Chunk:" in captured["context_blocks"]
    assert "GPU asset planning" in captured["context_blocks"]


def test_sync_public_articles_for_rag_backfills_public_articles_only(client):
    public_article_id = _insert_article(
        title="Public Backfill Article",
        slug="public-backfill-article",
        publish_date="2026-03-30",
        excerpt="This public article should be backfilled.",
        content="The public article discusses operating cadence, pricing control, and execution discipline.",
    )
    paid_article_id = _insert_article(
        title="Paid Backfill Article",
        slug="paid-backfill-article",
        publish_date="2026-03-29",
        excerpt="This paid article should stay outside the default public backfill.",
        content="The paid article discusses a premium topic outside the default public backfill run.",
    )
    with connection_scope() as connection:
        connection.execute("UPDATE articles SET access_level = 'paid' WHERE id = ?", (paid_article_id,))
        connection.commit()

    results = sync_public_articles_for_rag(limit=10)
    processed_ids = {int((item.get("version") or {}).get("article_id") or 0) for item in results}

    assert public_article_id in processed_ids
    assert paid_article_id not in processed_ids
    assert get_current_version(public_article_id)["status"] == "ready"
    assert get_current_version(paid_article_id) is None


def test_process_pending_ingestion_jobs_consumes_queued_jobs(client):
    article_id = _insert_article(
        title="Queued Ingestion Article",
        slug="queued-ingestion-article",
        publish_date="2026-03-28",
        excerpt="This article should be processed by the pending-job runner.",
        content="The queued article describes sequencing, review loops, and how product teams handle new operating constraints.",
    )

    queued = queue_article_ingestion(article_id, trigger_source="test_pending_queue")
    assert queued["job"]["status"] == "pending"

    processed = process_pending_ingestion_jobs(limit=5)

    assert processed
    assert any(int((item["version"] or {}).get("article_id") or 0) == article_id for item in processed)
    assert get_current_version(article_id)["status"] == "ready"


def test_embed_chunk_texts_rotates_to_next_key_after_failure(client, monkeypatch):
    calls: list[str] = []

    class _FakeClient:
        def __init__(self, api_key: str):
            self.api_key = api_key

        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            calls.append(self.api_key)
            if self.api_key == "key-one":
                raise RuntimeError("temporary embedding failure")
            return [[0.3, 0.7] for _ in texts]

    monkeypatch.setattr(knowledge_embedding_service, "is_chunk_embedding_enabled", lambda: True)
    monkeypatch.setattr(knowledge_embedding_service, "get_embedding_api_keys", lambda: ("key-one", "key-two"))
    monkeypatch.setattr(
        knowledge_embedding_service,
        "_embedding_client",
        lambda api_key, task_type: _FakeClient(api_key),
    )

    payload = knowledge_embedding_service.embed_chunk_texts(["alpha", "beta"])

    assert payload == [[0.3, 0.7], [0.3, 0.7]]
    assert calls[:2] == ["key-one", "key-two"]


def test_sync_public_articles_for_rag_continue_on_error_keeps_processing(client, monkeypatch):
    first_article_id = _insert_article(
        title="Backfill Continue One",
        slug="backfill-continue-one",
        publish_date="2027-01-02",
        excerpt="This article will simulate a temporary failure.",
        content="The first article exists to simulate a temporary backfill failure.",
    )
    second_article_id = _insert_article(
        title="Backfill Continue Two",
        slug="backfill-continue-two",
        publish_date="2027-01-03",
        excerpt="This article should still be processed.",
        content="The second article exists to prove the batch keeps moving after one failure.",
    )

    def _fake_sync(article_id: int, *, trigger_source: str = "scope_sync", force: bool = False):
        assert trigger_source == "public_backfill"
        assert force is False
        if article_id == first_article_id:
            raise RuntimeError("temporary network failure")
        return {
            "job": {"status": "completed"},
            "version": {"article_id": article_id, "status": "ready"},
        }

    monkeypatch.setattr(knowledge_ingestion_service, "sync_article_for_rag", _fake_sync)

    results = sync_public_articles_for_rag(limit=2, workers=2, continue_on_error=True)

    assert len(results) == 2
    error_result = next(item for item in results if item.get("article_id") == first_article_id)
    success_result = next(item for item in results if (item.get("version") or {}).get("article_id") == second_article_id)
    assert "temporary network failure" in str(error_result.get("error") or "")
    assert success_result["job"]["status"] == "completed"


def test_chunk_embeddings_are_persisted_and_used_in_retrieval(client, monkeypatch):
    article_id = _insert_article(
        title="Semantic Retrieval Article",
        slug="semantic-retrieval-article",
        publish_date="2026-03-27",
        excerpt="This article should win by semantic similarity.",
        content="The piece explains strategy maps, operating cadence, and board-level decision loops for AI transformation.",
    )

    monkeypatch.setattr(knowledge_embedding_service, "is_chunk_embedding_enabled", lambda: True)
    monkeypatch.setattr(knowledge_ingestion_service, "is_chunk_embedding_enabled", lambda: True)
    monkeypatch.setattr(knowledge_retrieval_service, "is_chunk_embedding_enabled", lambda: True)
    monkeypatch.setattr(
        knowledge_ingestion_service,
        "embed_chunk_texts",
        lambda texts: [[0.9, 0.1] for _ in texts],
    )
    monkeypatch.setattr(
        knowledge_retrieval_service,
        "embed_query_text",
        lambda text: [0.9, 0.1],
    )

    payload = sync_article_for_rag(article_id, trigger_source="test_embeddings", force=True)
    assert payload["version"]["status"] == "ready"

    with connection_scope() as connection:
        embedding_rows = connection.execute(
            "SELECT dimensions, embedding_json FROM article_chunk_embeddings WHERE article_id = ?",
            (article_id,),
        ).fetchall()
    assert embedding_rows
    assert int(embedding_rows[0]["dimensions"]) == 2
    assert "[0.9, 0.1]" in str(embedding_rows[0]["embedding_json"])

    retrieval = retrieve_scope_context(
        "board decision loops",
        scope=RetrievalScope(scope_type="selected_articles", article_ids=[article_id]),
        page_size=5,
        language="en",
    )
    assert retrieval["sources"]
    assert retrieval["sources"][0]["id"] == article_id
    assert retrieval["chunk_hits"][0]["vector_score"] > 0


def test_embed_chunk_texts_rotates_keys_after_retry(monkeypatch):
    calls: list[str] = []

    class _FakeClient:
        def __init__(self, api_key: str):
            self.api_key = api_key

        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            calls.append(self.api_key)
            if self.api_key == "key-one":
                raise RuntimeError("temporary upstream failure")
            return [[0.2, 0.8] for _ in texts]

    monkeypatch.setattr(knowledge_embedding_service, "is_chunk_embedding_enabled", lambda: True)
    monkeypatch.setattr(knowledge_embedding_service, "get_embedding_api_keys", lambda: ("key-one", "key-two"))
    monkeypatch.setattr(
        knowledge_embedding_service,
        "_embedding_client",
        lambda api_key, task_type: _FakeClient(api_key),
    )

    embeddings = knowledge_embedding_service.embed_chunk_texts(["alpha", "beta"])

    assert calls[:2] == ["key-one", "key-two"]
    assert embeddings == [[0.2, 0.8], [0.2, 0.8]]


def test_sync_public_articles_for_rag_continue_on_error_keeps_processing(client, monkeypatch):
    first_article_id = _insert_article(
        title="Backfill Failure Article",
        slug="backfill-failure-article",
        publish_date="2027-01-02",
        excerpt="This article will simulate a transient failure during backfill.",
        content="The article exists to verify that one failure does not stop the batch backfill runner.",
    )
    second_article_id = _insert_article(
        title="Backfill Success Article",
        slug="backfill-success-article",
        publish_date="2027-01-01",
        excerpt="This article should still complete during the same backfill batch.",
        content="The article exists to verify that the batch keeps running after one failure.",
    )

    def _fake_sync(article_id: int, *, trigger_source: str = "scope_sync", force: bool = False):
        del trigger_source
        del force
        if article_id == first_article_id:
            raise RuntimeError("transient embedding error")
        return {
            "job": {"status": "completed"},
            "version": {"article_id": article_id, "status": "ready"},
        }

    monkeypatch.setattr(knowledge_ingestion_service, "sync_article_for_rag", _fake_sync)

    results = sync_public_articles_for_rag(limit=2, workers=2, continue_on_error=True)

    assert len(results) == 2
    assert any(item.get("article_id") == first_article_id and item.get("error") for item in results)
    assert any((item.get("version") or {}).get("article_id") == second_article_id for item in results)
