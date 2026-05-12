from __future__ import annotations

import hashlib
import json
import random
import re
from collections import Counter
from datetime import date, datetime

from backend.config import SITE_BASE_URL
from backend.database import connection_scope, ensure_runtime_tables
from backend.services import ai_service
from backend.services.catalog_service import _current_local_datetime, _serialize_articles

ensure_runtime_tables()

_ZH_WEEKDAYS = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
_EN_WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
_GENERIC_THEME_WORDS = {
    "商业",
    "管理",
    "观察",
    "前沿",
    "趋势",
    "研究",
    "专题",
    "洞察",
    "知识",
    "今日",
}


_ZH_THEME_DETAIL_PATTERNS = (
    ("\u5927\u8bed\u8a00\u6a21\u578b", ("\u5927\u8bed\u8a00\u6a21\u578b", "\u8bed\u8a00\u6a21\u578b", "LLM")),
    ("\u5927\u6a21\u578b", ("\u5927\u6a21\u578b",)),
    ("\u795e\u7ecf\u7f51\u7edc", ("\u795e\u7ecf\u7f51\u7edc",)),
    ("\u673a\u5668\u5b66\u4e60", ("\u673a\u5668\u5b66\u4e60",)),
    ("\u6df1\u5ea6\u5b66\u4e60", ("\u6df1\u5ea6\u5b66\u4e60",)),
    ("\u751f\u6210\u5f0fAI", ("\u751f\u6210\u5f0fAI", "AIGC")),
    ("\u667a\u80fd\u4f53", ("\u667a\u80fd\u4f53",)),
    ("\u7b97\u529b", ("\u7b97\u529b", "GPU", "\u82af\u7247", "\u63a8\u7406", "\u8bad\u7ec3")),
    ("\u7ec4\u7ec7", ("\u7ec4\u7ec7", "\u4eba\u624d", "\u7ba1\u7406", "\u534f\u540c")),
)
_SHORT_THEME_ACRONYMS = ("AI", "AIGC", "AGI", "ESG", "GPU", "LLM")


def _copy(language: str, zh: str, en: str) -> str:
    return zh if language == "zh" else en


def _safe_iso_date(raw_value: str | None) -> date | None:
    value = str(raw_value or "").strip()
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _now_iso() -> str:
    return datetime.now().astimezone().replace(microsecond=0).isoformat()


def _load_cached_snapshot(user_id: str, bookmark_date: str, language: str) -> dict | None:
    with connection_scope() as connection:
        row = connection.execute(
            """
            SELECT source_hash, payload_json
            FROM user_daily_bookmarks
            WHERE user_id = ? AND bookmark_date = ? AND language = ?
            """,
            (user_id, bookmark_date, language),
        ).fetchone()
    if row is None:
        return None
    try:
        payload = json.loads(row["payload_json"] or "{}")
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    payload["source_hash"] = row["source_hash"]
    payload["cached"] = True
    return payload


def _save_snapshot(
    *,
    user_id: str,
    bookmark_date: str,
    language: str,
    source_hash: str,
    primary_theme: str,
    article_count: int,
    payload: dict,
) -> None:
    timestamp = _now_iso()
    with connection_scope() as connection:
        connection.execute(
            """
            INSERT INTO user_daily_bookmarks (
                user_id,
                bookmark_date,
                language,
                source_hash,
                primary_theme,
                article_count,
                payload_json,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, bookmark_date, language) DO UPDATE SET
                source_hash = excluded.source_hash,
                primary_theme = excluded.primary_theme,
                article_count = excluded.article_count,
                payload_json = excluded.payload_json,
                updated_at = excluded.updated_at
            """,
            (
                user_id,
                bookmark_date,
                language,
                source_hash,
                primary_theme,
                article_count,
                json.dumps(payload, ensure_ascii=False),
                timestamp,
                timestamp,
            ),
        )
        connection.commit()


def _fetch_articles_for_day(user_id: str, bookmark_date: str) -> list[dict]:
    with connection_scope() as connection:
        rows = connection.execute(
            """
            SELECT
                a.id,
                a.title,
                a.slug,
                a.publish_date,
                a.source,
                a.excerpt,
                a.article_type,
                a.main_topic,
                a.view_count,
                a.cover_image_path,
                a.link,
                a.content,
                a.tag_text,
                a.updated_at,
                MAX(ave.created_at) AS last_viewed_at
            FROM article_view_events ave
            JOIN articles a ON a.id = ave.article_id
            WHERE ave.user_id = ? AND ave.view_date = ?
            GROUP BY a.id
            ORDER BY last_viewed_at DESC, a.id DESC
            LIMIT 24
            """,
            (user_id, bookmark_date),
        ).fetchall()
        serialized = _serialize_articles(connection, rows, current_user_id=user_id, language="zh")
    payload: list[dict] = []
    serialized_map = {int(item["id"]): item for item in serialized}
    for row in rows:
        base = serialized_map.get(int(row["id"])) or {}
        payload.append(
            {
                **base,
                "content": row["content"] or "",
                "tag_text": row["tag_text"] or "",
                "updated_at": row["updated_at"],
                "last_viewed_at": row["last_viewed_at"],
                "main_topic": row["main_topic"] or base.get("main_topic"),
                "excerpt": row["excerpt"] or base.get("excerpt") or "",
            }
        )
    return payload


def _build_source_hash(rows: list[dict], bookmark_date: str, language: str) -> str:
    digest_payload = [
        {
            "id": int(row["id"]),
            "updated_at": row.get("updated_at"),
            "last_viewed_at": row.get("last_viewed_at"),
        }
        for row in rows
    ]
    raw = json.dumps(
        {
            "bookmark_date": bookmark_date,
            "language": language,
            "articles": digest_payload,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _split_label_parts(text: str) -> list[str]:
    parts = [item.strip() for item in re.split(r"[|/、，,；;]+", str(text or "")) if item.strip()]
    return [part[:24] for part in parts if len(part) <= 24]


def _normalize_phrase(text: str) -> str:
    value = str(text or "").strip()
    value = re.sub(r"\s+", " ", value)
    value = re.sub(r"^[#>*•·\-—–\d\.\)\(（）\[\]\s]+", "", value)
    value = re.sub(r"[|]+", " ", value)
    value = value.strip("，,。；;：:、!?！？“”\"'（）()[]【】<>《》 ")
    value = re.sub(r"\s+", " ", value).strip()
    if not value:
        return ""
    if len(value) > 26:
        return ""
    if len(value) < 2:
        return ""
    if value.isdigit():
        return ""
    return value


def _candidate_phrases_from_sentence(sentence: str) -> list[str]:
    normalized = str(sentence or "").replace("\r", "\n")
    chunks = re.split(r"[\n]+|[。！？!?；;]+", normalized)
    phrases: list[str] = []
    for chunk in chunks:
        fragment = chunk.strip()
        if not fragment:
            continue
        sub_parts = re.split(r"[，,、：:（）()]", fragment)
        for part in sub_parts:
            phrase = _normalize_phrase(part)
            if phrase:
                phrases.append(phrase)
            for nested in re.split(r"(?<=[\u4e00-\u9fffA-Za-z0-9])(?:与|和|及)(?=[\u4e00-\u9fffA-Za-z0-9])", part):
                nested_phrase = _normalize_phrase(nested)
                if nested_phrase:
                    phrases.append(nested_phrase)
        whole = _normalize_phrase(fragment)
        if whole and len(whole) <= 18:
            phrases.append(whole)
    return phrases


def _extract_phrase_candidates(rows: list[dict]) -> list[dict]:
    scored: dict[str, dict] = {}

    def push(text: str, *, emphasis: int, tone: str, article_id: int, bonus: int = 1) -> None:
        phrase = _normalize_phrase(text)
        if not phrase:
            return
        current = scored.get(phrase)
        if current is None:
            scored[phrase] = {
                "text": phrase,
                "emphasis": emphasis,
                "tone": tone,
                "source_article_id": article_id,
                "score": emphasis * 4 + bonus,
            }
            return
        current["score"] += bonus + emphasis
        current["emphasis"] = max(current["emphasis"], emphasis)
        if current["tone"] == "slate" and tone != "slate":
            current["tone"] = tone

    for row in rows:
        article_id = int(row["id"])
        title = str(row.get("title") or "").strip()
        excerpt = str(row.get("excerpt") or "").strip()
        content = str(row.get("content") or "").strip()
        main_topic = str(row.get("main_topic") or "").strip()
        tags = _split_label_parts(row.get("tag_text") or "")

        if main_topic:
            push(main_topic, emphasis=5, tone="orange", article_id=article_id, bonus=8)
        for index, tag in enumerate(tags[:8]):
            push(tag, emphasis=4 if index < 3 else 3, tone="blue" if index % 2 == 0 else "orange", article_id=article_id, bonus=4)
        for phrase in _candidate_phrases_from_sentence(title):
            push(phrase, emphasis=5 if phrase == title else 4, tone="blue", article_id=article_id, bonus=6)
        for phrase in _candidate_phrases_from_sentence(excerpt):
            push(phrase, emphasis=3, tone="orange", article_id=article_id, bonus=3)
        content_limit = 72
        seen_from_content = 0
        for phrase in _candidate_phrases_from_sentence(content):
            push(phrase, emphasis=2 if len(phrase) <= 8 else 1, tone="slate", article_id=article_id, bonus=1)
            seen_from_content += 1
            if seen_from_content >= content_limit:
                break

    ranked = sorted(
        scored.values(),
        key=lambda item: (item["score"], item["emphasis"], len(item["text"])),
        reverse=True,
    )
    return ranked[:96]


def _theme_hints(rows: list[dict]) -> list[dict]:
    counter: Counter[str] = Counter()
    for row in rows:
        main_topic = str(row.get("main_topic") or "").strip()
        if main_topic:
            counter[main_topic] += 3
        for tag in _split_label_parts(row.get("tag_text") or "")[:6]:
            counter[tag] += 1
    return [{"label": label, "weight": weight} for label, weight in counter.most_common(8)]


def _fallback_theme_from_hints(hints: list[dict]) -> dict[str, str]:
    if not hints:
        return {"theme": "今日阅读", "reason": "今天的阅读主题还比较分散，先用泛化主题兜底。"}
    best = str(hints[0]["label"] or "").strip()
    best = re.sub(r"[|/、，,；;：:\s]+", "", best)
    if not best:
        best = "今日阅读"
    if len(best) > 4:
        best = best[:4]
    if best in _GENERIC_THEME_WORDS:
        best = "今日阅读"
    return {"theme": best, "reason": "根据当天阅读里出现频率最高的主题与标签做了规则归并。"}


def _normalize_theme_text(theme: str, language: str) -> str:
    raw_value = str(theme or "").strip()
    value = re.sub(r"\s+", "" if language == "zh" else " ", raw_value).strip()
    value = re.sub(r"[：:，,。.!！？、/|]+", "", value)
    if language == "zh":
        if len(value) > 4:
            value = value[:4]
        if not value or value in _GENERIC_THEME_WORDS:
            return "今日阅读"
        return value
    words = [item for item in re.split(r"\s+", value) if item]
    if len(words) > 4:
        words = words[:4]
    return " ".join(words) or "Today"


def _pick_headline_detail(hints: list[dict], article_titles: list[str], article_excerpts: list[str]) -> str:
    sources = [str(item.get("label") or "").strip() for item in hints[:8]]
    sources.extend(str(item or "").strip() for item in article_titles[:8])
    sources.extend(str(item or "").strip() for item in article_excerpts[:6])
    joined = "\n".join(source for source in sources if source)
    if not joined:
        return ""

    ranked: list[tuple[int, str]] = []
    for label, variants in _ZH_THEME_DETAIL_PATTERNS:
        score = sum(joined.count(variant) for variant in variants)
        if score > 0:
            ranked.append((score, label))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return ranked[0][1] if ranked else ""


def _normalize_headline_theme(
    theme: str,
    *,
    hints: list[dict],
    article_titles: list[str],
    article_excerpts: list[str],
    language: str,
) -> str:
    raw_theme = str(theme or "").strip()
    if language == "en":
        normalized = re.sub(r"\s+", " ", raw_theme).strip()
        return normalized or "Today"

    compact_theme = re.sub(r"\s+", "", raw_theme)
    if "&" in compact_theme and len(compact_theme) <= 12:
        return compact_theme

    sources = [compact_theme]
    sources.extend(str(item.get("label") or "").strip() for item in hints[:8])
    sources.extend(str(item or "").strip() for item in article_titles[:8])
    has_ai = any("AI" in source.upper() or "\u4eba\u5de5\u667a\u80fd" in source for source in sources if source)
    detail = _pick_headline_detail(hints, article_titles, article_excerpts)

    if has_ai and detail and detail not in {"AI", "\u4eba\u5de5\u667a\u80fd"}:
        return f"AI&{detail}"

    normalized = re.sub(r"[|/、，,；;：:\s]+", "", compact_theme)
    if normalized and normalized not in _GENERIC_THEME_WORDS:
        return normalized[:12]

    for item in hints[:8]:
        label = re.sub(r"[|/、，,；;：:\s]+", "", str(item.get("label") or "").strip())
        if label and label not in _GENERIC_THEME_WORDS:
            return label[:12]
    return "\u4eca\u65e5\u9605\u8bfb"


def _normalize_core_theme(theme: str, headline_theme: str, *, hints: list[dict], language: str) -> str:
    if language == "en":
        normalized = _normalize_theme_text(theme or headline_theme, language)
        words = [item for item in normalized.split() if item]
        if not words:
            return "Today"
        return " ".join(words[:2])

    sources = [str(theme or "").strip(), str(headline_theme or "").strip()]
    sources.extend(str(item.get("label") or "").strip() for item in hints[:6])
    joined_upper = " ".join(source.upper() for source in sources if source)
    for acronym in _SHORT_THEME_ACRONYMS:
        if acronym in joined_upper:
            return acronym

    normalized = _normalize_theme_text(theme, language)
    if normalized and normalized not in _GENERIC_THEME_WORDS and len(normalized) <= 4:
        return normalized

    for part in re.split(r"[&/、，,和与·\s]+", str(headline_theme or "")):
        candidate = _normalize_theme_text(part, language)
        if candidate and candidate not in _GENERIC_THEME_WORDS and len(candidate) <= 4:
            return candidate
    return normalized or "\u4eca\u65e5\u9605\u8bfb"


def _pick_headline_detail(hints: list[dict], article_titles: list[str], article_excerpts: list[str]) -> str:
    sources = [str(item.get("label") or "").strip() for item in hints[:8]]
    sources.extend(str(item or "").strip() for item in article_titles[:8])
    sources.extend(str(item or "").strip() for item in article_excerpts[:6])
    joined = "\n".join(source for source in sources if source)
    if not joined:
        return ""

    ranked: list[tuple[int, str]] = []
    for label, variants in _ZH_THEME_DETAIL_PATTERNS:
        score = sum(joined.count(variant) for variant in variants)
        if score > 0:
            ranked.append((score, label))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return ranked[0][1] if ranked else ""


def _normalize_headline_theme(
    theme: str,
    *,
    hints: list[dict],
    article_titles: list[str],
    article_excerpts: list[str],
    language: str,
) -> str:
    raw_theme = str(theme or "").strip()
    if language == "en":
        normalized = re.sub(r"\s+", " ", raw_theme).strip()
        return normalized or "Today"

    compact_theme = re.sub(r"\s+", "", raw_theme)
    if "&" in compact_theme and len(compact_theme) <= 12:
        return compact_theme

    sources = [compact_theme]
    sources.extend(str(item.get("label") or "").strip() for item in hints[:8])
    sources.extend(str(item or "").strip() for item in article_titles[:8])
    has_ai = any("AI" in source.upper() or "\u4eba\u5de5\u667a\u80fd" in source for source in sources if source)
    detail = _pick_headline_detail(hints, article_titles, article_excerpts)

    if has_ai and detail and detail not in {"AI", "\u4eba\u5de5\u667a\u80fd"}:
        return f"AI&{detail}"

    normalized = re.sub(r"[|/、，,；;：:\s]+", "", compact_theme)
    if normalized and normalized not in _GENERIC_THEME_WORDS:
        return normalized[:12]

    for item in hints[:8]:
        label = re.sub(r"[|/、，,；;：:\s]+", "", str(item.get("label") or "").strip())
        if label and label not in _GENERIC_THEME_WORDS:
            return label[:12]
    return "\u4eca\u65e5\u9605\u8bfb"


def _normalize_core_theme(theme: str, headline_theme: str, *, hints: list[dict], language: str) -> str:
    if language == "en":
        normalized = _normalize_theme_text(theme or headline_theme, language)
        words = [item for item in normalized.split() if item]
        if not words:
            return "Today"
        return " ".join(words[:2])

    sources = [str(theme or "").strip(), str(headline_theme or "").strip()]
    sources.extend(str(item.get("label") or "").strip() for item in hints[:6])
    joined_upper = " ".join(source.upper() for source in sources if source)
    for acronym in _SHORT_THEME_ACRONYMS:
        if acronym in joined_upper:
            return acronym

    normalized = _normalize_theme_text(theme, language)
    if normalized and normalized not in _GENERIC_THEME_WORDS and len(normalized) <= 4:
        return normalized

    for part in re.split(r"[&/、，,和与·\s]+", str(headline_theme or "")):
        candidate = _normalize_theme_text(part, language)
        if candidate and candidate not in _GENERIC_THEME_WORDS and len(candidate) <= 4:
            return candidate
    return normalized or "\u4eca\u65e5\u9605\u8bfb"


def _deterministic_shuffle(items: list[dict], seed_value: str) -> list[dict]:
    seeded = random.Random(seed_value)
    copied = [dict(item) for item in items]
    seeded.shuffle(copied)
    return copied


def _expand_phrase_cloud(candidates: list[dict]) -> list[dict]:
    expanded: list[dict] = []
    for index, item in enumerate(candidates):
        expanded.append(dict(item))
        if item["emphasis"] >= 4 and len(item["text"]) <= 10:
            echo = dict(item)
            echo["tone"] = "blue" if item["tone"] == "orange" else "orange"
            echo["emphasis"] = max(3, item["emphasis"] - 1)
            echo["score"] = item["score"] - 1
            expanded.append(echo)
        if index < 18 and len(item["text"]) <= 8:
            mini = dict(item)
            mini["tone"] = "slate" if item["tone"] != "slate" else item["tone"]
            mini["emphasis"] = max(1, min(3, item["emphasis"]))
            mini["score"] = item["score"] - 2
            expanded.append(mini)
    return expanded


def _format_date_labels(target_date: date, language: str) -> tuple[str, str]:
    if language == "en":
        return (
            target_date.strftime("%B %d, %Y"),
            _EN_WEEKDAYS[target_date.weekday()],
        )
    return (
        f"{target_date.year}年{target_date.month}月{target_date.day}日",
        _ZH_WEEKDAYS[target_date.weekday()],
    )


def get_today_bookmark(
    user_id: str,
    *,
    target_date: str | None = None,
    language: str = "zh",
    force_refresh: bool = False,
) -> dict:
    normalized_language = "en" if language == "en" else "zh"
    current_moment = _current_local_datetime()
    anchor_date = _safe_iso_date(target_date) or current_moment.date()
    bookmark_date = anchor_date.isoformat()
    date_label, weekday_label = _format_date_labels(anchor_date, normalized_language)

    rows = _fetch_articles_for_day(user_id, bookmark_date)
    if not rows:
        return {
            "available": False,
            "bookmark_date": bookmark_date,
            "weekday_label": weekday_label,
            "date_label": date_label,
            "language": normalized_language,
            "article_count": 0,
            "headline_theme": None,
            "source_articles": [],
            "phrases": [],
            "theme_hints": [],
            "empty_message": _copy(
                normalized_language,
                "今天还没有新的阅读记录，先去看几篇文章，系统再为你生成今日书签。",
                "There is no reading history for today yet. Read a few articles first, then come back for your daily bookmark.",
            ),
            "qr_label": _copy(normalized_language, "知识库入口", "Knowledge Base"),
            "qr_target_url": f"{SITE_BASE_URL}/me/knowledge",
            "generated_at": current_moment.isoformat(),
            "cached": False,
        }

    source_hash = _build_source_hash(rows, bookmark_date, normalized_language)
    if not force_refresh:
        cached_payload = _load_cached_snapshot(user_id, bookmark_date, normalized_language)
        if cached_payload and cached_payload.get("source_hash") == source_hash:
            return cached_payload

    hints = _theme_hints(rows)
    candidate_topics = [item["label"] for item in hints[:6]]
    candidate_tags = [item["label"] for item in hints[6:12]]
    if not candidate_tags:
        candidate_tags = [item["label"] for item in hints[:8]]
    article_titles = [str(row.get("title") or "").strip() for row in rows]
    article_excerpts = [str(row.get("excerpt") or "").strip() for row in rows if str(row.get("excerpt") or "").strip()]
    theme_payload = _fallback_theme_from_hints(hints)
    if ai_service.is_ai_enabled():
        try:
            theme_payload = ai_service.generate_daily_bookmark_theme(
                language=normalized_language,
                candidate_topics=candidate_topics,
                candidate_tags=candidate_tags,
                article_titles=article_titles,
                article_excerpts=article_excerpts,
            )
        except Exception:
            theme_payload = _fallback_theme_from_hints(hints)
    headline_theme = _normalize_headline_theme(
        str(theme_payload.get("headline_theme") or theme_payload.get("theme") or ""),
        hints=hints,
        article_titles=article_titles,
        article_excerpts=article_excerpts,
        language=normalized_language,
    )
    primary_theme = _normalize_core_theme(
        str(theme_payload.get("core_theme") or theme_payload.get("theme") or ""),
        headline_theme,
        hints=hints,
        language=normalized_language,
    )
    theme_reason = str(theme_payload.get("reason") or "").strip() or _fallback_theme_from_hints(hints)["reason"]

    phrase_candidates = _extract_phrase_candidates(rows)
    boosted_candidates: list[dict] = []
    for item in phrase_candidates:
        boosted = dict(item)
        if primary_theme and primary_theme in boosted["text"]:
            boosted["emphasis"] = max(boosted["emphasis"], 5)
            boosted["tone"] = "orange"
            boosted["score"] += 12
        boosted_candidates.append(boosted)
    boosted_candidates.sort(
        key=lambda item: (item["score"], item["emphasis"], len(item["text"])),
        reverse=True,
    )
    expanded_cloud = _expand_phrase_cloud(boosted_candidates[:84])
    shuffled_phrases = _deterministic_shuffle(expanded_cloud, f"{source_hash}:{primary_theme}")
    final_phrases = [
        {
            "text": item["text"],
            "emphasis": item["emphasis"],
            "tone": item["tone"],
            "source_article_id": item["source_article_id"],
        }
        for item in shuffled_phrases[:112]
    ]

    source_articles = [{key: value for key, value in row.items() if key not in {"content", "tag_text", "updated_at", "last_viewed_at"}} for row in rows[:8]]
    payload = {
        "available": True,
        "bookmark_date": bookmark_date,
        "weekday_label": weekday_label,
        "date_label": date_label,
        "language": normalized_language,
        "primary_theme": primary_theme,
        "headline_theme": headline_theme,
        "theme_reason": theme_reason,
        "article_count": len(rows),
        "source_hash": source_hash,
        "generated_at": current_moment.isoformat(),
        "cached": False,
        "qr_label": _copy(normalized_language, "知识库入口", "Knowledge Base"),
        "qr_target_url": f"{SITE_BASE_URL}/me/knowledge",
        "source_articles": source_articles,
        "theme_hints": hints[:8],
        "phrases": final_phrases,
        "empty_message": None,
    }
    _save_snapshot(
        user_id=user_id,
        bookmark_date=bookmark_date,
        language=normalized_language,
        source_hash=source_hash,
        primary_theme=primary_theme,
        article_count=len(rows),
        payload=payload,
    )
    return payload
