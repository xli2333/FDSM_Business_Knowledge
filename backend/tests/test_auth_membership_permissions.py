from fastapi.testclient import TestClient

from backend.main import app


client = TestClient(app)

FREE_HEADERS = {
    "X-Debug-User-Id": "mock-free-member",
    "X-Debug-User-Email": "reader@example.com",
}

PAID_HEADERS = {
    "X-Debug-User-Id": "mock-paid-member",
    "X-Debug-User-Email": "paid@example.com",
}


def test_auth_status_restores_free_and_paid_memberships_in_local_preview_mode():
    free_status = client.get("/api/auth/status", headers=FREE_HEADERS).json()
    paid_status = client.get("/api/auth/status", headers=PAID_HEADERS).json()

    assert free_status["enabled"] is True
    assert free_status["authenticated"] is True
    assert free_status["auth_mode"] == "password"
    assert free_status["membership"]["tier"] == "free_member"
    assert free_status["membership"]["can_access_member"] is True
    assert free_status["membership"]["can_access_paid"] is False
    assert free_status["role_home_path"] == "/me"

    assert paid_status["enabled"] is True
    assert paid_status["authenticated"] is True
    assert paid_status["auth_mode"] == "password"
    assert paid_status["membership"]["tier"] == "paid_member"
    assert paid_status["membership"]["can_access_member"] is True
    assert paid_status["membership"]["can_access_paid"] is True
    assert paid_status["role_home_path"] == "/membership"


def test_password_login_returns_paid_member_profile():
    response = client.post(
        "/api/auth/login",
        json={"email": "paid@example.com", "password": "Paid2026!"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["authenticated"] is True
    assert payload["auth_mode"] == "password"
    assert payload["membership"]["tier"] == "paid_member"
    assert payload["membership"]["can_access_paid"] is True
    assert payload["role_home_path"] == "/membership"


def test_media_permissions_split_free_and_paid_members():
    free_membership = client.get("/api/membership/me", headers=FREE_HEADERS).json()
    paid_membership = client.get("/api/membership/me", headers=PAID_HEADERS).json()
    free_audio = client.get("/api/media/audio?limit=24", headers=FREE_HEADERS).json()
    paid_audio = client.get("/api/media/audio?limit=24", headers=PAID_HEADERS).json()
    free_video = client.get("/api/media/video?limit=24", headers=FREE_HEADERS).json()
    paid_video = client.get("/api/media/video?limit=24", headers=PAID_HEADERS).json()

    assert free_membership["tier"] == "free_member"
    assert free_membership["can_access_member"] is True
    assert free_membership["can_access_paid"] is False
    assert paid_membership["tier"] == "paid_member"
    assert paid_membership["can_access_paid"] is True

    assert free_audio["viewer_tier"] == "free_member"
    assert paid_audio["viewer_tier"] == "paid_member"
    assert free_audio["items"]
    assert paid_audio["items"]
    assert all(item["visibility"] == "paid" for item in free_audio["items"])
    assert all(item["accessible"] is False for item in free_audio["items"])
    assert all(item["preview_duration_seconds"] == 60 for item in free_audio["items"])
    assert all(item["accessible"] is True for item in paid_audio["items"])
    assert all(item["preview_duration_seconds"] == 0 for item in paid_audio["items"])

    free_video_map = {item["slug"]: item for item in free_video["items"]}
    paid_video_map = {item["slug"]: item for item in paid_video["items"]}
    assert free_video["viewer_tier"] == "free_member"
    assert paid_video["viewer_tier"] == "paid_member"
    assert free_video_map["video-industry-observer"]["accessible"] is True
    assert free_video_map["video-classroom-clip"]["accessible"] is True
    assert free_video_map["video-ceo-deep-briefing"]["accessible"] is False
    assert free_video_map["video-ceo-deep-briefing"]["preview_duration_seconds"] == 60
    assert all(item["accessible"] is True for item in paid_video_map.values())
