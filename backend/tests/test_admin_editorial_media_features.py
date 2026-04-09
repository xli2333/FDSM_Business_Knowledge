from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from backend.main import app
from backend.routers import editorial as editorial_router
from backend.routers import media as media_router
from backend.services import ai_service, media_service

client = TestClient(app)


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
            "markdown": "# 自动排版标题\n\n## 核心要点\n\n- 保留事实\n- 提升结构",
            "model": "gemini-3-flash-preview",
        },
    )

    create_response = client.post(
        "/api/editorial/articles",
        json={
            "title": "自动排版测试",
            "source_markdown": "原稿第一段\n\n原稿第二段",
            "content_markdown": "原稿第一段\n\n原稿第二段",
            "layout_mode": "auto",
        },
    )
    assert create_response.status_code == 200
    editorial_id = create_response.json()["id"]

    format_response = client.post(
        f"/api/editorial/articles/{editorial_id}/auto-format",
        json={
            "source_markdown": "原稿第一段\n\n原稿第二段",
            "layout_mode": "briefing",
            "formatting_notes": "保留列表感",
        },
    )
    assert format_response.status_code == 200
    payload = format_response.json()

    assert payload["formatter_model"] == "gemini-3-flash-preview"
    assert payload["layout_mode"] == "briefing"
    assert payload["formatting_notes"] == "保留列表感"
    assert payload["content_markdown"].startswith("# 自动排版标题")
    assert payload["source_markdown"] == "原稿第一段\n\n原稿第二段"


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
