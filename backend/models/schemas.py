from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class TagSummary(BaseModel):
    id: int
    name: str
    slug: str
    category: str
    color: str | None = None
    article_count: int = 0


class ColumnSummary(BaseModel):
    id: int
    name: str
    slug: str
    description: str | None = None
    icon: str | None = None
    accent_color: str | None = None
    article_count: int = 0


class OrganizationSummary(BaseModel):
    name: str
    slug: str
    article_count: int = 0
    latest_publish_date: str | None = None


class ArticleEngagement(BaseModel):
    views: int = 0
    like_count: int = 0
    bookmark_count: int = 0
    liked_by_me: bool = False
    bookmarked_by_me: bool = False
    can_interact: bool = False


class ArticleAccess(BaseModel):
    access_level: str = "public"
    access_label: str = "公开"
    locked: bool = False
    required_membership: str | None = None
    required_membership_label: str | None = None
    message: str | None = None


class ArticleCard(BaseModel):
    id: int
    title: str
    slug: str
    publish_date: str
    source: str = "business"
    excerpt: str
    article_type: str | None = None
    main_topic: str | None = None
    access_level: str = "public"
    access_label: str = "公开"
    view_count: int = 0
    like_count: int = 0
    bookmark_count: int = 0
    cover_url: str | None = None
    link: str | None = None
    tags: list[TagSummary] = Field(default_factory=list)
    columns: list[ColumnSummary] = Field(default_factory=list)
    score: float | None = None


class TopicSummary(BaseModel):
    id: int
    title: str
    slug: str
    description: str
    type: str
    view_count: int = 0
    article_count: int = 0
    cover_article_id: int | None = None
    cover_url: str | None = None
    tags: list[TagSummary] = Field(default_factory=list)


class TopicDetail(TopicSummary):
    total: int = 0
    page: int = 1
    page_size: int = 12
    timeline: list[dict[str, Any]] = Field(default_factory=list)
    insights: list[str] = Field(default_factory=list)
    articles: list[ArticleCard] = Field(default_factory=list)


class OrganizationDetail(OrganizationSummary):
    page: int = 1
    page_size: int = 12
    articles: list[ArticleCard] = Field(default_factory=list)


class ArticleDetail(ArticleCard):
    content: str
    html_web: str | None = None
    html_wechat: str | None = None
    relative_path: str
    source_mode: str | None = None
    primary_org_name: str | None = None
    series_or_column: str | None = None
    word_count: int = 0
    access: ArticleAccess = Field(default_factory=ArticleAccess)
    engagement: ArticleEngagement = Field(default_factory=ArticleEngagement)
    topics: list[TopicSummary] = Field(default_factory=list)
    related_articles: list[ArticleCard] = Field(default_factory=list)


class ArticleTranslationResponse(BaseModel):
    article_id: int
    language: str = "en"
    source_hash: str
    title: str
    excerpt: str = ""
    summary: str
    summary_html: str | None = None
    content: str
    html_web: str | None = None
    html_wechat: str | None = None
    model: str
    cached: bool = False
    content_scope: str = "full"
    access_locked: bool = False
    updated_at: str | None = None


class EditorialAiAssetStatus(BaseModel):
    status: str = "pending"
    summary_ready: bool = False
    format_ready: bool = False
    translation_ready: bool = False
    source_hash: str | None = None
    source_hash_matches_current: bool = True
    updated_at: str | None = None


class EditorialSourceArticleSummary(BaseModel):
    article_id: int
    title: str
    publish_date: str
    excerpt: str = ""
    source: str = "business"
    link: str | None = None
    article_type: str | None = None
    main_topic: str | None = None
    primary_org_name: str | None = None
    access_level: str = "public"
    access_label: str = "public"
    ai: EditorialAiAssetStatus = Field(default_factory=EditorialAiAssetStatus)


class EditorialAiOutputDetail(BaseModel):
    article_id: int
    title: str
    publish_date: str
    excerpt: str = ""
    source: str = "business"
    link: str | None = None
    article_type: str | None = None
    main_topic: str | None = None
    primary_org_name: str | None = None
    access_level: str = "public"
    access_label: str = "public"
    source_hash: str | None = None
    source_hash_matches_current: bool = True
    status: str = "pending"
    summary_ready: bool = False
    format_ready: bool = False
    translation_ready: bool = False
    summary_zh: str | None = None
    summary_html_zh: str | None = None
    formatted_markdown_zh: str | None = None
    translation_title_en: str | None = None
    translation_excerpt_en: str | None = None
    translation_summary_en: str | None = None
    summary_html_en: str | None = None
    translation_content_en: str | None = None
    html_web_zh: str | None = None
    html_wechat_zh: str | None = None
    html_web_en: str | None = None
    html_wechat_en: str | None = None
    translation_model: str | None = None
    format_model: str | None = None
    updated_at: str | None = None


class SearchRequest(BaseModel):
    query: str
    mode: str = "smart"
    language: str = "zh"
    filters: dict[str, Any] = Field(default_factory=dict)
    sort: str = "relevance"
    page: int = 1
    page_size: int = 12


class SearchResponse(BaseModel):
    query: str
    mode: str
    total: int
    page: int
    page_size: int
    query_terms: list[str] = Field(default_factory=list)
    items: list[ArticleCard] = Field(default_factory=list)


class HomeFeedResponse(BaseModel):
    hero: ArticleCard | None = None
    editors_picks: list[ArticleCard] = Field(default_factory=list)
    trending: list[ArticleCard] = Field(default_factory=list)
    column_previews: list[dict[str, Any]] = Field(default_factory=list)
    latest: list[ArticleCard] = Field(default_factory=list)
    hot_tags: list[TagSummary] = Field(default_factory=list)
    topics: list[TopicSummary] = Field(default_factory=list)


class TagGroup(BaseModel):
    category: str
    label: str
    items: list[TagSummary] = Field(default_factory=list)


class TagsResponse(BaseModel):
    groups: list[TagGroup] = Field(default_factory=list)
    hot: list[TagSummary] = Field(default_factory=list)


class ChatMessageIn(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessageIn]
    session_id: str | None = None
    mode: str = "precise"
    language: str = "zh"


class ChatResponse(BaseModel):
    session_id: str
    answer: str
    sources: list[ArticleCard] = Field(default_factory=list)
    follow_up_questions: list[str] = Field(default_factory=list)
    confidence: float = 0.0


class ChatSessionSummary(BaseModel):
    session_id: str
    title: str
    updated_at: str
    last_question: str


class ChatSessionMessage(BaseModel):
    role: str
    content: str
    sources: list[ArticleCard] = Field(default_factory=list)
    follow_ups: list[str] = Field(default_factory=list)
    created_at: str


class ChatSessionDetail(BaseModel):
    session_id: str
    title: str
    created_at: str
    updated_at: str
    messages: list[ChatSessionMessage] = Field(default_factory=list)


class ChatSessionDeleteResponse(BaseModel):
    session_id: str
    deleted: bool = True


class TimeMachineResponse(BaseModel):
    id: int
    title: str
    publish_date: str
    quote: str
    excerpt: str
    cover_url: str | None = None


class CommerceMetric(BaseModel):
    label: str
    value: str
    detail: str


class CommerceOverviewResponse(BaseModel):
    metrics: list[CommerceMetric] = Field(default_factory=list)
    top_topics: list[TopicSummary] = Field(default_factory=list)
    hot_tags: list[TagSummary] = Field(default_factory=list)
    faiss_ready: bool = False
    ai_ready: bool = False
    updated_at: str | None = None
    lead_count: int = 0


class DemoRequestIn(BaseModel):
    name: str
    organization: str
    role: str
    email: str
    phone: str | None = None
    use_case: str
    message: str | None = None


class DemoRequestResponse(BaseModel):
    id: int
    status: str
    created_at: str
    summary: str


class DemoRequestSummary(BaseModel):
    id: int
    name: str
    organization: str
    role: str
    email: str
    phone: str | None = None
    use_case: str
    message: str | None = None
    status: str
    created_at: str


class UserIdentity(BaseModel):
    id: str
    email: str | None = None


class MembershipProfile(BaseModel):
    tier: str = "guest"
    tier_label: str = "游客"
    status: str = "anonymous"
    status_label: str = "未登录"
    is_authenticated: bool = False
    is_admin: bool = False
    can_access_member: bool = False
    can_access_paid: bool = False
    user_id: str | None = None
    email: str | None = None
    note: str | None = None
    started_at: str | None = None
    expires_at: str | None = None
    benefits: list[str] = Field(default_factory=list)


class MockAuthAccount(BaseModel):
    user_id: str
    email: str | None = None
    display_name: str
    title: str | None = None
    organization: str | None = None
    description: str | None = None
    tier: str
    tier_label: str
    status: str
    status_label: str
    role_home_path: str = "/"


class BusinessUserProfile(BaseModel):
    user_id: str | None = None
    email: str | None = None
    display_name: str = "访客"
    title: str | None = None
    organization: str | None = None
    bio: str | None = None
    tier: str = "guest"
    tier_label: str = "游客"
    status: str = "anonymous"
    status_label: str = "未登录"
    role_home_path: str = "/"
    auth_source: str = "guest"
    locale: str = "zh-CN"
    is_seed: bool = False
    is_authenticated: bool = False
    is_admin: bool = False


class UserAssetSummary(BaseModel):
    bookmark_count: int = 0
    like_count: int = 0
    recent_view_count: int = 0
    follow_count: int = 0
    accessible_media_count: int = 0
    unlocked_access_level: str = "public"


class QuickLinkItem(BaseModel):
    label: str
    path: str
    description: str


class MembershipSummary(BaseModel):
    user_id: str
    email: str | None = None
    tier: str
    tier_label: str
    status: str
    status_label: str
    note: str | None = None
    started_at: str | None = None
    expires_at: str | None = None
    created_at: str
    updated_at: str


class MembershipTierCount(BaseModel):
    tier: str
    tier_label: str
    total: int


class MembershipListResponse(BaseModel):
    items: list[MembershipSummary] = Field(default_factory=list)
    counts: list[MembershipTierCount] = Field(default_factory=list)
    total: int = 0


class MembershipUpdateRequest(BaseModel):
    email: str | None = None
    tier: str
    status: str = "active"
    note: str | None = None
    expires_at: str | None = None


class MediaChapter(BaseModel):
    title: str
    timestamp_label: str
    timestamp_seconds: int = 0


class MediaItemSummary(BaseModel):
    id: int
    slug: str
    kind: str
    title: str
    summary: str
    speaker: str | None = None
    series_name: str | None = None
    episode_number: int = 1
    publish_date: str
    duration_seconds: int = 0
    visibility: str
    visibility_label: str
    status: str = "published"
    accessible: bool = False
    gate_copy: str | None = None
    cover_image_url: str | None = None
    media_url: str | None = None
    preview_url: str | None = None
    source_url: str | None = None
    transcript_excerpt: str | None = None
    chapter_count: int = 0


class MediaItemDetail(MediaItemSummary):
    transcript_markdown: str = ""
    body_markdown: str = ""
    chapters: list[MediaChapter] = Field(default_factory=list)


class MediaItemCreate(BaseModel):
    slug: str | None = None
    kind: str
    title: str
    summary: str
    speaker: str | None = None
    series_name: str | None = None
    episode_number: int = 1
    publish_date: str
    duration_seconds: int = 0
    visibility: str = "public"
    status: str = "draft"
    cover_image_url: str | None = None
    media_url: str | None = None
    preview_url: str | None = None
    source_url: str | None = None
    body_markdown: str | None = None
    transcript_markdown: str | None = None
    chapters: list[MediaChapter] = Field(default_factory=list)


class MediaItemUpdate(BaseModel):
    slug: str | None = None
    kind: str | None = None
    title: str | None = None
    summary: str | None = None
    speaker: str | None = None
    series_name: str | None = None
    episode_number: int | None = None
    publish_date: str | None = None
    duration_seconds: int | None = None
    visibility: str | None = None
    status: str | None = None
    cover_image_url: str | None = None
    media_url: str | None = None
    preview_url: str | None = None
    source_url: str | None = None
    body_markdown: str | None = None
    transcript_markdown: str | None = None
    chapters: list[MediaChapter] | None = None


class MediaAdminListResponse(BaseModel):
    items: list[MediaItemDetail] = Field(default_factory=list)
    total: int = 0


class MediaUploadResponse(BaseModel):
    kind: str
    usage: str
    filename: str
    content_type: str | None = None
    size_bytes: int = 0
    url: str


class MediaHubResponse(BaseModel):
    kind: str
    viewer_tier: str
    total: int = 0
    public_count: int = 0
    member_count: int = 0
    paid_count: int = 0
    items: list[MediaItemSummary] = Field(default_factory=list)


class BillingPlan(BaseModel):
    plan_code: str
    name: str
    tier: str
    tier_label: str
    price_cents: int = 0
    currency: str = "CNY"
    billing_period: str = "month"
    billing_period_label: str = "month"
    headline: str | None = None
    description: str | None = None
    features: list[str] = Field(default_factory=list)
    is_public: bool = True
    is_enabled: bool = False
    checkout_available: bool = False
    sort_order: int = 0


class BillingPlansResponse(BaseModel):
    payments_enabled: bool = False
    payment_provider: str = "mock"
    items: list[BillingPlan] = Field(default_factory=list)


class BillingCheckoutIntentRequest(BaseModel):
    plan_code: str
    success_url: str | None = None
    cancel_url: str | None = None


class BillingCheckoutIntentResponse(BaseModel):
    intent_id: int
    order_id: int
    plan_code: str
    status: str
    payment_provider: str
    payments_enabled: bool = False
    checkout_url: str | None = None
    message: str


class BillingOrderSummary(BaseModel):
    id: int
    user_id: str | None = None
    email: str | None = None
    plan_code: str
    plan_name: str | None = None
    amount_cents: int = 0
    currency: str = "CNY"
    status: str
    payment_provider: str
    created_at: str
    updated_at: str


class BillingSubscriptionSummary(BaseModel):
    id: int
    user_id: str
    email: str | None = None
    plan_code: str
    plan_name: str | None = None
    tier: str
    tier_label: str
    status: str
    started_at: str
    expires_at: str | None = None
    auto_renew: bool = False
    payment_provider: str
    updated_at: str


class BillingMeResponse(BaseModel):
    payments_enabled: bool = False
    payment_provider: str = "mock"
    membership: MembershipProfile | None = None
    active_subscription: BillingSubscriptionSummary | None = None
    recent_orders: list[BillingOrderSummary] = Field(default_factory=list)


class BillingOrdersResponse(BaseModel):
    items: list[BillingOrderSummary] = Field(default_factory=list)
    total: int = 0


class AuthStatusResponse(BaseModel):
    enabled: bool = False
    authenticated: bool = False
    user: UserIdentity | None = None
    auth_mode: str = "password"
    membership: MembershipProfile | None = None
    business_profile: BusinessUserProfile | None = None
    role_home_path: str = "/"


class AuthPasswordLoginRequest(BaseModel):
    email: str
    password: str


class AuthLoginResponse(BaseModel):
    authenticated: bool = True
    auth_mode: str = "password"
    user: UserIdentity
    membership: MembershipProfile | None = None
    business_profile: BusinessUserProfile | None = None
    role_home_path: str = "/"


class ReactionRequest(BaseModel):
    reaction_type: str
    active: bool = True


class FollowItem(BaseModel):
    entity_type: str
    entity_slug: str
    entity_label: str
    created_at: str


class FollowRequest(BaseModel):
    entity_type: str
    entity_slug: str
    active: bool = True


class FollowListResponse(BaseModel):
    items: list[FollowItem] = Field(default_factory=list)
    total: int = 0


class FollowToggleResponse(BaseModel):
    active: bool = False
    item: FollowItem | None = None


class UserLibraryResponse(BaseModel):
    bookmarks: list[ArticleCard] = Field(default_factory=list)
    likes: list[ArticleCard] = Field(default_factory=list)
    recent_views: list[ArticleCard] = Field(default_factory=list)


class UserDashboardResponse(BaseModel):
    business_profile: BusinessUserProfile
    membership: MembershipProfile
    asset_summary: UserAssetSummary
    quick_links: list[QuickLinkItem] = Field(default_factory=list)
    welcome_title: str
    welcome_description: str


class WatchlistArticle(ArticleCard):
    matched_entities: list[str] = Field(default_factory=list)


class WatchlistResponse(BaseModel):
    follows: list[FollowItem] = Field(default_factory=list)
    items: list[WatchlistArticle] = Field(default_factory=list)
    total: int = 0


class AnalyticsSeriesPoint(BaseModel):
    label: str
    value: int


class AnalyticsMetric(BaseModel):
    label: str
    value: str
    detail: str


class AnalyticsOverviewResponse(BaseModel):
    metrics: list[AnalyticsMetric] = Field(default_factory=list)
    views_trend: list[AnalyticsSeriesPoint] = Field(default_factory=list)
    top_viewed: list[ArticleCard] = Field(default_factory=list)
    top_liked: list[ArticleCard] = Field(default_factory=list)
    top_bookmarked: list[ArticleCard] = Field(default_factory=list)


class AdminAuditLogItem(BaseModel):
    id: int
    target_user_id: str
    actor_user_id: str | None = None
    actor_email: str | None = None
    previous_tier: str | None = None
    next_tier: str
    previous_status: str | None = None
    next_status: str
    note: str | None = None
    created_at: str


class AdminOverviewResponse(BaseModel):
    metrics: list[AnalyticsMetric] = Field(default_factory=list)
    role_counts: list[MembershipTierCount] = Field(default_factory=list)
    recent_users: list[BusinessUserProfile] = Field(default_factory=list)
    recent_audits: list[AdminAuditLogItem] = Field(default_factory=list)


class EditorialTagSuggestion(BaseModel):
    name: str
    slug: str
    category: str
    color: str | None = None
    confidence: float = 0.0


class EditorialWorkflowCount(BaseModel):
    workflow_status: str
    workflow_label: str
    total: int = 0


class EditorialArticleBase(BaseModel):
    title: str
    subtitle: str | None = None
    author: str | None = None
    organization: str | None = None
    publish_date: str | None = None
    source_url: str | None = None
    cover_image_url: str | None = None
    primary_column_slug: str | None = None
    article_type: str | None = None
    main_topic: str | None = None
    access_level: str = "public"
    source_markdown: str | None = None
    layout_mode: str = "auto"
    formatting_notes: str | None = None
    content_markdown: str


class EditorialArticleCreate(EditorialArticleBase):
    slug: str | None = None


class EditorialArticleUpdate(BaseModel):
    slug: str | None = None
    title: str | None = None
    subtitle: str | None = None
    author: str | None = None
    organization: str | None = None
    publish_date: str | None = None
    source_url: str | None = None
    cover_image_url: str | None = None
    primary_column_slug: str | None = None
    article_type: str | None = None
    main_topic: str | None = None
    access_level: str | None = None
    source_markdown: str | None = None
    layout_mode: str | None = None
    formatting_notes: str | None = None
    content_markdown: str | None = None


class EditorialWorkflowRequest(BaseModel):
    action: str
    review_note: str | None = None
    scheduled_publish_at: str | None = None


class EditorialAiImportRequest(BaseModel):
    editorial_id: int | None = None


class EditorialAutoFormatRequest(BaseModel):
    source_markdown: str | None = None
    layout_mode: str | None = None
    formatting_notes: str | None = None


class EditorialArticleSummary(BaseModel):
    id: int
    article_id: int | None = None
    source_article_id: int | None = None
    slug: str
    title: str
    author: str | None = None
    publish_date: str
    status: str
    excerpt: str | None = None
    updated_at: str
    primary_column_slug: str | None = None
    article_type: str | None = None
    main_topic: str | None = None
    access_level: str = "public"
    workflow_status: str = "draft"
    workflow_label: str = "draft"
    review_note: str | None = None
    scheduled_publish_at: str | None = None
    submitted_at: str | None = None
    approved_at: str | None = None
    ai_synced_at: str | None = None
    access_label: str = "公开"
    layout_mode: str = "auto"
    formatting_notes: str | None = None
    formatter_model: str | None = None
    last_formatted_at: str | None = None
    tags: list[EditorialTagSuggestion] = Field(default_factory=list)


class EditorialArticleDetail(EditorialArticleSummary):
    subtitle: str | None = None
    organization: str | None = None
    source_url: str | None = None
    cover_image_url: str | None = None
    source_markdown: str = ""
    content_markdown: str
    plain_text_content: str
    html_web: str | None = None
    html_wechat: str | None = None
    created_at: str
    published_at: str | None = None
    source_article_ai: EditorialAiOutputDetail | None = None


class EditorialHtmlResponse(BaseModel):
    article_id: int
    html_web: str
    html_wechat: str
    summary: str


class EditorialPublishResponse(BaseModel):
    editorial_id: int
    article_id: int
    status: str
    article_url: str
    updated_at: str


class EditorialUploadResponse(BaseModel):
    filename: str
    article: EditorialArticleDetail


class EditorialDashboardResponse(BaseModel):
    draft_count: int = 0
    published_count: int = 0
    pending_review_count: int = 0
    approved_count: int = 0
    scheduled_count: int = 0
    latest_published_at: str | None = None
    latest_article_id: int | None = None
    export_ready_count: int = 0
    workflow_counts: list[EditorialWorkflowCount] = Field(default_factory=list)
    recent_items: list[EditorialArticleSummary] = Field(default_factory=list)
