from __future__ import annotations

from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_today_read_returns_structured_followups_and_persists_session_detail():
    response = client.post(
        "/api/chat",
        json={
            "messages": [{"role": "user", "content": "/\u4eca\u65e5\u4e00\u8bfb"}],
            "language": "zh",
        },
    )
    assert response.status_code == 200
    payload = response.json()

    assert payload["answer"].startswith("## \u4eca\u65e5\u4e00\u8bfb")
    assert payload["sources"]
    assert payload["follow_up_questions"]
    assert payload["follow_up_questions"][0].startswith("/\u7b80\u62a5 ")

    detail_response = client.get(f"/api/chat/session/{payload['session_id']}")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assistant_messages = [message for message in detail["messages"] if message["role"] == "assistant"]
    assert assistant_messages
    assert assistant_messages[-1]["follow_ups"] == payload["follow_up_questions"]


def test_today_read_accepts_explicit_reading_date_argument():
    response = client.post(
        "/api/chat",
        json={
            "messages": [{"role": "user", "content": "/\u4eca\u65e5\u4e00\u8bfb 2026-04-03"}],
            "language": "zh",
        },
    )
    assert response.status_code == 200
    payload = response.json()

    assert "2026-04-03" in payload["answer"]
    assert payload["sources"]


def test_continue_reading_uses_new_command_label_and_keeps_original_session_title():
    first_response = client.post(
        "/api/chat",
        json={
            "session_id": "test-chat-title-stability",
            "messages": [{"role": "user", "content": "/\u7b80\u62a5 AI\u91cd\u6784\u7ba1\u7406"}],
            "language": "zh",
        },
    )
    assert first_response.status_code == 200

    second_response = client.post(
        "/api/chat",
        json={
            "session_id": "test-chat-title-stability",
            "messages": [{"role": "user", "content": "/\u7ee7\u7eed\u9605\u8bfb"}],
            "language": "zh",
        },
    )
    assert second_response.status_code == 200
    second_payload = second_response.json()

    assert second_payload["answer"].startswith("## \u7ee7\u7eed\u9605\u8bfb")
    assert second_payload["follow_up_questions"][0] == "/\u4eca\u65e5\u4e00\u8bfb"

    sessions_response = client.get("/api/chat/sessions")
    assert sessions_response.status_code == 200
    sessions = sessions_response.json()
    matching = next((session for session in sessions if session["session_id"] == "test-chat-title-stability"), None)
    assert matching is not None
    assert matching["title"] == "/\u7b80\u62a5 AI\u91cd\u6784\u7ba1\u7406"
