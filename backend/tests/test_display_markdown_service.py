from backend.services.display_markdown_service import normalize_article_display_markdown


def test_periodical_article_lines_become_real_paragraphs_and_drop_qr_noise():
    raw = (
        "第42期\n"
        "《管理视野》\n"
        "卷首语正文第一段。\n"
        "卷首语正文第二段。\n"
        "扫描图片二维码订阅新刊\n"
        "趋势\n"
        "Trend\n"
        "01\n"
        "做个会提供情绪价值的领导\n"
        "文 | 胡佳\n"
        "导读：\n"
        "今天的管理者不仅要处理复杂多变的业务问题。\n"
    )

    normalized = normalize_article_display_markdown(raw, "zh")

    assert "扫描图片二维码订阅新刊" not in normalized
    assert "卷首语正文第一段。\n\n卷首语正文第二段。" in normalized
    assert "### 趋势" in normalized
    assert "### Trend" in normalized
    assert "### 1. 做个会提供情绪价值的领导" in normalized
    assert "文 | 胡佳" in normalized
    assert "**导读：**" in normalized


def test_multiline_attribution_stays_metadata_instead_of_headings():
    raw = (
        "02\n"
        "不完美创业者更受投资人青睐吗？\n"
        "原作者：Lauren C. Howe\n"
        "Jochen I. Menges\n"
        "改写者：刘知\n"
        "导读：\n"
        "创业者展现出不同类型的短板会带来截然不同的反应。\n"
    )

    normalized = normalize_article_display_markdown(raw, "zh")

    assert "### 2. 不完美创业者更受投资人青睐吗？" in normalized
    assert "原作者：Lauren C. Howe Jochen I. Menges" in normalized
    assert "### Jochen I. Menges" not in normalized
    assert "### 改写者：刘知" not in normalized


def test_short_titles_after_headings_are_promoted_but_year_lines_are_not():
    raw = (
        "对谈\n"
        "Executive Perspectives\n"
        "呈现企业家思想的源头和流变\n"
        "2025年1月于美国西雅图\n"
        "正文段落。\n"
    )

    normalized = normalize_article_display_markdown(raw, "zh")

    assert "### 对谈" in normalized
    assert "### Executive Perspectives" in normalized
    assert "### 呈现企业家思想的源头和流变" in normalized
    assert "### 2025年1月于美国西雅图" not in normalized
    assert "2025年1月于美国西雅图\n\n正文段落。" in normalized


def test_qa_and_part_lines_become_headings():
    raw = (
        "教师与企业家部分互动内容\n"
        "Part 1 道客的商业模式\n"
        "Q1 道客最早的切入点是什么？\n"
        "A by 陈齐彦：我们先从开发者社区切入。\n"
    )

    normalized = normalize_article_display_markdown(raw, "zh")

    assert "### 教师与企业家部分互动内容" in normalized
    assert "### Part 1 道客的商业模式" in normalized
    assert "### Q1 道客最早的切入点是什么？" in normalized
    assert "**A by 陈齐彦：我们先从开发者社区切入。**" in normalized


def test_combined_head_noise_and_inline_numbered_title_are_split_cleanly():
    raw = (
        "往期精彩文章 请访问 管理视野 小程序\n"
        "01 识别周期，找准位置 马克·吐温说历史不会重演。\n"
    )

    normalized = normalize_article_display_markdown(raw, "zh")

    assert "往期精彩文章" not in normalized
    assert "### 1. 识别周期，找准位置" in normalized
    assert "马克·吐温说历史不会重演。" in normalized


def test_short_standalone_quotes_become_blockquotes():
    raw = (
        "她说：\n"
        "“不管是否跨界，很重要的一点是要快。”\n"
    )

    normalized = normalize_article_display_markdown(raw, "zh")

    assert "> “不管是否跨界，很重要的一点是要快。”" in normalized
