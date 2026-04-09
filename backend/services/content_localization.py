from __future__ import annotations

import re

_CJK_PATTERN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
_ASCII_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+")

TAG_CATEGORY_LABELS = {
    "zh": {
        "industry": "行业标签",
        "topic": "主题标签",
        "type": "内容类型",
        "entity": "实体标签",
        "series": "系列标签",
    },
    "en": {
        "industry": "Industry tags",
        "topic": "Topic tags",
        "type": "Content types",
        "entity": "Entity tags",
        "series": "Series tags",
    },
}

COLUMN_LOCALIZATIONS = {
    "insights": {
        "name": "Deep Insights",
        "description": "A core column for long-form analysis, interviews, case studies, and essays.",
    },
    "industry": {
        "name": "Industry Watch",
        "description": "Continuous observation of industries, companies, markets, and business models.",
    },
    "research": {
        "name": "Research Frontiers",
        "description": "Research insight, paper decoding, and management knowledge from Fudan and related scholars.",
    },
    "deans-view": {
        "name": "Dean's View",
        "description": "Viewpoints and commentary from Fudan faculty leaders and core teaching staff.",
    },
}

TOPIC_LOCALIZATIONS = {
    "ai-management": {
        "title": "AI Reframing Management",
        "description": "An ongoing topic at the intersection of AI, large models, and management practice.",
    },
    "esg-sustainability": {
        "title": "ESG and Sustainable Transition",
        "description": "A business topic focused on ESG, dual-carbon transformation, and long-term value creation.",
    },
    "leadership-change": {
        "title": "Leadership and Organizational Change",
        "description": "A management topic covering teams, organizations, and culture change.",
    },
    "digital-transformation": {
        "title": "Digital Transformation",
        "description": "A topic that gathers business reading on digitization, platforms, and business-model redesign.",
    },
    "entrepreneurship-innovation": {
        "title": "Entrepreneurship and Innovation",
        "description": "A topic tracking startups, innovation leaders, and new-growth playbooks.",
    },
    "globalization-outbound": {
        "title": "Globalization and Going Global",
        "description": "A topic focused on cross-border operations, global competition, and industrial collaboration.",
    },
    "family-business": {
        "title": "Family Business and Succession",
        "description": "A topic on succession governance, generational transition, and long-term operation.",
    },
    "brand-consumer": {
        "title": "Brand and New Consumption",
        "description": "A topic on brand building, consumer insight, and retail innovation.",
    },
    "capital-markets-governance": {
        "title": "Capital Strategy and Value Management",
        "description": "An automatically generated topic on capital strategy, value management, and corporate governance.",
    },
    "case-teaching-management-education": {
        "title": "Case Teaching and Management Education",
        "description": "An automatically generated topic on case teaching, management education, and classroom application.",
    },
    "smart-manufacturing-upgrade": {
        "title": "Smart Manufacturing and Industrial Upgrade",
        "description": "An automatically generated topic on manufacturing digitization, industrial upgrade, and supply-chain redesign.",
    },
    "ai-healthcare": {
        "title": "AI and Smart Healthcare",
        "description": "An automatically generated topic on AI in healthcare and smart-hospital scenarios.",
    },
    "venture-capital-innovation": {
        "title": "Venture Capital and Innovation Ecosystems",
        "description": "An automatically generated topic on venture capital, startup methods, and innovation ecosystems.",
    },
    "new-energy-green-industry": {
        "title": "New Energy and Green Industry",
        "description": "An automatically generated topic on new-energy industries, green transition, and manufacturing upgrade.",
    },
    "consumer-global-expansion": {
        "title": "Chinese Brands Going Global",
        "description": "An automatically generated topic on global growth paths for Chinese consumer brands.",
    },
    "tech-startup-ecosystem": {
        "title": "Tech Entrepreneurship and Innovation Ecosystems",
        "description": "An automatically generated topic on tech startups, innovation ecosystems, and platform evolution.",
    },
}

TAG_NAME_LOCALIZATIONS = {
    "AI/人工智能": "AI",
    "人工智能": "Artificial Intelligence",
    "数字化转型": "Digital Transformation",
    "科技互联网": "Technology and Internet",
    "创业创新": "Entrepreneurship and Innovation",
    "全球化": "Globalization",
    "金融投资": "Finance and Investment",
    "教育": "Education",
    "消费零售": "Consumer and Retail",
    "制造业": "Manufacturing",
    "领导力": "Leadership",
    "资本市场": "Capital Markets",
    "ESG/可持续": "ESG and Sustainability",
    "ESG": "ESG",
    "可持续发展": "Sustainable Development",
    "双碳": "Dual Carbon",
    "碳中和": "Carbon Neutrality",
    "绿色转型": "Green Transition",
    "企业社会责任": "Corporate Social Responsibility",
    "组织变革": "Organizational Change",
    "企业文化": "Corporate Culture",
    "人才管理": "Talent Management",
    "组织管理": "Organizational Management",
    "组织设计": "Organizational Design",
    "团队管理": "Team Management",
    "数字经济": "Digital Economy",
    "数智化": "Digital Intelligence",
    "大数据": "Big Data",
    "云计算": "Cloud Computing",
    "平台经济": "Platform Economy",
    "数据资产": "Data Assets",
    "智能制造": "Smart Manufacturing",
    "商业模式": "Business Models",
    "创业": "Startups",
    "创业者": "Entrepreneurs",
    "企业家精神": "Entrepreneurship",
    "创新": "Innovation",
    "技术创新": "Technology Innovation",
    "商业创新": "Business Innovation",
    "风险投资": "Venture Capital",
    "出海": "Going Global",
    "国际化": "International Expansion",
    "跨境": "Cross-border",
    "供应链": "Supply Chain",
    "全球供应链": "Global Supply Chain",
    "海外运营": "Overseas Operations",
    "家族企业": "Family Business",
    "家族传承": "Family Succession",
    "代际传承": "Generational Succession",
    "家族财富传承": "Family Wealth Succession",
    "家族企业传承": "Family Business Succession",
    "接班人": "Successor Development",
    "传承治理": "Succession Governance",
    "品牌营销": "Brand Marketing",
    "新零售": "New Retail",
    "消费者洞察": "Consumer Insight",
    "消费心理": "Consumer Psychology",
    "品牌资产": "Brand Equity",
    "营销": "Marketing",
    "医疗健康": "Healthcare",
    "智慧医院": "Smart Hospitals",
    "能源环保": "Energy and Environment",
    "新能源汽车": "New Energy Vehicles",
    "ChatGPT": "ChatGPT",
    "DeepSeek": "DeepSeek",
    "生成式AI": "Generative AI",
    "智能体": "AI Agents",
    "人机协同": "Human-AI Collaboration",
    "人机协作": "Human-AI Collaboration",
    "管理教育": "Management Education",
    "商学院": "Business Schools",
}

TAG_SLUG_LOCALIZATIONS = {
    "topic-ai-人工智能": "AI",
    "topic-数字化转型": "Digital Transformation",
    "industry-科技互联网": "Technology and Internet",
    "topic-创业创新": "Entrepreneurship and Innovation",
    "topic-人工智能": "Artificial Intelligence",
    "topic-全球化": "Globalization",
    "industry-金融投资": "Finance and Investment",
    "industry-教育": "Education",
    "industry-消费零售": "Consumer and Retail",
    "industry-制造业": "Manufacturing",
    "topic-领导力": "Leadership",
    "topic-资本市场": "Capital Markets",
}

_UPPERCASE_TOKENS = {
    "ai": "AI",
    "esg": "ESG",
    "hr": "HR",
    "ipo": "IPO",
    "csr": "CSR",
    "chatgpt": "ChatGPT",
    "deepseek": "DeepSeek",
}


def contains_cjk(value: str | None) -> bool:
    return bool(_CJK_PATTERN.search(str(value or "")))


def tag_category_label(category: str, language: str = "zh") -> str:
    return TAG_CATEGORY_LABELS.get(language, TAG_CATEGORY_LABELS["zh"]).get(category, category)


def _humanize_slug(slug: str | None) -> str:
    cleaned = re.sub(r"^(topic|industry|entity|series|type)-", "", str(slug or ""))
    tokens = _ASCII_TOKEN_PATTERN.findall(cleaned)
    if not tokens:
        return ""
    words = []
    for token in tokens:
        lowered = token.lower()
        words.append(_UPPERCASE_TOKENS.get(lowered, lowered.capitalize()))
    return " ".join(words).strip()


def localize_column_payload(column: dict, language: str = "zh") -> dict:
    payload = dict(column)
    if language != "en":
        return payload
    translation = COLUMN_LOCALIZATIONS.get(str(payload.get("slug") or ""))
    if not translation:
        return payload
    payload["name"] = translation["name"]
    payload["description"] = translation["description"]
    return payload


def localize_tag_name(name: str | None, slug: str | None = None, language: str = "zh") -> str | None:
    if language != "en":
        return str(name or "").strip()
    raw_name = str(name or "").strip()
    raw_slug = str(slug or "").strip()
    if raw_slug in TAG_SLUG_LOCALIZATIONS:
        return TAG_SLUG_LOCALIZATIONS[raw_slug]
    if raw_name in TAG_NAME_LOCALIZATIONS:
        return TAG_NAME_LOCALIZATIONS[raw_name]
    if raw_name and not contains_cjk(raw_name):
        return raw_name
    fallback = _humanize_slug(raw_slug)
    return fallback or None


def localize_tag_payload(tag: dict, language: str = "zh") -> dict | None:
    payload = dict(tag)
    if language != "en":
        return payload
    localized_name = localize_tag_name(payload.get("name"), payload.get("slug"), language=language)
    if not localized_name:
        return None
    payload["name"] = localized_name
    return payload


def localize_topic_title(slug: str | None, title: str | None, language: str = "zh") -> str:
    if language != "en":
        return str(title or "")
    slug_value = str(slug or "")
    translation = TOPIC_LOCALIZATIONS.get(slug_value)
    if translation:
        return translation["title"]
    if title and not contains_cjk(title):
        return str(title)
    fallback = _humanize_slug(slug_value)
    return fallback or "Topic Reading"


def localize_topic_description(
    *,
    slug: str | None,
    title: str | None,
    description: str | None,
    article_count: int | None = None,
    first_date: str | None = None,
    last_date: str | None = None,
    language: str = "zh",
) -> str:
    if language != "en":
        return str(description or "")
    slug_value = str(slug or "")
    translation = TOPIC_LOCALIZATIONS.get(slug_value)
    base = translation["description"] if translation else ""
    if not base and description and not contains_cjk(description):
        base = str(description).strip()
    if not base:
        topic_title = localize_topic_title(slug_value, title, language=language)
        base = f"Structured topic reading around {topic_title.lower()}."
    extras: list[str] = []
    if article_count:
        extras.append(f"This topic currently groups {article_count} business articles.")
    if first_date and last_date:
        extras.append(f"Coverage spans {first_date} to {last_date}.")
    elif last_date:
        extras.append(f"Coverage runs through {last_date}.")
    return " ".join(part for part in [base, *extras] if part).strip()


def localize_topic_payload(
    topic: dict,
    *,
    language: str = "zh",
    article_count: int | None = None,
    first_date: str | None = None,
    last_date: str | None = None,
) -> dict:
    payload = dict(topic)
    if language != "en":
        return payload
    payload["title"] = localize_topic_title(payload.get("slug"), payload.get("title"), language=language)
    payload["description"] = localize_topic_description(
        slug=payload.get("slug"),
        title=payload.get("title"),
        description=payload.get("description"),
        article_count=article_count or payload.get("article_count"),
        first_date=first_date,
        last_date=last_date,
        language=language,
    )
    localized_tags = []
    for tag in payload.get("tags", []):
        localized = localize_tag_payload(tag, language=language)
        if localized:
            localized_tags.append(localized)
    payload["tags"] = localized_tags
    return payload


def english_article_ready(article: dict) -> bool:
    title = str(article.get("title") or "").strip()
    excerpt = str(article.get("excerpt") or article.get("main_topic") or "").strip()
    if not title:
        return False
    if contains_cjk(title):
        return False
    if excerpt and contains_cjk(excerpt):
        return False
    return True
