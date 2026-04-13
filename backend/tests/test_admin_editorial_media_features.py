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
from backend.routers import editorial as editorial_router
from backend.routers import media as media_router
from backend.services import ai_service, editorial_service, media_service

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

    reopen_response = client.post(f'/api/editorial/source-articles/{article_id}/reopen-draft')
    assert reopen_response.status_code == 200
    reopened = reopen_response.json()

    assert reopened['id'] == editorial_id
    assert reopened['draft_box_state'] == 'active'
    assert reopened['status'] == 'published'
    assert reopened['workflow_status'] == 'draft'
    assert reopened['is_reopened_from_published'] is True
    assert reopened['article_id'] == article_id

    active_after_reopen = client.get('/api/editorial/articles')
    assert active_after_reopen.status_code == 200
    assert editorial_id in {item['id'] for item in active_after_reopen.json()}

    reopen_again = client.post(f'/api/editorial/source-articles/{article_id}/reopen-draft')
    assert reopen_again.status_code == 200
    assert reopen_again.json()['id'] == editorial_id

    removed_route = client.post(f'/api/editorial/articles/{editorial_id}/archive-draft-box')
    assert removed_route.status_code == 404

def test_reopen_non_editorial_article_creates_single_linked_editorial_draft(monkeypatch):
    _allow_admin_access(monkeypatch)

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
            VALUES (?, ?, ?, ?, 'business', 'import', ?, '2026-04-10', NULL, ?, ?, ?, ?, 'Original Column', ?, '', '', ?, ?, ?, NULL, 'public', 0, 0, ?, ?)
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
    upload_root = Path("backend/tests/_tmp_media_uploads").resolve()
    if upload_root.exists():
        for path in sorted(upload_root.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
    upload_root.mkdir(parents=True, exist_ok=True)
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
            "summary": "节目围绕音视频工作流对齐展开，说明上传、转录和发布如何贯通。",
            "body_markdown": "## 节目简介\n\n节目从后台工作流切入，说明主媒体、转录和脚本如何驱动发布素材生成。\n\n同时点出草稿箱、回编和重新发布之间的关系。",
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
    assert (upload_root / "audio" / "transcript" / payload["filename"]).exists()


def test_media_draft_workflow_generates_copy_publishes_and_leaves_draft_box(monkeypatch):
    workflow = _publish_video_media_draft(monkeypatch, stem="video-workflow")
    generated = workflow["generated"]
    published = workflow["published"]
    upload_root = workflow["upload_root"]

    assert generated["copy_model"] == "media-copy-test-model"
    assert generated["summary"].startswith("节目围绕音视频工作流对齐展开")
    assert generated["body_markdown"].startswith("## 节目简介")
    assert len(generated["chapters"]) >= 2

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

    source_response = client.get("/api/media/admin/source-items?kind=video&query=video%20workflow")
    assert source_response.status_code == 200
    source_items = source_response.json()["items"]
    assert published["media_item_id"] in {item["id"] for item in source_items}


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


def test_media_reopen_reuses_existing_draft(monkeypatch):
    workflow = _publish_video_media_draft(monkeypatch, stem="reopen-video")
    published = workflow["published"]

    first_reopen = client.post(f"/api/media/admin/source-items/{published['media_item_id']}/reopen-draft")
    assert first_reopen.status_code == 200
    reopened = first_reopen.json()

    assert reopened["media_item_id"] == published["media_item_id"]
    assert reopened["status"] == "draft"
    assert reopened["workflow_status"] == "draft"
    assert reopened["draft_box_state"] == "active"
    assert reopened["is_reopened_from_published"] is True

    second_reopen = client.post(f"/api/media/admin/source-items/{published['media_item_id']}/reopen-draft")
    assert second_reopen.status_code == 200
    assert second_reopen.json()["id"] == reopened["id"]

    active_response = client.get("/api/media/admin/items?kind=video")
    assert active_response.status_code == 200
    active_ids = {item["id"] for item in active_response.json()["items"]}
    assert reopened["id"] in active_ids


def test_deleting_reopened_media_draft_keeps_published_media_item(monkeypatch):
    workflow = _publish_video_media_draft(monkeypatch, stem="delete-reopened-video")
    published = workflow["published"]

    reopen_response = client.post(f"/api/media/admin/source-items/{published['media_item_id']}/reopen-draft")
    assert reopen_response.status_code == 200
    reopened = reopen_response.json()

    delete_response = client.delete(f"/api/media/admin/items/{reopened['id']}")
    assert delete_response.status_code == 200
    assert delete_response.json()["deleted"] is True

    draft_response = client.get("/api/media/admin/items?kind=video&limit=40")
    assert draft_response.status_code == 200
    assert reopened["id"] not in {item["id"] for item in draft_response.json()["items"]}

    source_response = client.get("/api/media/admin/source-items?kind=video&limit=40")
    assert source_response.status_code == 200
    assert published["media_item_id"] in {item["id"] for item in source_response.json()["items"]}
