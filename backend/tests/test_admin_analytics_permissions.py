from __future__ import annotations

from fastapi.testclient import TestClient

from backend.main import app
from backend.routers import analytics as analytics_router

client = TestClient(app)


def test_analytics_overview_requires_login():
    response = client.get("/api/analytics/overview")
    assert response.status_code == 401


def test_admin_can_access_analytics_overview(monkeypatch):
    admin_user = {"id": "admin-analytics", "email": "admin@example.com"}
    monkeypatch.setattr(
        analytics_router,
        "get_authenticated_user",
        lambda authorization, debug_user_id=None, debug_user_email=None: admin_user,
    )
    monkeypatch.setattr(analytics_router, "require_admin_profile", lambda user: {"is_admin": True})
    monkeypatch.setattr(
        analytics_router,
        "get_analytics_overview",
        lambda: {
            "metrics": [{"label": "累计浏览", "value": "100", "detail": "测试"}],
            "views_trend": [{"label": "04-03", "value": 10}],
            "top_viewed": [],
            "top_liked": [],
            "top_bookmarked": [],
        },
    )

    response = client.get("/api/analytics/overview")
    assert response.status_code == 200
    payload = response.json()
    assert payload["metrics"][0]["value"] == "100"
    assert payload["views_trend"][0]["value"] == 10
