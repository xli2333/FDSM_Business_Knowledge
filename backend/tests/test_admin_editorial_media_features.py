from __future__ import annotations

import atexit
import json
import os
import shutil
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

TEST_DATA_DIR = Path(tempfile.mkdtemp(prefix="fdsm_test_db_"))
SOURCE_DB_PATH = Path(__file__).resolve().parents[2] / "fudan_knowledge_base.db"

if SOURCE_DB_PATH.exists():
    shutil.copy2(SOURCE_DB_PATH, TEST_DATA_DIR / "fudan_knowledge_base.db")

os.environ["FDSM_DATA_DIR"] = str(TEST_DATA_DIR)
atexit.register(lambda: shutil.rmtree(TEST_DATA_DIR, ignore_errors=True))

from backend.database import connection_scope
from backend.main import app
from backend.routers import admin as admin_router
from backend.routers import editorial as editorial_router
from backend.routers import media as media_router
from backend.services import ai_service, editorial_service, knowledge_ingestion_service, media_service

client = TestClient(app)


def _mock_preview_html(title: str) -> str:
    return (
        '<!doctype html><html><body>'
        f'<div class="wechat-preview-shell" data-wechat-decoration="1"><article>{title}</article></div>'
        '</body></html>'
    )


def _mock_renderer(title_prefix: str = 'Rendered'):
    def _render(item, *, timeout_seconds=60.0):
        del timeout_seconds
        title = item.get('title') or title_prefix
        return {
            'previewHtml': _mock_preview_html(title),
            'contentHtml': _mock_preview_html(title),
            'renderPlan': {'layout': 'mocked'},
            'metadata': {'engine': 'test'},
            'warnings': [],
        }

    return _render


def _allow_admin_access(monkeypatch):
    admin_user = {"id": "admin-test", "email": "admin@example.com"}
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
        media_router,
        "get_authenticated_user",
        lambda authorization, debug_user_id=None, debug_user_email=None: admin_user,
    )
    monkeypatch.setattr(media_router, "require_admin_profile", lambda user: {"is_admin": True})
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
        ai_service,
        "translate_editorial_assets_to_english",
        lambda title, excerpt, summary_markdown, content_markdown: {
            "title": f"{title} EN",
            "excerpt": excerpt or "English deck",
            "summary": summary_markdown or "English summary",
            "content": content_markdown or "English content",
            "model": "gemini-3-flash-preview",
        },
    )


def test_wechat_bridge_uses_bundled_runtime_only():
    project_root = Path(__file__).resolve().parents[2]
    bridge_path = project_root / 'backend' / 'scripts' / 'wechat_fudan_bridge.mjs'
    runtime_service_path = project_root / 'backend' / 'wechat_runtime' / 'wechatOfficialPublisherService.mjs'
    runtime_package_path = project_root / 'backend' / 'wechat_runtime' / 'package.json'

    bridge_source = bridge_path.read_text(encoding='utf-8')

    assert 'wechat_runtime' in bridge_source
    assert 'AI_writer' not in bridge_source
    assert '公众号排版' not in bridge_source
    assert runtime_service_path.exists()
    assert runtime_package_path.exists()


def test_editorial_admin_routes_require_login():
    response = client.post(
        "/api/editorial/articles",
        json={"title": "Test", "source_markdown": "raw", "content_markdown": "raw"},
    )
    assert response.status_code == 401


def test_media_admin_upload_requires_login():
    response = client.post(
        "/api/media/admin/upload",
        data={"kind": "audio", "usage": "media"},
        files={"file": ("sample.mp3", b"ID3test", "audio/mpeg")},
    )
    assert response.status_code == 401


def test_admin_can_auto_format_editorial_article(monkeypatch):
    _allow_admin_access(monkeypatch)
    monkeypatch.setattr(
        ai_service,
        "auto_format_editorial_markdown",
        lambda **kwargs: {
            "markdown": "# Auto Format Draft\n\n## Key Points\n\n- Keep structure\n- Keep readability",
            "model": "gemini-3-flash-preview",
        },
    )

    create_response = client.post(
        "/api/editorial/articles",
        json={
            "title": "Auto Format Draft",
            "source_markdown": "raw paragraph one\n\nraw paragraph two",
            "content_markdown": "raw paragraph one\n\nraw paragraph two",
            "layout_mode": "auto",
        },
    )
    assert create_response.status_code == 200
    editorial_id = create_response.json()["id"]

    format_response = client.post(
        f"/api/editorial/articles/{editorial_id}/auto-format",
        json={
            "source_markdown": "raw paragraph one\n\nraw paragraph two",
            "layout_mode": "briefing",
            "formatting_notes": "keep bullet list",
        },
    )
    assert format_response.status_code == 200
    payload = format_response.json()

    assert payload["formatter_model"] == "gemini-3-flash-preview"
    assert payload["layout_mode"] == "briefing"
    assert payload["formatting_notes"] == "keep bullet list"
    assert payload["content_markdown"].startswith("# Auto Format Draft")
    assert payload["source_markdown"] == "raw paragraph one\n\nraw paragraph two"
    assert 'wechat-preview-shell' in payload['final_html']
    assert payload['render_metadata']['render_plan']


def test_admin_can_translate_editorial_assets_and_publish_into_english_chain(monkeypatch):
    _allow_admin_access(monkeypatch)
    monkeypatch.setattr(editorial_service, 'render_fudan_wechat', _mock_renderer('English Layout'))

    create_response = client.post(
        "/api/editorial/articles",
        json={
            "title": "GPU Finance Draft",
            "source_markdown": "算力账本段落一\n\n算力账本段落二",
            "content_markdown": "# GPU Finance Draft\n\n## Key Point\n\n- GPU 资产折旧正在重估。",
            "summary_markdown": "算力资产折旧周期正在改写 AI 云基础设施的财务判断。",
            "summary_html": "<div><p>算力资产折旧周期正在改写 AI 云基础设施的财务判断。</p></div>",
            "final_html": "<div><h1>GPU Finance Draft</h1><p>GPU 资产折旧正在重估。</p></div>",
            "primary_column_slug": "insights",
            "primary_column_manual": True,
            "tags": [{"name": "GPU", "slug": "topic-gpu", "category": "topic", "confidence": 0.92}],
        },
    )
    assert create_response.status_code == 200
    editorial_id = create_response.json()["id"]

    translate_response = client.post(f"/api/editorial/articles/{editorial_id}/auto-translate")
    assert translate_response.status_code == 200
    translated = translate_response.json()

    assert translated["translation_ready"] is True
    assert translated["translation_status"] == "completed"
    assert translated["translation_title_en"].endswith(" EN")
    assert translated["translation_content_en"]
    assert translated["html_web_en"]

    publish_response = client.post(f"/api/editorial/articles/{editorial_id}/publish")
    assert publish_response.status_code == 200
    article_id = publish_response.json()["article_id"]

    with connection_scope() as connection:
        translation_row = connection.execute(
            """
            SELECT title, summary, content, model
            FROM article_translations
            WHERE article_id = ? AND target_lang = 'en'
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (article_id,),
        ).fetchone()
        ai_row = connection.execute(
            """
            SELECT translation_status, translation_title_en, translation_summary_en, translation_content_en, html_web_en
            FROM article_ai_outputs
            WHERE article_id = ?
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (article_id,),
        ).fetchone()

    assert translation_row is not None
    assert translation_row["title"].endswith(" EN")
    assert translation_row["content"]
    assert ai_row is not None
    assert ai_row["translation_status"] == "completed"
    assert ai_row["translation_title_en"].endswith(" EN")
    assert ai_row["translation_summary_en"]
    assert ai_row["translation_content_en"]
    assert ai_row["html_web_en"]


def test_publish_auto_generates_editorial_translation_and_exposes_english_article(monkeypatch):
    _allow_admin_access(monkeypatch)
    monkeypatch.setattr(editorial_service, 'render_fudan_wechat', _mock_renderer('English Layout'))

    create_response = client.post(
        "/api/editorial/articles",
        json={
            "title": "GPU Auto Translation Draft",
            "source_markdown": "算力财务叙事原稿",
            "content_markdown": "# GPU Auto Translation Draft\n\n英文链路需要自动接入。",
            "summary_markdown": "这篇文章讨论 GPU 折旧年限变化。",
            "summary_html": "<div><p>这篇文章讨论 GPU 折旧年限变化。</p></div>",
            "final_html": "<div><h1>GPU Auto Translation Draft</h1><p>英文链路需要自动接入。</p></div>",
            "primary_column_slug": "insights",
            "primary_column_manual": True,
            "tags": [{"name": "GPU", "slug": "topic-gpu-auto", "category": "topic", "confidence": 0.9}],
        },
    )
    assert create_response.status_code == 200
    editorial_id = create_response.json()["id"]
    assert create_response.json()["translation_ready"] is False

    publish_response = client.post(f"/api/editorial/articles/{editorial_id}/publish")
    assert publish_response.status_code == 200
    article_id = publish_response.json()["article_id"]

    detail_response = client.get(f"/api/editorial/articles/{editorial_id}")
    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload["translation_ready"] is True
    assert detail_payload["translation_status"] == "completed"
    assert detail_payload["translation_title_en"].endswith(" EN")
    assert detail_payload["published_final_html_en"]

    translation_response = client.get(f"/api/article/{article_id}/translation?lang=en")
    assert translation_response.status_code == 200
    translation_payload = translation_response.json()
    assert translation_payload["title"].endswith(" EN")
    assert translation_payload["summary"]
    assert translation_payload["content"]
    assert translation_payload["html_web"]


def test_regenerating_chinese_summary_clears_stale_editorial_translation(monkeypatch):
    _allow_admin_access(monkeypatch)
    monkeypatch.setattr(editorial_service, 'render_fudan_wechat', _mock_renderer('English Layout'))
    monkeypatch.setattr(
        ai_service,
        "summarize_article_payload",
        lambda title, content: {
            "summary": "更新后的中文摘要：GPU 折旧正在改变算力财务叙事。",
            "model": "gemini-3-flash-preview",
        },
    )

    create_response = client.post(
        "/api/editorial/articles",
        json={
            "title": "Stale Translation Draft",
            "source_markdown": "中文原稿一\n\n中文原稿二",
            "content_markdown": "# Stale Translation Draft\n\n正文",
            "summary_markdown": "旧中文摘要",
            "summary_html": "<div><p>旧中文摘要</p></div>",
            "final_html": "<div><h1>Stale Translation Draft</h1><p>正文</p></div>",
        },
    )
    assert create_response.status_code == 200
    editorial_id = create_response.json()["id"]

    translate_response = client.post(f"/api/editorial/articles/{editorial_id}/auto-translate")
    assert translate_response.status_code == 200
    assert translate_response.json()["translation_ready"] is True

    summary_response = client.post(f"/api/editorial/articles/{editorial_id}/auto-summary")
    assert summary_response.status_code == 200
    payload = summary_response.json()

    assert "更新后的中文摘要" in payload["summary_markdown"]
    assert payload["translation_ready"] is False
    assert payload["translation_status"] == "pending"
    assert payload["translation_content_en"] is None


def test_admin_can_upload_media_files(monkeypatch):
    _allow_admin_access(monkeypatch)
    upload_root = Path("backend/tests/_tmp_media_uploads").resolve()
    if upload_root.exists():
        for path in sorted(upload_root.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
    upload_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(media_service, "MEDIA_UPLOADS_DIR", upload_root)

    response = client.post(
        "/api/media/admin/upload",
        data={"kind": "audio", "usage": "media"},
        files={"file": ("sample.mp3", b"ID3test", "audio/mpeg")},
    )
    assert response.status_code == 200
    payload = response.json()

    assert payload["kind"] == "audio"
    assert payload["usage"] == "media"
    assert payload["url"].startswith("/media-uploads/audio/media/")
    assert (upload_root / "audio" / "media" / payload["filename"]).exists()


def _prepare_editorial_upload_root(monkeypatch):
    upload_root = Path("backend/tests/_tmp_editorial_uploads").resolve()
    if upload_root.exists():
        for path in sorted(upload_root.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
    upload_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(editorial_service, "EDITORIAL_UPLOADS_DIR", upload_root)
    return upload_root


def test_admin_can_upload_editorial_cover_and_publish_to_article_cover(monkeypatch):
    _allow_admin_access(monkeypatch)
    upload_root = _prepare_editorial_upload_root(monkeypatch)

    create_response = client.post(
        "/api/editorial/articles",
        json={
            "title": "Editorial Cover Draft",
            "source_markdown": "first paragraph\n\nsecond paragraph",
            "content_markdown": "first paragraph\n\nsecond paragraph",
            "primary_column_slug": "insights",
            "primary_column_manual": True,
            "tags": [{"name": "数据治理", "slug": "topic-data-governance", "category": "topic", "confidence": 0.92}],
            "final_html": "<div><h1>Editorial Cover Draft</h1><p>Ready.</p></div>",
        },
    )
    assert create_response.status_code == 200
    editorial_id = create_response.json()["id"]

    upload_response = client.post(
        "/api/editorial/upload",
        data={"usage": "cover", "editorial_id": str(editorial_id)},
        files={"file": ("editorial-cover.png", b"\x89PNG\r\n\x1a\ncover", "image/png")},
    )
    assert upload_response.status_code == 200
    payload = upload_response.json()

    assert payload["usage"] == "cover"
    assert payload["url"].startswith("/editorial-uploads/covers/")
    assert payload["article"]["cover_image_url"] == payload["url"]
    assert (upload_root / "covers" / payload["filename"]).exists()

    publish_response = client.post(f"/api/editorial/articles/{editorial_id}/publish")
    assert publish_response.status_code == 200
    article_id = publish_response.json()["article_id"]

    latest_response = client.get("/api/articles/latest?limit=20")
    assert latest_response.status_code == 200
    cards = latest_response.json()
    card = next(item for item in cards if item["id"] == article_id)
    assert card["cover_url"] == f"/api/article/{article_id}/cover"

    cover_response = client.get(f"/api/article/{article_id}/cover", follow_redirects=False)
    assert cover_response.status_code in {302, 307}
    assert cover_response.headers["location"] == payload["url"]


def test_autotag_keeps_admin_removed_tags_removed(monkeypatch):
    _allow_admin_access(monkeypatch)
    monkeypatch.setattr(
        ai_service,
        'suggest_editorial_metadata',
        lambda title, content: {
            'excerpt': 'AI summary',
            'article_type': 'insight',
            'main_topic': 'Topic Governance',
            'column_slug': 'industry',
            'tags': [
                {'name': 'Topic Governance', 'category': 'topic', 'confidence': 0.91},
                {'name': 'Market Signals', 'category': 'topic', 'confidence': 0.83},
            ],
        },
    )

    create_response = client.post(
        '/api/editorial/articles',
        json={
            'title': 'Tag Review Draft',
            'source_markdown': 'first paragraph\n\nsecond paragraph',
            'content_markdown': 'first paragraph\n\nsecond paragraph',
        },
    )
    assert create_response.status_code == 200
    editorial_id = create_response.json()['id']

    autotag_response = client.post(f'/api/editorial/articles/{editorial_id}/autotag')
    assert autotag_response.status_code == 200
    tagged = autotag_response.json()
    assert tagged['primary_column_slug'] == 'industry'
    assert tagged['primary_column_ai_slug'] == 'industry'
    assert {item['name'] for item in tagged['tags']} >= {'Topic Governance', 'Market Signals'}

    retained_tags = [item for item in tagged['tags'] if item['name'] != 'Market Signals']
    update_response = client.put(
        f'/api/editorial/articles/{editorial_id}',
        json={'tags': retained_tags},
    )
    assert update_response.status_code == 200

    autotag_again = client.post(f'/api/editorial/articles/{editorial_id}/autotag')
    assert autotag_again.status_code == 200
    payload = autotag_again.json()

    assert 'Market Signals' not in {item['name'] for item in payload['tags']}
    assert 'Market Signals' in {item['name'] for item in payload['removed_tags']}


def test_suggest_editorial_metadata_uses_json_http_path(monkeypatch):
    monkeypatch.setattr(
        ai_service,
        '_request_gemini_text',
        lambda **kwargs: json.dumps(
            {
                'excerpt': '23andMe 数据泄露冲击了用户对基因检测平台的信任，也暴露了数据治理与隐私保护缺口。',
                'article_type': '行业分析',
                'main_topic': '数据安全',
                'column_slug': 'industry',
                'tags': [
                    {'name': '23andMe', 'category': 'entity', 'confidence': 0.99},
                    {'name': '基因检测', 'category': 'industry', 'confidence': 0.95},
                    {'name': '数据泄露', 'category': 'topic', 'confidence': 0.93},
                ],
            },
            ensure_ascii=False,
        ),
    )

    payload = ai_service.suggest_editorial_metadata(
        '23andMe 数据治理危机与 1500 万人基因隐私的命运',
        '23andMe 遭遇数据泄露，暴露出数据治理和隐私保护问题。',
    )

    assert payload['main_topic'] == '数据安全'
    assert payload['column_slug'] == 'industry'
    assert {item['name'] for item in payload['tags']} == {'23andMe', '基因检测', '数据泄露'}


def test_autotag_filters_low_signal_ai_tags(monkeypatch):
    _allow_admin_access(monkeypatch)
    monkeypatch.setattr(
        ai_service,
        'suggest_editorial_metadata',
        lambda title, content: {
            'excerpt': 'AI summary',
            'article_type': '行业分析',
            'main_topic': '数据安全',
            'column_slug': 'industry',
            'tags': [
                {'name': 'L', 'category': 'entity', 'confidence': 0.91},
                {'name': '23andMe', 'category': 'entity', 'confidence': 0.99},
                {'name': '数据泄露', 'category': 'topic', 'confidence': 0.95},
            ],
        },
    )

    create_response = client.post(
        '/api/editorial/articles',
        json={
            'title': '23andMe 数据治理危机',
            'source_markdown': '23andMe 遭遇数据泄露。',
            'content_markdown': '23andMe 遭遇数据泄露。',
        },
    )
    assert create_response.status_code == 200
    editorial_id = create_response.json()['id']

    autotag_response = client.post(f'/api/editorial/articles/{editorial_id}/autotag')
    assert autotag_response.status_code == 200
    payload = autotag_response.json()

    tag_names = {item['name'] for item in payload['tags']}
    assert 'L' not in tag_names
    assert '23andMe' in tag_names
    assert '数据泄露' in tag_names


def test_autotag_fallback_extracts_strong_tags_for_23andme_case(monkeypatch):
    _allow_admin_access(monkeypatch)
    monkeypatch.setattr(ai_service, 'suggest_editorial_metadata', lambda title, content: {})

    article_text = """
23andMe 数据治理危机与 1500 万人基因隐私的命运

2023年10月1日，一个自称“Golem”的匿名黑客在地下网络犯罪论坛Breach Forums上发布了一则帖子。
这些数据出自消费级基因检测公司23andMe。事件暴露了基因隐私、数据治理、数据泄露和网络安全问题。
公司还收购了 Lemonaid Health，并与葛兰素史克（GSK）合作药物研发。
2025年6月，加拿大隐私专员办公室（OPC）和英国信息专员办公室（ICO）指出其违反了英国《通用数据保护条例》（GDPR）的数据安全原则。
""".strip()

    create_response = client.post(
        '/api/editorial/articles',
        json={
            'title': '23andMe 数据治理危机与 1500 万人基因隐私的命运',
            'source_markdown': article_text,
            'content_markdown': article_text,
        },
    )
    assert create_response.status_code == 200
    editorial_id = create_response.json()['id']

    autotag_response = client.post(f'/api/editorial/articles/{editorial_id}/autotag')
    assert autotag_response.status_code == 200
    payload = autotag_response.json()

    tag_names = {item['name'] for item in payload['tags']}
    assert '23andMe' in tag_names
    assert tag_names & {'数据治理', '数据安全', '数据泄露', '隐私保护'}
    assert tag_names & {'基因检测', '生物科技', '医疗健康'}
    assert 'Fudan Business Knowledge' not in tag_names


def test_publish_requires_final_html(monkeypatch):
    _allow_admin_access(monkeypatch)

    create_response = client.post(
        '/api/editorial/articles',
        json={
            'title': 'Publish Validation Draft',
            'source_markdown': 'first paragraph\n\nsecond paragraph',
            'content_markdown': 'first paragraph\n\nsecond paragraph',
            'primary_column_slug': 'insights',
            'primary_column_manual': True,
            'tags': [{'name': 'Topic Governance', 'slug': 'topic-governance', 'category': 'topic', 'confidence': 0.92}],
        },
    )
    assert create_response.status_code == 200
    editorial_id = create_response.json()['id']

    publish_response = client.post(f'/api/editorial/articles/{editorial_id}/publish')
    assert publish_response.status_code == 400
    assert 'HTML' in publish_response.json()['detail']


def test_saving_same_render_sensitive_values_keeps_final_html_publishable(monkeypatch):
    _allow_admin_access(monkeypatch)

    create_response = client.post(
        '/api/editorial/articles',
        json={
            'title': 'Stable Publish Draft',
            'author': 'Alice',
            'organization': 'FBK',
            'source_markdown': 'first paragraph\n\nsecond paragraph',
            'content_markdown': 'first paragraph\n\nsecond paragraph',
            'primary_column_slug': 'insights',
            'primary_column_manual': True,
            'tags': [{'name': '数据安全', 'slug': 'topic-data-security', 'category': 'topic', 'confidence': 0.92}],
            'final_html': '<div><h1>Stable Publish Draft</h1><p>Ready to publish.</p></div>',
        },
    )
    assert create_response.status_code == 200
    editorial_id = create_response.json()['id']

    update_response = client.put(
        f'/api/editorial/articles/{editorial_id}',
        json={
            'title': 'Stable Publish Draft',
            'author': 'Alice',
            'organization': 'FBK',
            'source_markdown': 'first paragraph\n\nsecond paragraph',
            'content_markdown': 'first paragraph\n\nsecond paragraph',
            'primary_column_slug': 'insights',
            'primary_column_manual': True,
            'tags': [{'name': '数据安全', 'slug': 'topic-data-security', 'category': 'topic', 'confidence': 0.92}],
        },
    )
    assert update_response.status_code == 200
    updated = update_response.json()

    assert updated['final_html'] == '<div><h1>Stable Publish Draft</h1><p>Ready to publish.</p></div>'
    assert updated['publish_validation'] == []

    publish_response = client.post(f'/api/editorial/articles/{editorial_id}/publish')
    assert publish_response.status_code == 200


def test_changing_render_sensitive_values_clears_final_html_until_reformatted(monkeypatch):
    _allow_admin_access(monkeypatch)

    create_response = client.post(
        '/api/editorial/articles',
        json={
            'title': 'Invalidate Render Draft',
            'source_markdown': 'old paragraph',
            'content_markdown': 'old paragraph',
            'primary_column_slug': 'insights',
            'primary_column_manual': True,
            'tags': [{'name': '数据安全', 'slug': 'topic-data-security', 'category': 'topic', 'confidence': 0.92}],
            'final_html': '<div><h1>Invalidate Render Draft</h1><p>Old rendered HTML.</p></div>',
        },
    )
    assert create_response.status_code == 200
    editorial_id = create_response.json()['id']

    update_response = client.put(
        f'/api/editorial/articles/{editorial_id}',
        json={
            'source_markdown': 'new paragraph that changes the article materially',
        },
    )
    assert update_response.status_code == 200
    updated = update_response.json()

    assert updated['final_html'] is None
    assert any(issue['code'] == 'missing_final_html' for issue in updated['publish_validation'])


def test_published_editorial_article_detail_prefers_editorial_html(monkeypatch):
    _allow_admin_access(monkeypatch)
    monkeypatch.setattr(
        ai_service,
        'auto_format_editorial_markdown',
        lambda **kwargs: {
            'markdown': '# Published Layout\n\nThis is the formatted content.',
            'model': 'gemini-3-flash-preview',
        },
    )
    monkeypatch.setattr(editorial_service, 'render_fudan_wechat', _mock_renderer('Published Layout'))

    create_response = client.post(
        '/api/editorial/articles',
        json={
            'title': 'Published Layout Draft',
            'source_markdown': 'original content',
            'content_markdown': 'original content',
            'primary_column_slug': 'insights',
            'primary_column_manual': True,
            'tags': [{'name': 'Topic Governance', 'slug': 'topic-governance', 'category': 'topic', 'confidence': 0.92}],
        },
    )
    assert create_response.status_code == 200
    editorial_id = create_response.json()['id']

    format_response = client.post(
        f'/api/editorial/articles/{editorial_id}/auto-format',
        json={'source_markdown': 'original content', 'layout_mode': 'auto'},
    )
    assert format_response.status_code == 200
    assert 'wechat-preview-shell' in format_response.json()['final_html']

    publish_response = client.post(f'/api/editorial/articles/{editorial_id}/publish')
    assert publish_response.status_code == 200
    article_id = publish_response.json()['article_id']

    article_response = client.get(f'/api/article/{article_id}')
    assert article_response.status_code == 200
    payload = article_response.json()

    assert payload['html_web'] == format_response.json()['final_html']
    assert payload['html_wechat'] == format_response.json()['final_html']


def test_published_editorial_detail_includes_rag_status(monkeypatch):
    _allow_admin_access(monkeypatch)
    monkeypatch.setattr(editorial_service, 'sync_article_for_rag', knowledge_ingestion_service.sync_article_for_rag)
    monkeypatch.setattr(knowledge_ingestion_service, 'is_chunk_embedding_enabled', lambda: True)
    monkeypatch.setattr(
        knowledge_ingestion_service,
        'embed_chunk_texts',
        lambda texts: [[0.8, 0.2, 0.1] for _ in texts],
    )
    monkeypatch.setattr(
        ai_service,
        'auto_format_editorial_markdown',
        lambda **kwargs: {
            'markdown': '# GPU Finance Draft\n\nGPU depreciation resets change AI capital discipline.',
            'model': 'gemini-3-flash-preview',
        },
    )
    monkeypatch.setattr(editorial_service, 'render_fudan_wechat', _mock_renderer('GPU Finance Draft'))

    create_response = client.post(
        '/api/editorial/articles',
        json={
            'title': 'GPU Finance Draft',
            'source_markdown': 'GPU depreciation resets change AI capital discipline.',
            'content_markdown': 'GPU depreciation resets change AI capital discipline.',
            'primary_column_slug': 'insights',
            'primary_column_manual': True,
            'tags': [{'name': 'AI Finance', 'slug': 'topic-ai-finance', 'category': 'topic', 'confidence': 0.94}],
        },
    )
    assert create_response.status_code == 200
    editorial_id = create_response.json()['id']

    format_response = client.post(
        f'/api/editorial/articles/{editorial_id}/auto-format',
        json={'source_markdown': 'GPU depreciation resets change AI capital discipline.', 'layout_mode': 'auto'},
    )
    assert format_response.status_code == 200

    publish_response = client.post(f'/api/editorial/articles/{editorial_id}/publish')
    assert publish_response.status_code == 200

    detail_response = client.get(f'/api/editorial/articles/{editorial_id}')
    assert detail_response.status_code == 200
    payload = detail_response.json()

    assert payload['article_id'] == publish_response.json()['article_id']
    assert payload['rag_status']['in_knowledge_base'] is True
    assert payload['rag_status']['chunk_count'] > 0
    assert payload['rag_status']['embedding_count'] > 0
    assert payload['rag_status']['latest_job']['status'] == 'completed'


def test_admin_rag_overview_returns_latest_assets_and_jobs(monkeypatch):
    _allow_admin_access(monkeypatch)
    monkeypatch.setattr(knowledge_ingestion_service, 'is_chunk_embedding_enabled', lambda: True)
    monkeypatch.setattr(
        knowledge_ingestion_service,
        'embed_chunk_texts',
        lambda texts: [[0.5, 0.3, 0.2] for _ in texts],
    )

    with connection_scope() as connection:
        article_id = int(connection.execute('SELECT COALESCE(MAX(id), 0) + 1 FROM articles').fetchone()[0])
        timestamp = '2026-04-16T09:30:00'
        title = 'RAG Console GPU Asset'
        connection.execute(
            """
            INSERT INTO articles (
                id, doc_id, slug, relative_path, source, source_mode, title, publish_date, link,
                content, excerpt, main_topic, article_type, series_or_column, primary_org_name,
                tag_text, people_text, org_text, search_text, word_count, cover_image_path,
                access_level, view_count, is_featured, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, 'business', 'import', ?, '2026-04-16', NULL, ?, ?, ?, ?, 'Insights', ?, '', '', ?, ?, ?, NULL, 'public', 0, 0, ?, ?)
            """,
            (
                article_id,
                f'rag-admin-doc-{article_id}',
                f'rag-console-gpu-asset-{article_id}',
                f'business/rag-console-gpu-asset-{article_id}.md',
                title,
                'GPU infrastructure depreciation resets and chunk-based retrieval visibility for administrators.',
                'A public article for testing the RAG console.',
                'GPU strategy',
                'insight',
                'Fudan Business Knowledge',
                'Fudan Business Knowledge',
                f'{title} GPU infrastructure depreciation resets and chunk-based retrieval visibility for administrators.',
                12,
                timestamp,
                timestamp,
            ),
        )
        connection.commit()

    result = knowledge_ingestion_service.sync_article_for_rag(article_id, trigger_source='test_admin_rag_console', force=True)
    assert (result.get('version') or {}).get('article_id') == article_id

    response = client.get('/api/admin/rag?asset_limit=6&job_limit=6&event_limit=4')
    assert response.status_code == 200
    payload = response.json()

    assert payload['ready_article_count'] >= 1
    assert payload['total_chunk_count'] >= 1
    assert payload['latest_assets']
    assert payload['latest_assets'][0]['article_id'] == article_id
    assert payload['latest_assets'][0]['chunk_count'] >= 1
    assert payload['latest_jobs']
    assert payload['latest_jobs'][0]['article_id'] == article_id


def test_admin_rag_overview_failed_job_count_ignores_historical_failures(monkeypatch):
    _allow_admin_access(monkeypatch)
    monkeypatch.setattr(knowledge_ingestion_service, 'is_chunk_embedding_enabled', lambda: True)
    monkeypatch.setattr(
        knowledge_ingestion_service,
        'embed_chunk_texts',
        lambda texts: [[0.4, 0.4, 0.2] for _ in texts],
    )

    with connection_scope() as connection:
        article_id = int(connection.execute('SELECT COALESCE(MAX(id), 0) + 1 FROM articles').fetchone()[0])
        timestamp = '2026-04-16T11:00:00'
        title = 'RAG Console Historical Failure'
        connection.execute(
            """
            INSERT INTO articles (
                id, doc_id, slug, relative_path, source, source_mode, title, publish_date, link,
                content, excerpt, main_topic, article_type, series_or_column, primary_org_name,
                tag_text, people_text, org_text, search_text, word_count, cover_image_path,
                access_level, view_count, is_featured, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, 'business', 'import', ?, '2026-04-16', NULL, ?, ?, ?, ?, 'Insights', ?, '', '', ?, ?, ?, NULL, 'public', 0, 0, ?, ?)
            """,
            (
                article_id,
                f'rag-admin-history-{article_id}',
                f'rag-admin-history-{article_id}',
                f'business/rag-admin-history-{article_id}.md',
                title,
                'A public article used to prove the admin console ignores historical failed jobs.',
                'A public article for testing failed-job counting.',
                'RAG operations',
                'insight',
                'Fudan Business Knowledge',
                'Fudan Business Knowledge',
                f'{title} historical failed jobs should not count after a later success.',
                14,
                timestamp,
                timestamp,
            ),
        )
        connection.execute(
            """
            INSERT INTO ingestion_jobs (
                article_id,
                version_id,
                trigger_source,
                status,
                stage,
                error_message,
                metrics_json,
                created_at,
                updated_at,
                started_at,
                completed_at
            )
            VALUES (?, NULL, 'legacy_failure', 'failed', 'failed', 'temporary outage', '{}', ?, ?, ?, ?)
            """,
            ('%d' % article_id, '2026-04-16T10:00:00', '2026-04-16T10:00:00', '2026-04-16T10:00:00', '2026-04-16T10:00:00'),
        )
        connection.commit()

    result = knowledge_ingestion_service.sync_article_for_rag(article_id, trigger_source='test_admin_rag_console_recovery', force=True)
    assert (result.get('version') or {}).get('article_id') == article_id

    response = client.get('/api/admin/rag?asset_limit=6&job_limit=6&event_limit=4')
    assert response.status_code == 200
    payload = response.json()

    assert payload['failed_job_count'] == 0


def test_admin_rag_overview_lists_public_assets_only(monkeypatch):
    _allow_admin_access(monkeypatch)
    monkeypatch.setattr(knowledge_ingestion_service, 'is_chunk_embedding_enabled', lambda: True)
    monkeypatch.setattr(
        knowledge_ingestion_service,
        'embed_chunk_texts',
        lambda texts: [[0.6, 0.2, 0.2] for _ in texts],
    )

    with connection_scope() as connection:
        base_id = int(connection.execute('SELECT COALESCE(MAX(id), 0) + 1 FROM articles').fetchone()[0])
        timestamp = '2026-04-16T12:00:00'
        public_article_id = base_id
        paid_article_id = base_id + 1
        for article_id, title, access_level in (
            (public_article_id, 'RAG Console Public Asset', 'public'),
            (paid_article_id, 'RAG Console Paid Asset', 'paid'),
        ):
            connection.execute(
                """
                INSERT INTO articles (
                    id, doc_id, slug, relative_path, source, source_mode, title, publish_date, link,
                    content, excerpt, main_topic, article_type, series_or_column, primary_org_name,
                    tag_text, people_text, org_text, search_text, word_count, cover_image_path,
                    access_level, view_count, is_featured, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, 'business', 'import', ?, '2026-04-16', NULL, ?, ?, ?, ?, 'Insights', ?, '', '', ?, ?, ?, NULL, ?, 0, 0, ?, ?)
                """,
                (
                    article_id,
                    f'rag-admin-scope-{article_id}',
                    f'rag-admin-scope-{article_id}',
                    f'business/rag-admin-scope-{article_id}.md',
                    title,
                    f'{title} exists to verify public-only filtering inside the RAG admin console.',
                    f'{title} test excerpt.',
                    'RAG operations',
                    'insight',
                    'Fudan Business Knowledge',
                    'Fudan Business Knowledge',
                    f'{title} public-only filtering check.',
                    10,
                    access_level,
                    timestamp,
                    timestamp,
                ),
            )
        connection.commit()

    knowledge_ingestion_service.sync_article_for_rag(public_article_id, trigger_source='test_admin_rag_public_scope', force=True)
    knowledge_ingestion_service.sync_article_for_rag(paid_article_id, trigger_source='test_admin_rag_public_scope', force=True)

    response = client.get('/api/admin/rag?asset_limit=20&job_limit=20&event_limit=4')
    assert response.status_code == 200
    payload = response.json()

    latest_asset_ids = {int(item['article_id']) for item in payload['latest_assets']}
    latest_job_ids = {int(item['article_id']) for item in payload['latest_jobs']}
    assert public_article_id in latest_asset_ids
    assert public_article_id in latest_job_ids
    assert paid_article_id not in latest_asset_ids
    assert paid_article_id not in latest_job_ids


def test_republish_updates_existing_article_id(monkeypatch):
    _allow_admin_access(monkeypatch)
    monkeypatch.setattr(
        ai_service,
        'auto_format_editorial_markdown',
        lambda **kwargs: {
            'markdown': f"# {kwargs.get('title')}\n\nformatted body",
            'model': 'gemini-3-flash-preview',
        },
    )
    monkeypatch.setattr(editorial_service, 'render_fudan_wechat', _mock_renderer())

    create_response = client.post(
        '/api/editorial/articles',
        json={
            'title': 'Republish Source Draft',
            'source_markdown': 'initial source content',
            'content_markdown': 'initial source content',
            'primary_column_slug': 'insights',
            'primary_column_manual': True,
            'tags': [{'name': 'Topic Governance', 'slug': 'topic-governance', 'category': 'topic', 'confidence': 0.92}],
        },
    )
    assert create_response.status_code == 200
    editorial_id = create_response.json()['id']

    assert client.post(
        f'/api/editorial/articles/{editorial_id}/auto-format',
        json={'source_markdown': 'initial source content', 'layout_mode': 'auto'},
    ).status_code == 200
    first_publish = client.post(f'/api/editorial/articles/{editorial_id}/publish')
    assert first_publish.status_code == 200
    article_id = first_publish.json()['article_id']
    first_article_response = client.get(f'/api/article/{article_id}')
    assert first_article_response.status_code == 200
    assert 'Republish Source Draft' in first_article_response.json()['html_web']

    update_response = client.put(
        f'/api/editorial/articles/{editorial_id}',
        json={'title': 'Republish Test Updated', 'source_markdown': 'updated raw content'},
    )
    assert update_response.status_code == 200
    assert client.post(
        f'/api/editorial/articles/{editorial_id}/auto-format',
        json={'source_markdown': 'updated source content', 'layout_mode': 'auto'},
    ).status_code == 200
    article_before_republish = client.get(f'/api/article/{article_id}')
    assert article_before_republish.status_code == 200
    assert 'Republish Source Draft' in article_before_republish.json()['html_web']
    assert 'Republish Test Updated' not in article_before_republish.json()['html_web']
    second_publish = client.post(f'/api/editorial/articles/{editorial_id}/publish')
    assert second_publish.status_code == 200

    assert second_publish.json()['article_id'] == article_id
    article_after_republish = client.get(f'/api/article/{article_id}')
    assert article_after_republish.status_code == 200
    assert 'Republish Test Updated' in article_after_republish.json()['html_web']
def test_auto_format_initializes_editor_document_fields(monkeypatch):
    _allow_admin_access(monkeypatch)
    monkeypatch.setattr(
        ai_service,
        'auto_format_editorial_markdown',
        lambda **kwargs: {
            'markdown': '# Editor Seed\n\nThis is the formatted body.',
            'model': 'gemini-3-flash-preview',
        },
    )
    monkeypatch.setattr(editorial_service, 'render_fudan_wechat', _mock_renderer('Editor Seed'))

    create_response = client.post(
        '/api/editorial/articles',
        json={
            'title': 'Editor Seed',
            'source_markdown': 'raw content',
            'content_markdown': 'raw content',
            'primary_column_slug': 'insights',
            'primary_column_manual': True,
            'tags': [{'name': 'Strategy', 'slug': 'topic-strategy', 'category': 'topic', 'confidence': 0.9}],
        },
    )
    assert create_response.status_code == 200
    editorial_id = create_response.json()['id']

    format_response = client.post(
        f'/api/editorial/articles/{editorial_id}/auto-format',
        json={'source_markdown': 'raw content', 'layout_mode': 'auto'},
    )
    assert format_response.status_code == 200
    payload = format_response.json()

    assert payload['editor_source'] == 'ai_formatted'
    assert payload['editor_document']['schema'] == 'html-fallback-v1'
    assert payload['editor_updated_at']
    assert 'wechat-preview-shell' in payload['final_html']


def test_manual_final_html_save_updates_publish_chain(monkeypatch):
    _allow_admin_access(monkeypatch)

    create_response = client.post(
        '/api/editorial/articles',
        json={
            'title': 'Manual HTML Publish',
            'source_markdown': 'raw content',
            'content_markdown': 'raw content',
            'primary_column_slug': 'insights',
            'primary_column_manual': True,
            'tags': [{'name': 'Strategy', 'slug': 'topic-strategy', 'category': 'topic', 'confidence': 0.9}],
        },
    )
    assert create_response.status_code == 200
    editorial_id = create_response.json()['id']

    manual_html = '<div><h1>Manual HTML Publish</h1><p>Final manual sentence.</p></div>'
    update_response = client.put(
        f'/api/editorial/articles/{editorial_id}',
        json={
            'final_html': manual_html,
            'editor_document': {
                'type': 'doc',
                'content': [
                    {
                        'type': 'paragraph',
                        'content': [{'type': 'text', 'text': 'Final manual sentence.'}],
                    }
                ],
            },
        },
    )
    assert update_response.status_code == 200
    updated = update_response.json()

    assert updated['editor_source'] == 'manual_edited'
    assert updated['is_manual_edit'] is True
    assert 'Final manual sentence.' in updated['plain_text_content']
    assert updated['final_html'] == manual_html

    publish_response = client.post(f'/api/editorial/articles/{editorial_id}/publish')
    assert publish_response.status_code == 200
    article_id = publish_response.json()['article_id']

    article_response = client.get(f'/api/article/{article_id}')
    assert article_response.status_code == 200
    payload = article_response.json()

    assert payload['html_web'] == manual_html
    assert payload['html_wechat'] == manual_html


def test_manual_final_html_preserves_title_table_emphasis_body_and_style(monkeypatch):
    _allow_admin_access(monkeypatch)

    create_response = client.post(
        '/api/editorial/articles',
        json={
            'title': 'Template Preserve Draft',
            'source_markdown': 'raw content',
            'content_markdown': 'raw content',
            'primary_column_slug': 'insights',
            'primary_column_manual': True,
            'tags': [{'name': 'Strategy', 'slug': 'topic-strategy', 'category': 'topic', 'confidence': 0.9}],
        },
    )
    assert create_response.status_code == 200
    editorial_id = create_response.json()['id']

    manual_html = """
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <style>
      body { background: #ffffff; }
      .hero { color: #0d0783; }
      table { width: 100%; border-collapse: collapse; }
      th, td { border: 1px solid #cbd5e1; padding: 12px; }
    </style>
  </head>
  <body>
    <article class="wechat-preview-shell" data-wechat-decoration="1">
      <section class="hero">
        <h1>Template Preserve Draft</h1>
      </section>
      <p>正文第一段，<strong>重点句</strong> 继续展开。</p>
      <table>
        <thead>
          <tr><th>栏目</th><th>说明</th></tr>
        </thead>
        <tbody>
          <tr><td>标题</td><td>保留模板标题样式</td></tr>
        </tbody>
      </table>
      <p>正文第二段。</p>
    </article>
  </body>
</html>
""".strip()

    update_response = client.put(
        f'/api/editorial/articles/{editorial_id}',
        json={
            'final_html': manual_html,
            'editor_document': {'schema': 'editable-html-v1', 'html': manual_html},
        },
    )
    assert update_response.status_code == 200
    updated = update_response.json()

    assert '<style>' in updated['final_html']
    assert '<table>' in updated['final_html']
    assert '<strong>重点句</strong>' in updated['final_html']
    assert 'Template Preserve Draft' in updated['final_html']
    assert '正文第二段。' in updated['final_html']
    assert updated['editor_document']['schema'] == 'editable-html-v1'

    detail_response = client.get(f'/api/editorial/articles/{editorial_id}')
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert '<style>' in detail['final_html']
    assert '<table>' in detail['final_html']
    assert '<strong>重点句</strong>' in detail['final_html']
    assert '正文第一段' in detail['plain_text_content']

    publish_response = client.post(f'/api/editorial/articles/{editorial_id}/publish')
    assert publish_response.status_code == 200
    article_id = publish_response.json()['article_id']

    article_response = client.get(f'/api/article/{article_id}')
    assert article_response.status_code == 200
    payload = article_response.json()

    assert '<style>' in payload['html_web']
    assert '<table>' in payload['html_web']
    assert '<strong>重点句</strong>' in payload['html_web']
    assert '正文第二段。' in payload['html_web']


def _legacy_test_auto_summary_publishes_and_article_detail_reads_same_summary_html(monkeypatch):
    _allow_admin_access(monkeypatch)
    monkeypatch.setattr(
        ai_service,
        'summarize_article_payload',
        lambda title, content: {
            'summary': '### 核心判断\n\n- **23andMe** 数据泄露暴露了治理缺口。\n- 监管问责与用户信任流失同步发生。',
            'model': 'gemini-2.5-flash',
        },
    )

    create_response = client.post(
        '/api/editorial/articles',
        json={
            'title': '23andMe Summary Contract Draft',
            'source_markdown': 'first paragraph\n\nsecond paragraph',
            'content_markdown': 'first paragraph\n\nsecond paragraph',
            'primary_column_slug': 'insights',
            'primary_column_manual': True,
            'tags': [{'name': '数据治理', 'slug': 'topic-data-governance', 'category': 'topic', 'confidence': 0.92}],
            'final_html': '<!doctype html><html><body><h1>23andMe Summary Contract Draft</h1><p>Final body.</p></body></html>',
        },
    )
    assert create_response.status_code == 200
    editorial_id = create_response.json()['id']

    summary_response = client.post(f'/api/editorial/articles/{editorial_id}/auto-summary')
    assert summary_response.status_code == 200
    summary_payload = summary_response.json()

    assert summary_payload['summary_model'] == 'gemini-2.5-flash'
    assert summary_payload['summary_markdown'].startswith('### 核心判断')
    assert 'summary-preview-shell' in summary_payload['summary_html']
    assert '<strong>23andMe</strong>' in summary_payload['summary_html']

    publish_response = client.post(f'/api/editorial/articles/{editorial_id}/publish')
    assert publish_response.status_code == 200
    article_id = publish_response.json()['article_id']

    article_response = client.get(f'/api/article/{article_id}')
    assert article_response.status_code == 200
    article_payload = article_response.json()

    assert article_payload['summary'].startswith('### 核心判断')
    assert article_payload['summary_html'] == summary_payload['summary_html']
    assert article_payload['html_web'].endswith('Final body.</p></body></html>')

    summary_api_response = client.get(f'/api/summarize_article/{article_id}')
    assert summary_api_response.status_code == 200
    assert summary_api_response.json()['summary_html'] == summary_payload['summary_html']
    assert summary_api_response.json()['summary'] == article_payload['summary']


def _legacy_test_auto_summary_contract_flattens_brief_style_output_before_publish(monkeypatch):
    _allow_admin_access(monkeypatch)
    monkeypatch.setattr(
        ai_service,
        'summarize_article_payload',
        lambda title, content: {
            'summary': '以下是这篇文章的商业知识简报：\n\n### 核心判断\n\n- **23andMe** 数据泄露暴露了治理缺口。\n- 监管问责与用户信任流失同步发生。',
            'model': 'gemini-2.5-flash',
        },
    )

    create_response = client.post(
        '/api/editorial/articles',
        json={
            'title': '23andMe Summary Contract Draft',
            'source_markdown': 'first paragraph\n\nsecond paragraph',
            'content_markdown': 'first paragraph\n\nsecond paragraph',
            'primary_column_slug': 'insights',
            'primary_column_manual': True,
            'tags': [{'name': '数据治理', 'slug': 'topic-data-governance', 'category': 'topic', 'confidence': 0.92}],
            'final_html': '<!doctype html><html><body><h1>23andMe Summary Contract Draft</h1><p>Final body.</p></body></html>',
        },
    )
    assert create_response.status_code == 200
    editorial_id = create_response.json()['id']

    summary_response = client.post(f'/api/editorial/articles/{editorial_id}/auto-summary')
    assert summary_response.status_code == 200
    summary_payload = summary_response.json()

    assert summary_payload['summary_model'] == 'gemini-2.5-flash'
    assert '以下是' not in summary_payload['summary_markdown']
    assert '简报' not in summary_payload['summary_markdown']
    assert '###' not in summary_payload['summary_markdown']
    assert '- ' not in summary_payload['summary_markdown']
    assert len(summary_payload['summary_markdown'].replace('\n', '')) <= ai_service.EDITORIAL_SUMMARY_MAX_CHARS
    assert 'summary-preview-shell' in summary_payload['summary_html']
    assert '23andMe' in summary_payload['summary_html']

    publish_response = client.post(f'/api/editorial/articles/{editorial_id}/publish')
    assert publish_response.status_code == 200
    article_id = publish_response.json()['article_id']

    article_response = client.get(f'/api/article/{article_id}')
    assert article_response.status_code == 200
    article_payload = article_response.json()

    assert '以下是' not in article_payload['summary']
    assert '简报' not in article_payload['summary']
    assert '###' not in article_payload['summary']
    assert article_payload['summary_html'] == summary_payload['summary_html']
    assert article_payload['html_web'].endswith('Final body.</p></body></html>')

    summary_api_response = client.get(f'/api/summarize_article/{article_id}')
    assert summary_api_response.status_code == 200
    assert summary_api_response.json()['summary_html'] == summary_payload['summary_html']
    assert summary_api_response.json()['summary'] == article_payload['summary']


def test_auto_summary_contract_generates_hybrid_summary_before_publish(monkeypatch):
    _allow_admin_access(monkeypatch)
    summary_markdown = (
        '**SBTI 社交扩散**在微信朋友区迅速形成自传播，年轻人借助标签化测试重组低门槛社交，也把它当作情绪出口与身份识别工具。'
        '这股热度背后不是简单跟风，而是熟人背书、轻量标签与情绪认同共同推动的一轮社交协作重构。\n\n'
        '- **现象层面：** 熟人网络背书降低了传播门槛，让这类自我解构内容迅速跨圈扩散，也让更多人愿意公开参与和转发。\n'
        '- **机制层面：** 它同时满足自我识别、互动破冰和情绪投射三重需求，因此比普通娱乐测试更容易形成持续讨论与复用。\n'
        '- **影响层面：** 关系建立正在进一步依赖可复制的话术模板与轻量身份确认，平台和品牌都可能围绕这种结构设计互动增长动作。\n'
    )
    monkeypatch.setattr(
        editorial_service,
        '_build_summary_editorial_assets',
        lambda title, content: {
            'summary_markdown': summary_markdown,
            'summary_html': editorial_service._build_summary_editorial_html(summary_markdown),
            'summary_model': 'gemini-2.5-flash',
        },
    )

    create_response = client.post(
        '/api/editorial/articles',
        json={
            'title': 'Hybrid Summary Contract Draft',
            'source_markdown': 'first paragraph\n\nsecond paragraph\n\nthird paragraph',
            'content_markdown': 'first paragraph\n\nsecond paragraph\n\nthird paragraph',
            'primary_column_slug': 'insights',
            'primary_column_manual': True,
            'tags': [{'name': '数据治理', 'slug': 'topic-data-governance', 'category': 'topic', 'confidence': 0.92}],
            'final_html': '<!doctype html><html><body><h1>Hybrid Summary Contract Draft</h1><p>Final body.</p></body></html>',
        },
    )
    assert create_response.status_code == 200
    editorial_id = create_response.json()['id']

    summary_response = client.post(f'/api/editorial/articles/{editorial_id}/auto-summary')
    assert summary_response.status_code == 200
    summary_payload = summary_response.json()

    assert summary_payload['summary_model'] == 'gemini-2.5-flash'
    assert '以下是' not in summary_payload['summary_markdown']
    assert 200 <= ai_service.editorial_summary_visible_length(summary_payload['summary_markdown']) <= ai_service.EDITORIAL_SUMMARY_MAX_CHARS
    assert '**' in summary_payload['summary_markdown']
    assert '- **' in summary_payload['summary_markdown']
    assert summary_payload['summary_markdown'].count('- **') >= 3
    assert not summary_payload['summary_markdown'].lstrip().startswith('- ')
    assert 'summary-preview-shell' in summary_payload['summary_html']

    publish_response = client.post(f'/api/editorial/articles/{editorial_id}/publish')
    assert publish_response.status_code == 200
    article_id = publish_response.json()['article_id']

    article_response = client.get(f'/api/article/{article_id}')
    assert article_response.status_code == 200
    article_payload = article_response.json()

    assert '以下是' not in article_payload['summary']
    assert '**' in article_payload['summary']
    assert '- **' in article_payload['summary']
    assert article_payload['summary'].count('- **') >= 3
    assert article_payload['summary_html'] == summary_payload['summary_html']
    assert article_payload['html_web'].endswith('Final body.</p></body></html>')

    summary_api_response = client.get(f'/api/summarize_article/{article_id}')
    assert summary_api_response.status_code == 200
    assert summary_api_response.json()['summary_html'] == summary_payload['summary_html']
    assert summary_api_response.json()['summary'] == article_payload['summary']


def test_editorial_detail_repairs_legacy_stripped_wechat_preview(monkeypatch):
    _allow_admin_access(monkeypatch)

    full_preview_html = """
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <style>.hero { color: #0d0783; }</style>
  </head>
  <body>
    <div class="wechat-preview-shell" data-wechat-decoration="1">
      <section class="hero"><h1>Legacy Template Repair</h1></section>
      <article><p>修复后的正文段落。</p></article>
    </div>
  </body>
</html>
""".strip()

    def fake_renderer(item, *, timeout_seconds=60.0):
        del timeout_seconds
        assert item['render_plan']['creditsVariant'] == 'fudan_meta'
        return {
            'previewHtml': full_preview_html,
            'contentHtml': full_preview_html,
            'renderPlan': item['render_plan'],
            'metadata': {'engine': 'repair-test'},
            'warnings': [],
        }

    monkeypatch.setattr(editorial_service, 'render_fudan_wechat', fake_renderer)

    create_response = client.post(
        '/api/editorial/articles',
        json={
            'title': 'Legacy Template Repair',
            'source_markdown': 'legacy raw body',
            'content_markdown': 'legacy raw body',
            'primary_column_slug': 'insights',
            'primary_column_manual': True,
            'tags': [{'name': 'Strategy', 'slug': 'topic-strategy', 'category': 'topic', 'confidence': 0.9}],
        },
    )
    assert create_response.status_code == 200
    editorial_id = create_response.json()['id']

    stripped_preview_html = """
<!doctype html>
<html lang="zh-CN">
  <head><meta charset="utf-8" /><title>Legacy Template Repair</title></head>
  <body>
    <div class="wechat-preview-shell" data-wechat-decoration="1">
      <article><p>只剩被裁剪后的正文。</p></article>
    </div>
  </body>
</html>
""".strip()

    with connection_scope() as connection:
        connection.execute(
            """
            UPDATE editorial_articles
            SET final_html = ?,
                html_web = ?,
                html_wechat = ?,
                editor_document_json = ?,
                editor_source = 'ai_formatted',
                render_metadata_json = ?
            WHERE id = ?
            """,
            (
                stripped_preview_html,
                stripped_preview_html,
                stripped_preview_html,
                json.dumps({'schema': 'html-fallback-v1', 'html': stripped_preview_html}, ensure_ascii=False),
                json.dumps({'render_plan': {'creditsVariant': 'fudan_meta'}, 'metadata': {}, 'warnings': []}, ensure_ascii=False),
                editorial_id,
            ),
        )
        connection.commit()

    detail_response = client.get(f'/api/editorial/articles/{editorial_id}')
    assert detail_response.status_code == 200
    detail = detail_response.json()

    assert 'Legacy Template Repair' in detail['final_html']
    assert '修复后的正文段落。' in detail['final_html']
    assert '<style>.hero' in detail['final_html']

    with connection_scope() as connection:
        row = connection.execute(
            'SELECT final_html, html_web, html_wechat FROM editorial_articles WHERE id = ?',
            (editorial_id,),
        ).fetchone()
    assert 'Legacy Template Repair' in row['final_html']
    assert row['final_html'] == row['html_web'] == row['html_wechat']


def test_auto_format_keeps_previous_manual_html_as_backup(monkeypatch):
    _allow_admin_access(monkeypatch)
    monkeypatch.setattr(
        ai_service,
        'auto_format_editorial_markdown',
        lambda **kwargs: {
            'markdown': '# Reformatted\n\nAI version body.',
            'model': 'gemini-3-flash-preview',
        },
    )
    monkeypatch.setattr(editorial_service, 'render_fudan_wechat', _mock_renderer('Reformatted'))

    create_response = client.post(
        '/api/editorial/articles',
        json={
            'title': 'Backup Flow',
            'source_markdown': 'raw content',
            'content_markdown': 'raw content',
            'primary_column_slug': 'insights',
            'primary_column_manual': True,
            'tags': [{'name': 'Strategy', 'slug': 'topic-strategy', 'category': 'topic', 'confidence': 0.9}],
        },
    )
    assert create_response.status_code == 200
    editorial_id = create_response.json()['id']

    manual_html = '<div><h1>Backup Flow</h1><p>Manual version body.</p></div>'
    update_response = client.put(
        f'/api/editorial/articles/{editorial_id}',
        json={'final_html': manual_html},
    )
    assert update_response.status_code == 200

    format_response = client.post(
        f'/api/editorial/articles/{editorial_id}/auto-format',
        json={'source_markdown': 'raw content', 'layout_mode': 'auto'},
    )
    assert format_response.status_code == 200
    payload = format_response.json()

    assert payload['editor_source'] == 'ai_formatted'
    assert payload['has_manual_backup'] is True
    assert payload['manual_final_html_backup'] == manual_html


def test_admin_can_delete_unpublished_editorial_draft_but_not_published_one(monkeypatch):
    _allow_admin_access(monkeypatch)

    create_response = client.post(
        '/api/editorial/articles',
        json={
            'title': 'Delete Draft',
            'source_markdown': 'raw content',
            'content_markdown': 'raw content',
        },
    )
    assert create_response.status_code == 200
    draft_id = create_response.json()['id']

    delete_response = client.delete(f'/api/editorial/articles/{draft_id}')
    assert delete_response.status_code == 200
    assert delete_response.json()['deleted'] is True
    assert client.get(f'/api/editorial/articles/{draft_id}').status_code == 404

    published_response = client.post(
        '/api/editorial/articles',
        json={
            'title': 'Published Draft',
            'source_markdown': 'raw content',
            'content_markdown': 'raw content',
            'primary_column_slug': 'insights',
            'primary_column_manual': True,
            'tags': [{'name': 'Strategy', 'slug': 'topic-strategy', 'category': 'topic', 'confidence': 0.9}],
            'final_html': '<div><h1>Published Draft</h1><p>Ready.</p></div>',
        },
    )
    assert published_response.status_code == 200
    published_id = published_response.json()['id']
    assert client.post(f'/api/editorial/articles/{published_id}/publish').status_code == 200

    delete_published = client.delete(f'/api/editorial/articles/{published_id}')
    assert delete_published.status_code == 400


def test_published_editorial_auto_leaves_draft_box_and_reopen_reuses_existing_editorial(monkeypatch):
    _allow_admin_access(monkeypatch)

    published_response = client.post(
        '/api/editorial/articles',
        json={
            'title': 'Auto Leave Draft Box',
            'source_markdown': 'raw content',
            'content_markdown': 'raw content',
            'primary_column_slug': 'insights',
            'primary_column_manual': True,
            'tags': [{'name': 'Strategy', 'slug': 'topic-strategy', 'category': 'topic', 'confidence': 0.9}],
            'final_html': '<div><h1>Auto Leave Draft Box</h1><p>Ready.</p></div>',
        },
    )
    assert published_response.status_code == 200
    editorial_id = published_response.json()['id']

    publish_response = client.post(f'/api/editorial/articles/{editorial_id}/publish')
    assert publish_response.status_code == 200
    article_id = publish_response.json()['article_id']
    assert client.get(f'/api/article/{article_id}').status_code == 200

    active_list = client.get('/api/editorial/articles')
    assert active_list.status_code == 200
    assert editorial_id not in {item['id'] for item in active_list.json()}
    archived_list = client.get('/api/editorial/articles?draft_box_state=archived')
    assert archived_list.status_code == 200
    assert editorial_id in {item['id'] for item in archived_list.json()}

    reopen_response = client.post(f'/api/editorial/source-articles/{article_id}/reopen-draft')
    assert reopen_response.status_code == 200
    reopened = reopen_response.json()

    assert reopened['id'] == editorial_id
    assert reopened['draft_box_state'] == 'active'
    assert reopened['status'] == 'published'
    assert reopened['workflow_status'] == 'draft'
    assert reopened['is_reopened_from_published'] is True
    assert reopened['article_id'] == article_id

    detail_after_reopen = client.get(f'/api/editorial/articles/{editorial_id}')
    assert detail_after_reopen.status_code == 200
    assert detail_after_reopen.json()['workflow_status'] == 'draft'
    assert detail_after_reopen.json()['draft_box_state'] == 'active'

    active_after_reopen = client.get('/api/editorial/articles')
    assert active_after_reopen.status_code == 200
    assert editorial_id in {item['id'] for item in active_after_reopen.json()}
    explicit_active_after_reopen = client.get('/api/editorial/articles?draft_box_state=active')
    assert explicit_active_after_reopen.status_code == 200
    assert editorial_id in {item['id'] for item in explicit_active_after_reopen.json()}

    reopen_again = client.post(f'/api/editorial/source-articles/{article_id}/reopen-draft')
    assert reopen_again.status_code == 200
    assert reopen_again.json()['id'] == editorial_id

    removed_route = client.post(f'/api/editorial/articles/{editorial_id}/archive-draft-box')
    assert removed_route.status_code == 404


def test_reopen_and_republish_preserves_existing_cover_image(monkeypatch):
    _allow_admin_access(monkeypatch)
    cover_url = '/editorial-uploads/covers/reopen-cover.png'

    create_response = client.post(
        '/api/editorial/articles',
        json={
            'title': 'Reopen Cover Draft',
            'source_markdown': 'raw content',
            'content_markdown': 'raw content',
            'primary_column_slug': 'insights',
            'primary_column_manual': True,
            'cover_image_url': cover_url,
            'tags': [{'name': 'Strategy', 'slug': 'topic-strategy', 'category': 'topic', 'confidence': 0.9}],
            'final_html': '<div><h1>Reopen Cover Draft</h1><p>Ready.</p></div>',
        },
    )
    assert create_response.status_code == 200
    editorial_id = create_response.json()['id']

    publish_response = client.post(f'/api/editorial/articles/{editorial_id}/publish')
    assert publish_response.status_code == 200
    article_id = publish_response.json()['article_id']

    initial_cover_response = client.get(f'/api/article/{article_id}/cover', follow_redirects=False)
    assert initial_cover_response.status_code in {302, 307}
    assert initial_cover_response.headers['location'] == cover_url

    reopen_response = client.post(f'/api/editorial/source-articles/{article_id}/reopen-draft')
    assert reopen_response.status_code == 200
    reopened = reopen_response.json()
    assert reopened['cover_image_url'] == cover_url

    update_response = client.put(
        f'/api/editorial/articles/{editorial_id}',
        json={'main_topic': 'Updated focus after reopen'},
    )
    assert update_response.status_code == 200

    republish_response = client.post(f'/api/editorial/articles/{editorial_id}/publish')
    assert republish_response.status_code == 200
    assert republish_response.json()['article_id'] == article_id

    final_cover_response = client.get(f'/api/article/{article_id}/cover', follow_redirects=False)
    assert final_cover_response.status_code in {302, 307}
    assert final_cover_response.headers['location'] == cover_url


def test_reopen_and_republish_preserves_english_translation_assets(monkeypatch):
    _allow_admin_access(monkeypatch)
    monkeypatch.setattr(editorial_service, 'render_fudan_wechat', _mock_renderer('English Layout'))

    create_response = client.post(
        '/api/editorial/articles',
        json={
            'title': 'Reopen Translation Draft',
            'source_markdown': '中文原稿',
            'content_markdown': '# Reopen Translation Draft\n\n正文内容',
            'summary_markdown': '这是一段中文摘要。',
            'summary_html': '<div><p>这是一段中文摘要。</p></div>',
            'final_html': '<div><h1>Reopen Translation Draft</h1><p>正文内容</p></div>',
            'primary_column_slug': 'insights',
            'primary_column_manual': True,
            'tags': [{'name': 'Translation', 'slug': 'topic-translation-reopen', 'category': 'topic', 'confidence': 0.9}],
        },
    )
    assert create_response.status_code == 200
    editorial_id = create_response.json()['id']

    publish_response = client.post(f'/api/editorial/articles/{editorial_id}/publish')
    assert publish_response.status_code == 200
    article_id = publish_response.json()['article_id']

    reopen_response = client.post(f'/api/editorial/source-articles/{article_id}/reopen-draft')
    assert reopen_response.status_code == 200
    reopened = reopen_response.json()
    assert reopened['id'] == editorial_id
    assert reopened['translation_ready'] is True
    assert reopened['translation_status'] == 'completed'
    assert reopened['translation_title_en'].endswith(' EN')
    assert reopened['translation_summary_en']
    assert reopened['final_html_en']

    update_response = client.put(
        f'/api/editorial/articles/{editorial_id}',
        json={'main_topic': 'Updated English asset follow-up'},
    )
    assert update_response.status_code == 200

    republish_response = client.post(f'/api/editorial/articles/{editorial_id}/publish')
    assert republish_response.status_code == 200
    assert republish_response.json()['article_id'] == article_id

    translation_response = client.get(f'/api/article/{article_id}/translation?lang=en')
    assert translation_response.status_code == 200
    translation_payload = translation_response.json()
    assert translation_payload['title'].endswith(' EN')
    assert translation_payload['summary']
    assert translation_payload['html_web']


def test_reopen_draft_recovers_english_summary_from_published_english_body(monkeypatch):
    _allow_admin_access(monkeypatch)
    with connection_scope() as connection:
        article_id = int(connection.execute('SELECT COALESCE(MAX(id), 0) + 1 FROM articles').fetchone()[0])
        now = '2026-04-16T22:00:00'
        title = f'Legacy English Summary Body {article_id}'
        connection.execute(
            """
            INSERT INTO articles (
                id, doc_id, slug, relative_path, source, source_mode, title, publish_date, link,
                content, excerpt, main_topic, article_type, series_or_column, primary_org_name,
                tag_text, people_text, org_text, search_text, word_count, cover_image_path,
                access_level, view_count, is_featured, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, 'editorial', 'cms', ?, '2026-04-16', NULL, ?, ?, ?, ?, '内容后台', NULL, '', '', ?, ?, ?, NULL, 'public', 0, 0, ?, ?)
            """,
            (
                article_id,
                f'legacy-en-doc-{article_id}',
                f'legacy-english-summary-body-{article_id}',
                f'editorial/legacy-english-summary-body-{article_id}.md',
                title,
                '中文正文',
                '中文摘要',
                'GPU finance',
                'insight',
                'Fudan Business Knowledge',
                f'{title} 中文正文',
                8,
                now,
                now,
            ),
        )
        column_row = connection.execute("SELECT id FROM columns WHERE slug = 'insights'").fetchone()
        assert column_row is not None
        connection.execute(
            "INSERT OR REPLACE INTO article_columns (article_id, column_id, is_featured, sort_order) VALUES (?, ?, 1, 0)",
            (article_id, int(column_row['id'])),
        )
        source_row = connection.execute("SELECT * FROM articles WHERE id = ?", (article_id,)).fetchone()
        source_hash = editorial_service.build_current_article_source_hash(source_row)
        legacy_english_html = (
            '<!doctype html><html lang="en"><body><div class="wechat-preview-shell">'
            '<h1>Legacy English Summary Body</h1>'
            '<p>The first English summary paragraph is still preserved inside the published body.</p>'
            '<p>The second paragraph continues the summary before the article sections begin.</p>'
            '<h2>Section One</h2>'
            '<p>This is the main English body.</p>'
            '</div></body></html>'
        )
        connection.execute(
            """
            INSERT INTO article_ai_outputs (
                article_id, doc_id, slug, relative_path, source_hash, source_lang, target_lang, source_title, source_excerpt,
                summary_zh, summary_html_zh, summary_model, formatted_markdown_zh, formatted_markdown_en,
                translation_title_en, translation_excerpt_en, translation_summary_en, summary_html_en, translation_content_en,
                html_web_zh, html_wechat_zh, html_web_en, html_wechat_en,
                summary_status, format_status, translation_status,
                summary_error, format_error, translation_error,
                translation_model, format_model, format_template,
                status, error_message, worker_name, started_at, completed_at, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, 'zh-CN', 'en', ?, ?, NULL, NULL, NULL, NULL, ?, ?, ?, NULL, NULL, ?, NULL, NULL, ?, ?, 'pending', 'pending', 'completed', NULL, NULL, NULL, ?, NULL, 'fudan-business-knowledge-v1', 'completed', NULL, 'legacy-test', ?, ?, ?, ?)
            """,
            (
                article_id,
                source_row['doc_id'],
                source_row['slug'],
                source_row['relative_path'],
                source_hash,
                source_row['title'],
                source_row['excerpt'] or '',
                '# Legacy English Summary Body\n\nThis is the main English body.',
                'Legacy English Summary Body',
                '',
                '# Legacy English Summary Body\n\nThis is the main English body.',
                legacy_english_html,
                legacy_english_html,
                'gemini-3-flash-preview',
                now,
                now,
                now,
                now,
            ),
        )
        connection.commit()

    reopen_response = client.post(f'/api/editorial/source-articles/{article_id}/reopen-draft')
    assert reopen_response.status_code == 200
    reopened = reopen_response.json()

    assert reopened['translation_summary_en']
    assert 'The first English summary paragraph is still preserved' in reopened['translation_summary_en']
    assert reopened['summary_html_en']
    assert 'The second paragraph continues the summary' in reopened['summary_html_en']


def test_reopen_non_editorial_article_creates_single_linked_editorial_draft(monkeypatch):
    _allow_admin_access(monkeypatch)
    source_cover_url = '/media-uploads/covers/source-cover.png'

    with connection_scope() as connection:
        article_id = int(connection.execute('SELECT COALESCE(MAX(id), 0) + 1 FROM articles').fetchone()[0])
        now = '2026-04-10T12:00:00'
        title = f'Reopen Source Draft {article_id}'
        connection.execute(
            """
            INSERT INTO articles (
                id, doc_id, slug, relative_path, source, source_mode, title, publish_date, link,
                content, excerpt, main_topic, article_type, series_or_column, primary_org_name,
                tag_text, people_text, org_text, search_text, word_count, cover_image_path,
                access_level, view_count, is_featured, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, 'business', 'import', ?, '2026-04-10', NULL, ?, ?, ?, ?, 'Original Column', ?, '', '', ?, ?, ?, ?, 'public', 0, 0, ?, ?)
            """,
            (
                article_id,
                f'test-doc-{article_id}',
                f'reopen-source-{article_id}',
                f'business/reopen-source-{article_id}.md',
                title,
                'first source paragraph\n\nsecond source paragraph',
                'AI summary',
                'Topic Governance',
                'insight',
                'Fudan Business Knowledge',
                'Fudan Business Knowledge',
                f'{title} first source paragraph second source paragraph',
                8,
                source_cover_url,
                now,
                now,
            ),
        )
        tag_row = connection.execute("SELECT id FROM tags WHERE slug = 'topic-reopen-source-test'").fetchone()
        if tag_row is None:
            connection.execute(
                """
                INSERT INTO tags (name, slug, category, description, color, article_count)
                VALUES ('Reopen Source Tag', 'topic-reopen-source-test', 'topic', NULL, '#64748b', 1)
                """
            )
            tag_id = int(connection.execute('SELECT last_insert_rowid()').fetchone()[0])
        else:
            tag_id = int(tag_row['id'])
        connection.execute(
            "INSERT OR REPLACE INTO article_tags (article_id, tag_id, confidence) VALUES (?, ?, ?)",
            (article_id, tag_id, 0.88),
        )
        column_row = connection.execute("SELECT id FROM columns WHERE slug = 'insights'").fetchone()
        assert column_row is not None
        connection.execute(
            "INSERT OR REPLACE INTO article_columns (article_id, column_id, is_featured, sort_order) VALUES (?, ?, 1, 0)",
            (article_id, int(column_row['id'])),
        )
        connection.commit()

    reopen_response = client.post(f'/api/editorial/source-articles/{article_id}/reopen-draft')
    assert reopen_response.status_code == 200
    reopened = reopen_response.json()

    assert reopened['article_id'] == article_id
    assert reopened['source_article_id'] == article_id
    assert reopened['status'] == 'published'
    assert reopened['workflow_status'] == 'draft'
    assert reopened['draft_box_state'] == 'active'
    assert reopened['final_html']
    assert title in reopened['final_html']
    assert reopened['cover_image_url'] == source_cover_url
    assert reopened['primary_column_slug'] == 'insights'
    assert len(reopened['tags']) == 1
    assert reopened['tags'][0]['category'] == 'topic'

    active_list = client.get('/api/editorial/articles')
    assert active_list.status_code == 200
    assert reopened['id'] in {item['id'] for item in active_list.json()}

    reopen_again = client.post(f'/api/editorial/source-articles/{article_id}/reopen-draft')
    assert reopen_again.status_code == 200
    assert reopen_again.json()['id'] == reopened['id']


def _prepare_media_upload_root(monkeypatch):
    upload_root = Path(tempfile.mkdtemp(prefix="fdsm_media_uploads_", dir=TEST_DATA_DIR))
    monkeypatch.setattr(media_service, "MEDIA_UPLOADS_DIR", upload_root)
    monkeypatch.setattr(media_service, "LOCAL_AUDIO_ITEMS", [])
    return upload_root


def _publish_video_media_draft(monkeypatch, *, stem="launch-video", with_cover=False):
    _allow_admin_access(monkeypatch)
    upload_root = _prepare_media_upload_root(monkeypatch)
    monkeypatch.setattr(
        ai_service,
        "generate_media_text_assets",
        lambda **kwargs: {
            "summary": "**节目摘要：** 节目围绕音视频工作流对齐展开，说明上传、转录和发布如何贯通。",
            "body_markdown": (
                "## 节目简介\n\n"
                "节目从后台工作流切入，说明主媒体、转录和脚本如何驱动发布素材生成。\n\n"
                "### 核心看点\n\n"
                "- 上传链路先落草稿，再补文字素材。\n"
                "- 文案生成、章节提取与发布动作在同一工作台完成。\n"
                "- 已发布内容需要修改时，从正式页重新进入编辑流。"
            ),
            "chapters": [
                {"timestamp_label": "00:00", "title": "上传先进入草稿箱"},
                {"timestamp_label": "00:42", "title": "脚本识别与文案生成"},
                {"timestamp_label": "01:26", "title": "正式页重新进入编辑"},
            ],
            "model": "media-copy-test-model",
        },
    )

    media_response = client.post(
        "/api/media/admin/upload",
        data={"kind": "video", "usage": "media"},
        files={"file": (f"{stem}.mp4", b"\x00\x00\x00\x18ftypmp42", "video/mp4")},
    )
    assert media_response.status_code == 200
    media_payload = media_response.json()
    draft_id = media_payload["item"]["id"]

    cover_payload = None
    if with_cover:
        cover_response = client.post(
            "/api/media/admin/upload",
            data={"kind": "video", "usage": "cover", "draft_id": str(draft_id)},
            files={"file": (f"{stem}-cover.png", b"\x89PNG\r\n\x1a\ncover", "image/png")},
        )
        assert cover_response.status_code == 200
        cover_payload = cover_response.json()

    transcript_response = client.post(
        "/api/media/admin/upload",
        data={"kind": "video", "usage": "script", "draft_id": str(draft_id)},
        files={
            "file": (
                f"{stem}.md",
                "# 转录\n\n00:00 开场说明\n\n00:42 进入工作流拆解\n\n01:26 结尾回到发布和回编",
                "text/markdown",
            )
        },
    )
    assert transcript_response.status_code == 200

    generated_response = client.post(f"/api/media/admin/items/{draft_id}/generate-copy")
    assert generated_response.status_code == 200
    generated = generated_response.json()

    publish_response = client.post(f"/api/media/admin/items/{draft_id}/publish")
    assert publish_response.status_code == 200
    published = publish_response.json()
    return {
        "upload_root": upload_root,
        "draft_id": draft_id,
        "media_upload": media_payload,
        "cover_upload": cover_payload,
        "generated": generated,
        "published": published,
    }


def _create_and_publish_media_item(
    monkeypatch,
    *,
    kind="video",
    slug=None,
    title="媒体详情测试",
    visibility="public",
):
    _allow_admin_access(monkeypatch)
    create_response = client.post(
        "/api/media/admin/items",
        json={
            "kind": kind,
            "slug": slug,
            "title": title,
            "summary": "**节目摘要：** 本期节目围绕媒体详情页的摘要、简介与目录结构展开。",
            "speaker": "节目组",
            "series_name": "媒体正式页",
            "episode_number": 1,
            "publish_date": "2026-04-15",
            "duration_seconds": 565,
            "visibility": visibility,
            "cover_image_url": f"/media-uploads/{kind}/cover/detail-cover.png",
            "media_url": f"/media-uploads/{kind}/media/detail-item.{'mp3' if kind == 'audio' else 'mp4'}",
            "source_url": f"/media-uploads/{kind}/media/detail-item.{'mp3' if kind == 'audio' else 'mp4'}",
            "body_markdown": (
                "## 节目简介\n\n"
                "本期节目按正式详情页思路组织内容，突出摘要、简介和章节目录。\n\n"
                "### 核心看点\n\n"
                "- 流页只负责发现与进入详情。\n"
                "- 正式页负责完整展示媒体内容。"
            ),
            "transcript_markdown": (
                "发言人 1 00:00\n先解释为什么媒体流和详情页需要拆开。\n\n"
                "发言人 1 00:42\n再说明摘要、简介和章节目录为什么要留在正式页。"
            ),
            "chapters": [
                {"timestamp_label": "00:00", "timestamp_seconds": 0, "title": "媒体流和详情页为何要拆开"},
                {"timestamp_label": "00:42", "timestamp_seconds": 42, "title": "摘要简介和目录为何留在正式页"},
            ],
        },
    )
    assert create_response.status_code == 200
    draft_id = create_response.json()["id"]

    publish_response = client.post(f"/api/media/admin/items/{draft_id}/publish")
    assert publish_response.status_code == 200
    return publish_response.json()
def test_media_script_upload_creates_draft_and_parses_text(monkeypatch):
    _allow_admin_access(monkeypatch)
    upload_root = _prepare_media_upload_root(monkeypatch)

    response = client.post(
        "/api/media/admin/upload",
        data={"kind": "audio", "usage": "transcript"},
        files={
            "file": (
                "founder-brief.md",
                "## 节目脚本\n\n围绕创始人决策复盘展开。\n\n00:00 开场\n\n00:48 进入案例。",
                "text/markdown",
            )
        },
    )
    assert response.status_code == 200
    payload = response.json()

    assert payload["usage"] == "transcript"
    assert payload["item"]["id"] > 0
    assert "创始人决策复盘" in payload["item"]["transcript_markdown"]
    assert payload["item"]["draft_box_state"] == "active"
    assert len(payload["item"]["chapters"]) >= 2
    assert payload["item"]["chapters"][0]["timestamp_label"] == "00:00"
    assert (upload_root / "audio" / "transcript" / payload["filename"]).exists()


def test_media_text_upload_prefers_ai_generated_chapters_when_available(monkeypatch):
    _allow_admin_access(monkeypatch)
    _prepare_media_upload_root(monkeypatch)
    monkeypatch.setattr(
        ai_service,
        "generate_media_chapter_outline",
        lambda **kwargs: {
            "chapters": [
                {"timestamp_label": "00:00", "title": "问题引入：机器人高毛利意味着什么"},
                {"timestamp_label": "00:57", "title": "核心悬念：盈利后为何仍急于募资"},
            ],
            "model": "gemini-2.5-flash",
        },
    )

    response = client.post(
        "/api/media/admin/upload",
        data={"kind": "audio", "usage": "transcript"},
        files={
            "file": (
                "ai-outline.md",
                "发言人 1 00:00\n欢迎来到节目。\n\n发言人 1 00:57\n看完招股书后我们回到募资问题。",
                "text/markdown",
            )
        },
    )
    assert response.status_code == 200
    payload = response.json()

    assert [item["timestamp_label"] for item in payload["item"]["chapters"]] == ["00:00", "00:57"]
    assert payload["item"]["chapters"][0]["title"] == "机器人高毛利意味着什么"
    assert payload["item"]["chapters"][1]["title"] == "盈利后为何仍急于募资"
    assert all("：" not in item["title"] for item in payload["item"]["chapters"])


def test_generate_media_chapter_outline_prefers_full_transcript_over_script(monkeypatch):
    transcript_middle_signal = "中段唯一线索 这里集中讨论供应链控制如何影响资本效率。"
    transcript_markdown = (
        "发言人 1 00:00\n开场先抛出问题。\n"
        + ("前文铺垫" * 3000)
        + f"\n{transcript_middle_signal}\n"
        + ("后文延展" * 3000)
        + "\n发言人 1 01:00\n结尾回到上市窗口。"
    )
    script_markdown = "00:00 脚本独有摘要\n01:00 脚本独有收尾"

    monkeypatch.setattr(ai_service, "is_ai_enabled", lambda: True)

    def fake_request_gemini_text(**kwargs):
        prompt = str(kwargs.get("prompt") or "")
        assert transcript_middle_signal in prompt
        assert "脚本独有摘要" not in prompt
        assert "[中段内容省略]" not in prompt
        return json.dumps(
            {
                "chapters": [
                    {"timestamp_label": "00:00", "title": "供应链控制如何改变资本效率"},
                    {"timestamp_label": "01:00", "title": "上市窗口为何取决于募资节奏"},
                ]
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr(ai_service, "_request_gemini_text", fake_request_gemini_text)

    payload = ai_service.generate_media_chapter_outline(
        title="Full Transcript Chapter Prompt",
        kind="audio",
        speaker="主持人",
        series_name="商业拆解",
        transcript_markdown=transcript_markdown,
        script_markdown=script_markdown,
    )

    assert [item["timestamp_label"] for item in payload["chapters"]] == ["00:00", "01:00"]
    assert [item["title"] for item in payload["chapters"]] == [
        "供应链控制如何改变资本效率",
        "上市窗口为何取决于募资节奏",
    ]
    assert payload["model"] == ai_service.GEMINI_CHAT_MODEL


def test_generate_media_text_assets_prefers_full_transcript_over_script(monkeypatch):
    transcript_middle_signal = "中段唯一线索 这里展开利润结构与资本开支的关系。"
    transcript_markdown = (
        "发言人 1 00:00\n开场先抛出利润问题。\n"
        + ("上文展开" * 3200)
        + f"\n{transcript_middle_signal}\n"
        + ("下文展开" * 3200)
        + "\n发言人 1 00:45\n结尾回到上市节奏。"
    )
    script_markdown = "00:00 脚本里的假主题\n00:45 脚本里的假结尾"

    monkeypatch.setattr(ai_service, "is_ai_enabled", lambda: True)

    def fake_request_gemini_text(**kwargs):
        prompt = str(kwargs.get("prompt") or "")
        assert transcript_middle_signal in prompt
        assert "脚本里的假主题" not in prompt
        assert "[中段内容省略]" not in prompt
        return json.dumps(
            {
                "summary": "**节目摘要：** 本期围绕利润结构与资本开支的关系展开。",
                "body_markdown": "## 节目简介\n\n本期节目拆解利润结构如何影响资本开支。\n\n### 核心看点\n\n- 毛利扩张背后的成本拆分\n- 资本开支如何牵动上市节奏",
                "chapters": [
                    {"timestamp_label": "00:00", "title": "利润结构如何决定资本开支"},
                    {"timestamp_label": "00:45", "title": "上市节奏为何被资本开支牵动"},
                ],
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr(ai_service, "_request_gemini_text", fake_request_gemini_text)

    payload = ai_service.generate_media_text_assets(
        title="Full Transcript Copy Prompt",
        kind="audio",
        speaker="主持人",
        series_name="商业拆解",
        transcript_markdown=transcript_markdown,
        script_markdown=script_markdown,
    )

    assert payload["summary"].startswith("**节目摘要：** 本期围绕利润结构与资本开支的关系展开")
    assert payload["body_markdown"].startswith("## 节目简介")
    assert [item["title"] for item in payload["chapters"]] == [
        "利润结构如何决定资本开支",
        "上市节奏为何被资本开支牵动",
    ]
    assert payload["model"] == ai_service.GEMINI_CHAT_MODEL


def test_media_text_upload_without_timestamps_keeps_chapters_empty(monkeypatch):
    _allow_admin_access(monkeypatch)
    _prepare_media_upload_root(monkeypatch)

    response = client.post(
        "/api/media/admin/upload",
        data={"kind": "video", "usage": "script"},
        files={
            "file": (
                "strategy-brief.md",
                "## 节目脚本\n\n本期节目围绕策略拆解展开。\n\n这里没有任何时间戳。",
                "text/markdown",
            )
        },
    )
    assert response.status_code == 200
    payload = response.json()

    assert payload["item"]["script_markdown"]
    assert payload["item"]["chapters"] == []


def test_media_speaker_timestamp_transcript_creates_chapters_from_following_content(monkeypatch):
    _allow_admin_access(monkeypatch)
    _prepare_media_upload_root(monkeypatch)

    response = client.post(
        "/api/media/admin/upload",
        data={"kind": "audio", "usage": "transcript"},
        files={
            "file": (
                "speaker-timestamps.md",
                (
                    "发言人 1 00:00↵\n"
                    "└ 欢迎来到复旦商业知识。今天我们先抛出一个反直觉的问题：一家机器人公司毛利率冲到 60%，这到底意味着什么？\n\n"
                    "发言人 1 00:57↵\n"
                    "看完招股书后，真正的悬念不是营收增长，而是公司已经盈利，为何还要急着募资 42 亿冲刺上市？\n\n"
                    "发言人 1 01:43↵\n"
                    "要解开这个问题，就得回到招股书里的利润结构、费用安排和资本路径。"
                ),
                "text/markdown",
            )
        },
    )
    assert response.status_code == 200
    payload = response.json()

    chapters = payload["item"]["chapters"]
    assert [item["timestamp_label"] for item in chapters] == ["00:00", "00:57", "01:43"]
    assert any(keyword in chapters[0]["title"] for keyword in ("毛利", "商业逻辑", "机器人公司"))
    assert any(keyword in chapters[1]["title"] for keyword in ("募资", "上市", "悬念"))
    assert any(keyword in chapters[2]["title"] for keyword in ("招股书", "资本路径", "利润结构"))
    assert all("欢迎来到" not in item["title"] for item in chapters)
    assert all("看完招股书后" not in item["title"] for item in chapters)
    assert all("↵" not in item["title"] for item in chapters)
    assert all("：" not in item["title"] for item in chapters)
    assert len({item["title"] for item in chapters}) == len(chapters)


def test_media_update_script_markdown_rebuilds_chapters_without_explicit_chapter_payload(monkeypatch):
    _allow_admin_access(monkeypatch)
    monkeypatch.setattr(
        ai_service,
        "generate_media_chapter_outline",
        lambda **kwargs: {
            "chapters": [
                {"timestamp_label": "00:00", "title": "问题引入：开场抛出核心问题"},
                {"timestamp_label": "00:42", "title": "案例拆解：进入关键事实"},
                {"timestamp_label": "01:18", "title": "收束判断：回到发布复盘"},
            ],
            "model": "gemini-2.5-flash",
        },
    )
    create_response = client.post(
        "/api/media/admin/items",
        json={
            "kind": "video",
            "title": "Chapter Refresh Draft",
            "publish_date": "2026-04-14",
        },
    )
    assert create_response.status_code == 200
    draft_id = create_response.json()["id"]

    update_response = client.put(
        f"/api/media/admin/items/{draft_id}",
        json={
            "script_markdown": "00:00 开场\n00:42 进入案例\n01:18 回到发布复盘",
        },
    )
    assert update_response.status_code == 200
    updated = update_response.json()

    assert len(updated["chapters"]) == 3
    assert [item["timestamp_label"] for item in updated["chapters"]] == ["00:00", "00:42", "01:18"]
    assert [item["title"] for item in updated["chapters"]] == [
        "开场抛出核心问题",
        "进入关键事实",
        "回到发布复盘",
    ]


def test_media_save_with_same_script_markdown_keeps_existing_chapters(monkeypatch):
    _allow_admin_access(monkeypatch)
    chapter_calls = []

    def fake_generate_chapters(**kwargs):
        chapter_calls.append(str(kwargs.get("script_markdown") or kwargs.get("transcript_markdown") or ""))
        return {
            "chapters": [
                {"timestamp_label": "00:00", "title": "问题引入：第一次章节"},
                {"timestamp_label": "00:42", "title": "案例拆解：第二部分"},
            ],
            "model": "gemini-2.5-flash",
        }

    monkeypatch.setattr(ai_service, "generate_media_chapter_outline", fake_generate_chapters)
    create_response = client.post(
        "/api/media/admin/items",
        json={
            "kind": "video",
            "title": "Stable Save Draft",
            "publish_date": "2026-04-15",
        },
    )
    assert create_response.status_code == 200
    draft_id = create_response.json()["id"]

    first_update = client.put(
        f"/api/media/admin/items/{draft_id}",
        json={
            "script_markdown": "00:00 开场\n00:42 进入案例",
        },
    )
    assert first_update.status_code == 200
    first_payload = first_update.json()
    assert len(chapter_calls) == 1
    assert [item["title"] for item in first_payload["chapters"]] == ["第一次章节", "第二部分"]

    second_update = client.put(
        f"/api/media/admin/items/{draft_id}",
        json={
            "title": "Stable Save Draft Renamed",
            "script_markdown": "00:00 开场\n00:42 进入案例",
        },
    )
    assert second_update.status_code == 200
    second_payload = second_update.json()

    assert len(chapter_calls) == 1
    assert second_payload["title"] == "Stable Save Draft Renamed"
    assert second_payload["chapters"] == first_payload["chapters"]


def test_media_rewrite_chapters_endpoint_refreshes_outline_without_regenerating_copy(monkeypatch):
    _allow_admin_access(monkeypatch)
    chapter_versions = iter(
        [
            {
                "chapters": [
                    {"timestamp_label": "00:00", "title": "问题引入：第一次章节"},
                    {"timestamp_label": "00:42", "title": "案例拆解：第一次第二节"},
                ],
                "model": "gemini-2.5-flash",
            },
            {
                "chapters": [
                    {"timestamp_label": "00:00", "title": "问题引入：重写后的新章节"},
                    {"timestamp_label": "00:42", "title": "案例拆解：重写后的第二节"},
                ],
                "model": "gemini-2.5-flash",
            },
        ]
    )
    monkeypatch.setattr(ai_service, "generate_media_chapter_outline", lambda **kwargs: next(chapter_versions))

    create_response = client.post(
        "/api/media/admin/items",
        json={
            "kind": "video",
            "title": "Rewrite Chapter Draft",
            "publish_date": "2026-04-15",
        },
    )
    assert create_response.status_code == 200
    draft_id = create_response.json()["id"]

    update_response = client.put(
        f"/api/media/admin/items/{draft_id}",
        json={
            "summary": "**节目摘要：** 固定摘要。",
            "body_markdown": "## 节目简介\n\n固定简介。",
            "script_markdown": "00:00 开场\n00:42 进入案例",
        },
    )
    assert update_response.status_code == 200
    initial = update_response.json()
    assert [item["title"] for item in initial["chapters"]] == ["第一次章节", "第一次第二节"]

    rewrite_response = client.post(f"/api/media/admin/items/{draft_id}/rewrite-chapters")
    assert rewrite_response.status_code == 200
    rewritten = rewrite_response.json()

    assert rewritten["summary"] == initial["summary"]
    assert rewritten["body_markdown"] == initial["body_markdown"]
    assert [item["title"] for item in rewritten["chapters"]] == ["重写后的新章节", "重写后的第二节"]


def test_media_rewrite_chapters_fallback_prefers_transcript_over_script(monkeypatch):
    _allow_admin_access(monkeypatch)
    monkeypatch.setattr(
        ai_service,
        "generate_media_chapter_outline",
        lambda **kwargs: {"chapters": [], "model": "gemini-2.5-flash"},
    )

    create_response = client.post(
        "/api/media/admin/items",
        json={
            "kind": "video",
            "title": "Rewrite Chapter Transcript First",
            "publish_date": "2026-04-15",
        },
    )
    assert create_response.status_code == 200
    draft_id = create_response.json()["id"]

    update_response = client.put(
        f"/api/media/admin/items/{draft_id}",
        json={
            "transcript_markdown": (
                "发言人 1 00:00\n先讨论盈利结构为什么会变化。\n\n"
                "发言人 1 00:57\n再讨论上市窗口和募资节奏。"
            ),
            "script_markdown": "00:00 脚本假开场\n09:09 脚本假收尾",
            "chapters": [
                {"timestamp_label": "00:00", "timestamp_seconds": 0, "title": "待重写旧标题一"},
                {"timestamp_label": "09:09", "timestamp_seconds": 549, "title": "待重写旧标题二"},
            ],
        },
    )
    assert update_response.status_code == 200

    rewrite_response = client.post(f"/api/media/admin/items/{draft_id}/rewrite-chapters")
    assert rewrite_response.status_code == 200
    rewritten = rewrite_response.json()

    assert [item["timestamp_label"] for item in rewritten["chapters"]] == ["00:00", "00:57"]
    assert rewritten["chapters"][0]["title"] != "待重写旧标题一"
    assert rewritten["chapters"][1]["title"] != "待重写旧标题二"
    assert all(item["timestamp_label"] != "09:09" for item in rewritten["chapters"])


def test_media_generate_copy_forces_chapter_refresh_from_latest_source(monkeypatch):
    _allow_admin_access(monkeypatch)
    create_response = client.post(
        "/api/media/admin/items",
        json={
            "kind": "video",
            "title": "Generate Copy Refresh Draft",
            "publish_date": "2026-04-15",
        },
    )
    assert create_response.status_code == 200
    draft_id = create_response.json()["id"]

    update_response = client.put(
        f"/api/media/admin/items/{draft_id}",
        json={
            "script_markdown": "00:00 开场\n00:42 进入案例",
            "chapters": [
                {"timestamp_label": "00:00", "timestamp_seconds": 0, "title": "旧章节一"},
                {"timestamp_label": "00:42", "timestamp_seconds": 42, "title": "旧章节二"},
            ],
        },
    )
    assert update_response.status_code == 200

    monkeypatch.setattr(
        ai_service,
        "generate_media_text_assets",
        lambda **kwargs: {
            "summary": "**节目摘要：** 生成文案时同步重写章节。",
            "body_markdown": "## 节目简介\n\n生成文案会强制刷新章节。",
            "chapters": [
                {"timestamp_label": "00:00", "title": "问题引入：生成后的新章节"},
                {"timestamp_label": "00:42", "title": "案例拆解：生成后的第二章节"},
            ],
            "model": "media-copy-test-model",
        },
    )

    generated_response = client.post(f"/api/media/admin/items/{draft_id}/generate-copy")
    assert generated_response.status_code == 200
    generated = generated_response.json()

    assert generated["summary"].startswith("**节目摘要：** 生成文案时同步重写章节")
    assert [item["title"] for item in generated["chapters"]] == ["生成后的新章节", "生成后的第二章节"]


def test_media_draft_workflow_generates_copy_publishes_and_leaves_draft_box(monkeypatch):
    workflow = _publish_video_media_draft(monkeypatch, stem="video-workflow")
    generated = workflow["generated"]
    published = workflow["published"]
    upload_root = workflow["upload_root"]

    assert generated["copy_model"] == "media-copy-test-model"
    assert generated["summary"].startswith("**节目摘要：** 节目围绕音视频工作流对齐展开")
    assert generated["body_markdown"].startswith("## 节目简介")
    assert "### 核心看点" in generated["body_markdown"]
    assert 1 <= generated["body_markdown"].count("\n- ") <= 3
    assert [item["title"] for item in generated["chapters"]] == [
        "上传先进入草稿箱",
        "脚本识别与文案生成",
        "正式页重新进入编辑",
    ]

    assert published["status"] == "published"
    assert published["workflow_status"] == "published"
    assert published["draft_box_state"] == "archived"
    assert published["media_item_id"] is not None
    assert published["published_summary"] == generated["summary"]
    assert published["published_body_markdown"] == generated["body_markdown"]
    assert (upload_root / "video" / "media" / workflow["media_upload"]["filename"]).exists()

    active_response = client.get("/api/media/admin/items")
    assert active_response.status_code == 200
    active_ids = {item["id"] for item in active_response.json()["items"]}
    assert workflow["draft_id"] not in active_ids

    deleted_detail_response = client.get(f"/api/media/admin/items/{workflow['draft_id']}")
    assert deleted_detail_response.status_code == 404

    source_response = client.get("/api/media/video?limit=20")
    assert source_response.status_code == 200
    source_items = source_response.json()["items"]
    assert published["media_item_id"] in {item["media_item_id"] for item in source_items}


def test_media_summary_markdown_normalization_and_excerpt_strip_markdown():
    summary = ai_service.normalize_media_summary_markdown("下面是节目摘要：本期围绕媒体工作台的上传、生成与发布链路展开。")

    assert summary.startswith("**节目摘要：**")
    assert "下面是" not in summary

    excerpt = media_service._extract_excerpt(summary)
    assert excerpt.startswith("节目摘要：")
    assert "**" not in excerpt


def test_media_body_markdown_normalization_adds_takeaways_and_caps_at_three():
    body = ai_service.normalize_media_body_markdown(
        "## 节目简介\n\n本期节目拆解媒体工作台的上传、生成与发布链路。\n\n- 第一条要点\n- 第二条要点\n- 第三条要点\n- 第四条要点",
        summary="**节目摘要：** 本期节目拆解媒体工作台的上传、生成与发布链路。",
        source_text="00:00 上传主媒体\n00:35 补充脚本\n01:10 生成节目简介\n01:48 发布并重新编辑",
    )

    assert body.startswith("## 节目简介")
    assert "### 核心看点" in body
    assert 1 <= body.count("\n- ") <= 3
    assert "第四条要点" not in body


def test_media_generated_chapters_normalization_strips_labels_and_deduplicates_titles():
    chapters = ai_service.normalize_media_generated_chapters(
        [
            {"timestamp_label": "00:00", "title": "问题引入：机器人公司 60% 毛利意味着什么"},
            {"timestamp_label": "00:57", "title": "行业背景：人形机器人热潮与具身智能逻辑"},
            {"timestamp_label": "01:43", "title": "行业背景：人形机器人热潮与具身智能逻辑"},
        ],
        source_text="00:00 开场\n00:57 进入行业背景\n01:43 回到不同部分",
    )

    assert [item["timestamp_label"] for item in chapters] == ["00:00", "00:57"]
    assert chapters[0]["title"] == "机器人公司 60% 毛利意味着什么"
    assert chapters[1]["title"] == "人形机器人热潮与具身智能逻辑"
    assert all("：" not in item["title"] for item in chapters)


def test_media_chapter_fallback_builds_direct_workflow_titles():
    chapters = media_service._extract_media_chapters_from_text(
        "发言人 1 00:00\n今天我们先抛出一个问题：媒体上传后为什么先进入草稿箱，而不是直接上线？\n\n"
        "发言人 1 00:42\n接下来真正要拆的是工作流逻辑：脚本上传、章节识别和生成文案为什么要放在同一个后台页面里。\n\n"
        "发言人 1 01:25\n最后回到发布动作，解释为什么正式上线后要自动离开草稿箱，并且从正式页重新进入编辑流。"
    )

    assert [item["timestamp_label"] for item in chapters] == ["00:00", "00:42", "01:25"]
    assert chapters[0]["title"] == "媒体上传后为何先进入草稿箱"
    assert chapters[1]["title"] == "脚本上传和章节识别为何放在同一后台"
    assert chapters[2]["title"] == "正式上线后为何自动离开草稿箱"
    assert all("：" not in item["title"] for item in chapters)
    assert all("先抛出一个问题" not in item["title"] for item in chapters)
    assert all("要拆的是" not in item["title"] for item in chapters)
    assert len({item["title"] for item in chapters}) == len(chapters)


def test_media_cover_upload_persists_into_published_item(monkeypatch):
    workflow = _publish_video_media_draft(monkeypatch, stem="video-cover-workflow", with_cover=True)
    published = workflow["published"]
    upload_root = workflow["upload_root"]
    cover_upload = workflow["cover_upload"]

    assert cover_upload is not None
    assert cover_upload["usage"] == "cover"
    assert cover_upload["url"].startswith("/media-uploads/video/cover/")
    assert published["cover_image_url"] == cover_upload["url"]
    assert (upload_root / "video" / "cover" / cover_upload["filename"]).exists()

    source_response = client.get("/api/media/video?limit=20")
    assert source_response.status_code == 200
    items = source_response.json()["items"]
    item = next(entry for entry in items if entry["media_item_id"] == published["media_item_id"])
    assert item["cover_image_url"] == cover_upload["url"]


def test_public_media_detail_route_returns_summary_body_and_chapters(monkeypatch):
    published = _create_and_publish_media_item(
        monkeypatch,
        kind="video",
        slug="detail-video-program",
        title="媒体详情页视频样本",
        visibility="public",
    )
    monkeypatch.setattr(
        media_router,
        "get_authenticated_user",
        lambda authorization, debug_user_id=None, debug_user_email=None: None,
    )

    response = client.get(f"/api/media/video/{published['slug']}")
    assert response.status_code == 200
    payload = response.json()

    assert payload["slug"] == "detail-video-program"
    assert payload["kind"] == "video"
    assert payload["accessible"] is True
    assert payload["media_url"] == published["media_url"]
    assert payload["cover_image_url"] == published["cover_image_url"]
    assert payload["summary"].startswith("**节目摘要：**")
    assert payload["body_markdown"].startswith("## 节目简介")
    assert [item["timestamp_label"] for item in payload["chapters"]] == ["00:00", "00:42"]
    assert [item["title"] for item in payload["chapters"]] == [
        "媒体流和详情页为何要拆开",
        "摘要简介和目录为何留在正式页",
    ]


def test_paid_media_detail_route_keeps_preview_and_gate_copy_for_guest(monkeypatch):
    published = _create_and_publish_media_item(
        monkeypatch,
        kind="audio",
        slug="detail-audio-paid",
        title="受限音频详情样本",
        visibility="paid",
    )
    monkeypatch.setattr(
        media_router,
        "get_authenticated_user",
        lambda authorization, debug_user_id=None, debug_user_email=None: None,
    )

    response = client.get(f"/api/media/audio/{published['slug']}")
    assert response.status_code == 200
    payload = response.json()

    assert payload["kind"] == "audio"
    assert payload["visibility"] == "paid"
    assert payload["accessible"] is False
    assert payload["media_url"] is None
    assert payload["preview_url"] == published["media_url"]
    assert payload["preview_duration_seconds"] == 60
    assert payload["gate_copy"]
    assert payload["body_markdown"].startswith("## 节目简介")
    assert len(payload["chapters"]) == 2


def test_media_edit_published_item_reuses_existing_draft(monkeypatch):
    workflow = _publish_video_media_draft(monkeypatch, stem="reopen-video")
    published = workflow["published"]

    first_reopen = client.post(f"/api/media/admin/published-items/{published['media_item_id']}/edit-draft")
    assert first_reopen.status_code == 200
    reopened = first_reopen.json()

    assert reopened["media_item_id"] == published["media_item_id"]
    assert reopened["status"] == "draft"
    assert reopened["workflow_status"] == "draft"
    assert reopened["draft_box_state"] == "active"
    assert reopened["is_reopened_from_published"] is True

    second_reopen = client.post(f"/api/media/admin/published-items/{published['media_item_id']}/edit-draft")
    assert second_reopen.status_code == 200
    assert second_reopen.json()["id"] == reopened["id"]

    active_response = client.get("/api/media/admin/items?kind=video")
    assert active_response.status_code == 200
    active_ids = {item["id"] for item in active_response.json()["items"]}
    assert reopened["id"] in active_ids


def test_deleting_reopened_media_draft_keeps_published_media_item(monkeypatch):
    workflow = _publish_video_media_draft(monkeypatch, stem="delete-reopened-video")
    published = workflow["published"]

    reopen_response = client.post(f"/api/media/admin/published-items/{published['media_item_id']}/edit-draft")
    assert reopen_response.status_code == 200
    reopened = reopen_response.json()

    delete_response = client.delete(f"/api/media/admin/items/{reopened['id']}")
    assert delete_response.status_code == 200
    assert delete_response.json()["deleted"] is True

    draft_response = client.get("/api/media/admin/items?kind=video&limit=40")
    assert draft_response.status_code == 200
    assert reopened["id"] not in {item["id"] for item in draft_response.json()["items"]}

    source_response = client.get("/api/media/video?limit=40")
    assert source_response.status_code == 200
    assert published["media_item_id"] in {item["media_item_id"] for item in source_response.json()["items"]}
