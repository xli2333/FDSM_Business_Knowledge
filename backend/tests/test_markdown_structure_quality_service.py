from backend.services.markdown_structure_quality_service import (
    markdown_structure_needs_rerun,
    markdown_structure_quality_signals,
)


def test_periodical_source_without_headings_needs_rerun():
    source = (
        "第42期\n"
        "《管理视野》\n"
        "卷首语正文第一段。\n"
        "卷首语正文第二段。\n"
        "趋势\n"
        "Trend\n"
        "01\n"
        "做个会提供情绪价值的领导\n"
        "文 | 胡佳\n"
        "导读：\n"
        "今天的管理者不仅要处理复杂多变的业务问题。\n"
        "02\n"
        "谁正在被AI取代？\n"
        "在线自由职业平台的生存图鉴\n"
    )
    formatted = source
    summary = "这是一段普通摘要。"

    payload = markdown_structure_quality_signals(
        source_text=source,
        formatted_markdown=formatted,
        summary_text=summary,
    )

    assert payload["source_signal_count"] >= 8
    assert payload["markdown_structure_count"] == 0
    assert payload["leading_lines_match"] is True
    assert markdown_structure_needs_rerun(
        source_text=source,
        formatted_markdown=formatted,
        summary_text=summary,
    )


def test_well_structured_markdown_does_not_need_rerun():
    source = (
        "第42期\n《管理视野》\n趋势\nTrend\n01\n做个会提供情绪价值的领导\n导读：\n今天的管理者不仅要处理复杂多变的业务问题。\n"
    )
    formatted = (
        "## 第42期\n\n"
        "## 《管理视野》\n\n"
        "## 趋势\n\n"
        "## Trend\n\n"
        "## 1. 做个会提供情绪价值的领导\n\n"
        "**导读：**\n\n"
        "今天的管理者不仅要处理复杂多变的业务问题。"
    )
    summary = "一段简洁摘要。"

    assert not markdown_structure_needs_rerun(
        source_text=source,
        formatted_markdown=formatted,
        summary_text=summary,
    )


def test_bullet_heavy_summary_triggers_rerun():
    source = "普通正文第一段。\n普通正文第二段。"
    formatted = "普通正文第一段。\n\n普通正文第二段。"
    summary = "*   **自动化浪潮：** 摘要仍然是项目符号列表。"

    payload = markdown_structure_quality_signals(
        source_text=source,
        formatted_markdown=formatted,
        summary_text=summary,
    )

    assert payload["bullet_summary"] is True
    assert payload["needs_rerun"] is True


def test_dialogue_and_bold_subheads_count_as_visible_structure():
    source = (
        "陈晓萍：请谈谈你的管理思想。\n"
        "马云：我认为管理要回到文化和信仰。\n"
        "后来两人继续对谈，谈到人才培养和领导力。\n"
    )
    formatted = (
        "### 对谈\n\n"
        "**陈晓萍：** 请谈谈你的管理思想。\n\n"
        "**马云：** 我认为管理要回到文化和信仰。\n\n"
        "**领导力与文化根基**\n\n"
        "> 天下所有的老师都希望学生超过自己。\n"
    )
    summary = "一段简洁摘要。"

    payload = markdown_structure_quality_signals(
        source_text=source,
        formatted_markdown=formatted,
        summary_text=summary,
    )

    assert payload["markdown_structure_count"] >= 4
    assert payload["needs_rerun"] is False
