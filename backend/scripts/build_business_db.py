from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import (
    BUSINESS_DATA_DIR,
    COLUMN_DEFINITIONS,
    GEMINI_AGGREGATE_PATH,
    SQLITE_DB_PATH,
    TOPIC_AUTO_CLUSTERS,
)
from backend.services.clustering_rules import derive_column_slugs
from backend.services.taxonomy_service import (
    KEYWORD_STOPWORDS,
    SERIES_NOISE,
    build_tag_entries,
    normalize_keyword,
)

HEADER_SEPARATOR = "----------------------------------------"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
FDSM_RELATION_KEYWORDS = (
    "教师",
    "教授",
    "院长",
    "教职",
    "老师",
    "学术院长",
    "特聘教授",
)

COLOR_BY_CATEGORY = {
    "industry": "#ea6b00",
    "topic": "#0d0783",
    "type": "#4f46e5",
    "entity": "#64748b",
    "series": "#7c3aed",
}


@dataclass
class RawDocument:
    article_id: int
    doc_id: str
    slug: str
    relative_path: str
    title: str
    publish_date: str
    link: str
    source_mode: str
    content: str
    excerpt: str
    word_count: int
    article_type: str
    main_topic: str | None
    series_or_column: str | None
    primary_org_name: str | None
    cover_image_path: str | None
    tag_names: list[tuple[str, str, float]]
    column_slugs: list[str]
    people_text: str
    org_text: str
    tag_text: str
    search_text: str
    view_count: int
    is_featured: int


def slugify(value: str) -> str:
    safe = (
        value.strip()
        .lower()
        .replace("/", "-")
        .replace("|", "-")
        .replace("丨", "-")
        .replace("·", "-")
        .replace(" ", "-")
    )
    safe = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", safe)
    safe = re.sub(r"-{2,}", "-", safe).strip("-")
    return safe or hashlib.sha1(value.encode("utf-8")).hexdigest()[:12]


def doc_id_for_path(relative_path: str) -> str:
    return hashlib.sha1(relative_path.encode("utf-8")).hexdigest()[:20]


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace").replace("\x00", "")


def split_header_and_body(text: str) -> tuple[list[str], str]:
    if HEADER_SEPARATOR in text:
        head, body = text.split(HEADER_SEPARATOR, 1)
        header_lines = [line.strip() for line in head.splitlines() if line.strip()]
        return header_lines, body.strip()
    lines = text.splitlines()
    return [line.strip() for line in lines[:6] if line.strip()], "\n".join(lines[6:]).strip()


def parse_header(header_lines: list[str]) -> dict[str, str]:
    payload = {"title": "", "publish_date": "", "link": "", "source_mode": ""}
    mapping = {
        "标题:": "title",
        "日期:": "publish_date",
        "链接:": "link",
        "来源模式:": "source_mode",
    }
    for line in header_lines:
        for prefix, field in mapping.items():
            if line.startswith(prefix):
                payload[field] = line[len(prefix) :].strip()
    return payload


def excerpt_from_content(content: str, limit: int = 180) -> str:
    cleaned = re.sub(r"\s+", " ", content).strip()
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[:limit].rstrip()}..."


def count_words(content: str) -> int:
    compact = re.sub(r"\s+", "", content)
    return len(compact)


def load_ai_output() -> dict[str, dict]:
    if not GEMINI_AGGREGATE_PATH.exists():
        return {}
    rows = json.loads(GEMINI_AGGREGATE_PATH.read_text(encoding="utf-8"))
    return {row["relative_path"]: row for row in rows}


def infer_article_type(title: str, content: str) -> str:
    if "专访" in title or "专访" in content[:200]:
        return "专访"
    if "对谈" in title:
        return "对谈"
    if "访谈" in title:
        return "访谈"
    if "案例" in title:
        return "案例报道"
    if "研究" in title or "论文" in title:
        return "研究/论文解读"
    if "预告" in title or "报名" in title:
        return "活动/预告"
    if "书" in title and ("阅读" in title or "书评" in title or "翻书" in title):
        return "书摘/书评"
    return "评论/观点"


def normalize_fdsm_relation(value: str | None) -> str | None:
    if not value:
        return None
    text = value.strip()
    for keyword in FDSM_RELATION_KEYWORDS:
        if keyword in text:
            return keyword
    return text or None


def first_cover_path(article_dir: Path) -> str | None:
    for file in sorted(article_dir.iterdir()):
        if file.is_file() and file.suffix.lower() in IMAGE_EXTENSIONS:
            return file.relative_to(BUSINESS_DATA_DIR).as_posix()
    return None


def stable_view_count(doc_id: str, publish_date: str, word_count: int, hot_tag_count: int) -> int:
    try:
        age_days = max((date.today() - date.fromisoformat(publish_date)).days, 1)
    except ValueError:
        age_days = 3650
    recency_factor = max(0.2, 3.2 - age_days / 1200)
    length_factor = min(2.4, word_count / 1800)
    noise = int(hashlib.sha1(doc_id.encode("utf-8")).hexdigest()[:6], 16) % 1800
    return int(520 + recency_factor * 950 + length_factor * 420 + hot_tag_count * 180 + noise)


def feature_score(document: RawDocument) -> float:
    score = document.view_count / 600
    score += min(document.word_count / 2000, 3.5)
    score += 1.2 if document.article_type in {"专访", "访谈", "对谈", "案例报道"} else 0
    score += 0.8 if "AI/人工智能" in document.tag_text else 0
    score += 0.6 if "ESG/可持续" in document.tag_text else 0
    score -= 1.4 if document.series_or_column in SERIES_NOISE else 0
    return score


def create_schema(connection: sqlite3.Connection) -> None:
    cursor = connection.cursor()
    cursor.executescript(
        """
        PRAGMA journal_mode=WAL;
        DROP TABLE IF EXISTS chat_messages;
        DROP TABLE IF EXISTS chat_sessions;
        DROP TABLE IF EXISTS topic_tags;
        DROP TABLE IF EXISTS topic_articles;
        DROP TABLE IF EXISTS topics;
        DROP TABLE IF EXISTS featured_articles;
        DROP TABLE IF EXISTS article_columns;
        DROP TABLE IF EXISTS columns;
        DROP TABLE IF EXISTS article_tags;
        DROP TABLE IF EXISTS tags;
        DROP TABLE IF EXISTS articles;
        DROP TABLE IF EXISTS meta;

        CREATE TABLE meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE articles (
            id INTEGER PRIMARY KEY,
            doc_id TEXT UNIQUE NOT NULL,
            slug TEXT UNIQUE NOT NULL,
            relative_path TEXT UNIQUE NOT NULL,
            source TEXT NOT NULL,
            source_mode TEXT,
            title TEXT NOT NULL,
            publish_date TEXT NOT NULL,
            link TEXT,
            content TEXT NOT NULL,
            excerpt TEXT,
            main_topic TEXT,
            article_type TEXT,
            series_or_column TEXT,
            primary_org_name TEXT,
            tag_text TEXT DEFAULT '',
            people_text TEXT DEFAULT '',
            org_text TEXT DEFAULT '',
            search_text TEXT DEFAULT '',
            word_count INTEGER DEFAULT 0,
            cover_image_path TEXT,
            view_count INTEGER DEFAULT 0,
            is_featured INTEGER DEFAULT 0,
            created_at TEXT,
            updated_at TEXT
        );

        CREATE TABLE tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            slug TEXT UNIQUE NOT NULL,
            category TEXT NOT NULL,
            description TEXT,
            color TEXT,
            article_count INTEGER DEFAULT 0,
            UNIQUE(name, category)
        );

        CREATE TABLE article_tags (
            article_id INTEGER NOT NULL REFERENCES articles(id),
            tag_id INTEGER NOT NULL REFERENCES tags(id),
            confidence REAL DEFAULT 1.0,
            PRIMARY KEY (article_id, tag_id)
        );

        CREATE TABLE columns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            slug TEXT UNIQUE NOT NULL,
            description TEXT,
            icon TEXT,
            sort_order INTEGER DEFAULT 0,
            accent_color TEXT
        );

        CREATE TABLE article_columns (
            article_id INTEGER NOT NULL REFERENCES articles(id),
            column_id INTEGER NOT NULL REFERENCES columns(id),
            is_featured INTEGER DEFAULT 0,
            sort_order INTEGER DEFAULT 0,
            PRIMARY KEY (article_id, column_id)
        );

        CREATE TABLE featured_articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            article_id INTEGER NOT NULL REFERENCES articles(id),
            position TEXT NOT NULL,
            start_date TEXT,
            end_date TEXT,
            is_active INTEGER DEFAULT 1
        );

        CREATE TABLE topics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            slug TEXT UNIQUE NOT NULL,
            description TEXT,
            cover_image TEXT,
            cover_article_id INTEGER,
            type TEXT NOT NULL,
            auto_rules TEXT,
            status TEXT DEFAULT 'draft',
            created_at TEXT,
            updated_at TEXT,
            view_count INTEGER DEFAULT 0
        );

        CREATE TABLE topic_articles (
            topic_id INTEGER NOT NULL REFERENCES topics(id),
            article_id INTEGER NOT NULL REFERENCES articles(id),
            sort_order INTEGER DEFAULT 0,
            editor_note TEXT,
            PRIMARY KEY (topic_id, article_id)
        );

        CREATE TABLE topic_tags (
            topic_id INTEGER NOT NULL REFERENCES topics(id),
            tag_id INTEGER NOT NULL REFERENCES tags(id),
            PRIMARY KEY (topic_id, tag_id)
        );

        CREATE TABLE chat_sessions (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            last_question TEXT NOT NULL
        );

        CREATE TABLE chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL REFERENCES chat_sessions(id),
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            sources_json TEXT,
            follow_ups_json TEXT,
            created_at TEXT NOT NULL
        );

        CREATE INDEX idx_articles_date ON articles(publish_date DESC);
        CREATE INDEX idx_articles_view_count ON articles(view_count DESC);
        CREATE INDEX idx_tags_category ON tags(category, article_count DESC);
        CREATE INDEX idx_article_columns_column ON article_columns(column_id, article_id);
        CREATE INDEX idx_article_tags_tag ON article_tags(tag_id, article_id);
        CREATE INDEX idx_topic_articles_topic ON topic_articles(topic_id, sort_order);
        """
    )


def build_documents() -> list[RawDocument]:
    ai_map = load_ai_output()
    paths = sorted(
        path
        for path in BUSINESS_DATA_DIR.rglob("content.txt")
        if "gemini_flash_batch" not in path.as_posix()
    )

    prepared: list[dict] = []
    keyword_counter = Counter()
    series_counter = Counter()

    for index, content_path in enumerate(paths, start=1):
        relative_path = content_path.relative_to(BUSINESS_DATA_DIR).as_posix()
        text = read_text(content_path)
        header_lines, content = split_header_and_body(text)
        header = parse_header(header_lines)
        ai_row = ai_map.get(relative_path, {})
        model = ai_row.get("model_output") or {}
        title = header["title"] or ai_row.get("title") or content_path.parent.name
        publish_date = header["publish_date"] or ai_row.get("publish_date") or "2000-01-01"
        link = header["link"] or ai_row.get("source_url") or ""
        source_mode = header["source_mode"] or ai_row.get("source_mode") or "business"
        article_type = model.get("article_type") or infer_article_type(title, content)
        main_topic = model.get("main_topic") or None
        series_or_column = model.get("series_or_column") or None
        if series_or_column:
            series_counter[series_or_column] += 1

        raw_keywords = []
        for keyword in (model.get("topic_keywords") or [])[:5]:
            normalized = normalize_keyword(keyword)
            if normalized:
                raw_keywords.append(normalized)
                keyword_counter[normalized] += 1
        if main_topic:
            normalized_topic = normalize_keyword(main_topic)
            if normalized_topic:
                raw_keywords.append(normalized_topic)
                keyword_counter[normalized_topic] += 1

        prepared.append(
            {
                "article_id": index,
                "doc_id": ai_row.get("doc_id") or doc_id_for_path(relative_path),
                "slug": slugify(f"{publish_date}-{title}")[:96],
                "relative_path": relative_path,
                "title": title,
                "publish_date": publish_date,
                "link": link,
                "source_mode": source_mode,
                "content": content,
                "excerpt": excerpt_from_content(content),
                "word_count": count_words(content),
                "article_type": article_type,
                "main_topic": main_topic,
                "series_or_column": series_or_column,
                "primary_org_name": model.get("primary_org_name") or None,
                "cover_image_path": first_cover_path(content_path.parent),
                "people": model.get("people") or [],
                "raw_keywords": raw_keywords,
            }
        )

    allowed_keywords = {
        keyword
        for keyword, count in keyword_counter.items()
        if count >= 6 and keyword not in KEYWORD_STOPWORDS and len(keyword) <= 18
    }
    strong_series = {
        keyword
        for keyword, count in series_counter.items()
        if count >= 8 and keyword not in SERIES_NOISE and len(keyword) <= 20
    }

    documents: list[RawDocument] = []
    for item in prepared:
        people_names = []
        org_names = []
        fdsm_hits = []
        for person in item["people"]:
            name = person.get("person_name")
            org_name = person.get("org_name")
            relation = normalize_fdsm_relation(person.get("fdsm_relation"))
            if name:
                people_names.append(name)
            if org_name:
                org_names.append(org_name)
            if relation:
                fdsm_hits.append(relation)
        if item["primary_org_name"]:
            org_names.append(item["primary_org_name"])
        people_names = list(dict.fromkeys(people_names))[:4]
        org_names = list(dict.fromkeys(org_names))[:4]

        deduped_tag_entries = build_tag_entries(
            title=item["title"],
            main_topic=item["main_topic"],
            excerpt=item["excerpt"],
            content=item["content"],
            article_type=item["article_type"],
            series_or_column=item["series_or_column"],
            raw_keywords=item["raw_keywords"],
            people_names=people_names,
            org_names=org_names,
            allowed_keywords=allowed_keywords,
            strong_series=strong_series,
        )

        hot_tag_count = sum(1 for _, category, _ in deduped_tag_entries if category in {"topic", "industry"})
        view_count = stable_view_count(item["doc_id"], item["publish_date"], item["word_count"], hot_tag_count)

        column_slugs = derive_column_slugs(
            word_count=item["word_count"],
            article_type=item["article_type"],
            series_or_column=item["series_or_column"],
            tag_entries=deduped_tag_entries,
            fdsm_hits=fdsm_hits,
        )

        tag_text = " | ".join(name for name, _, _ in deduped_tag_entries)
        people_text = " | ".join(people_names)
        org_text = " | ".join(org_names)
        search_text = " ".join(
            [
                item["title"],
                item["main_topic"] or "",
                tag_text,
                people_text,
                org_text,
                item["excerpt"],
            ]
        )

        documents.append(
            RawDocument(
                article_id=item["article_id"],
                doc_id=item["doc_id"],
                slug=item["slug"],
                relative_path=item["relative_path"],
                title=item["title"],
                publish_date=item["publish_date"],
                link=item["link"],
                source_mode=item["source_mode"],
                content=item["content"],
                excerpt=item["excerpt"],
                word_count=item["word_count"],
                article_type=item["article_type"],
                main_topic=item["main_topic"],
                series_or_column=item["series_or_column"],
                primary_org_name=item["primary_org_name"],
                cover_image_path=item["cover_image_path"],
                tag_names=deduped_tag_entries,
                column_slugs=column_slugs,
                people_text=people_text,
                org_text=org_text,
                tag_text=tag_text,
                search_text=search_text,
                view_count=view_count,
                is_featured=0,
            )
        )

    ranked = sorted(documents, key=feature_score, reverse=True)
    featured_ids = {document.article_id for document in ranked[:24]}
    return [
        RawDocument(**{**document.__dict__, "is_featured": 1 if document.article_id in featured_ids else 0})
        for document in documents
    ]


def insert_documents(connection: sqlite3.Connection, documents: list[RawDocument]) -> None:
    cursor = connection.cursor()
    now = datetime.utcnow().isoformat()
    for document in documents:
        cursor.execute(
            """
            INSERT INTO articles (
                id, doc_id, slug, relative_path, source, source_mode, title, publish_date, link,
                content, excerpt, main_topic, article_type, series_or_column, primary_org_name,
                tag_text, people_text, org_text, search_text, word_count, cover_image_path,
                view_count, is_featured, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                document.article_id,
                document.doc_id,
                document.slug,
                document.relative_path,
                "business",
                document.source_mode,
                document.title,
                document.publish_date,
                document.link,
                document.content,
                document.excerpt,
                document.main_topic,
                document.article_type,
                document.series_or_column,
                document.primary_org_name,
                document.tag_text,
                document.people_text,
                document.org_text,
                document.search_text,
                document.word_count,
                document.cover_image_path,
                document.view_count,
                document.is_featured,
                now,
                now,
            ),
        )

    tag_to_articles: dict[tuple[str, str], list[tuple[int, float]]] = defaultdict(list)
    for document in documents:
        for name, category, confidence in document.tag_names:
            tag_to_articles[(name, category)].append((document.article_id, confidence))

    tag_ids: dict[tuple[str, str], int] = {}
    used_tag_slugs: set[str] = set()
    for (name, category), article_refs in sorted(tag_to_articles.items(), key=lambda item: (item[0][1], item[0][0])):
        base_slug = slugify(f"{category}-{name}")[:80]
        slug = base_slug
        if slug in used_tag_slugs:
            suffix = hashlib.sha1(f"{category}:{name}".encode("utf-8")).hexdigest()[:8]
            slug = f"{base_slug[:71]}-{suffix}"
        used_tag_slugs.add(slug)
        cursor.execute(
            """
            INSERT INTO tags (name, slug, category, description, color, article_count)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                slug,
                category,
                f"{name} 相关文章聚合标签",
                COLOR_BY_CATEGORY.get(category, "#64748b"),
                len(article_refs),
            ),
        )
        tag_ids[(name, category)] = cursor.lastrowid

    for (name, category), article_refs in tag_to_articles.items():
        tag_id = tag_ids[(name, category)]
        for article_id, confidence in article_refs:
            cursor.execute(
                """
                INSERT INTO article_tags (article_id, tag_id, confidence)
                VALUES (?, ?, ?)
                """,
                (article_id, tag_id, confidence),
            )

    for column in COLUMN_DEFINITIONS:
        cursor.execute(
            """
            INSERT INTO columns (name, slug, description, icon, sort_order, accent_color)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                column["name"],
                column["slug"],
                column["description"],
                column["icon"],
                column["sort_order"],
                column["accent_color"],
            ),
        )
    column_ids = {row["slug"]: row["id"] for row in cursor.execute("SELECT id, slug FROM columns").fetchall()}

    for document in documents:
        for sort_order, slug in enumerate(document.column_slugs, start=1):
            cursor.execute(
                """
                INSERT INTO article_columns (article_id, column_id, is_featured, sort_order)
                VALUES (?, ?, ?, ?)
                """,
                (
                    document.article_id,
                    column_ids[slug],
                    1 if document.is_featured else 0,
                    sort_order,
                ),
            )

    featured_rank = sorted(documents, key=feature_score, reverse=True)
    if featured_rank:
        hero = featured_rank[0]
        cursor.execute(
            """
            INSERT INTO featured_articles (article_id, position, start_date, end_date, is_active)
            VALUES (?, 'hero', ?, ?, 1)
            """,
            (hero.article_id, date.today().isoformat(), None),
        )
        for index, document in enumerate(featured_rank[1:7], start=1):
            cursor.execute(
                """
                INSERT INTO featured_articles (article_id, position, start_date, end_date, is_active)
                VALUES (?, ?, ?, ?, 1)
                """,
                (document.article_id, f"editor-{index}", date.today().isoformat(), None),
            )

    from backend.services.topic_engine import rebuild_topics

    rebuild_topics(connection=connection, limit_auto=len(TOPIC_AUTO_CLUSTERS))

    cursor.execute("INSERT INTO meta (key, value) VALUES (?, ?)", ("business_article_count", str(len(documents))))
    cursor.execute("INSERT INTO meta (key, value) VALUES (?, ?)", ("updated_at", now))
    connection.commit()


def rebuild_database() -> None:
    documents = build_documents()
    connection = sqlite3.connect(SQLITE_DB_PATH)
    connection.row_factory = sqlite3.Row
    try:
        create_schema(connection)
        insert_documents(connection, documents)
    finally:
        connection.close()

    from backend.services.rag_engine import refresh_search_cache

    refresh_search_cache()


def main() -> None:
    rebuild_database()
    print(f"Business knowledge base rebuilt at {SQLITE_DB_PATH}")


if __name__ == "__main__":
    main()
