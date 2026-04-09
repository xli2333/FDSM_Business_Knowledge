from __future__ import annotations

from datetime import datetime
import csv
import io

from backend.config import FAISS_DB_DIR
from backend.database import connection_scope
from backend.services import ai_service
from backend.services.catalog_service import list_topics


def get_commerce_overview() -> dict:
    with connection_scope() as connection:
        article_count = connection.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
        tag_count = connection.execute("SELECT COUNT(*) FROM tags").fetchone()[0]
        topic_count = connection.execute(
            "SELECT COUNT(*) FROM topics WHERE status = 'published'"
        ).fetchone()[0]
        column_count = connection.execute("SELECT COUNT(*) FROM columns").fetchone()[0]
        latest_publish_date = connection.execute(
            "SELECT MAX(publish_date) FROM articles"
        ).fetchone()[0]
        updated_at_row = connection.execute(
            "SELECT value FROM meta WHERE key = 'updated_at'"
        ).fetchone()
        lead_count = connection.execute("SELECT COUNT(*) FROM demo_requests").fetchone()[0]
        hot_tags = connection.execute(
            """
            SELECT id, name, slug, category, color, article_count
            FROM tags
            WHERE category IN ('topic', 'industry')
            ORDER BY article_count DESC, name ASC
            LIMIT 6
            """
        ).fetchall()

    metrics = [
        {
            "label": "业务文章",
            "value": str(article_count),
            "detail": f"最新数据覆盖至 {latest_publish_date}",
        },
        {
            "label": "标签体系",
            "value": str(tag_count),
            "detail": "行业、主题、类型、实体多维索引",
        },
        {
            "label": "专题栏目",
            "value": str(topic_count + column_count),
            "detail": f"{topic_count} 个专题 + {column_count} 个栏目",
        },
        {
            "label": "商业线索",
            "value": str(lead_count),
            "detail": "演示申请与商业咨询统一沉淀",
        },
    ]

    return {
        "metrics": metrics,
        "top_topics": list_topics()[:4],
        "hot_tags": [dict(row) for row in hot_tags],
        "faiss_ready": (FAISS_DB_DIR / "index.faiss").exists(),
        "ai_ready": ai_service.is_ai_enabled(),
        "updated_at": updated_at_row["value"] if updated_at_row else None,
        "lead_count": lead_count,
    }


def create_demo_request(payload: dict) -> dict:
    created_at = datetime.utcnow().isoformat()
    summary = f"{payload['organization']} / {payload['role']} / {payload['use_case']}"
    with connection_scope() as connection:
        connection.execute(
            """
            INSERT INTO demo_requests (
                name, organization, role, email, phone, use_case, message, status, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 'new', ?)
            """,
            (
                payload["name"].strip(),
                payload["organization"].strip(),
                payload["role"].strip(),
                payload["email"].strip(),
                (payload.get("phone") or "").strip(),
                payload["use_case"].strip(),
                (payload.get("message") or "").strip(),
                created_at,
            ),
        )
        request_id = connection.execute("SELECT last_insert_rowid()").fetchone()[0]
        connection.commit()
    return {
        "id": request_id,
        "status": "new",
        "created_at": created_at,
        "summary": summary,
    }


def list_demo_requests(limit: int = 50) -> list[dict]:
    safe_limit = max(1, min(limit, 200))
    with connection_scope() as connection:
        rows = connection.execute(
            """
            SELECT id, name, organization, role, email, phone, use_case, message, status, created_at
            FROM demo_requests
            ORDER BY id DESC
            LIMIT ?
            """,
            (safe_limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def export_demo_requests_csv(limit: int = 200) -> str:
    rows = list_demo_requests(limit=limit)
    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer,
        fieldnames=[
            "id",
            "name",
            "organization",
            "role",
            "email",
            "phone",
            "use_case",
            "message",
            "status",
            "created_at",
        ],
    )
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()
