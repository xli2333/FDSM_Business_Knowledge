from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("FDSM_DATA_DIR", BASE_DIR))
BUSINESS_DATA_DIR = DATA_DIR / "Fudan_Business_Knowledge_Data"
SQLITE_DB_PATH = DATA_DIR / "fudan_knowledge_base.db"
FAISS_DB_DIR = DATA_DIR / "faiss_index_business"
LEGACY_ARCHIVE_DIR = DATA_DIR / "archive" / "legacy_pre_knowledge_base"
LEGACY_FAISS_DB_DIR = LEGACY_ARCHIVE_DIR / "indexes" / "faiss_index"
UPLOADS_DIR = DATA_DIR / "uploads"
MEDIA_UPLOADS_DIR = UPLOADS_DIR / "media"
GEMINI_AGGREGATE_PATH = (
    BUSINESS_DATA_DIR / "gemini_flash_batch" / "output" / "aggregate" / "all_documents.json"
)

APP_TITLE = "复旦管院商业智识库 API"
DEFAULT_PAGE_SIZE = 12
MAX_PAGE_SIZE = 48

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "").strip()
GEMINI_API_KEYS = [item.strip() for item in os.getenv("GEMINI_API_KEYS", "").split(",") if item.strip()]
PRIMARY_GEMINI_KEY = GOOGLE_API_KEY or (GEMINI_API_KEYS[0] if GEMINI_API_KEYS else "")
GEMINI_CHAT_MODEL = os.getenv("GEMINI_CHAT_MODEL", "gemini-3-flash").strip()
GEMINI_FLASH_MODEL = os.getenv("GEMINI_FLASH_MODEL", "gemini-2.5-flash")
GEMINI_EMBEDDING_MODEL = os.getenv("GEMINI_EMBEDDING_MODEL", "models/gemini-embedding-001")
GEMINI_EDITORIAL_FORMAT_MODEL = "gemini-3-flash-preview"
GEMINI_RUNTIME_MODEL_ALIASES = {
    "gemini-3-flash": "gemini-3-flash-preview",
}


def resolve_gemini_model_name(model_name: str) -> str:
    cleaned = str(model_name or "").strip()
    return GEMINI_RUNTIME_MODEL_ALIASES.get(cleaned, cleaned)

ALLOWED_ORIGINS = [origin.strip() for origin in os.getenv("ALLOWED_ORIGINS", "*").split(",") if origin.strip()]
SITE_BASE_URL = os.getenv("SITE_BASE_URL", "http://127.0.0.1:4173").rstrip("/")
SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "").strip()
SUPABASE_AUTH_TIMEOUT_SECONDS = float(os.getenv("SUPABASE_AUTH_TIMEOUT_SECONDS", "8"))
ADMIN_EMAILS = {item.strip().lower() for item in os.getenv("ADMIN_EMAILS", "").split(",") if item.strip()}
DEV_AUTH_ENABLED = os.getenv("DEV_AUTH_ENABLED", "0").strip() == "1"
SUPABASE_AUTH_ENABLED = bool(SUPABASE_URL and SUPABASE_ANON_KEY)
PREVIEW_AUTH_ENABLED = DEV_AUTH_ENABLED or not SUPABASE_AUTH_ENABLED
PAYMENTS_ENABLED = os.getenv("PAYMENTS_ENABLED", "0").strip() == "1"
PAYMENT_PROVIDER = os.getenv("PAYMENT_PROVIDER", "mock")

BILLING_PLAN_DEFINITIONS = [
    {
        "plan_code": "free_member_monthly",
        "name": "免费会员",
        "tier": "free_member",
        "price_cents": 0,
        "currency": "CNY",
        "billing_period": "month",
        "headline": "读者留存与资产沉淀入口",
        "description": "适合建立阅读账户、保留收藏点赞、解锁基础会员内容。",
        "features": [
            "保留阅读历史、点赞与收藏",
            "解锁会员音频和视频基础内容",
            "作为付费升级的承接层",
        ],
        "sort_order": 1,
    },
    {
        "plan_code": "paid_member_monthly",
        "name": "付费会员月订阅",
        "tier": "paid_member",
        "price_cents": 3000,
        "currency": "CNY",
        "billing_period": "month",
        "headline": "高价值会员内容的主力套餐",
        "description": "适合深度商业知识服务、闭门内容、专题专报和付费音视频。",
        "features": [
            "解锁付费文章、付费音频和付费视频",
            "适合专题专报、课程和闭门简报",
            "可继续接入续费、试用和优惠券体系",
        ],
        "sort_order": 2,
    },
    {
        "plan_code": "paid_member_yearly",
        "name": "付费会员年订阅",
        "tier": "paid_member",
        "price_cents": 30000,
        "currency": "CNY",
        "billing_period": "year",
        "headline": "面向机构高价值用户的年度方案",
        "description": "适合长期跟踪行业、专题化学习和稳定续费运营。",
        "features": [
            "包含全年付费内容访问权限",
            "适合绑定年度专报、课程和线下活动",
            "为后续机构版与席位版打基础",
        ],
        "sort_order": 3,
    },
]

COLUMN_DEFINITIONS = [
    {
        "name": "深度洞察",
        "slug": "insights",
        "description": "面向深度分析、专访、案例与长文的核心栏目。",
        "icon": "Sparkles",
        "sort_order": 1,
        "accent_color": "#0d0783",
    },
    {
        "name": "行业观察",
        "slug": "industry",
        "description": "围绕产业、公司、市场与商业模式的持续观察。",
        "icon": "Building2",
        "sort_order": 2,
        "accent_color": "#ea6b00",
    },
    {
        "name": "学术前沿",
        "slug": "research",
        "description": "复旦管院及相关学者的研究洞见、论文解读与管理新知。",
        "icon": "GraduationCap",
        "sort_order": 3,
        "accent_color": "#4f46e5",
    },
    {
        "name": "院长说",
        "slug": "deans-view",
        "description": "聚焦复旦管院教授、院长与核心师资的观点表达。",
        "icon": "Mic2",
        "sort_order": 4,
        "accent_color": "#b45309",
    },
]

TOPIC_SEEDS = [
    {
        "slug": "ai-management",
        "title": "AI 重构管理",
        "primary_tags": ["AI/人工智能", "人工智能", "ChatGPT", "DeepSeek", "生成式AI", "智能体"],
        "support_tags": ["人机协同", "人机协作", "数字化转型"],
        "match_tags": ["AI/人工智能", "人工智能", "ChatGPT", "DeepSeek", "生成式AI", "智能体", "人机协同", "人机协作", "数字化转型"],
        "description_prefix": "聚焦人工智能、大模型与管理实践交汇地带的持续专题。",
    },
    {
        "slug": "esg-sustainability",
        "title": "ESG 与可持续转型",
        "primary_tags": ["ESG/可持续", "ESG", "可持续发展", "双碳", "碳中和"],
        "support_tags": ["绿色转型", "企业社会责任"],
        "match_tags": ["ESG/可持续", "ESG", "可持续发展", "双碳", "碳中和", "绿色转型", "企业社会责任"],
        "description_prefix": "围绕 ESG、双碳与长期价值创造的商业专题。",
    },
    {
        "slug": "leadership-change",
        "title": "领导力与组织变革",
        "primary_tags": ["领导力", "组织变革", "企业文化", "人才管理"],
        "support_tags": ["组织管理", "组织设计", "团队管理"],
        "match_tags": ["领导力", "组织变革", "企业文化", "人才管理", "组织管理", "组织设计", "团队管理"],
        "description_prefix": "从团队、组织到文化升级的管理专题。",
    },
    {
        "slug": "digital-transformation",
        "title": "数字化转型",
        "primary_tags": ["数字化转型", "数字经济", "数智化", "大数据", "云计算"],
        "support_tags": ["平台经济", "数据资产", "智能制造", "商业模式"],
        "match_tags": ["数字化转型", "数字经济", "数智化", "大数据", "云计算", "平台经济", "数据资产", "智能制造", "商业模式"],
        "description_prefix": "聚合数字化、平台化与商业模式重构相关内容。",
    },
    {
        "slug": "entrepreneurship-innovation",
        "title": "创业创新",
        "primary_tags": ["创业创新", "创业", "创业者", "企业家精神"],
        "support_tags": ["创新", "技术创新", "商业创新", "风险投资"],
        "match_tags": ["创业创新", "创业", "创业者", "企业家精神", "创新", "技术创新", "商业创新", "风险投资"],
        "description_prefix": "跟踪创新企业、创业者与新增长方法论的专题。",
    },
    {
        "slug": "globalization-outbound",
        "title": "全球化与出海",
        "primary_tags": ["全球化", "出海", "国际化", "跨境"],
        "support_tags": ["供应链", "全球供应链", "海外运营"],
        "match_tags": ["全球化", "出海", "国际化", "跨境", "供应链", "全球供应链", "海外运营"],
        "description_prefix": "聚焦跨境经营、全球竞争与产业协同的专题。",
    },
    {
        "slug": "family-business",
        "title": "家族企业与传承",
        "primary_tags": ["家族企业", "家族传承", "代际传承", "家族财富传承", "家族企业传承"],
        "support_tags": ["接班人", "传承治理"],
        "match_tags": ["家族企业", "家族传承", "代际传承", "家族财富传承", "家族企业传承", "接班人", "传承治理"],
        "description_prefix": "关于传承治理、代际更替与长期经营的专题。",
    },
    {
        "slug": "brand-consumer",
        "title": "品牌与新消费",
        "primary_tags": ["品牌营销", "新零售", "消费零售", "消费者洞察", "消费心理"],
        "support_tags": ["品牌资产", "营销"],
        "match_tags": ["品牌营销", "新零售", "消费零售", "消费者洞察", "消费心理", "品牌资产", "营销"],
        "description_prefix": "聚焦品牌塑造、消费者洞察与零售创新的专题。",
    },
]

TOPIC_AUTO_CLUSTERS = [
    {
        "slug": "capital-markets-governance",
        "title": "资本运作与价值管理",
        "required_tags": ["金融投资", "资本市场"],
        "support_tags": ["公司治理", "股权激励", "上市公司", "并购"],
        "description_prefix": "围绕资本运作、价值管理与公司治理的自动专题。",
        "min_articles": 10,
        "article_limit": 18,
    },
    {
        "slug": "case-teaching-management-education",
        "title": "案例教学与管理教育",
        "required_tags": ["案例教学", "教育"],
        "support_tags": ["管理教育", "商学院"],
        "description_prefix": "聚焦案例教学、管理教育与课堂实践转化的自动专题。",
        "min_articles": 10,
        "article_limit": 18,
    },
    {
        "slug": "smart-manufacturing-upgrade",
        "title": "智能制造与产业升级",
        "required_tags": ["制造业", "数字化转型"],
        "support_tags": ["智能制造", "工业4.0", "供应链"],
        "description_prefix": "聚焦制造业数智化、产业升级与供应链重构的自动专题。",
        "min_articles": 10,
        "article_limit": 18,
    },
    {
        "slug": "ai-healthcare",
        "title": "AI 与智慧医疗",
        "required_tags": ["AI/人工智能", "医疗健康"],
        "support_tags": ["人工智能", "智慧医院"],
        "description_prefix": "围绕 AI 技术进入医疗健康与智慧医院场景的自动专题。",
        "min_articles": 8,
        "article_limit": 16,
    },
    {
        "slug": "venture-capital-innovation",
        "title": "风险投资与创业生态",
        "required_tags": ["创业创新", "金融投资"],
        "support_tags": ["风险投资", "企业家精神", "创业"],
        "description_prefix": "聚焦风险投资、创业方法论与创新生态的自动专题。",
        "min_articles": 10,
        "article_limit": 18,
    },
    {
        "slug": "new-energy-green-industry",
        "title": "新能源与绿色产业",
        "required_tags": ["能源环保", "新能源汽车"],
        "support_tags": ["制造业", "碳中和", "可持续发展"],
        "description_prefix": "围绕新能源产业、绿色转型与制造升级的自动专题。",
        "min_articles": 8,
        "article_limit": 16,
    },
    {
        "slug": "consumer-global-expansion",
        "title": "中国品牌出海",
        "required_tags": ["消费零售", "全球化"],
        "support_tags": ["品牌营销", "出海", "新零售"],
        "description_prefix": "聚焦中国消费品牌出海与全球化增长路径的自动专题。",
        "min_articles": 8,
        "article_limit": 16,
    },
    {
        "slug": "tech-startup-ecosystem",
        "title": "科技创业与创新生态",
        "required_tags": ["科技互联网", "创业创新"],
        "support_tags": ["AI/人工智能", "风险投资", "数字化转型"],
        "description_prefix": "围绕科技创业、创新生态与平台演化的自动专题。",
        "min_articles": 10,
        "article_limit": 18,
    },
]
