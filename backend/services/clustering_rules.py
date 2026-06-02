from __future__ import annotations

from collections.abc import Iterable

INSIGHT_ARTICLE_TYPES = {
    "专访",
    "访谈",
    "对谈",
    "案例报道",
    "评论/观点",
    "书摘/书评",
}

INDUSTRY_ARTICLE_TYPES = {
    "专访",
    "访谈",
    "对谈",
    "案例报道",
    "评论/观点",
    "资讯/观察",
    "会议报道",
}

DEANS_VIEW_ARTICLE_TYPES = {
    "专访",
    "访谈",
    "对谈",
    "评论/观点",
    "研究/论文解读",
    "书摘/书评",
}

DEANS_VIEW_ROLE_SIGNALS = {
    "教授",
    "院长",
    "学术院长",
    "特聘教授",
}

INDUSTRY_TOPIC_SIGNALS = {
    "AI/人工智能",
    "数字化转型",
    "创业创新",
    "全球化",
    "供应链",
    "ESG/可持续",
    "品牌营销",
    "资本市场",
    "家族企业",
    "案例教学",
}

CASE_DECISION_SIGNALS = {
    "案例",
    "案例教学",
    "案例报道",
    "案例研究",
    "决策",
    "复盘",
    "商业模式",
    "公司治理",
    "战略",
}

CLASSROOM_SIGNALS = {
    "课程",
    "课堂",
    "校友",
    "EMBA",
    "MBA",
    "教学",
    "招生",
    "毕业",
    "开学",
    "复旦管理案例课堂",
    "复旦科创案例工作坊",
    "FDSM CASE HOUR",
}


def _tag_name_set(tag_entries: Iterable[tuple[str, str, float]], category: str) -> set[str]:
    return {
        name
        for name, entry_category, _ in tag_entries
        if entry_category == category and name
    }


def derive_column_slugs(
    *,
    word_count: int,
    article_type: str | None,
    series_or_column: str | None,
    tag_entries: Iterable[tuple[str, str, float]],
    fdsm_hits: Iterable[str] = (),
) -> list[str]:
    topic_names = _tag_name_set(tag_entries, "topic")
    industry_names = _tag_name_set(tag_entries, "industry")
    fdsm_role_hits = {item for item in fdsm_hits if item in DEANS_VIEW_ROLE_SIGNALS}
    haystack = " ".join(
        item
        for item in [
            article_type or "",
            series_or_column or "",
            " ".join(topic_names),
            " ".join(industry_names),
        ]
        if item
    )

    columns: list[str] = []

    has_classroom_signal = any(token in haystack for token in CLASSROOM_SIGNALS)
    if has_classroom_signal:
        columns.append("fudan-classroom")

    has_case_signal = (
        article_type in {"案例报道", "案例研究"}
        or any(token in haystack for token in CASE_DECISION_SIGNALS)
    )
    if has_case_signal:
        columns.append("case-decisions")

    is_research = article_type == "研究/论文解读" or "管理视野" in (series_or_column or "")
    if is_research:
        columns.append("research")

    if fdsm_role_hits and article_type in DEANS_VIEW_ARTICLE_TYPES:
        columns.append("deans-view")

    has_industry_signal = bool(industry_names) and (
        article_type in INDUSTRY_ARTICLE_TYPES
        or len(industry_names) >= 2
        or bool(topic_names.intersection(INDUSTRY_TOPIC_SIGNALS))
    )
    if has_industry_signal:
        columns.append("industry")

    is_insight = (
        word_count >= 2200
        or article_type in INSIGHT_ARTICLE_TYPES
        or (article_type == "研究/论文解读" and word_count >= 2600)
    )
    if is_insight or not columns:
        columns.append("insights")

    deduped: list[str] = []
    seen: set[str] = set()
    for slug in columns:
        if slug in seen:
            continue
        seen.add(slug)
        deduped.append(slug)
    return deduped or ["insights"]
