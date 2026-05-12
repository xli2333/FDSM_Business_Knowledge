from datetime import datetime

import pytest
from fastapi.testclient import TestClient

import backend.routers.media as media_router
from backend.database import connection_scope
from backend.main import app


client = TestClient(app)

STREAM_SLUG = "test-paid-stream-query-token"


@pytest.fixture()
def paid_stream_media_item():
    timestamp = datetime.now().replace(microsecond=0).isoformat()
    with connection_scope() as connection:
        connection.execute("DELETE FROM media_items WHERE slug = ?", (STREAM_SLUG,))
        connection.execute(
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
                media_url,
                preview_url,
                source_url,
                body_markdown,
                transcript_markdown,
                chapter_payload_json,
                sort_order,
                created_at,
                updated_at
            )
            VALUES (
                ?,
                'audio',
                'Paid stream fixture',
                'Stream auth fixture',
                'Test Suite',
                '2099-01-01',
                120,
                'paid',
                'published',
                '',
                '/media-uploads/audio/media/test-paid-stream-query-token.mp3',
                '',
                '/media-uploads/audio/media/test-paid-stream-query-token.mp3',
                'Body',
                '',
                '[]',
                1,
                ?,
                ?
            )
            """,
            (STREAM_SLUG, timestamp, timestamp),
        )
        connection.commit()
    try:
        yield STREAM_SLUG
    finally:
        with connection_scope() as connection:
            connection.execute("DELETE FROM media_items WHERE slug = ?", (STREAM_SLUG,))
            connection.commit()


@pytest.fixture()
def stream_auth_mocks(monkeypatch):
    def fake_authenticated_user(authorization, **_kwargs):
        if authorization == "Bearer stream-test-token":
            return {"id": "stream-paid-user", "email": "paid@example.com"}
        return None

    def fake_membership_profile(user):
        if user:
            return {
                "tier": "paid_member",
                "can_access_member": True,
                "can_access_paid": True,
            }
        return {
            "tier": "guest",
            "can_access_member": False,
            "can_access_paid": False,
        }

    monkeypatch.setattr(media_router, "get_authenticated_user", fake_authenticated_user)
    monkeypatch.setattr(media_router, "get_membership_profile", fake_membership_profile)


def test_paid_media_stream_rejects_missing_token(paid_stream_media_item, stream_auth_mocks):
    response = client.get(f"/api/media/audio/{paid_stream_media_item}/stream")

    assert response.status_code == 403


def test_paid_media_stream_accepts_query_token(paid_stream_media_item, stream_auth_mocks):
    response = client.get(f"/api/media/audio/{paid_stream_media_item}/stream?token=stream-test-token")

    assert response.status_code == 200
    assert response.headers["x-accel-redirect"] == "/media-uploads/audio/media/test-paid-stream-query-token.mp3"
    assert response.headers["cache-control"] == "private, max-age=300"


def test_paid_media_stream_still_accepts_authorization_header(paid_stream_media_item, stream_auth_mocks):
    response = client.get(
        f"/api/media/audio/{paid_stream_media_item}/stream",
        headers={"Authorization": "Bearer stream-test-token"},
    )

    assert response.status_code == 200
    assert response.headers["x-accel-redirect"] == "/media-uploads/audio/media/test-paid-stream-query-token.mp3"
