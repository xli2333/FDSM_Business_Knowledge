from __future__ import annotations

import re
from typing import Any

PLACEHOLDER_ONLY_PREFIX = "此页面触发全局图片搜索模式"
PROMOTIONAL_MARKERS = (
    "留言赠礼",
    "投票赢好礼",
    "扫码订阅杂志",
    "订阅杂志",
    "全年四期优惠征订",
    "关注公众号",
    "请后台留言",
    "点赞数前",
    "活动有效期",
    "亲笔签名版",
    "评论区留言",
)
PROMOTIONAL_BODY_SHORT_MAX_LEN = 250
PROMOTIONAL_BODY_MID_MAX_LEN = 400
PROMOTIONAL_SHORT_MARKER_HIT_MIN = 3
PROMOTIONAL_MID_MARKER_HIT_MIN = 4


def _extract_title_and_content(article: Any) -> tuple[str, str]:
    if isinstance(article, dict):
        return str(article.get("title") or ""), str(article.get("content") or "")
    if article is None:
        return "", ""
    title = str(article["title"] or "") if "title" in article.keys() else ""
    content = str(article["content"] or "") if "content" in article.keys() else ""
    return title, content


def _compact_text(text: str) -> str:
    return re.sub(r"[\s\u200b\u2060\ufeff]+", "", str(text or ""))


def is_placeholder_only_article(article: Any) -> bool:
    _title, content = _extract_title_and_content(article)
    normalized = str(content or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized.startswith(PLACEHOLDER_ONLY_PREFIX):
        return False
    lines = [line.strip() for line in normalized.splitlines() if line.strip()]
    if len(lines) > 3:
        return False
    return all(
        ("图片" in line)
        or ("此页面" in line)
        or ("全局图片搜索模式" in line)
        for line in lines
    )


def is_promotional_low_value_article(article: Any) -> bool:
    _title, content = _extract_title_and_content(article)
    compact_content = _compact_text(content)
    if not compact_content or len(compact_content) > PROMOTIONAL_BODY_MID_MAX_LEN:
        return False
    marker_hits = sum(compact_content.count(marker) for marker in PROMOTIONAL_MARKERS)
    if len(compact_content) <= PROMOTIONAL_BODY_SHORT_MAX_LEN:
        return marker_hits >= PROMOTIONAL_SHORT_MARKER_HIT_MIN
    return marker_hits >= PROMOTIONAL_MID_MARKER_HIT_MIN


def is_hidden_low_value_article(article: Any) -> bool:
    return is_placeholder_only_article(article) or is_promotional_low_value_article(article)
