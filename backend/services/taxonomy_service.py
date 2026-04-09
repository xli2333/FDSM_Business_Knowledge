from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

KEYWORD_STOPWORDS = {
    "商业",
    "管理",
    "企业",
    "复旦商业知识",
    "复旦大学管理学院",
    "管理视野",
    "FBK翻书日签",
    "翻书日签",
    "日签",
    "书单",
}

SERIES_NOISE = {"FBK翻书日签", "翻书日签", "《管理视野》", "管理视野"}

RAW_KEYWORD_BLOCKLIST = {
    "日签",
    "书单",
    "管理视野",
    "FBK翻书日签",
    "翻书日签",
    "复旦大学管理学院",
    "复旦管院",
}

ASCII_TOKEN_PATTERN = re.compile(r"^[a-z0-9.+-]+$", re.IGNORECASE)
WHITESPACE_PATTERN = re.compile(r"\s+")
PRIMARY_RULE_FIELDS = ("keywords", "main_topic", "title")
STRONG_FIELD_WEIGHTS = {
    "keywords": 2.4,
    "main_topic": 2.0,
    "title": 1.7,
    "excerpt": 0.75,
    "content": 0.45,
}
WEAK_FIELD_WEIGHTS = {
    "keywords": 1.2,
    "main_topic": 1.0,
    "title": 0.85,
    "excerpt": 0.25,
    "content": 0.15,
}
MAX_LABELS_BY_CATEGORY = {"topic": 4, "industry": 2}


@dataclass(frozen=True)
class TaxonomyRule:
    name: str
    category: str
    strong_phrases: tuple[str, ...]
    weak_phrases: tuple[str, ...] = ()
    threshold: float = 2.2
    require_primary_strong: bool = True


TAXONOMY_RULES = (
    TaxonomyRule(
        name="AI/人工智能",
        category="topic",
        strong_phrases=("人工智能", "AIGC", "ChatGPT", "DeepSeek", "大模型", "生成式AI", "智能体", "机器学习", "深度学习", "AI"),
        weak_phrases=("人机协同", "人机协作", "算法"),
        threshold=2.4,
    ),
    TaxonomyRule(
        name="ESG/可持续",
        category="topic",
        strong_phrases=("ESG", "可持续发展", "可持续", "双碳", "碳中和", "绿色转型", "企业社会责任"),
        weak_phrases=("减排", "低碳", "碳排放"),
        threshold=2.25,
    ),
    TaxonomyRule(
        name="数字化转型",
        category="topic",
        strong_phrases=("数字化转型", "数智化", "数字化", "数字经济", "大数据", "云计算", "工业4.0", "智能制造"),
        weak_phrases=("数据资产", "平台经济", "信息化"),
        threshold=2.25,
    ),
    TaxonomyRule(
        name="创业创新",
        category="topic",
        strong_phrases=("创业创新", "创业", "创业者", "初创企业", "企业家精神", "风险投资"),
        weak_phrases=("创新", "技术创新", "商业创新"),
        threshold=2.25,
    ),
    TaxonomyRule(
        name="供应链",
        category="topic",
        strong_phrases=("供应链", "供应链管理", "物流", "产业链", "制造升级", "采购", "库存"),
        weak_phrases=("交付",),
        threshold=2.2,
    ),
    TaxonomyRule(
        name="领导力",
        category="topic",
        strong_phrases=("领导力", "领导者", "管理者领导"),
        weak_phrases=("高管", "中层管理者", "管理团队"),
        threshold=2.35,
    ),
    TaxonomyRule(
        name="品牌营销",
        category="topic",
        strong_phrases=("品牌营销", "新零售", "消费者洞察", "消费心理", "品牌资产"),
        weak_phrases=("品牌", "营销", "广告", "用户增长"),
        threshold=2.1,
    ),
    TaxonomyRule(
        name="组织管理",
        category="topic",
        strong_phrases=("组织管理", "组织设计", "组织行为", "组织发展", "组织治理", "团队管理", "组织能力"),
        weak_phrases=("组织变革", "企业文化", "人才管理", "企业管理"),
        threshold=2.4,
    ),
    TaxonomyRule(
        name="资本市场",
        category="topic",
        strong_phrases=("资本市场", "IPO", "并购", "证券", "市值管理", "上市公司", "股权激励", "融资"),
        weak_phrases=("一级市场", "二级市场", "基金"),
        threshold=2.2,
    ),
    TaxonomyRule(
        name="全球化",
        category="topic",
        strong_phrases=("全球化", "国际化", "出海", "跨境", "海外市场", "全球竞争"),
        weak_phrases=("全球供应链", "海外运营"),
        threshold=2.2,
    ),
    TaxonomyRule(
        name="家族企业",
        category="topic",
        strong_phrases=("家族企业", "家族传承", "代际传承", "家族财富传承", "家族治理"),
        weak_phrases=("接班人", "传承治理"),
        threshold=2.2,
    ),
    TaxonomyRule(
        name="案例教学",
        category="topic",
        strong_phrases=("案例教学", "案例工作坊", "管理案例", "案例研究", "案例课堂", "复旦管理案例工作坊"),
        threshold=2.2,
    ),
    TaxonomyRule(
        name="科技互联网",
        category="industry",
        strong_phrases=("科技互联网", "互联网", "科技公司", "软件", "SaaS", "芯片", "半导体", "云计算", "机器人", "平台经济", "智能硬件", "自动驾驶", "无人驾驶"),
        weak_phrases=("算法",),
        threshold=2.35,
    ),
    TaxonomyRule(
        name="金融投资",
        category="industry",
        strong_phrases=("金融投资", "资本市场", "银行", "基金", "证券", "保险", "并购", "IPO", "风险投资"),
        weak_phrases=("投资",),
        threshold=2.25,
    ),
    TaxonomyRule(
        name="消费零售",
        category="industry",
        strong_phrases=("消费零售", "零售", "新零售", "电商", "消费品", "消费者", "餐饮"),
        weak_phrases=("品牌",),
        threshold=2.1,
    ),
    TaxonomyRule(
        name="制造业",
        category="industry",
        strong_phrases=("制造业", "制造", "工业", "工厂", "汽车", "工业4.0", "智能制造"),
        weak_phrases=("生产",),
        threshold=2.0,
    ),
    TaxonomyRule(
        name="医疗健康",
        category="industry",
        strong_phrases=("医疗健康", "医疗", "医院", "制药", "生命科学", "医药"),
        weak_phrases=("健康",),
        threshold=2.0,
    ),
    TaxonomyRule(
        name="教育",
        category="industry",
        strong_phrases=("教育", "教学", "课堂", "人才培养", "商学院", "高考改革", "管理教育"),
        weak_phrases=("高校", "学校", "学习"),
        threshold=2.25,
    ),
    TaxonomyRule(
        name="能源环保",
        category="industry",
        strong_phrases=("能源环保", "能源", "环保", "新能源", "光伏", "储能", "双碳", "碳中和"),
        weak_phrases=("可持续",),
        threshold=2.1,
    ),
    TaxonomyRule(
        name="文化传媒",
        category="industry",
        strong_phrases=("文化传媒", "传媒", "出版", "影视", "电影", "游戏", "动漫", "播客", "广告"),
        weak_phrases=("IP运营", "IP开发"),
        threshold=2.2,
    ),
)

TOPIC_SYNONYMS = {
    rule.name: [*rule.strong_phrases, *rule.weak_phrases]
    for rule in TAXONOMY_RULES
    if rule.category == "topic"
}

INDUSTRY_RULES = {
    rule.name: [*rule.strong_phrases, *rule.weak_phrases]
    for rule in TAXONOMY_RULES
    if rule.category == "industry"
}


def normalize_keyword(value: str) -> str | None:
    text = value.strip()
    if not text or text in KEYWORD_STOPWORDS:
        return None
    text = text.replace("（", "(").replace("）", ")")
    text = WHITESPACE_PATTERN.sub("", text)
    return text[:24] if text else None


def _normalize_text(value: str | None) -> str:
    return (value or "").strip().lower()


def _compact_text(value: str | None) -> str:
    return WHITESPACE_PATTERN.sub("", _normalize_text(value))


def _contains_phrase(raw_text: str, compact_text: str, phrase: str) -> bool:
    normalized_phrase = _normalize_text(phrase)
    if not normalized_phrase:
        return False
    if ASCII_TOKEN_PATTERN.fullmatch(normalized_phrase):
        pattern = rf"(?<![a-z0-9]){re.escape(normalized_phrase)}(?![a-z0-9])"
        return re.search(pattern, raw_text) is not None
    return _compact_text(phrase) in compact_text


def _best_phrase_hit(
    phrase: str,
    field_texts: dict[str, tuple[str, str]],
    field_weights: dict[str, float],
) -> tuple[str, str, float] | None:
    best_field = None
    best_weight = 0.0
    for field_name, (raw_text, compact_text) in field_texts.items():
        if not raw_text:
            continue
        if _contains_phrase(raw_text, compact_text, phrase):
            weight = field_weights[field_name]
            if weight > best_weight:
                best_field = field_name
                best_weight = weight
    if best_field is None:
        return None
    return best_field, phrase, best_weight


def _score_rule(
    rule: TaxonomyRule,
    field_texts: dict[str, tuple[str, str]],
) -> tuple[float, list[tuple[str, str, float]], list[tuple[str, str, float]]]:
    score = 0.0
    strong_hits: list[tuple[str, str, float]] = []
    weak_hits: list[tuple[str, str, float]] = []

    for phrase in rule.strong_phrases:
        hit = _best_phrase_hit(phrase, field_texts, STRONG_FIELD_WEIGHTS)
        if hit is None:
            continue
        strong_hits.append(hit)
        score += hit[2]

    if rule.require_primary_strong and not any(hit[0] in PRIMARY_RULE_FIELDS for hit in strong_hits):
        return 0.0, [], []

    if not strong_hits:
        return 0.0, [], []

    for phrase in rule.weak_phrases:
        hit = _best_phrase_hit(phrase, field_texts, WEAK_FIELD_WEIGHTS)
        if hit is None:
            continue
        weak_hits.append(hit)
        score += hit[2]

    return score, strong_hits, weak_hits


def _score_to_confidence(score: float, threshold: float) -> float:
    ceiling = threshold + 3.2
    normalized = min(1.0, max(0.0, (score - threshold) / max(ceiling - threshold, 0.1)))
    return round(0.76 + normalized * 0.18, 2)


def _clean_keyword_list(raw_keywords: Iterable[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for value in raw_keywords:
        normalized = normalize_keyword(value)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        cleaned.append(normalized)
    return cleaned


def _keyword_allowed(keyword: str, allowed_keywords: set[str] | None) -> bool:
    if not keyword or keyword in RAW_KEYWORD_BLOCKLIST:
        return False
    if ASCII_TOKEN_PATTERN.fullmatch(keyword) and len(keyword) <= 4:
        return False
    if allowed_keywords is not None and keyword not in allowed_keywords:
        return False
    return True


def build_tag_entries(
    *,
    title: str = "",
    main_topic: str | None = None,
    excerpt: str = "",
    content: str = "",
    article_type: str | None = None,
    series_or_column: str | None = None,
    raw_keywords: Iterable[str] = (),
    people_names: Iterable[str] = (),
    org_names: Iterable[str] = (),
    allowed_keywords: set[str] | None = None,
    strong_series: set[str] | None = None,
    known_categories: dict[str, str] | None = None,
) -> list[tuple[str, str, float]]:
    keyword_list = _clean_keyword_list(raw_keywords)
    field_texts = {
        "keywords": (_normalize_text(" ".join(keyword_list)), _compact_text(" ".join(keyword_list))),
        "main_topic": (_normalize_text(main_topic), _compact_text(main_topic)),
        "title": (_normalize_text(title), _compact_text(title)),
        "excerpt": (_normalize_text(excerpt), _compact_text(excerpt)),
        "content": (_normalize_text((content or "")[:1800]), _compact_text((content or "")[:1800])),
    }

    scored_labels: list[tuple[str, str, float, float]] = []
    for rule in TAXONOMY_RULES:
        score, _, _ = _score_rule(rule, field_texts)
        if score < rule.threshold:
            continue
        scored_labels.append((rule.name, rule.category, _score_to_confidence(score, rule.threshold), score))

    selected_label_names: set[str] = set()
    entries: list[tuple[str, str, float]] = []
    for category in ("topic", "industry"):
        bucket = [item for item in scored_labels if item[1] == category]
        bucket.sort(key=lambda item: (item[3], item[2], item[0]), reverse=True)
        for name, _, confidence, _ in bucket[: MAX_LABELS_BY_CATEGORY.get(category, 2)]:
            selected_label_names.add(name)
            entries.append((name, category, confidence))

    keyword_entries: list[tuple[str, str, float]] = []
    for keyword in keyword_list:
        if keyword in selected_label_names or not _keyword_allowed(keyword, allowed_keywords):
            continue
        category = (known_categories or {}).get(keyword, "topic")
        if category not in {"topic", "industry"}:
            category = "topic"
        keyword_entries.append((keyword, category, 0.81 if category == "topic" else 0.79))
    entries.extend(keyword_entries[:3])

    if article_type:
        entries.append((article_type, "type", 1.0))

    allow_series = (
        bool(series_or_column)
        and series_or_column not in SERIES_NOISE
        and (strong_series is None or series_or_column in strong_series)
    )
    if allow_series:
        entries.append((series_or_column or "", "series", 0.8))

    for name in list(dict.fromkeys(item.strip() for item in people_names if item and item.strip()))[:3]:
        entries.append((name, "entity", 0.76))
    for name in list(dict.fromkeys(item.strip() for item in org_names if item and item.strip()))[:2]:
        if len(name) <= 30:
            entries.append((name, "entity", 0.73))

    deduped: list[tuple[str, str, float]] = []
    seen: set[tuple[str, str]] = set()
    for name, category, confidence in entries:
        key = (name, category)
        if key in seen or not name:
            continue
        seen.add(key)
        deduped.append((name, category, confidence))
    return deduped
