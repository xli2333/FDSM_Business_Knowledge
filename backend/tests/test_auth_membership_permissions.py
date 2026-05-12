from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from backend.database import connection_scope
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

VIDEO_FIXTURE_SLUGS = (
    "test-media-permission-public-video",
    "test-media-permission-member-video",
    "test-media-permission-paid-video",
)


@pytest.fixture()
def media_permission_video_slugs():
    timestamp = datetime.now().replace(microsecond=0).isoformat()
    rows = [
        (VIDEO_FIXTURE_SLUGS[0], "public", 1),
        (VIDEO_FIXTURE_SLUGS[1], "member", 2),
        (VIDEO_FIXTURE_SLUGS[2], "paid", 3),
    ]
    with connection_scope() as connection:
        connection.execute(
            "DELETE FROM media_items WHERE slug IN (?, ?, ?)",
            VIDEO_FIXTURE_SLUGS,
        )
        connection.executemany(
            """
            INSERT INTO media_items (
                slug,
                kind,
                title,
                summary,
                speaker,
                publish_date,
                duration_seconds,
                visibility,
                status,
                cover_image_url,
                source_url,
                body_markdown,
                sort_order,
                created_at,
                updated_at
            )
            VALUES (?, 'video', ?, ?, 'Test Suite', '2099-01-01', 120, ?, 'published', '', '', 'Test body', ?, ?, ?)
            """,
            [
                (slug, f"Permission video {order}", f"Permission fixture {visibility}", visibility, order, timestamp, timestamp)
                for slug, visibility, order in rows
            ],
        )
        connection.commit()
    try:
        yield VIDEO_FIXTURE_SLUGS
    finally:
        with connection_scope() as connection:
            connection.execute(
                "DELETE FROM media_items WHERE slug IN (?, ?, ?)",
                VIDEO_FIXTURE_SLUGS,
            )
            connection.commit()


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


def test_media_permissions_split_free_and_paid_members(media_permission_video_slugs):
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

    free_video_map = {
        slug: client.get(f"/api/media/video/{slug}", headers=FREE_HEADERS).json()
        for slug in media_permission_video_slugs
    }
    paid_video_map = {
        slug: client.get(f"/api/media/video/{slug}", headers=PAID_HEADERS).json()
        for slug in media_permission_video_slugs
    }
    public_slug, member_slug, paid_slug = media_permission_video_slugs
    assert free_video["viewer_tier"] == "free_member"
    assert paid_video["viewer_tier"] == "paid_member"
    assert free_video_map[public_slug]["accessible"] is True
    assert free_video_map[member_slug]["accessible"] is True
    assert free_video_map[paid_slug]["accessible"] is False
    assert free_video_map[paid_slug]["preview_duration_seconds"] == 60
    assert all(item["accessible"] is True for item in paid_video_map.values())
