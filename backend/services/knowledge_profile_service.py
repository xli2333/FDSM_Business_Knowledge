from __future__ import annotations

import json
from collections import Counter
from datetime import datetime

from backend.database import connection_scope, ensure_runtime_tables

ensure_runtime_tables()


def _now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def _top_labels(rows, key: str, *, limit: int = 3) -> list[str]:
    counter: Counter[str] = Counter()
    for row in rows:
        raw_value = str(row[key] or "").strip()
        if not raw_value:
            continue
        for part in [item.strip() for item in raw_value.split(" | ") if item.strip()]:
            counter[part] += 1
    return [item for item, _ in counter.most_common(limit)]


def refresh_user_library_profile(user_id: str) -> dict:
    timestamp = _now_iso()
    with connection_scope() as connection:
        rows = connection.execute(
            """
            SELECT
                usa.article_id,
                usa.updated_at,
                a.main_topic,
                a.tag_text,
                a.publish_date,
                a.title
            FROM user_saved_articles usa
            JOIN articles a ON a.id = usa.article_id
            WHERE usa.user_id = ? AND usa.is_active = 1
            ORDER BY usa.updated_at DESC, usa.article_id DESC
            """,
            (user_id,),
        ).fetchall()
        saved_count = len(rows)
        latest_saved_at = rows[0]["updated_at"] if rows else None
        top_topics = _top_labels(rows, "main_topic")
        top_tags = _top_labels(rows, "tag_text")
        summary_text = None
        if saved_count > 0:
            focus = " / ".join(top_topics or top_tags[:3])
            summary_text = f"已收藏 {saved_count} 篇文章" + (f"，当前重点覆盖 {focus}" if focus else "")
        profile_payload = {
            "top_topics": top_topics,
            "top_tags": top_tags,
            "latest_titles": [str(row["title"]) for row in rows[:3]],
        }
        connection.execute(
            """
            INSERT INTO user_library_profiles (
                user_id,
                saved_count,
                latest_saved_at,
                summary_text,
                profile_json,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                saved_count = excluded.saved_count,
                latest_saved_at = excluded.latest_saved_at,
                summary_text = excluded.summary_text,
                profile_json = excluded.profile_json,
                updated_at = excluded.updated_at
            """,
            (
                user_id,
                saved_count,
                latest_saved_at,
                summary_text,
                json.dumps(profile_payload, ensure_ascii=False),
                timestamp,
                timestamp,
            ),
        )
        connection.commit()
    return {
        "saved_count": saved_count,
        "latest_saved_at": latest_saved_at,
        "summary_text": summary_text,
        **profile_payload,
    }


def get_user_library_profile(user_id: str) -> dict:
    with connection_scope() as connection:
        row = connection.execute(
            """
            SELECT saved_count, latest_saved_at, summary_text, profile_json
            FROM user_library_profiles
            WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()
    if row is None:
        return refresh_user_library_profile(user_id)
    try:
        profile_payload = json.loads(row["profile_json"] or "{}")
    except json.JSONDecodeError:
        profile_payload = {}
    return {
        "saved_count": int(row["saved_count"] or 0),
        "latest_saved_at": row["latest_saved_at"],
        "summary_text": row["summary_text"],
        "top_topics": list(profile_payload.get("top_topics") or []),
        "top_tags": list(profile_payload.get("top_tags") or []),
        "latest_titles": list(profile_payload.get("latest_titles") or []),
    }


def refresh_theme_profile(theme_id: int) -> dict:
    timestamp = _now_iso()
    with connection_scope() as connection:
        theme_row = connection.execute(
            """
            SELECT id, user_id, title, description
            FROM user_knowledge_themes
            WHERE id = ?
            """,
            (theme_id,),
        ).fetchone()
        if theme_row is None:
            raise ValueError("Theme not found")
        rows = connection.execute(
            """
            SELECT
                a.id,
                a.publish_date,
                a.main_topic,
                a.tag_text
            FROM user_knowledge_theme_articles ta
            JOIN articles a ON a.id = ta.article_id
            WHERE ta.theme_id = ?
            ORDER BY ta.created_at DESC, a.publish_date DESC, a.id DESC
            """,
            (theme_id,),
        ).fetchall()
        article_count = len(rows)
        latest_publish_date = rows[0]["publish_date"] if rows else None
        top_topics = _top_labels(rows, "main_topic")
        top_tags = _top_labels(rows, "tag_text")
        summary_text = str(theme_row["description"] or "").strip() or None
        if not summary_text and article_count > 0:
            focus = " / ".join(top_topics or top_tags[:3])
            summary_text = f"收录 {article_count} 篇文章" + (f"，当前重点围绕 {focus}" if focus else "")
        profile_payload = {
            "top_topics": top_topics,
            "top_tags": top_tags,
            "theme_title": theme_row["title"],
        }
        connection.execute(
            """
            INSERT INTO user_theme_profiles (
                theme_id,
                user_id,
                article_count,
                latest_publish_date,
                summary_text,
                profile_json,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(theme_id) DO UPDATE SET
                user_id = excluded.user_id,
                article_count = excluded.article_count,
                latest_publish_date = excluded.latest_publish_date,
                summary_text = excluded.summary_text,
                profile_json = excluded.profile_json,
                updated_at = excluded.updated_at
            """,
            (
                theme_id,
                theme_row["user_id"],
                article_count,
                latest_publish_date,
                summary_text,
                json.dumps(profile_payload, ensure_ascii=False),
                timestamp,
                timestamp,
            ),
        )
        connection.commit()
    return {
        "article_count": article_count,
        "latest_publish_date": latest_publish_date,
        "summary_text": summary_text,
        **profile_payload,
    }


def get_theme_profile(theme_id: int) -> dict:
    with connection_scope() as connection:
        row = connection.execute(
            """
            SELECT article_count, latest_publish_date, summary_text, profile_json
            FROM user_theme_profiles
            WHERE theme_id = ?
            """,
            (theme_id,),
        ).fetchone()
    if row is None:
        return refresh_theme_profile(theme_id)
    try:
        profile_payload = json.loads(row["profile_json"] or "{}")
    except json.JSONDecodeError:
        profile_payload = {}
    return {
        "article_count": int(row["article_count"] or 0),
        "latest_publish_date": row["latest_publish_date"],
        "summary_text": row["summary_text"],
        "top_topics": list(profile_payload.get("top_topics") or []),
        "top_tags": list(profile_payload.get("top_tags") or []),
        "theme_title": profile_payload.get("theme_title"),
    }
