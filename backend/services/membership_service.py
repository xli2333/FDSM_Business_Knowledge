from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException

from backend.config import ADMIN_EMAILS
from backend.database import connection_scope

TIER_LABELS = {
    "guest": "游客",
    "free_member": "免费会员",
    "paid_member": "付费会员",
    "admin": "管理员",
}
STATUS_LABELS = {
    "anonymous": "未登录",
    "active": "有效",
    "trial": "试用中",
    "paused": "已暂停",
    "expired": "已过期",
}
VALID_TIERS = {"free_member", "paid_member", "admin"}
VALID_STATUSES = {"active", "trial", "paused", "expired"}
BENEFIT_MAP = {
    "guest": [
        "可浏览公开文章与公开音视频样刊",
        "可查看商业化方案和知识库结构",
    ],
    "free_member": [
        "可保留点赞、收藏与阅读历史",
        "可访问会员专属音频和视频栏目中的基础内容",
        "可逐步沉淀个人知识资产与推荐偏好",
    ],
    "paid_member": [
        "可访问付费音频、付费视频和深度会员内容",
        "适合扩展为专题专报、课程、闭门简报与陪跑服务",
        "可承接更高价值的商业知识服务与内容订阅",
    ],
    "admin": [
        "拥有会员配置权限",
        "可查看完整会员列表并调整等级",
        "可继续扩展到专题运营、内容发布与商业后台管理",
    ],
}
ACCESS_LEVEL_LABELS = {
    "public": "公开",
    "member": "会员",
    "paid": "付费",
}


def _now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def _normalize_tier(value: str | None) -> str:
    tier = (value or "").strip()
    if tier not in VALID_TIERS:
        raise HTTPException(status_code=400, detail="Unsupported membership tier")
    return tier


def _normalize_status(value: str | None) -> str:
    status = (value or "").strip()
    if status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail="Unsupported membership status")
    return status


def _is_admin_email(email: str | None) -> bool:
    return bool(email and email.strip().lower() in ADMIN_EMAILS)


def _tier_label(tier: str) -> str:
    return TIER_LABELS.get(tier, tier)


def _status_label(status: str) -> str:
    return STATUS_LABELS.get(status, status)


def membership_tier_label(tier: str) -> str:
    return _tier_label(tier)


def membership_status_label(status: str) -> str:
    return _status_label(status)


def normalize_access_level(value: str | None) -> str:
    access_level = (value or "").strip() or "public"
    if access_level not in ACCESS_LEVEL_LABELS:
        raise HTTPException(status_code=400, detail="Unsupported access level")
    return access_level


def access_level_label(access_level: str) -> str:
    return ACCESS_LEVEL_LABELS.get(access_level, access_level)


def membership_can_access(membership: dict | None, access_level: str) -> bool:
    normalized = normalize_access_level(access_level)
    current = membership or _serialize_profile(None)
    if normalized == "public":
        return True
    if normalized == "member":
        return bool(current.get("can_access_member"))
    if normalized == "paid":
        return bool(current.get("can_access_paid"))
    return False


def build_content_access(access_level: str, membership: dict | None) -> dict:
    normalized = normalize_access_level(access_level)
    locked = not membership_can_access(membership, normalized)
    if normalized == "public":
        required_membership = None
        message = "公开内容，所有访客均可阅读全文。"
    elif normalized == "member":
        required_membership = "free_member"
        message = "登录成为免费会员后可阅读全文与完整 AI 摘要。"
    else:
        required_membership = "paid_member"
        message = "升级为付费会员后可阅读全文、完整 AI 摘要与高价值会员内容。"
    return {
        "access_level": normalized,
        "access_label": access_level_label(normalized),
        "locked": locked,
        "required_membership": required_membership,
        "required_membership_label": _tier_label(required_membership) if required_membership else None,
        "message": message,
    }


def _serialize_membership_row(row, *, fallback_email: str | None = None) -> dict:
    tier = row["tier"]
    status = row["status"]
    return {
        "user_id": row["user_id"],
        "email": row["email"] or fallback_email,
        "tier": tier,
        "tier_label": _tier_label(tier),
        "status": status,
        "status_label": _status_label(status),
        "note": row["note"],
        "started_at": row["started_at"],
        "expires_at": row["expires_at"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _serialize_profile(row, *, user: dict | None = None) -> dict:
    if row is None:
        return {
            "tier": "guest",
            "tier_label": _tier_label("guest"),
            "status": "anonymous",
            "status_label": _status_label("anonymous"),
            "is_authenticated": False,
            "is_admin": False,
            "can_access_member": False,
            "can_access_paid": False,
            "user_id": None,
            "email": None,
            "note": None,
            "started_at": None,
            "expires_at": None,
            "benefits": BENEFIT_MAP["guest"],
        }

    tier = row["tier"]
    status = row["status"]
    is_admin = tier == "admin"
    can_access_member = tier in {"free_member", "paid_member", "admin"}
    can_access_paid = tier in {"paid_member", "admin"}
    return {
        "tier": tier,
        "tier_label": _tier_label(tier),
        "status": status,
        "status_label": _status_label(status),
        "is_authenticated": bool(user),
        "is_admin": is_admin,
        "can_access_member": can_access_member,
        "can_access_paid": can_access_paid,
        "user_id": row["user_id"],
        "email": row["email"] or (user or {}).get("email"),
        "note": row["note"],
        "started_at": row["started_at"],
        "expires_at": row["expires_at"],
        "benefits": BENEFIT_MAP["admin" if is_admin else tier],
    }


def _ensure_membership_row(connection, user_id: str, email: str | None) -> None:
    from backend.services.user_profile_service import ensure_business_user_profile

    timestamp = _now_iso()
    existing = connection.execute(
        "SELECT user_id, tier, status, email FROM user_memberships WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    if existing is None:
        tier = "admin" if _is_admin_email(email) else "free_member"
        connection.execute(
            """
            INSERT INTO user_memberships (
                user_id,
                email,
                tier,
                status,
                note,
                started_at,
                expires_at,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, 'active', NULL, ?, NULL, ?, ?)
            """,
            (user_id, email, tier, timestamp, timestamp, timestamp),
        )
        return

    next_tier = "admin" if _is_admin_email(email) and existing["tier"] != "admin" else existing["tier"]
    next_email = email or existing["email"]
    if next_tier != existing["tier"] or next_email != existing["email"]:
        connection.execute(
            """
            UPDATE user_memberships
            SET email = ?, tier = ?, updated_at = ?
            WHERE user_id = ?
            """,
            (next_email, next_tier, timestamp, user_id),
        )

    current = connection.execute(
        "SELECT tier, status, email FROM user_memberships WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    if current is not None:
        auth_source = "seed" if user_id.startswith("mock-") else "supabase"
        ensure_business_user_profile(
            user_id,
            current["email"] or email,
            current["tier"],
            current["status"],
            auth_source=auth_source,
            connection=connection,
        )


def get_membership_profile(user: dict | None) -> dict:
    if not user:
        return _serialize_profile(None, user=None)

    with connection_scope() as connection:
        _ensure_membership_row(connection, user["id"], user.get("email"))
        row = connection.execute(
            """
            SELECT user_id, email, tier, status, note, started_at, expires_at, created_at, updated_at
            FROM user_memberships
            WHERE user_id = ?
            """,
            (user["id"],),
        ).fetchone()
        connection.commit()
    return _serialize_profile(row, user=user)


def require_admin_profile(user: dict | None) -> dict:
    if not user:
        raise HTTPException(status_code=401, detail="Login required")
    profile = get_membership_profile(user)
    if not profile["is_admin"]:
        raise HTTPException(status_code=403, detail="Admin permission required")
    return profile


def require_paid_profile(user: dict | None) -> dict:
    if not user:
        raise HTTPException(status_code=401, detail="Login required")
    profile = get_membership_profile(user)
    if not profile["can_access_paid"]:
        raise HTTPException(status_code=403, detail="Paid membership required")
    return profile


def list_memberships(limit: int = 100, query: str = "") -> dict:
    limit = max(1, min(limit, 200))
    search_term = f"%{query.strip()}%" if query.strip() else ""
    with connection_scope() as connection:
        if search_term:
            rows = connection.execute(
                """
                SELECT user_id, email, tier, status, note, started_at, expires_at, created_at, updated_at
                FROM user_memberships
                WHERE user_id LIKE ? OR COALESCE(email, '') LIKE ? OR COALESCE(note, '') LIKE ?
                ORDER BY
                    CASE tier
                        WHEN 'admin' THEN 1
                        WHEN 'paid_member' THEN 2
                        WHEN 'free_member' THEN 3
                        ELSE 4
                    END,
                    updated_at DESC
                LIMIT ?
                """,
                (search_term, search_term, search_term, limit),
            ).fetchall()
            total = connection.execute(
                """
                SELECT COUNT(*) AS total
                FROM user_memberships
                WHERE user_id LIKE ? OR COALESCE(email, '') LIKE ? OR COALESCE(note, '') LIKE ?
                """,
                (search_term, search_term, search_term),
            ).fetchone()["total"]
        else:
            rows = connection.execute(
                """
                SELECT user_id, email, tier, status, note, started_at, expires_at, created_at, updated_at
                FROM user_memberships
                ORDER BY
                    CASE tier
                        WHEN 'admin' THEN 1
                        WHEN 'paid_member' THEN 2
                        WHEN 'free_member' THEN 3
                        ELSE 4
                    END,
                    updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            total = connection.execute("SELECT COUNT(*) AS total FROM user_memberships").fetchone()["total"]

        count_rows = connection.execute(
            """
            SELECT tier, COUNT(*) AS total
            FROM user_memberships
            GROUP BY tier
            ORDER BY
                CASE tier
                    WHEN 'admin' THEN 1
                    WHEN 'paid_member' THEN 2
                    WHEN 'free_member' THEN 3
                    ELSE 4
                END
            """
        ).fetchall()

    return {
        "items": [_serialize_membership_row(row) for row in rows],
        "counts": [
            {
                "tier": row["tier"],
                "tier_label": _tier_label(row["tier"]),
                "total": row["total"],
            }
            for row in count_rows
        ],
        "total": total,
    }


def update_membership(
    user_id: str,
    *,
    email: str | None,
    tier: str,
    status: str,
    note: str | None = None,
    expires_at: str | None = None,
    actor_user: dict | None = None,
) -> dict:
    from backend.services.user_profile_service import ensure_business_user_profile, record_admin_role_audit

    normalized_tier = _normalize_tier(tier)
    normalized_status = _normalize_status(status)
    timestamp = _now_iso()
    effective_email = email.strip() if email else None
    effective_tier = "admin" if _is_admin_email(effective_email) else normalized_tier

    with connection_scope() as connection:
        existing = connection.execute(
            "SELECT email, tier, status FROM user_memberships WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if existing is None:
            connection.execute(
                """
                INSERT INTO user_memberships (
                    user_id,
                    email,
                    tier,
                    status,
                    note,
                    started_at,
                    expires_at,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    effective_email,
                    effective_tier,
                    normalized_status,
                    note,
                    timestamp,
                    expires_at,
                    timestamp,
                    timestamp,
                ),
            )
            previous_tier = None
            previous_status = None
        else:
            connection.execute(
                """
                UPDATE user_memberships
                SET email = COALESCE(?, email),
                    tier = ?,
                    status = ?,
                    note = ?,
                    expires_at = ?,
                    updated_at = ?
                WHERE user_id = ?
                """,
                (
                    effective_email,
                    effective_tier,
                    normalized_status,
                    note,
                    expires_at,
                    timestamp,
                    user_id,
                ),
            )
            previous_tier = existing["tier"]
            previous_status = existing["status"]

        row = connection.execute(
            """
            SELECT user_id, email, tier, status, note, started_at, expires_at, created_at, updated_at
            FROM user_memberships
            WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()
        ensure_business_user_profile(
            user_id,
            row["email"] or effective_email,
            row["tier"],
            row["status"],
            auth_source="seed" if user_id.startswith("mock-") else "supabase",
            connection=connection,
        )
        record_admin_role_audit(
            connection,
            target_user_id=user_id,
            actor_user_id=actor_user["id"] if actor_user else None,
            actor_email=actor_user.get("email") if actor_user else None,
            previous_tier=previous_tier,
            next_tier=row["tier"],
            previous_status=previous_status,
            next_status=row["status"],
            note=note,
        )
        connection.commit()
    return _serialize_membership_row(row, fallback_email=effective_email)
