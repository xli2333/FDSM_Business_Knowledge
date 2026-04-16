from __future__ import annotations

from datetime import date, datetime, timedelta

from backend.config import PREVIEW_AUTH_ENABLED
from backend.database import connection_scope
from backend.services.membership_service import membership_status_label, membership_tier_label

ROLE_HOME_PATHS = {
    "guest": "/",
    "free_member": "/me",
    "paid_member": "/membership",
    "admin": "/admin",
}

SEED_USER_DEFINITIONS = [
    {
        "user_id": "mock-free-member",
        "email": "reader@example.com",
        "display_name": "陈知远",
        "title": "知识库读者",
        "organization": "FDSM Reader Lab",
        "bio": "负责持续整理个人阅读资产，适合关注公开文章、会员基础能力与升级路径。",
        "description": "免费会员账号，可查看收藏、点赞、历史与基础会员内容。",
        "tier": "free_member",
        "status": "active",
        "auth_source": "seed",
        "locale": "zh-CN",
    },
    {
        "user_id": "mock-paid-member",
        "email": "paid@example.com",
        "display_name": "林策言",
        "title": "深度会员",
        "organization": "FDSM Executive Circle",
        "bio": "关注深度商业内容与会员权益，适合阅读完整正文并进入音视频与高价值内容区。",
        "description": "付费会员账号，可访问完整付费正文、会员音视频与付费权益。",
        "tier": "paid_member",
        "status": "active",
        "auth_source": "seed",
        "locale": "zh-CN",
    },
    {
        "user_id": "mock-admin",
        "email": "admin@example.com",
        "display_name": "管理员",
        "title": "运营控制台",
        "organization": "FDSM Admin Office",
        "bio": "负责管理角色、会员、内容与审计记录，默认进入后台控制台与运营工作区。",
        "description": "管理员账号，可进入后台、调整角色权限并查看运营审计信息。",
        "tier": "admin",
        "status": "active",
        "auth_source": "seed",
        "locale": "zh-CN",
    },
]

SEED_USER_MAP = {item["user_id"]: item for item in SEED_USER_DEFINITIONS}
PREVIEW_ACCOUNT_PASSWORDS = {
    "reader@example.com": "Reader2026!",
    "paid@example.com": "Paid2026!",
    "admin@example.com": "Admin2026!",
}


def _now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def role_home_path_for_tier(tier: str | None) -> str:
    return ROLE_HOME_PATHS.get((tier or "").strip(), "/")


def _normalize_tier(tier: str | None) -> str:
    normalized = (tier or "free_member").strip() or "free_member"
    return normalized if normalized in {"free_member", "paid_member", "admin"} else "free_member"


def _normalize_status(status: str | None) -> str:
    normalized = (status or "active").strip() or "active"
    return normalized if normalized in {"active", "trial", "paused", "expired"} else "active"


def _seed_definition(user_id: str | None, email: str | None = None) -> dict | None:
    if user_id and user_id in SEED_USER_MAP:
        return SEED_USER_MAP[user_id]
    normalized_email = (email or "").strip().lower()
    if not normalized_email:
        return None
    for item in SEED_USER_DEFINITIONS:
        if item["email"].lower() == normalized_email:
            return item
    return None


def _default_profile_fields(user_id: str, email: str | None, tier: str, status: str) -> dict:
    seed = _seed_definition(user_id, email)
    if seed:
        return seed

    display_name = (email or user_id).split("@")[0].replace(".", " ").strip() or "知识库用户"
    display_name = display_name[:40]
    title = {
        "free_member": "会员读者",
        "paid_member": "付费会员",
        "admin": "管理员",
    }.get(tier, "知识库用户")
    return {
        "user_id": user_id,
        "email": email,
        "display_name": display_name,
        "title": title,
        "organization": "Fudan Business Knowledge Base",
        "bio": "登录后会自动映射到本地业务用户档案，用于角色、资产和后台权限控制。",
        "description": None,
        "tier": tier,
        "status": status,
        "auth_source": "supabase",
        "locale": "zh-CN",
    }


def authenticate_preview_account(email: str | None, password: str | None) -> dict | None:
    if not PREVIEW_AUTH_ENABLED:
        return None
    normalized_email = (email or "").strip().lower()
    if not normalized_email:
        return None
    expected_password = PREVIEW_ACCOUNT_PASSWORDS.get(normalized_email)
    if not expected_password or expected_password != (password or ""):
        return None
    seed = _seed_definition(None, normalized_email)
    if not seed:
        return None
    return seed


def _serialize_mock_account(row) -> dict:
    return {
        "user_id": row["user_id"],
        "email": row["email"],
        "display_name": row["display_name"],
        "title": row["title"],
        "organization": row["organization"],
        "description": row["description"],
        "tier": row["tier"],
        "tier_label": membership_tier_label(row["tier"]),
        "status": row["status"],
        "status_label": membership_status_label(row["status"]),
        "role_home_path": row["role_home_path"] or role_home_path_for_tier(row["tier"]),
    }


def _serialize_business_profile(row, membership: dict | None, *, is_authenticated: bool) -> dict:
    tier = (membership or {}).get("tier") or row["tier"]
    status = (membership or {}).get("status") or row["status"]
    return {
        "user_id": row["user_id"],
        "email": row["email"],
        "display_name": row["display_name"] or "知识库用户",
        "title": row["title"],
        "organization": row["organization"],
        "bio": row["bio"],
        "tier": tier,
        "tier_label": membership_tier_label(tier),
        "status": status,
        "status_label": membership_status_label(status),
        "role_home_path": row["role_home_path"] or role_home_path_for_tier(tier),
        "auth_source": row["auth_source"] or "supabase",
        "locale": row["locale"] or "zh-CN",
        "is_seed": bool(row["is_seed"]),
        "is_authenticated": is_authenticated,
        "is_admin": tier == "admin",
    }


def build_guest_business_profile() -> dict:
    return {
        "user_id": None,
        "email": None,
        "display_name": "访客",
        "title": "公开访客",
        "organization": None,
        "bio": "可浏览公开内容；登录后可进入个人资产、会员权益或后台工作区。",
        "tier": "guest",
        "tier_label": membership_tier_label("guest"),
        "status": "anonymous",
        "status_label": membership_status_label("anonymous"),
        "role_home_path": "/",
        "auth_source": "guest",
        "locale": "zh-CN",
        "is_seed": False,
        "is_authenticated": False,
        "is_admin": False,
    }


def ensure_business_user_seed_state(connection) -> None:
    timestamp = _now_iso()

    for seed in SEED_USER_DEFINITIONS:
        membership_row = connection.execute(
            "SELECT user_id, tier, status, email FROM user_memberships WHERE user_id = ?",
            (seed["user_id"],),
        ).fetchone()
        if membership_row is None:
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
                VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?)
                """,
                (
                    seed["user_id"],
                    seed["email"],
                    seed["tier"],
                    seed["status"],
                    seed["description"],
                    timestamp,
                    timestamp,
                    timestamp,
                ),
            )
            effective_tier = seed["tier"]
            effective_status = seed["status"]
            effective_email = seed["email"]
        else:
            effective_tier = membership_row["tier"]
            effective_status = membership_row["status"]
            effective_email = membership_row["email"] or seed["email"]

        business_row = connection.execute(
            "SELECT user_id FROM business_users WHERE user_id = ?",
            (seed["user_id"],),
        ).fetchone()
        if business_row is None:
            connection.execute(
                """
                INSERT INTO business_users (
                    user_id,
                    email,
                    display_name,
                    title,
                    organization,
                    bio,
                    description,
                    tier,
                    status,
                    role_home_path,
                    auth_source,
                    locale,
                    is_seed,
                    created_at,
                    updated_at,
                    last_seen_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
                """,
                (
                    seed["user_id"],
                    effective_email,
                    seed["display_name"],
                    seed["title"],
                    seed["organization"],
                    seed["bio"],
                    seed["description"],
                    effective_tier,
                    effective_status,
                    role_home_path_for_tier(effective_tier),
                    seed["auth_source"],
                    seed["locale"],
                    timestamp,
                    timestamp,
                    timestamp,
                ),
            )
        else:
            connection.execute(
                """
                UPDATE business_users
                SET email = ?,
                    display_name = ?,
                    title = ?,
                    organization = ?,
                    bio = ?,
                    description = ?,
                    tier = ?,
                    status = ?,
                    role_home_path = ?,
                    auth_source = ?,
                    locale = ?,
                    is_seed = 1,
                    updated_at = ?,
                    last_seen_at = ?
                WHERE user_id = ?
                """,
                (
                    effective_email,
                    seed["display_name"],
                    seed["title"],
                    seed["organization"],
                    seed["bio"],
                    seed["description"],
                    effective_tier,
                    effective_status,
                    role_home_path_for_tier(effective_tier),
                    seed["auth_source"],
                    seed["locale"],
                    timestamp,
                    timestamp,
                    seed["user_id"],
                ),
            )

    _ensure_seed_user_assets(connection)


def _ensure_seed_user_assets(connection) -> None:
    article_rows = connection.execute(
        "SELECT id FROM articles ORDER BY publish_date DESC, id DESC LIMIT 12"
    ).fetchall()
    article_ids = [int(row["id"]) for row in article_rows]
    if not article_ids:
        return

    tag_slug = connection.execute("SELECT slug, name FROM tags ORDER BY article_count DESC, id ASC LIMIT 1").fetchone()
    column_slug = connection.execute("SELECT slug, name FROM columns ORDER BY sort_order ASC, id ASC LIMIT 1").fetchone()
    topic_slug = connection.execute("SELECT slug, title FROM topics ORDER BY id ASC LIMIT 1").fetchone()

    seed_windows = {
        "mock-free-member": {"views": article_ids[:4], "likes": article_ids[:2], "bookmarks": article_ids[1:3]},
        "mock-paid-member": {"views": article_ids[:6], "likes": article_ids[:3], "bookmarks": article_ids[2:6]},
        "mock-admin": {"views": article_ids[:2], "likes": article_ids[:1], "bookmarks": article_ids[:1]},
    }

    for user_id, payload in seed_windows.items():
        visitor_id = f"{user_id}-visitor"
        profile_row = connection.execute(
            "SELECT visitor_id FROM visitor_profiles WHERE visitor_id = ?",
            (visitor_id,),
        ).fetchone()
        if profile_row is None:
            connection.execute(
                """
                INSERT INTO visitor_profiles (visitor_id, user_id, first_seen_at, last_seen_at)
                VALUES (?, ?, ?, ?)
                """,
                (visitor_id, user_id, _now_iso(), _now_iso()),
            )

        for offset, article_id in enumerate(payload["views"]):
            view_date = (date.today() - timedelta(days=offset % 4)).isoformat()
            created_at = datetime.combine(
                date.fromisoformat(view_date),
                datetime.min.time(),
            ).replace(hour=9 + (offset % 5)).isoformat()
            connection.execute(
                """
                INSERT INTO article_view_events (
                    article_id,
                    visitor_id,
                    user_id,
                    view_date,
                    source,
                    created_at
                )
                VALUES (?, ?, ?, ?, 'seed-user', ?)
                ON CONFLICT(article_id, visitor_id, view_date)
                DO UPDATE SET user_id = excluded.user_id, created_at = excluded.created_at
                """,
                (article_id, visitor_id, user_id, view_date, created_at),
            )

        for reaction_type, reaction_articles in (
            ("like", payload["likes"]),
            ("bookmark", payload["bookmarks"]),
        ):
            for index, article_id in enumerate(reaction_articles):
                updated_at = (datetime.now() - timedelta(hours=index)).replace(microsecond=0).isoformat()
                connection.execute(
                    """
                    INSERT INTO article_reactions (
                        article_id,
                        user_id,
                        reaction_type,
                        is_active,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, 1, ?, ?)
                    ON CONFLICT(article_id, user_id, reaction_type)
                    DO UPDATE SET is_active = 1, updated_at = excluded.updated_at
                    """,
                    (article_id, user_id, reaction_type, updated_at, updated_at),
                )

        follows = []
        if tag_slug is not None:
            follows.append(("tag", tag_slug["slug"], tag_slug["name"]))
        if column_slug is not None:
            follows.append(("column", column_slug["slug"], column_slug["name"]))
        if topic_slug is not None:
            follows.append(("topic", topic_slug["slug"], topic_slug["title"]))

        for entity_type, entity_slug, entity_label in follows[:2]:
            connection.execute(
                """
                INSERT INTO user_follows (
                    user_id,
                    entity_type,
                    entity_slug,
                    entity_label,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id, entity_type, entity_slug)
                DO NOTHING
                """,
                (user_id, entity_type, entity_slug, entity_label, _now_iso()),
            )


def ensure_business_user_profile(
    user_id: str,
    email: str | None,
    tier: str,
    status: str,
    *,
    auth_source: str = "supabase",
    connection=None,
) -> None:
    normalized_tier = _normalize_tier(tier)
    normalized_status = _normalize_status(status)
    defaults = _default_profile_fields(user_id, email, normalized_tier, normalized_status)
    timestamp = _now_iso()

    if connection is None:
        with connection_scope() as managed_connection:
            _ensure_business_user_profile_with_connection(
                managed_connection,
                user_id,
                email,
                normalized_tier,
                normalized_status,
                auth_source=auth_source,
                defaults=defaults,
            )
            managed_connection.commit()
        return

    _ensure_business_user_profile_with_connection(
        connection,
        user_id,
        email,
        normalized_tier,
        normalized_status,
        auth_source=auth_source,
        defaults=defaults,
    )


def _ensure_business_user_profile_with_connection(
    connection,
    user_id: str,
    email: str | None,
    normalized_tier: str,
    normalized_status: str,
    *,
    auth_source: str,
    defaults: dict,
) -> None:
    timestamp = _now_iso()
    row = connection.execute(
        "SELECT user_id FROM business_users WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    if row is None:
        connection.execute(
            """
            INSERT INTO business_users (
                user_id,
                email,
                display_name,
                title,
                organization,
                bio,
                description,
                tier,
                status,
                role_home_path,
                auth_source,
                locale,
                is_seed,
                created_at,
                updated_at,
                last_seen_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                email or defaults.get("email"),
                defaults["display_name"],
                defaults["title"],
                defaults["organization"],
                defaults["bio"],
                defaults.get("description"),
                normalized_tier,
                normalized_status,
                role_home_path_for_tier(normalized_tier),
                auth_source if auth_source != "supabase" else defaults.get("auth_source", auth_source),
                defaults.get("locale", "zh-CN"),
                1 if defaults.get("auth_source") == "seed" else 0,
                timestamp,
                timestamp,
                timestamp,
            ),
        )
        return

    connection.execute(
        """
        UPDATE business_users
        SET email = ?,
            tier = ?,
            status = ?,
            role_home_path = ?,
            auth_source = ?,
            updated_at = ?,
            last_seen_at = ?
        WHERE user_id = ?
        """,
        (
            email or defaults.get("email"),
            normalized_tier,
            normalized_status,
            role_home_path_for_tier(normalized_tier),
            auth_source if auth_source != "supabase" else defaults.get("auth_source", auth_source),
            timestamp,
            timestamp,
            user_id,
        ),
    )


def get_business_profile(user: dict | None, membership: dict | None) -> dict:
    if not user or not membership or not membership.get("user_id"):
        return build_guest_business_profile()

    auth_source = "debug" if (user.get("raw_user") or {}).get("debug") else "supabase"
    ensure_business_user_profile(
        membership["user_id"],
        membership.get("email") or user.get("email"),
        membership.get("tier"),
        membership.get("status"),
        auth_source=auth_source,
    )
    with connection_scope() as connection:
        row = connection.execute(
            """
            SELECT
                user_id,
                email,
                display_name,
                title,
                organization,
                bio,
                description,
                tier,
                status,
                role_home_path,
                auth_source,
                locale,
                is_seed
            FROM business_users
            WHERE user_id = ?
            """,
            (membership["user_id"],),
        ).fetchone()
    if row is None:
        return build_guest_business_profile()
    return _serialize_business_profile(row, membership, is_authenticated=True)


def list_mock_accounts() -> list[dict]:
    if not PREVIEW_AUTH_ENABLED:
        return []
    with connection_scope() as connection:
        rows = connection.execute(
            """
            SELECT
                user_id,
                email,
                display_name,
                title,
                organization,
                description,
                tier,
                status,
                role_home_path
            FROM business_users
            WHERE is_seed = 1
            ORDER BY
                CASE tier
                    WHEN 'free_member' THEN 1
                    WHEN 'paid_member' THEN 2
                    WHEN 'admin' THEN 3
                    ELSE 4
                END,
                user_id ASC
            """
        ).fetchall()
    return [_serialize_mock_account(row) for row in rows]


def get_user_asset_summary(user_id: str | None, membership: dict | None) -> dict:
    if not user_id:
        return {
            "bookmark_count": 0,
            "like_count": 0,
            "recent_view_count": 0,
            "follow_count": 0,
            "knowledge_theme_count": 0,
            "knowledge_article_count": 0,
            "accessible_media_count": 0,
            "unlocked_access_level": "public",
        }

    if membership and membership.get("can_access_paid"):
        media_levels = ("public", "member", "paid")
        unlocked_access_level = "paid"
    elif membership and membership.get("can_access_member"):
        media_levels = ("public", "member")
        unlocked_access_level = "member"
    else:
        media_levels = ("public",)
        unlocked_access_level = "public"

    with connection_scope() as connection:
        bookmark_count = connection.execute(
            """
            SELECT COUNT(*)
            FROM article_reactions
            WHERE user_id = ? AND reaction_type = 'bookmark' AND is_active = 1
            """,
            (user_id,),
        ).fetchone()[0]
        like_count = connection.execute(
            """
            SELECT COUNT(*)
            FROM article_reactions
            WHERE user_id = ? AND reaction_type = 'like' AND is_active = 1
            """,
            (user_id,),
        ).fetchone()[0]
        recent_view_count = connection.execute(
            """
            SELECT COUNT(DISTINCT article_id)
            FROM article_view_events
            WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()[0]
        follow_count = connection.execute(
            """
            SELECT COUNT(*)
            FROM user_follows
            WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()[0]
        knowledge_theme_count = connection.execute(
            """
            SELECT COUNT(*)
            FROM user_knowledge_themes
            WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()[0]
        knowledge_article_count = connection.execute(
            """
            SELECT COUNT(*)
            FROM user_knowledge_theme_articles ukta
            JOIN user_knowledge_themes ukt ON ukt.id = ukta.theme_id
            WHERE ukt.user_id = ?
            """,
            (user_id,),
        ).fetchone()[0]
        placeholders = ",".join("?" for _ in media_levels)
        accessible_media_count = connection.execute(
            f"""
            SELECT COUNT(*)
            FROM media_items
            WHERE status = 'published'
              AND visibility IN ({placeholders})
            """,
            media_levels,
        ).fetchone()[0]

    return {
        "bookmark_count": int(bookmark_count),
        "like_count": int(like_count),
        "recent_view_count": int(recent_view_count),
        "follow_count": int(follow_count),
        "knowledge_theme_count": int(knowledge_theme_count),
        "knowledge_article_count": int(knowledge_article_count),
        "accessible_media_count": int(accessible_media_count),
        "unlocked_access_level": unlocked_access_level,
    }


def get_user_dashboard(user: dict | None, membership: dict | None) -> dict:
    business_profile = get_business_profile(user, membership)
    tier = business_profile["tier"]
    asset_summary = get_user_asset_summary(business_profile.get("user_id"), membership)

    dashboard_copy = {
        "guest": {
            "welcome_title": "以访客身份进入公开知识层",
            "welcome_description": "当前可浏览公开文章与公开音视频样刊。登录后可进入个人资产、会员权益与更完整的内容权限。",
            "quick_links": [
                {"label": "登录中心", "path": "/login", "description": "进入统一登录页，并按身份自动进入对应工作区。"},
                {"label": "会员方案", "path": "/membership", "description": "查看免费会员、付费会员与后台角色的差异。"},
                {"label": "公开内容", "path": "/", "description": "继续浏览首页、专题和公开文章。"},
            ],
        },
        "free_member": {
            "welcome_title": "欢迎进入免费会员知识工作台",
            "welcome_description": "你已经拥有收藏、点赞、历史与关注能力，适合持续沉淀个人知识资产，并承接后续付费升级。",
            "quick_links": [
                {"label": "我的资产", "path": "/me", "description": "查看收藏、点赞、历史和资产概览。"},
                {"label": "我的关注", "path": "/following", "description": "沿着关注标签、栏目和专题继续阅读。"},
                {"label": "升级会员", "path": "/membership", "description": "解锁完整付费文章、音频和视频。"},
            ],
        },
        "paid_member": {
            "welcome_title": "欢迎进入付费会员专属空间",
            "welcome_description": "你已经拥有完整付费正文、会员音视频与更高价值知识产品入口。",
            "quick_links": [
                {"label": "会员权益", "path": "/membership", "description": "查看已解锁的付费文章、音频和视频权益。"},
                {"label": "音频节目", "path": "/audio", "description": "进入完整音频流与试听入口。"},
                {"label": "视频节目", "path": "/video", "description": "进入公开视频、试看与会员视频入口。"},
            ],
        },
        "admin": {
            "welcome_title": "欢迎进入管理员控制台",
            "welcome_description": "你可以管理用户角色、查看审计日志、进入内容后台并核验角色分发是否正确。",
            "quick_links": [
                {"label": "管理总览", "path": "/admin", "description": "查看角色分布、最近用户与最近调权记录。"},
                {"label": "会员管理", "path": "/admin/memberships", "description": "调整用户等级、状态与到期时间。"},
                {"label": "文章后台", "path": "/editorial", "description": "进入内容编辑、审核与发布工作流。"},
            ],
        },
    }
    copy = dashboard_copy.get(tier, dashboard_copy["guest"])

    return {
        "business_profile": business_profile,
        "membership": membership or {
            "tier": "guest",
            "tier_label": membership_tier_label("guest"),
            "status": "anonymous",
            "status_label": membership_status_label("anonymous"),
            "is_authenticated": False,
            "is_admin": False,
            "can_access_member": False,
            "can_access_paid": False,
            "user_id": None,
            "email": None,
            "note": None,
            "started_at": None,
            "expires_at": None,
            "benefits": [],
        },
        "asset_summary": asset_summary,
        "quick_links": copy["quick_links"],
        "welcome_title": copy["welcome_title"],
        "welcome_description": copy["welcome_description"],
    }


def record_admin_role_audit(
    connection,
    *,
    target_user_id: str,
    actor_user_id: str | None,
    actor_email: str | None,
    previous_tier: str | None,
    next_tier: str,
    previous_status: str | None,
    next_status: str,
    note: str | None = None,
) -> None:
    connection.execute(
        """
        INSERT INTO admin_role_audit_logs (
            target_user_id,
            actor_user_id,
            actor_email,
            previous_tier,
            next_tier,
            previous_status,
            next_status,
            note,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            target_user_id,
            actor_user_id,
            actor_email,
            previous_tier,
            next_tier,
            previous_status,
            next_status,
            note,
            _now_iso(),
        ),
    )


def get_admin_overview(limit: int = 8) -> dict:
    safe_limit = max(3, min(limit, 20))
    with connection_scope() as connection:
        total_users = connection.execute("SELECT COUNT(*) FROM business_users").fetchone()[0]
        paid_members = connection.execute(
            "SELECT COUNT(*) FROM user_memberships WHERE tier = 'paid_member'"
        ).fetchone()[0]
        admin_count = connection.execute(
            "SELECT COUNT(*) FROM user_memberships WHERE tier = 'admin'"
        ).fetchone()[0]
        audit_count = connection.execute(
            "SELECT COUNT(*) FROM admin_role_audit_logs"
        ).fetchone()[0]
        counts = connection.execute(
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
        recent_user_candidates = connection.execute(
            """
            SELECT
                user_id,
                email,
                display_name,
                title,
                organization,
                bio,
                tier,
                status,
                role_home_path,
                auth_source,
                locale,
                is_seed
            FROM business_users
            ORDER BY
                CASE is_seed WHEN 1 THEN 0 ELSE 1 END,
                last_seen_at DESC,
                updated_at DESC
            LIMIT ?
            """,
            (safe_limit * 4,),
        ).fetchall()
        audit_rows = connection.execute(
            """
            SELECT
                id,
                target_user_id,
                actor_user_id,
                actor_email,
                previous_tier,
                next_tier,
                previous_status,
                next_status,
                note,
                created_at
            FROM admin_role_audit_logs
            ORDER BY id DESC
            LIMIT ?
            """,
            (safe_limit,),
        ).fetchall()

    recent_users_rows = []
    seen_recent_users = set()
    for row in recent_user_candidates:
        key = (row["email"] or row["user_id"] or "").strip().lower() or row["user_id"]
        if key in seen_recent_users:
            continue
        seen_recent_users.add(key)
        recent_users_rows.append(row)
        if len(recent_users_rows) >= safe_limit:
            break

    return {
        "metrics": [
            {"label": "用户总数", "value": str(total_users), "detail": "本地业务用户库中的角色化用户数"},
            {"label": "付费会员", "value": str(paid_members), "detail": "当前可访问付费正文与音视频的用户数"},
            {"label": "管理员", "value": str(admin_count), "detail": "拥有后台入口与调权能力的用户数"},
            {"label": "调权记录", "value": str(audit_count), "detail": "管理员等级调整与状态调整审计条数"},
        ],
        "role_counts": [
            {
                "tier": row["tier"],
                "tier_label": membership_tier_label(row["tier"]),
                "total": row["total"],
            }
            for row in counts
        ],
        "recent_users": [
            _serialize_business_profile(
                row,
                {
                    "tier": row["tier"],
                    "status": row["status"],
                },
                is_authenticated=True,
            )
            for row in recent_users_rows
        ],
        "recent_audits": [
            {
                "id": row["id"],
                "target_user_id": row["target_user_id"],
                "actor_user_id": row["actor_user_id"],
                "actor_email": row["actor_email"],
                "previous_tier": row["previous_tier"],
                "next_tier": row["next_tier"],
                "previous_status": row["previous_status"],
                "next_status": row["next_status"],
                "note": row["note"],
                "created_at": row["created_at"],
            }
            for row in audit_rows
        ],
    }
