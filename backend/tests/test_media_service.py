from backend.services.media_service import (
    MEDIA_PREVIEW_SECONDS,
    _apply_visibility_policy,
    _resolve_access,
    _serialize_media_row,
)


def _membership(tier: str, *, can_access_member: bool, can_access_paid: bool) -> dict:
    return {
        "tier": tier,
        "can_access_member": can_access_member,
        "can_access_paid": can_access_paid,
    }


def test_audio_visibility_is_forced_to_paid():
    assert _apply_visibility_policy("audio", "public") == "paid"
    assert _apply_visibility_policy("audio", "member") == "paid"
    assert _apply_visibility_policy("video", "member") == "member"


def test_audio_access_uses_paid_rule_with_preview_copy():
    guest_accessible, guest_gate = _resolve_access("audio", "public", _membership("guest", can_access_member=False, can_access_paid=False))
    free_accessible, free_gate = _resolve_access("audio", "member", _membership("free_member", can_access_member=True, can_access_paid=False))
    paid_accessible, paid_gate = _resolve_access("audio", "public", _membership("paid_member", can_access_member=True, can_access_paid=True))

    assert not guest_accessible
    assert not free_accessible
    assert paid_accessible
    assert paid_gate is None
    assert str(MEDIA_PREVIEW_SECONDS // 60) in guest_gate
    assert "付费会员" in guest_gate
    assert str(MEDIA_PREVIEW_SECONDS // 60) in free_gate
    assert "升级" in free_gate


def test_serialize_media_row_hides_full_media_url_for_locked_audio():
    row = {
        "id": 1,
        "slug": "sample-audio",
        "kind": "audio",
        "title": "Sample Audio",
        "summary": "Summary",
        "speaker": "Host",
        "series_name": "Series",
        "episode_number": 1,
        "publish_date": "2026-04-09",
        "duration_seconds": 320,
        "visibility": "public",
        "status": "published",
        "cover_image_url": "",
        "media_url": "/audio-files/sample.mp3",
        "preview_url": "",
        "source_url": "",
        "body_markdown": "Long body",
        "transcript_markdown": "Long transcript",
        "chapter_payload_json": "[]",
    }

    payload = _serialize_media_row(row, _membership("free_member", can_access_member=True, can_access_paid=False))

    assert payload["visibility"] == "paid"
    assert payload["accessible"] is False
    assert payload["media_url"] is None
    assert payload["preview_url"] == "/audio-files/sample.mp3"
    assert payload["preview_duration_seconds"] == MEDIA_PREVIEW_SECONDS
