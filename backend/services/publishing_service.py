from __future__ import annotations

from html import escape

from backend.config import SITE_BASE_URL
from backend.database import connection_scope


def _absolute_url(path: str) -> str:
    return f"{SITE_BASE_URL}{path}"


def build_sitemap_xml() -> str:
    static_urls = [
        ("/", "daily"),
        ("/topics", "daily"),
        ("/chat", "weekly"),
        ("/commercial", "weekly"),
    ]

    entries: list[str] = []
    for path, changefreq in static_urls:
        entries.append(
            f"<url><loc>{escape(_absolute_url(path))}</loc><changefreq>{changefreq}</changefreq></url>"
        )

    with connection_scope() as connection:
        article_rows = connection.execute(
            """
            SELECT id, COALESCE(updated_at, publish_date) AS changed_at
            FROM articles
            ORDER BY publish_date DESC, id DESC
            LIMIT 800
            """
        ).fetchall()
        topic_rows = connection.execute(
            """
            SELECT slug, COALESCE(updated_at, created_at) AS changed_at
            FROM topics
            WHERE status = 'published'
            ORDER BY updated_at DESC, id DESC
            """
        ).fetchall()
        column_rows = connection.execute(
            "SELECT slug FROM columns ORDER BY sort_order ASC, id ASC"
        ).fetchall()
        tag_rows = connection.execute(
            """
            SELECT slug
            FROM tags
            WHERE article_count > 0
            ORDER BY article_count DESC, id DESC
            LIMIT 120
            """
        ).fetchall()

    for row in article_rows:
        lastmod = escape((row["changed_at"] or "")[:10])
        entries.append(
            f"<url><loc>{escape(_absolute_url(f'/article/{row['id']}'))}</loc><lastmod>{lastmod}</lastmod><changefreq>weekly</changefreq></url>"
        )
    for row in topic_rows:
        lastmod = escape((row["changed_at"] or "")[:10])
        entries.append(
            f"<url><loc>{escape(_absolute_url(f'/topic/{row['slug']}'))}</loc><lastmod>{lastmod}</lastmod><changefreq>weekly</changefreq></url>"
        )
    for row in column_rows:
        entries.append(
            f"<url><loc>{escape(_absolute_url(f'/column/{row['slug']}'))}</loc><changefreq>weekly</changefreq></url>"
        )
    for row in tag_rows:
        entries.append(
            f"<url><loc>{escape(_absolute_url(f'/tag/{row['slug']}'))}</loc><changefreq>weekly</changefreq></url>"
        )

    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        + "".join(entries)
        + "</urlset>"
    )


def build_rss_xml(limit: int = 30) -> str:
    safe_limit = max(5, min(limit, 50))
    with connection_scope() as connection:
        rows = connection.execute(
            """
            SELECT id, title, excerpt, publish_date, COALESCE(updated_at, created_at, publish_date) AS changed_at
            FROM articles
            ORDER BY publish_date DESC, id DESC
            LIMIT ?
            """,
            (safe_limit,),
        ).fetchall()

    items = []
    for row in rows:
        description = escape(row["excerpt"] or "")
        items.append(
            "<item>"
            f"<title>{escape(row['title'])}</title>"
            f"<link>{escape(_absolute_url(f'/article/{row['id']}'))}</link>"
            f"<guid>{escape(_absolute_url(f'/article/{row['id']}'))}</guid>"
            f"<pubDate>{escape(row['publish_date'])}</pubDate>"
            f"<description>{description}</description>"
            "</item>"
        )

    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<rss version=\"2.0\"><channel>"
        "<title>复旦商业知识库</title>"
        f"<link>{escape(_absolute_url('/'))}</link>"
        "<description>聚合 Fudan_Business_Knowledge_Data 与编辑后台发布内容的商业知识站点。</description>"
        + "".join(items)
        + "</channel></rss>"
    )


def build_robots_txt() -> str:
    return "\n".join(
        [
            "User-agent: *",
            "Allow: /",
            "Disallow: /editorial",
            "Disallow: /commercial/leads",
            f"Sitemap: {_absolute_url('/sitemap.xml')}",
            "",
        ]
    )
