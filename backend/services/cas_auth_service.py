from __future__ import annotations

import hashlib
import json
import secrets
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from urllib.parse import quote, urlencode

import requests
from fastapi import HTTPException

from backend.config import (
    ADMIN_EMAILS,
    CAS_ADMIN_EMPLOYEE_NUMBERS,
    CAS_ADMIN_USERNAMES,
    CAS_ENABLED,
    CAS_SERVER_URL,
    CAS_SESSION_RETENTION_DAYS,
    CAS_SERVICE_URL,
    CAS_SESSION_TTL_SECONDS,
    CAS_VALIDATE_TIMEOUT_SECONDS,
)
from backend.database import connection_scope, run_write_transaction

CAS_NAMESPACE = {"cas": "http://www.yale.edu/tp/cas"}


def _now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def _expires_iso() -> str:
    return (datetime.now().replace(microsecond=0) + timedelta(seconds=CAS_SESSION_TTL_SECONDS)).isoformat()


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def is_cas_enabled() -> bool:
    return bool(CAS_ENABLED and CAS_SERVER_URL and CAS_SERVICE_URL)


def normalize_redirect_path(redirect_path: str | None) -> str:
    redirect = (redirect_path or "").strip()
    if not redirect or not redirect.startswith("/") or redirect.startswith("//"):
        return "/"
    return redirect


def build_service_url(redirect_path: str | None = None) -> str:
    redirect = normalize_redirect_path(redirect_path)
    if redirect == "/":
        return CAS_SERVICE_URL
    separator = "&" if "?" in CAS_SERVICE_URL else "?"
    return f"{CAS_SERVICE_URL}{separator}{urlencode({'redirect': redirect})}"


def build_login_url(redirect_path: str | None = None) -> str:
    if not is_cas_enabled():
        raise HTTPException(status_code=503, detail="CAS authentication is not configured.")
    return f"{CAS_SERVER_URL}/login?{urlencode({'service': build_service_url(redirect_path)})}"


def build_logout_url(redirect_path: str | None = None) -> str:
    if not is_cas_enabled():
        raise HTTPException(status_code=503, detail="CAS authentication is not configured.")
    from backend.config import SITE_BASE_URL

    redirect = normalize_redirect_path(redirect_path)
    service = f"{SITE_BASE_URL}{redirect}" if SITE_BASE_URL else redirect
    return f"{CAS_SERVER_URL}/logout?{urlencode({'service': service})}"


def _find_text(parent: ET.Element | None, name: str) -> str:
    if parent is None:
        return ""
    namespaced = parent.find(f"cas:{name}", CAS_NAMESPACE)
    if namespaced is not None and namespaced.text:
        return namespaced.text.strip()
    plain = parent.find(name)
    return plain.text.strip() if plain is not None and plain.text else ""


def _find_success(root: ET.Element) -> ET.Element | None:
    success = root.find("cas:authenticationSuccess", CAS_NAMESPACE)
    if success is not None:
        return success
    return root.find("authenticationSuccess")


def validate_ticket(ticket: str, service_url: str | None = None) -> dict | None:
    if not is_cas_enabled():
        raise HTTPException(status_code=503, detail="CAS authentication is not configured.")
    cleaned_ticket = (ticket or "").strip()
    if not cleaned_ticket:
        return None

    response = requests.get(
        f"{CAS_SERVER_URL}/serviceValidate",
        params={"service": service_url or CAS_SERVICE_URL, "ticket": cleaned_ticket},
        timeout=CAS_VALIDATE_TIMEOUT_SECONDS,
    )
    if response.status_code != 200:
        return None

    try:
        root = ET.fromstring(response.text)
    except ET.ParseError:
        return None
    success = _find_success(root)
    if success is None:
        return None

    attributes_element = success.find("cas:attributes", CAS_NAMESPACE) or success.find("attributes")
    attributes: dict[str, str] = {}
    if attributes_element is not None:
        for child in list(attributes_element):
            tag = child.tag.split("}", 1)[-1] if "}" in child.tag else child.tag
            attributes[tag] = (child.text or "").strip()

    username = _find_text(success, "user") or attributes.get("username", "")
    return {
        "username": username,
        "employee_number": attributes.get("employeeNumber", ""),
        "display_name": attributes.get("displayName") or attributes.get("name") or username,
        "attributes": attributes,
    }


def _email_from_cas_user(cas_user: dict) -> str:
    attributes = cas_user.get("attributes") or {}
    email = attributes.get("email") or attributes.get("mail")
    if email:
        return email.strip()
    username = str(cas_user.get("username") or "").strip()
    if "@" in username:
        return username
    employee_number = str(cas_user.get("employee_number") or "").strip()
    return f"{employee_number or username}@fudan.edu.cn"


def _is_cas_admin(cas_user: dict, email: str | None) -> bool:
    employee_number = str(cas_user.get("employee_number") or "").strip()
    username = str(cas_user.get("username") or "").strip().lower()
    return bool(
        (employee_number and employee_number in CAS_ADMIN_EMPLOYEE_NUMBERS)
        or (username and username in CAS_ADMIN_USERNAMES)
        or (email and email.strip().lower() in ADMIN_EMAILS)
    )


def _local_user_id(cas_user: dict) -> str:
    employee_number = str(cas_user.get("employee_number") or "").strip()
    if employee_number:
        return f"cas-{employee_number}"
    username = str(cas_user.get("username") or "").strip()
    if username:
        return f"cas-{username}"
    raise ValueError("CAS user missing employeeNumber and username.")


def _ensure_local_user_from_cas(cas_user: dict) -> dict:
    from backend.services.user_profile_service import ensure_business_user_profile, role_home_path_for_tier

    user_id = _local_user_id(cas_user)
    email = _email_from_cas_user(cas_user)
    tier = "admin" if _is_cas_admin(cas_user, email) else "free_member"
    timestamp = _now_iso()
    display_name = str(cas_user.get("display_name") or cas_user.get("username") or user_id)
    username = str(cas_user.get("username") or "")
    employee_number = str(cas_user.get("employee_number") or "")

    def operation(connection) -> None:
        existing = connection.execute("SELECT tier, status FROM user_memberships WHERE user_id = ?", (user_id,)).fetchone()
        next_tier = tier if existing is None or tier == "admin" else existing["tier"]
        next_status = existing["status"] if existing is not None else "active"
        if existing is None:
            connection.execute(
                """
                INSERT INTO user_memberships (
                    user_id, email, tier, status, note, started_at, expires_at, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, NULL, ?, NULL, ?, ?)
                """,
                (user_id, email, next_tier, next_status, timestamp, timestamp, timestamp),
            )
        else:
            connection.execute(
                """
                UPDATE user_memberships
                SET email = ?, tier = ?, status = ?, updated_at = ?
                WHERE user_id = ?
                """,
                (email, next_tier, next_status, timestamp, user_id),
            )

        ensure_business_user_profile(
            user_id,
            email,
            next_tier,
            next_status,
            auth_source="cas",
            connection=connection,
        )
        connection.execute(
            """
            UPDATE business_users
            SET display_name = ?,
                role_home_path = ?,
                auth_source = 'cas',
                cas_username = ?,
                cas_employee_number = ?,
                updated_at = ?,
                last_seen_at = ?
            WHERE user_id = ?
            """,
            (display_name, role_home_path_for_tier(next_tier), username, employee_number, timestamp, timestamp, user_id),
        )

    run_write_transaction(operation, label="auth.cas.sync_user")
    return {
        "id": user_id,
        "email": email,
        "raw_user": {
            "auth_source": "cas",
            "cas": cas_user,
        },
    }


def issue_session(cas_user: dict) -> str:
    user = _ensure_local_user_from_cas(cas_user)
    token = secrets.token_urlsafe(48)
    token_hash = _token_hash(token)
    timestamp = _now_iso()
    expires_at = _expires_iso()

    def operation(connection) -> None:
        connection.execute(
            """
            INSERT INTO auth_sessions (
                token_hash, user_id, email, raw_user_json, issued_at, expires_at, revoked_at, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?)
            """,
            (
                token_hash,
                user["id"],
                user.get("email"),
                json.dumps(user.get("raw_user") or {}, ensure_ascii=False),
                timestamp,
                expires_at,
                timestamp,
                timestamp,
            ),
        )

    run_write_transaction(operation, label="auth.cas.issue_session")
    return token


def revoke_session(token: str) -> None:
    token_hash = _token_hash(token)
    timestamp = _now_iso()

    def operation(connection) -> None:
        connection.execute(
            """
            UPDATE auth_sessions
            SET revoked_at = COALESCE(revoked_at, ?), updated_at = ?
            WHERE token_hash = ?
            """,
            (timestamp, timestamp, token_hash),
        )

    run_write_transaction(operation, label="auth.cas.revoke_session")


def cleanup_expired_sessions(retention_days: int | None = None) -> int:
    retained_days = max(1, int(retention_days or CAS_SESSION_RETENTION_DAYS))
    cutoff = (datetime.now().replace(microsecond=0) - timedelta(days=retained_days)).isoformat()

    def operation(connection) -> int:
        cursor = connection.execute(
            """
            DELETE FROM auth_sessions
            WHERE expires_at < ?
               OR (revoked_at IS NOT NULL AND revoked_at < ?)
            """,
            (cutoff, cutoff),
        )
        return int(cursor.rowcount or 0)

    return run_write_transaction(operation, label="auth.cas.cleanup_expired_sessions")


def get_user_by_session(token: str) -> dict | None:
    token_hash = _token_hash(token)
    with connection_scope() as connection:
        row = connection.execute(
            """
            SELECT user_id, email, raw_user_json
            FROM auth_sessions
            WHERE token_hash = ?
              AND revoked_at IS NULL
              AND expires_at > ?
            """,
            (token_hash, _now_iso()),
        ).fetchone()
    if not row:
        return None
    try:
        raw_user = json.loads(row["raw_user_json"] or "{}")
    except json.JSONDecodeError:
        raw_user = {"auth_source": "cas"}
    raw_user.setdefault("auth_source", "cas")
    return {
        "id": row["user_id"],
        "email": row["email"],
        "raw_user": raw_user,
    }


def _extract_bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    text = authorization.strip()
    if not text.lower().startswith("bearer "):
        return None
    token = text[7:].strip()
    return token or None


def get_authenticated_user(
    authorization: str | None,
    *,
    debug_user_id: str | None = None,
    debug_user_email: str | None = None,
) -> dict | None:
    del debug_user_id, debug_user_email
    token = _extract_bearer_token(authorization)
    if not token:
        return None
    return get_user_by_session(token)


def get_auth_status_payload(
    authorization: str | None,
    *,
    debug_user_id: str | None = None,
    debug_user_email: str | None = None,
) -> dict:
    del debug_user_id, debug_user_email
    from backend.services.membership_service import get_membership_profile
    from backend.services.user_profile_service import get_business_profile, role_home_path_for_tier

    user = get_authenticated_user(authorization)
    membership = get_membership_profile(user)
    business_profile = get_business_profile(user, membership)
    return {
        "enabled": is_cas_enabled(),
        "authenticated": bool(user),
        "user": {"id": user["id"], "email": user.get("email")} if user else None,
        "auth_mode": "cas",
        "membership": membership,
        "business_profile": business_profile,
        "role_home_path": business_profile.get("role_home_path")
        or role_home_path_for_tier((membership or {}).get("tier")),
    }


def frontend_callback_url(token: str, redirect_path: str | None = None) -> str:
    from backend.config import CAS_FRONTEND_CALLBACK_PATH, SITE_BASE_URL

    redirect = normalize_redirect_path(redirect_path)
    fragment = urlencode({"token": token, "redirect": redirect}, quote_via=quote)
    return f"{SITE_BASE_URL}{CAS_FRONTEND_CALLBACK_PATH}#{fragment}"
