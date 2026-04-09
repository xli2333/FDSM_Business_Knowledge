from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime

from backend.config import BILLING_PLAN_DEFINITIONS, PAYMENTS_ENABLED, PAYMENT_PROVIDER, SQLITE_DB_PATH

REQUIRED_TABLES = {
    "articles",
    "tags",
    "article_tags",
    "columns",
    "article_columns",
    "topics",
    "topic_articles",
    "topic_tags",
    "featured_articles",
    "chat_sessions",
    "chat_messages",
}


def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(SQLITE_DB_PATH, timeout=60)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 60000")
    return connection


@contextmanager
def connection_scope():
    connection = get_connection()
    try:
        yield connection
    finally:
        connection.close()


def database_is_ready() -> bool:
    if not SQLITE_DB_PATH.exists():
        return False
    with connection_scope() as connection:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
        ).fetchall()
    existing = {row["name"] for row in rows}
    return REQUIRED_TABLES.issubset(existing)


def _table_has_column(connection: sqlite3.Connection, table_name: str, column_name: str) -> bool:
    rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    return any(row["name"] == column_name for row in rows)


def ensure_database_ready(force_rebuild: bool = False) -> None:
    if force_rebuild or not database_is_ready():
        from backend.scripts.build_business_db import rebuild_database

        rebuild_database()


def ensure_runtime_tables() -> None:
    with connection_scope() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS demo_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                organization TEXT NOT NULL,
                role TEXT NOT NULL,
                email TEXT NOT NULL,
                phone TEXT,
                use_case TEXT NOT NULL,
                message TEXT,
                status TEXT NOT NULL DEFAULT 'new',
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_demo_requests_created_at
            ON demo_requests(created_at DESC);

            CREATE TABLE IF NOT EXISTS editorial_articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                article_id INTEGER REFERENCES articles(id),
                source_article_id INTEGER REFERENCES articles(id),
                slug TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                subtitle TEXT,
                author TEXT,
                organization TEXT,
                publish_date TEXT NOT NULL,
                source_url TEXT,
                cover_image_url TEXT,
                primary_column_slug TEXT,
                article_type TEXT,
                main_topic TEXT,
                source_markdown TEXT NOT NULL DEFAULT '',
                layout_mode TEXT NOT NULL DEFAULT 'auto',
                formatting_notes TEXT,
                formatter_model TEXT,
                last_formatted_at TEXT,
                content_markdown TEXT NOT NULL,
                plain_text_content TEXT NOT NULL,
                excerpt TEXT,
                tag_payload_json TEXT NOT NULL DEFAULT '[]',
                html_web TEXT,
                html_wechat TEXT,
                status TEXT NOT NULL DEFAULT 'draft',
                ai_synced_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                published_at TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_editorial_articles_status
            ON editorial_articles(status, updated_at DESC);

            CREATE INDEX IF NOT EXISTS idx_editorial_articles_article_id
            ON editorial_articles(article_id);

            CREATE TABLE IF NOT EXISTS visitor_profiles (
                visitor_id TEXT PRIMARY KEY,
                user_id TEXT,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS article_view_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                article_id INTEGER NOT NULL REFERENCES articles(id),
                visitor_id TEXT NOT NULL,
                user_id TEXT,
                view_date TEXT NOT NULL,
                source TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(article_id, visitor_id, view_date)
            );

            CREATE INDEX IF NOT EXISTS idx_article_view_events_article
            ON article_view_events(article_id, view_date DESC);

            CREATE INDEX IF NOT EXISTS idx_article_view_events_user
            ON article_view_events(user_id, created_at DESC);

            CREATE TABLE IF NOT EXISTS article_reactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                article_id INTEGER NOT NULL REFERENCES articles(id),
                user_id TEXT NOT NULL,
                reaction_type TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(article_id, user_id, reaction_type)
            );

            CREATE INDEX IF NOT EXISTS idx_article_reactions_article
            ON article_reactions(article_id, reaction_type, is_active);

            CREATE INDEX IF NOT EXISTS idx_article_reactions_user
            ON article_reactions(user_id, updated_at DESC);

            CREATE TABLE IF NOT EXISTS user_follows (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_slug TEXT NOT NULL,
                entity_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(user_id, entity_type, entity_slug)
            );

            CREATE INDEX IF NOT EXISTS idx_user_follows_user
            ON user_follows(user_id, created_at DESC);

            CREATE TABLE IF NOT EXISTS user_memberships (
                user_id TEXT PRIMARY KEY,
                email TEXT,
                tier TEXT NOT NULL DEFAULT 'free_member',
                status TEXT NOT NULL DEFAULT 'active',
                note TEXT,
                started_at TEXT NOT NULL,
                expires_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_user_memberships_tier
            ON user_memberships(tier, status, updated_at DESC);

            CREATE INDEX IF NOT EXISTS idx_user_memberships_email
            ON user_memberships(email);

            CREATE TABLE IF NOT EXISTS business_users (
                user_id TEXT PRIMARY KEY,
                email TEXT,
                display_name TEXT NOT NULL,
                title TEXT,
                organization TEXT,
                bio TEXT,
                description TEXT,
                tier TEXT NOT NULL DEFAULT 'free_member',
                status TEXT NOT NULL DEFAULT 'active',
                role_home_path TEXT NOT NULL DEFAULT '/',
                auth_source TEXT NOT NULL DEFAULT 'supabase',
                locale TEXT NOT NULL DEFAULT 'zh-CN',
                is_seed INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_business_users_tier
            ON business_users(tier, status, updated_at DESC);

            CREATE INDEX IF NOT EXISTS idx_business_users_email
            ON business_users(email);

            CREATE TABLE IF NOT EXISTS admin_role_audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target_user_id TEXT NOT NULL,
                actor_user_id TEXT,
                actor_email TEXT,
                previous_tier TEXT,
                next_tier TEXT NOT NULL,
                previous_status TEXT,
                next_status TEXT NOT NULL,
                note TEXT,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_admin_role_audit_target
            ON admin_role_audit_logs(target_user_id, created_at DESC);

            CREATE TABLE IF NOT EXISTS media_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slug TEXT UNIQUE NOT NULL,
                kind TEXT NOT NULL,
                title TEXT NOT NULL,
                summary TEXT NOT NULL,
                speaker TEXT,
                series_name TEXT,
                episode_number INTEGER NOT NULL DEFAULT 1,
                publish_date TEXT NOT NULL,
                duration_seconds INTEGER NOT NULL DEFAULT 0,
                visibility TEXT NOT NULL DEFAULT 'public',
                status TEXT NOT NULL DEFAULT 'published',
                cover_image_url TEXT,
                media_url TEXT,
                preview_url TEXT,
                source_url TEXT,
                body_markdown TEXT NOT NULL DEFAULT '',
                transcript_markdown TEXT NOT NULL DEFAULT '',
                chapter_payload_json TEXT NOT NULL DEFAULT '[]',
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_media_items_kind
            ON media_items(kind, status, publish_date DESC, sort_order ASC);

            CREATE TABLE IF NOT EXISTS billing_plans (
                plan_code TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                tier TEXT NOT NULL,
                price_cents INTEGER NOT NULL DEFAULT 0,
                currency TEXT NOT NULL DEFAULT 'CNY',
                billing_period TEXT NOT NULL DEFAULT 'month',
                headline TEXT,
                description TEXT,
                features_json TEXT NOT NULL DEFAULT '[]',
                is_public INTEGER NOT NULL DEFAULT 1,
                is_enabled INTEGER NOT NULL DEFAULT 0,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS billing_checkout_intents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                email TEXT,
                plan_code TEXT NOT NULL,
                status TEXT NOT NULL,
                payment_provider TEXT NOT NULL,
                redirect_url TEXT,
                note TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_billing_checkout_intents_user
            ON billing_checkout_intents(user_id, created_at DESC);

            CREATE TABLE IF NOT EXISTS billing_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                email TEXT,
                plan_code TEXT NOT NULL,
                amount_cents INTEGER NOT NULL DEFAULT 0,
                currency TEXT NOT NULL DEFAULT 'CNY',
                status TEXT NOT NULL,
                payment_provider TEXT NOT NULL,
                checkout_intent_id INTEGER,
                provider_order_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_billing_orders_user
            ON billing_orders(user_id, created_at DESC);

            CREATE TABLE IF NOT EXISTS billing_subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                email TEXT,
                plan_code TEXT NOT NULL,
                tier TEXT NOT NULL,
                status TEXT NOT NULL,
                started_at TEXT NOT NULL,
                expires_at TEXT,
                auto_renew INTEGER NOT NULL DEFAULT 0,
                payment_provider TEXT NOT NULL,
                provider_subscription_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_billing_subscriptions_user
            ON billing_subscriptions(user_id, status, updated_at DESC);

            CREATE TABLE IF NOT EXISTS article_translations (
                article_id INTEGER NOT NULL REFERENCES articles(id),
                target_lang TEXT NOT NULL,
                source_hash TEXT NOT NULL,
                title TEXT NOT NULL,
                excerpt TEXT,
                summary TEXT NOT NULL,
                content TEXT NOT NULL,
                model TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (article_id, target_lang, source_hash)
            );

            CREATE INDEX IF NOT EXISTS idx_article_translations_lookup
            ON article_translations(article_id, target_lang, updated_at DESC);

            CREATE TABLE IF NOT EXISTS article_ai_outputs (
                article_id INTEGER NOT NULL REFERENCES articles(id),
                doc_id TEXT,
                slug TEXT,
                relative_path TEXT,
                source_hash TEXT NOT NULL,
                source_lang TEXT NOT NULL DEFAULT 'zh-CN',
                target_lang TEXT NOT NULL DEFAULT 'en',
                source_title TEXT NOT NULL,
                source_excerpt TEXT,
                summary_zh TEXT,
                summary_html_zh TEXT,
                summary_model TEXT,
                formatted_markdown_zh TEXT,
                formatted_markdown_en TEXT,
                translation_title_en TEXT,
                translation_excerpt_en TEXT,
                translation_summary_en TEXT,
                summary_html_en TEXT,
                translation_content_en TEXT,
                html_web_zh TEXT,
                html_wechat_zh TEXT,
                html_web_en TEXT,
                html_wechat_en TEXT,
                summary_status TEXT NOT NULL DEFAULT 'pending',
                format_status TEXT NOT NULL DEFAULT 'pending',
                translation_status TEXT NOT NULL DEFAULT 'pending',
                summary_error TEXT,
                format_error TEXT,
                translation_error TEXT,
                translation_model TEXT,
                format_model TEXT,
                format_template TEXT NOT NULL DEFAULT 'fudan-business-knowledge-v1',
                status TEXT NOT NULL DEFAULT 'pending',
                error_message TEXT,
                worker_name TEXT,
                started_at TEXT,
                completed_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (article_id, source_hash)
            );

            CREATE INDEX IF NOT EXISTS idx_article_ai_outputs_article
            ON article_ai_outputs(article_id, updated_at DESC);

            CREATE INDEX IF NOT EXISTS idx_article_ai_outputs_status
            ON article_ai_outputs(status, updated_at DESC);
            """
        )

        if not _table_has_column(connection, "articles", "access_level"):
            connection.execute("ALTER TABLE articles ADD COLUMN access_level TEXT NOT NULL DEFAULT 'public'")
        if not _table_has_column(connection, "editorial_articles", "access_level"):
            connection.execute("ALTER TABLE editorial_articles ADD COLUMN access_level TEXT NOT NULL DEFAULT 'public'")
        if not _table_has_column(connection, "editorial_articles", "source_article_id"):
            connection.execute("ALTER TABLE editorial_articles ADD COLUMN source_article_id INTEGER REFERENCES articles(id)")
        if not _table_has_column(connection, "editorial_articles", "workflow_status"):
            connection.execute("ALTER TABLE editorial_articles ADD COLUMN workflow_status TEXT NOT NULL DEFAULT 'draft'")
        if not _table_has_column(connection, "editorial_articles", "review_note"):
            connection.execute("ALTER TABLE editorial_articles ADD COLUMN review_note TEXT")
        if not _table_has_column(connection, "editorial_articles", "scheduled_publish_at"):
            connection.execute("ALTER TABLE editorial_articles ADD COLUMN scheduled_publish_at TEXT")
        if not _table_has_column(connection, "editorial_articles", "submitted_at"):
            connection.execute("ALTER TABLE editorial_articles ADD COLUMN submitted_at TEXT")
        if not _table_has_column(connection, "editorial_articles", "approved_at"):
            connection.execute("ALTER TABLE editorial_articles ADD COLUMN approved_at TEXT")
        if not _table_has_column(connection, "editorial_articles", "ai_synced_at"):
            connection.execute("ALTER TABLE editorial_articles ADD COLUMN ai_synced_at TEXT")
        if not _table_has_column(connection, "editorial_articles", "source_markdown"):
            connection.execute("ALTER TABLE editorial_articles ADD COLUMN source_markdown TEXT NOT NULL DEFAULT ''")
        if not _table_has_column(connection, "editorial_articles", "layout_mode"):
            connection.execute("ALTER TABLE editorial_articles ADD COLUMN layout_mode TEXT NOT NULL DEFAULT 'auto'")
        if not _table_has_column(connection, "editorial_articles", "formatting_notes"):
            connection.execute("ALTER TABLE editorial_articles ADD COLUMN formatting_notes TEXT")
        if not _table_has_column(connection, "editorial_articles", "formatter_model"):
            connection.execute("ALTER TABLE editorial_articles ADD COLUMN formatter_model TEXT")
        if not _table_has_column(connection, "editorial_articles", "last_formatted_at"):
            connection.execute("ALTER TABLE editorial_articles ADD COLUMN last_formatted_at TEXT")
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_editorial_articles_source_article_id
            ON editorial_articles(source_article_id)
            """
        )
        if not _table_has_column(connection, "media_items", "series_name"):
            connection.execute("ALTER TABLE media_items ADD COLUMN series_name TEXT")
        if not _table_has_column(connection, "media_items", "episode_number"):
            connection.execute("ALTER TABLE media_items ADD COLUMN episode_number INTEGER NOT NULL DEFAULT 1")
        if not _table_has_column(connection, "media_items", "media_url"):
            connection.execute("ALTER TABLE media_items ADD COLUMN media_url TEXT")
        if not _table_has_column(connection, "media_items", "preview_url"):
            connection.execute("ALTER TABLE media_items ADD COLUMN preview_url TEXT")
        if not _table_has_column(connection, "media_items", "transcript_markdown"):
            connection.execute("ALTER TABLE media_items ADD COLUMN transcript_markdown TEXT NOT NULL DEFAULT ''")
        if not _table_has_column(connection, "media_items", "chapter_payload_json"):
            connection.execute("ALTER TABLE media_items ADD COLUMN chapter_payload_json TEXT NOT NULL DEFAULT '[]'")
        if not _table_has_column(connection, "business_users", "description"):
            connection.execute("ALTER TABLE business_users ADD COLUMN description TEXT")
        if not _table_has_column(connection, "article_ai_outputs", "translation_title_en"):
            connection.execute("ALTER TABLE article_ai_outputs ADD COLUMN translation_title_en TEXT")
        if not _table_has_column(connection, "article_ai_outputs", "translation_excerpt_en"):
            connection.execute("ALTER TABLE article_ai_outputs ADD COLUMN translation_excerpt_en TEXT")
        if not _table_has_column(connection, "article_ai_outputs", "translation_summary_en"):
            connection.execute("ALTER TABLE article_ai_outputs ADD COLUMN translation_summary_en TEXT")
        if not _table_has_column(connection, "article_ai_outputs", "summary_html_zh"):
            connection.execute("ALTER TABLE article_ai_outputs ADD COLUMN summary_html_zh TEXT")
        if not _table_has_column(connection, "article_ai_outputs", "summary_html_en"):
            connection.execute("ALTER TABLE article_ai_outputs ADD COLUMN summary_html_en TEXT")
        if not _table_has_column(connection, "article_ai_outputs", "translation_content_en"):
            connection.execute("ALTER TABLE article_ai_outputs ADD COLUMN translation_content_en TEXT")
        if not _table_has_column(connection, "article_ai_outputs", "summary_status"):
            connection.execute("ALTER TABLE article_ai_outputs ADD COLUMN summary_status TEXT NOT NULL DEFAULT 'pending'")
        if not _table_has_column(connection, "article_ai_outputs", "format_status"):
            connection.execute("ALTER TABLE article_ai_outputs ADD COLUMN format_status TEXT NOT NULL DEFAULT 'pending'")
        if not _table_has_column(connection, "article_ai_outputs", "translation_status"):
            connection.execute("ALTER TABLE article_ai_outputs ADD COLUMN translation_status TEXT NOT NULL DEFAULT 'pending'")
        if not _table_has_column(connection, "article_ai_outputs", "summary_error"):
            connection.execute("ALTER TABLE article_ai_outputs ADD COLUMN summary_error TEXT")
        if not _table_has_column(connection, "article_ai_outputs", "format_error"):
            connection.execute("ALTER TABLE article_ai_outputs ADD COLUMN format_error TEXT")
        if not _table_has_column(connection, "article_ai_outputs", "translation_error"):
            connection.execute("ALTER TABLE article_ai_outputs ADD COLUMN translation_error TEXT")
        if not _table_has_column(connection, "chat_messages", "follow_ups_json"):
            connection.execute("ALTER TABLE chat_messages ADD COLUMN follow_ups_json TEXT")
        connection.execute(
            """
            UPDATE articles
            SET access_level = 'public'
            WHERE access_level IS NULL OR access_level = ''
            """
        )
        connection.execute(
            """
            UPDATE editorial_articles
            SET access_level = 'public'
            WHERE access_level IS NULL OR access_level = ''
            """
        )
        connection.execute(
            """
            UPDATE editorial_articles
            SET source_markdown = COALESCE(NULLIF(source_markdown, ''), content_markdown)
            WHERE source_markdown IS NULL OR source_markdown = ''
            """
        )
        connection.execute(
            """
            UPDATE editorial_articles
            SET layout_mode = COALESCE(NULLIF(layout_mode, ''), 'auto')
            WHERE layout_mode IS NULL OR layout_mode = ''
            """
        )
        connection.execute(
            """
            UPDATE editorial_articles
            SET workflow_status = CASE
                WHEN status = 'published' THEN 'published'
                ELSE COALESCE(NULLIF(workflow_status, ''), 'draft')
            END
            WHERE workflow_status IS NULL OR workflow_status = '' OR status = 'published'
            """
        )
        connection.execute(
            """
            UPDATE media_items
            SET
                series_name = COALESCE(NULLIF(series_name, ''), CASE
                    WHEN kind = 'audio' THEN '管理者音频'
                    ELSE '管理者视频'
                END),
                episode_number = CASE WHEN episode_number IS NULL OR episode_number <= 0 THEN 1 ELSE episode_number END,
                preview_url = COALESCE(preview_url, source_url),
                transcript_markdown = COALESCE(transcript_markdown, ''),
                chapter_payload_json = COALESCE(NULLIF(chapter_payload_json, ''), '[]')
            """
        )

        timestamp = datetime.now().replace(microsecond=0).isoformat()
        connection.executemany(
            """
            INSERT INTO billing_plans (
                plan_code,
                name,
                tier,
                price_cents,
                currency,
                billing_period,
                headline,
                description,
                features_json,
                is_public,
                is_enabled,
                sort_order,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?)
            ON CONFLICT(plan_code) DO UPDATE SET
                name = excluded.name,
                tier = excluded.tier,
                price_cents = excluded.price_cents,
                currency = excluded.currency,
                billing_period = excluded.billing_period,
                headline = excluded.headline,
                description = excluded.description,
                features_json = excluded.features_json,
                is_public = excluded.is_public,
                is_enabled = excluded.is_enabled,
                sort_order = excluded.sort_order,
                updated_at = excluded.updated_at
            """,
            [
                (
                    item["plan_code"],
                    item["name"],
                    item["tier"],
                    item["price_cents"],
                    item["currency"],
                    item["billing_period"],
                    item["headline"],
                    item["description"],
                    json.dumps(item["features"], ensure_ascii=False),
                    1 if PAYMENTS_ENABLED else 0,
                    item["sort_order"],
                    timestamp,
                    timestamp,
                )
                for item in BILLING_PLAN_DEFINITIONS
            ],
        )

        media_count = connection.execute("SELECT COUNT(*) AS total FROM media_items").fetchone()["total"]
        if media_count == 0:
            timestamp = datetime.now().replace(microsecond=0).isoformat()
            seeds = [
                (
                    "audio-ai-decision-lab",
                    "audio",
                    "AI 决策实验室",
                    "围绕 AI 时代管理判断与组织协同的 20 分钟音频策划样刊。",
                    "复旦商业知识库编辑部",
                    "2026-03-20",
                    1220,
                    "public",
                    "published",
                    "",
                    "",
                    "公开试听内容，用于承接首页与会员页的转化。",
                    1,
                    timestamp,
                    timestamp,
                ),
                (
                    "audio-case-briefing-weekly",
                    "audio",
                    "案例 Briefing 周报",
                    "把一周最值得跟进的商业案例浓缩成可通勤收听的音频快报。",
                    "案例研究团队",
                    "2026-03-18",
                    1560,
                    "member",
                    "published",
                    "",
                    "",
                    "免费会员可收听的栏目，用于提高登录留存。",
                    2,
                    timestamp,
                    timestamp,
                ),
                (
                    "audio-chairman-private-brief",
                    "audio",
                    "董事长私享研判",
                    "面向高阶会员的闭门内容模块，适合沉淀为付费会员专享音频。",
                    "商业研究院",
                    "2026-03-12",
                    2280,
                    "paid",
                    "published",
                    "",
                    "",
                    "付费会员内容样板，用于后续扩展专栏、课程和专报。",
                    3,
                    timestamp,
                    timestamp,
                ),
                (
                    "video-industry-observer",
                    "video",
                    "行业观察视频简报",
                    "对标 36 氪视频栏目，把重点行业变化整理成 8 分钟可传播短视频。",
                    "行业观察编辑部",
                    "2026-03-17",
                    520,
                    "public",
                    "published",
                    "",
                    "",
                    "公开视频样片，用于验证视频栏目布局与商业介绍。",
                    1,
                    timestamp,
                    timestamp,
                ),
                (
                    "video-classroom-clip",
                    "video",
                    "课堂精华剪辑",
                    "来自课程与论坛内容的精华片段，登录后可观看完整解析。",
                    "高管教育中心",
                    "2026-03-15",
                    930,
                    "member",
                    "published",
                    "",
                    "",
                    "会员专享视频样板，可扩展到论坛、课程与活动内容。",
                    2,
                    timestamp,
                    timestamp,
                ),
                (
                    "video-ceo-deep-briefing",
                    "video",
                    "CEO 深度闭门简报",
                    "为付费会员预留的高密度视频模块，适合专题化运营与高客单订阅。",
                    "复旦商业知识库研究团队",
                    "2026-03-08",
                    1980,
                    "paid",
                    "published",
                    "",
                    "",
                    "高价值付费视频样板，可继续扩展为专栏与陪跑服务。",
                    3,
                    timestamp,
                    timestamp,
                ),
            ]
            connection.executemany(
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
                    source_url,
                    body_markdown,
                    sort_order,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                seeds,
            )
            connection.execute(
                """
                UPDATE media_items
                SET
                    series_name = CASE
                        WHEN slug LIKE 'audio-%' THEN '管理者音频'
                        ELSE '管理者视频'
                    END,
                    episode_number = CASE sort_order WHEN 0 THEN 1 ELSE sort_order END,
                    media_url = '',
                    preview_url = source_url,
                    transcript_markdown = summary,
                    chapter_payload_json = '[]'
                WHERE COALESCE(series_name, '') = ''
                """
            )

        from backend.services.user_profile_service import ensure_business_user_seed_state

        ensure_business_user_seed_state(connection)
        connection.commit()
