from __future__ import annotations

from fastapi import APIRouter, Header, Query
from fastapi.responses import JSONResponse, RedirectResponse

from backend.services.cas_auth_service import (
    build_login_url,
    build_logout_url,
    build_service_url,
    frontend_callback_url,
    issue_session,
    normalize_redirect_path,
    revoke_session,
    validate_ticket,
)

router = APIRouter(prefix="/api/auth/cas", tags=["auth-cas"])


@router.get("/login")
def cas_login(redirect: str | None = Query(default=None)):
    return RedirectResponse(url=build_login_url(redirect), status_code=302)


@router.get("/callback")
def cas_callback(ticket: str = Query(...), redirect: str | None = Query(default=None)):
    redirect_path = normalize_redirect_path(redirect)
    cas_user = validate_ticket(ticket, service_url=build_service_url(redirect_path))
    if not cas_user:
        return JSONResponse(status_code=401, content={"detail": "CAS ticket validation failed."})
    token = issue_session(cas_user)
    return RedirectResponse(url=frontend_callback_url(token, redirect_path), status_code=302)


@router.get("/logout")
def cas_logout_get(authorization: str | None = Header(default=None), redirect: str | None = Query(default=None)):
    token = _extract_token(authorization)
    if token:
        revoke_session(token)
    return RedirectResponse(url=build_logout_url(redirect), status_code=302)


@router.post("/logout")
def cas_logout_post(authorization: str | None = Header(default=None), redirect: str | None = Query(default=None)):
    token = _extract_token(authorization)
    if token:
        revoke_session(token)
    return {"logout_url": build_logout_url(redirect)}


def _extract_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    text = authorization.strip()
    if not text.lower().startswith("bearer "):
        return None
    return text[7:].strip() or None
