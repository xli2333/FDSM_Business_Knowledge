from __future__ import annotations

from backend.config import resolve_gemini_model_name
from backend.services import ai_service


def test_resolve_gemini_model_name_maps_flash_alias_to_preview():
    assert resolve_gemini_model_name("gemini-3-flash") == "gemini-3-flash-preview"
    assert resolve_gemini_model_name("gemini-2.5-flash") == "gemini-2.5-flash"


def test_build_llm_uses_runtime_model_alias(monkeypatch):
    captured: dict[str, str] = {}

    def fake_constructor(**kwargs):
        captured.update(kwargs)
        return kwargs

    monkeypatch.setattr(ai_service, "ChatGoogleGenerativeAI", fake_constructor)
    monkeypatch.setattr(ai_service, "get_gemini_api_keys", lambda: ("test-key",))

    result = ai_service._build_llm("gemini-3-flash")

    assert result["model"] == "gemini-3-flash-preview"
    assert captured["google_api_key"] == "test-key"
