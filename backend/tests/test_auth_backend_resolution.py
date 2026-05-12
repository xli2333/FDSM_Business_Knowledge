from backend.services import auth_service


def _set_resolution_context(
    monkeypatch,
    *,
    app_is_production: bool,
    allow_legacy_supabase: bool,
    auth_backend: str,
    cas_enabled: bool,
    supabase_enabled: bool,
) -> None:
    monkeypatch.setattr(auth_service, "IS_PRODUCTION", app_is_production)
    monkeypatch.setattr(auth_service, "ALLOW_LEGACY_SUPABASE_AUTH", allow_legacy_supabase)
    monkeypatch.setattr(auth_service, "AUTH_BACKEND", auth_backend)
    monkeypatch.setattr(auth_service.cas_auth_service, "is_cas_enabled", lambda: cas_enabled)
    monkeypatch.setattr(auth_service.supabase_auth_service, "is_supabase_auth_enabled", lambda: supabase_enabled)


def test_production_auto_prefers_cas_and_does_not_activate_supabase_without_escape_hatch(monkeypatch):
    _set_resolution_context(
        monkeypatch,
        app_is_production=True,
        allow_legacy_supabase=False,
        auth_backend="auto",
        cas_enabled=True,
        supabase_enabled=True,
    )

    assert auth_service._resolved_backend() == "cas"


def test_production_auto_falls_back_to_cas_when_only_supabase_is_configured_without_escape_hatch(monkeypatch):
    _set_resolution_context(
        monkeypatch,
        app_is_production=True,
        allow_legacy_supabase=False,
        auth_backend="auto",
        cas_enabled=False,
        supabase_enabled=True,
    )

    assert auth_service._resolved_backend() == "cas"


def test_production_explicit_supabase_backend_is_runtime_blocked_without_escape_hatch(monkeypatch):
    _set_resolution_context(
        monkeypatch,
        app_is_production=True,
        allow_legacy_supabase=False,
        auth_backend="supabase",
        cas_enabled=False,
        supabase_enabled=True,
    )

    assert auth_service._resolved_backend() == "cas"


def test_production_legacy_escape_hatch_allows_dual_backend_for_controlled_rollback(monkeypatch):
    _set_resolution_context(
        monkeypatch,
        app_is_production=True,
        allow_legacy_supabase=True,
        auth_backend="auto",
        cas_enabled=True,
        supabase_enabled=True,
    )

    assert auth_service._resolved_backend() == "dual"


def test_development_auto_keeps_preview_supabase_path_available(monkeypatch):
    _set_resolution_context(
        monkeypatch,
        app_is_production=False,
        allow_legacy_supabase=False,
        auth_backend="auto",
        cas_enabled=False,
        supabase_enabled=False,
    )

    assert auth_service._resolved_backend() == "supabase"
