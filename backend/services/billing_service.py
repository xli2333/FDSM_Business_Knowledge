from __future__ import annotations

import json
from datetime import datetime

from fastapi import HTTPException

from backend.config import PAYMENTS_ENABLED, PAYMENT_PROVIDER, SITE_BASE_URL
from backend.database import connection_scope
from backend.services.content_localization import contains_cjk
from backend.services.membership_service import get_membership_profile, membership_tier_label

BILLING_PERIOD_LABELS = {
    "zh": {
        "month": "\u6708\u4ed8",
        "quarter": "\u5b63\u4ed8",
        "year": "\u5e74\u4ed8",
        "oneoff": "\u4e00\u6b21\u6027",
    },
    "en": {
        "month": "month",
        "quarter": "quarter",
        "year": "year",
        "oneoff": "one-off",
    },
}
ACTIVE_SUBSCRIPTION_STATUSES = {"active", "trial"}
TIER_LABELS = {
    "zh": {
        "guest": "\u8bbf\u5ba2",
        "free_member": "\u514d\u8d39\u4f1a\u5458",
        "paid_member": "\u4ed8\u8d39\u4f1a\u5458",
        "admin": "\u7ba1\u7406\u5458",
    },
    "en": {
        "guest": "Guest",
        "free_member": "Free Member",
        "paid_member": "Paid Member",
        "admin": "Admin",
    },
}
PLAN_LOCALIZATIONS = {
    "free_member_monthly": {
        "en": {
            "name": "Free Member",
            "headline": "Reader retention and knowledge-asset entry point",
            "description": "Ideal for setting up a reading account, keeping likes and bookmarks, and unlocking foundational member content.",
            "features": [
                "Keep reading history, likes, and bookmarks",
                "Unlock foundational member audio and video content",
                "Serve as the bridge into paid upgrades",
            ],
        }
    },
    "paid_member_monthly": {
        "en": {
            "name": "Paid Member Monthly",
            "headline": "The flagship package for premium member content",
            "description": "Built for deep business knowledge, gated content, topic briefings, and paid audio and video.",
            "features": [
                "Unlock paid articles, premium audio, and premium video",
                "Fit topic briefings, courses, and closed-door notes",
                "Stay compatible with renewals, trials, and promotional pricing",
            ],
        }
    },
    "paid_member_yearly": {
        "en": {
            "name": "Paid Member Yearly",
            "headline": "The annual package for high-value institutional users",
            "description": "Designed for long-horizon industry tracking, topic-based learning, and stable subscription operations.",
            "features": [
                "Includes a full year of paid-content access",
                "Fits annual briefings, course bundles, and offline programs",
                "Prepares the path for institution and seat-based editions",
            ],
        }
    },
}


def _now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def _normalize_language(language: str | None) -> str:
    return "en" if str(language or "").strip().lower() == "en" else "zh"


def _load_features(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(payload, list):
        return []
    return [str(item).strip() for item in payload if str(item).strip()]


def _translate_tier_label(tier: str, language: str) -> str:
    normalized_language = _normalize_language(language)
    if normalized_language == "en":
        return TIER_LABELS["en"].get(tier, tier)
    return membership_tier_label(tier)


def _localized_plan_copy(
    *,
    plan_code: str,
    language: str,
    fallback_name: str | None,
    fallback_headline: str | None,
    fallback_description: str | None,
    fallback_features: list[str],
) -> dict:
    normalized_language = _normalize_language(language)
    if normalized_language != "en":
        return {
            "name": fallback_name or plan_code,
            "headline": fallback_headline or "",
            "description": fallback_description or "",
            "features": fallback_features,
        }

    localized = PLAN_LOCALIZATIONS.get(plan_code, {}).get("en", {})
    return {
        "name": localized.get("name") or (fallback_name if fallback_name and not contains_cjk(fallback_name) else plan_code),
        "headline": localized.get("headline") or (fallback_headline if fallback_headline and not contains_cjk(fallback_headline) else ""),
        "description": localized.get("description") or (fallback_description if fallback_description and not contains_cjk(fallback_description) else ""),
        "features": localized.get("features") or [item for item in fallback_features if item and not contains_cjk(item)],
    }


def _serialize_plan_row(row, language: str = "zh") -> dict:
    normalized_language = _normalize_language(language)
    tier = row["tier"]
    checkout_available = bool(PAYMENTS_ENABLED and row["is_enabled"])
    features = _load_features(row["features_json"])
    localized_copy = _localized_plan_copy(
        plan_code=row["plan_code"],
        language=normalized_language,
        fallback_name=row["name"],
        fallback_headline=row["headline"],
        fallback_description=row["description"],
        fallback_features=features,
    )
    return {
        "plan_code": row["plan_code"],
        "name": localized_copy["name"],
        "tier": tier,
        "tier_label": _translate_tier_label(tier, normalized_language),
        "price_cents": row["price_cents"],
        "currency": row["currency"],
        "billing_period": row["billing_period"],
        "billing_period_label": BILLING_PERIOD_LABELS[normalized_language].get(row["billing_period"], row["billing_period"]),
        "headline": localized_copy["headline"],
        "description": localized_copy["description"],
        "features": localized_copy["features"],
        "is_public": bool(row["is_public"]),
        "is_enabled": bool(row["is_enabled"]),
        "checkout_available": checkout_available,
        "sort_order": row["sort_order"],
    }


def _serialize_order_row(row, language: str = "zh") -> dict:
    normalized_language = _normalize_language(language)
    localized_name = _localized_plan_copy(
        plan_code=row["plan_code"],
        language=normalized_language,
        fallback_name=row["plan_name"],
        fallback_headline=None,
        fallback_description=None,
        fallback_features=[],
    )["name"]
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "email": row["email"],
        "plan_code": row["plan_code"],
        "plan_name": localized_name,
        "amount_cents": row["amount_cents"],
        "currency": row["currency"],
        "status": row["status"],
        "payment_provider": row["payment_provider"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _serialize_subscription_row(row, language: str = "zh") -> dict:
    normalized_language = _normalize_language(language)
    tier = row["tier"]
    localized_name = _localized_plan_copy(
        plan_code=row["plan_code"],
        language=normalized_language,
        fallback_name=row["plan_name"],
        fallback_headline=None,
        fallback_description=None,
        fallback_features=[],
    )["name"]
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "email": row["email"],
        "plan_code": row["plan_code"],
        "plan_name": localized_name,
        "tier": tier,
        "tier_label": _translate_tier_label(tier, normalized_language),
        "status": row["status"],
        "started_at": row["started_at"],
        "expires_at": row["expires_at"],
        "auto_renew": bool(row["auto_renew"]),
        "payment_provider": row["payment_provider"],
        "updated_at": row["updated_at"],
    }


def list_billing_plans(language: str = "zh") -> dict:
    normalized_language = _normalize_language(language)
    with connection_scope() as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM billing_plans
            WHERE is_public = 1
            ORDER BY sort_order ASC, price_cents ASC, plan_code ASC
            """
        ).fetchall()
    return {
        "payments_enabled": PAYMENTS_ENABLED,
        "payment_provider": PAYMENT_PROVIDER,
        "items": [_serialize_plan_row(row, language=normalized_language) for row in rows],
    }


def get_billing_profile(user: dict | None, language: str = "zh") -> dict:
    normalized_language = _normalize_language(language)
    membership = get_membership_profile(user)
    if not user:
        return {
            "payments_enabled": PAYMENTS_ENABLED,
            "payment_provider": PAYMENT_PROVIDER,
            "membership": membership,
            "active_subscription": None,
            "recent_orders": [],
        }

    with connection_scope() as connection:
        subscription_row = connection.execute(
            """
            SELECT s.*, p.name AS plan_name
            FROM billing_subscriptions AS s
            LEFT JOIN billing_plans AS p ON p.plan_code = s.plan_code
            WHERE s.user_id = ? AND s.status IN ('active', 'trial')
            ORDER BY s.updated_at DESC, s.id DESC
            LIMIT 1
            """,
            (user["id"],),
        ).fetchone()
        order_rows = connection.execute(
            """
            SELECT o.*, p.name AS plan_name
            FROM billing_orders AS o
            LEFT JOIN billing_plans AS p ON p.plan_code = o.plan_code
            WHERE o.user_id = ?
            ORDER BY o.created_at DESC, o.id DESC
            LIMIT 12
            """,
            (user["id"],),
        ).fetchall()

    return {
        "payments_enabled": PAYMENTS_ENABLED,
        "payment_provider": PAYMENT_PROVIDER,
        "membership": membership,
        "active_subscription": _serialize_subscription_row(subscription_row, language=normalized_language) if subscription_row else None,
        "recent_orders": [_serialize_order_row(row, language=normalized_language) for row in order_rows],
    }


def create_checkout_intent(
    user: dict | None,
    *,
    plan_code: str,
    success_url: str | None = None,
    cancel_url: str | None = None,
) -> dict:
    if not user:
        raise HTTPException(status_code=401, detail="Login required")

    normalized_plan_code = (plan_code or "").strip()
    if not normalized_plan_code:
        raise HTTPException(status_code=400, detail="Plan code is required")

    with connection_scope() as connection:
        plan_row = connection.execute(
            """
            SELECT *
            FROM billing_plans
            WHERE plan_code = ? AND is_public = 1
            LIMIT 1
            """,
            (normalized_plan_code,),
        ).fetchone()
        if plan_row is None:
            raise HTTPException(status_code=404, detail="Billing plan not found")

        timestamp = _now_iso()
        payments_ready = bool(PAYMENTS_ENABLED and plan_row["is_enabled"])
        note = "Payment infrastructure is configured, but live payment capture is not enabled in this environment."
        status = "disabled"
        redirect_url = None
        if payments_ready:
            status = "pending"
            target = (success_url or "").strip() or f"{SITE_BASE_URL}/membership?checkout=mock&plan={normalized_plan_code}"
            redirect_url = target
            note = "A checkout intent has been created. Replace the mock redirect with your live payment gateway when ready."

        connection.execute(
            """
            INSERT INTO billing_checkout_intents (
                user_id,
                email,
                plan_code,
                status,
                payment_provider,
                redirect_url,
                note,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user["id"],
                user.get("email"),
                normalized_plan_code,
                status,
                PAYMENT_PROVIDER,
                redirect_url or cancel_url,
                note,
                timestamp,
                timestamp,
            ),
        )
        intent_id = int(connection.execute("SELECT last_insert_rowid()").fetchone()[0])
        order_status = "pending" if payments_ready else "disabled"
        connection.execute(
            """
            INSERT INTO billing_orders (
                user_id,
                email,
                plan_code,
                amount_cents,
                currency,
                status,
                payment_provider,
                checkout_intent_id,
                provider_order_id,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)
            """,
            (
                user["id"],
                user.get("email"),
                normalized_plan_code,
                plan_row["price_cents"],
                plan_row["currency"],
                order_status,
                PAYMENT_PROVIDER,
                intent_id,
                timestamp,
                timestamp,
            ),
        )
        order_id = int(connection.execute("SELECT last_insert_rowid()").fetchone()[0])
        connection.commit()

    return {
        "intent_id": intent_id,
        "order_id": order_id,
        "plan_code": normalized_plan_code,
        "status": status,
        "payment_provider": PAYMENT_PROVIDER,
        "payments_enabled": PAYMENTS_ENABLED,
        "checkout_url": redirect_url,
        "message": note,
    }


def list_billing_orders(limit: int = 100, query: str = "") -> dict:
    safe_limit = max(1, min(limit, 200))
    search_term = f"%{query.strip()}%" if query.strip() else ""
    with connection_scope() as connection:
        if search_term:
            rows = connection.execute(
                """
                SELECT o.*, p.name AS plan_name
                FROM billing_orders AS o
                LEFT JOIN billing_plans AS p ON p.plan_code = o.plan_code
                WHERE
                    COALESCE(o.user_id, '') LIKE ?
                    OR COALESCE(o.email, '') LIKE ?
                    OR COALESCE(o.plan_code, '') LIKE ?
                    OR COALESCE(o.status, '') LIKE ?
                ORDER BY o.created_at DESC, o.id DESC
                LIMIT ?
                """,
                (search_term, search_term, search_term, search_term, safe_limit),
            ).fetchall()
            total = connection.execute(
                """
                SELECT COUNT(*) AS total
                FROM billing_orders AS o
                WHERE
                    COALESCE(o.user_id, '') LIKE ?
                    OR COALESCE(o.email, '') LIKE ?
                    OR COALESCE(o.plan_code, '') LIKE ?
                    OR COALESCE(o.status, '') LIKE ?
                """,
                (search_term, search_term, search_term, search_term),
            ).fetchone()["total"]
        else:
            rows = connection.execute(
                """
                SELECT o.*, p.name AS plan_name
                FROM billing_orders AS o
                LEFT JOIN billing_plans AS p ON p.plan_code = o.plan_code
                ORDER BY o.created_at DESC, o.id DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
            total = connection.execute("SELECT COUNT(*) AS total FROM billing_orders").fetchone()["total"]

    return {
        "items": [_serialize_order_row(row) for row in rows],
        "total": total,
    }
