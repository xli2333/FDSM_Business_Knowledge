from backend.services.article_relayout_service import (
    cleanup_source_tail,
    looks_like_promotional_block,
    normalize_markdown_output,
    parse_json_payload,
    relayout_is_close_enough,
    summary_needs_regeneration,
)


def test_cleanup_source_tail_preserves_meta_and_removes_promotional_tail():
    source = (
        "导读：这是一段导读。\n\n"
        "正文第一段。\n\n"
        "正文第二段。\n\n"
        "来源：复旦商业知识\n\n"
        "扫码订阅并转发，欢迎报名下一场直播。"
    )

    cleaned = cleanup_source_tail(source, "zh")

    assert "导读：这是一段导读。" in cleaned
    assert "来源：复旦商业知识" in cleaned
    assert "扫码订阅" not in cleaned
    assert "欢迎报名" not in cleaned


def test_normalize_markdown_output_removes_h1_and_placeholder_blocks():
    source = (
        "# 文章标题\n\n"
        "导读：这是一段导读。\n\n"
        "此页面触发全局图片搜索模式\n\n"
        "共找到 12 张图片\n\n"
        "## 小节\n\n"
        "这里是正文。"
    )

    normalized = normalize_markdown_output(source, "zh", remove_h1=True)

    assert not normalized.startswith("# ")
    assert "导读：这是一段导读。" in normalized
    assert "此页面触发全局图片搜索模式" not in normalized
    assert "共找到 12 张图片" not in normalized
    assert "## 小节" in normalized
    assert "这里是正文。" in normalized


def test_long_body_with_generic_promo_words_is_not_misclassified_as_ad():
    fragment = (
        "在组织传播研究中，转发行为与信息扩散机制密切相关，平台订阅关系和二维码扫码路径也会影响内容触达效率。"
        "本文讨论的是这些行为在数字协同中的管理含义，而不是引导读者参与任何站外活动。"
        "为了说明员工分享、转发与订阅偏好的差异，研究进一步比较了不同部门在知识传播中的协作方式。"
        "研究者进一步结合问卷与访谈数据，分析知识节点、协作密度、内容再利用率与部门信任水平之间的关系，"
        "并讨论平台机制如何影响组织内部的学习路径、反馈速度、授权方式以及跨团队的信息再加工流程。"
    )
    block = fragment * 6

    assert not looks_like_promotional_block(block, "zh")
    normalized = normalize_markdown_output(block, "zh", remove_h1=True)
    assert "转发行为" in normalized
    assert "订阅关系" in normalized


def test_summary_needs_regeneration_detects_placeholder_and_accepts_real_summary():
    assert summary_needs_regeneration("重要提示：请补充完整正文后再生成摘要。")
    assert summary_needs_regeneration("-\n\n-")
    assert not summary_needs_regeneration("## 核心观点\n\n企业需要在增长与效率之间重新分配资源。")


def test_parse_json_payload_recovers_jsonish_summary_and_content():
    raw = (
        '{\n'
        '"summary": "## 要点\n\n第一条",\n'
        '"content": "第一段\n\n第二段"\n'
        '}\n'
        'trailing explanation should be ignored'
    )

    payload = parse_json_payload(raw)

    assert payload["summary"].startswith("## 要点")
    assert "第一段" in payload["content"]


def test_relayout_similarity_blocks_unrelated_rewrite():
    source = (
        "## 第一部分\n\n"
        "企业需要根据现金流与市场节奏调整扩张速度，同时在供应链、市场投放和组织扩张之间保持顺序。"
        "如果收入质量下降，管理层应优先修复客户结构与产品组合，而不是继续追求表面增长。"
        "在经营不确定性上升时，还需要重新评估预算节奏、渠道效率、产品定价、团队配置和客户留存策略，"
        "避免用短期补贴掩盖结构性问题，并通过更清晰的决策机制约束盲目扩张。"
    )
    close_candidate = (
        "## 第一部分\n\n"
        "企业需要根据现金流与市场节奏调整扩张速度，同时在供应链、市场投放和组织扩张之间保持顺序。"
        "如果收入质量下降，管理层应优先修复客户结构与产品组合，并控制投入节奏。"
        "在经营不确定性上升时，还需要重新评估预算节奏、渠道效率、产品定价、团队配置和客户留存策略，"
        "避免用短期补贴掩盖结构性问题，并通过更清晰的决策机制约束盲目扩张。"
    )
    drifted_candidate = "## Completely Different\n\nThis article is about travel photos and weekend coffee."

    assert relayout_is_close_enough(source, close_candidate, "zh")
    assert not relayout_is_close_enough(source, drifted_candidate, "zh")
