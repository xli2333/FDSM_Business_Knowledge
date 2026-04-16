from langchain_core.prompts import PromptTemplate

from backend.services import ai_service


def test_normalize_editorial_summary_output_keeps_hybrid_structure():
    raw = (
        "以下是针对该社会现象的商业知识简报：\n\n"
        "朋友圈 SBTI 爆火：解构上头下沉的社交自救\n\n"
        "SBTI 在微信朋友圈快速传播，年轻人借助标签化测试重新组织低门槛社交，也把它当作情绪出口与身份识别工具。"
        "熟人网络的背书降低了参与门槛，让这类内容在短时间内跨越圈层扩散，并持续激活围绕人格标签的互动冲动。\n"
        "- **现象层面：** 这种测试把复杂人格压缩成便于传播的标签，既方便自我表达，也方便发起对话和建立连接，天然适合在熟人网络里滚动扩散。\n"
        "- **机制层面：** 它同时满足自我识别、社交破冰和情绪投射三重需求，因此比单纯的娱乐测试更容易形成持续传播，还能不断制造新的参与话题。\n"
        "- **影响层面：** 热度背后反映出关系建立越来越依赖可复制的话术模板，个体也更倾向通过轻量标签寻找安全感与归属感。\n"
        "- **商业判断：** 对内容平台和消费品牌而言，围绕人格标签、情绪认同和低成本互动设计产品，更容易获得分享、停留与转化。\n"
    )

    summary = ai_service.normalize_editorial_summary_output(raw)

    assert "以下是" not in summary
    assert "简报" not in summary
    assert "朋友圈 SBTI 爆火" not in summary
    assert ai_service.editorial_summary_visible_length(summary) >= 200
    assert "**" in summary
    assert "- **" in summary
    assert summary.count("- **") >= 3
    assert summary.count("\n\n") >= 1
    assert not summary.lstrip().startswith("- ")


def test_summarize_article_payload_uses_full_article_summary_contract(monkeypatch):
    captured: dict[str, str] = {}

    def fake_invoke(template: str, payload: dict[str, str], *, llm=None) -> str:
        del llm
        captured["template"] = template
        captured["content"] = payload["content"]
        return (
            "以下是这篇文章的摘要：\n\n"
            "SBTI 在微信朋友圈快速扩散，年轻人把它当作身份识别、社交破冰和情绪表达的轻量入口，"
            "也借此完成一轮低成本的群体性社交自救。它的流行不是单纯跟风，而是说明熟人背书与标签叙事正在重塑社交协作的最低成本结构。\n"
            "- **现象层面：** 熟人关系链降低了传播门槛，让标签化表达更容易跨圈层扩散，也让参与者更愿意公开转发与对号入座。\n"
            "- **机制层面：** 这类测试同时提供自我识别、互动脚本和情绪投射，因此比普通娱乐内容更容易形成连续讨论。\n"
            "- **影响层面：** 关系建立正在进一步依赖可复制的话术模板与轻量身份确认，内容平台和品牌都可能围绕这套机制设计增长动作。\n"
            "总结来看，这篇文章真正关心的是熟人社交里的低成本连接方式如何被重新标准化，并进一步影响内容传播和互动设计。"
        )

    monkeypatch.setattr(ai_service, "is_ai_enabled", lambda: True)
    monkeypatch.setattr(ai_service, "_invoke_prompt", fake_invoke)

    payload = ai_service.summarize_article_payload(
        "朋友圈 SBTI 爆火",
        (
            "第一段。SBTI 在微信朋友圈快速扩散，年轻人把它当作情绪表达与身份识别的入口。"
            "第二段。熟人背书降低了参与门槛，标签叙事也让传播更容易跨圈层。"
            "第三段。它同时承担社交破冰、自我识别和情绪投射功能。"
            "第四段。内容平台与品牌都可能借此设计互动机制和转化链路。"
        ),
    )

    assert "roughly 320 to 1200 Chinese characters" in captured["template"]
    assert "3 to 5 Markdown bullet points" in captured["template"]
    assert "do not let the entire answer become only a bullet list" in captured["template"]
    assert "End with one short closing paragraph" in captured["template"]
    assert "visibly emphasized with Markdown bold" in captured["template"]
    assert payload["model"] == ai_service.GEMINI_CHAT_MODEL
    assert "以下是" not in payload["summary"]
    assert ai_service.editorial_summary_visible_length(payload["summary"]) >= 200
    assert "**" in payload["summary"]
    assert "- **" in payload["summary"]
    assert payload["summary"].count("- **") >= 3
    assert "总结来看" in payload["summary"]
    assert not payload["summary"].lstrip().startswith("- ")


def test_normalize_editorial_summary_output_does_not_script_truncate_bullet_body():
    raw = (
        "这篇文章讨论算力资产折旧、芯片迭代速度和云厂商估值逻辑之间的重新定价关系，"
        "核心不是单一会计参数，而是 AI 基础设施从训练周期转向应用周期后，资产回收节奏与财务叙事如何同步重写。\n\n"
        "- 现象层面：折旧年限的回调不只是利润表修饰失灵，更意味着旧一代 GPU 在推理时代仍有残余价值。"
        "但这种价值需要建立在更细颗粒度的利用率管理和客户结构优化之上，不能再被简单打包成线性摊销神话。\n"
        "- 机制层面：当模型性能提升越来越依赖系统工程、数据效率和服务编排时，A100 这类旧卡不会立刻归零。"
        "它们仍可能在批量推理、轻量微调和企业私有化部署里维持很高的边际贡献，这部分长尾价值必须被完整讨论。\n"
        "- 影响层面：如果管理层继续用过长折旧年限掩盖技术代际风险，资本市场会把会计平滑理解成价值透支。"
        "但如果折旧回调过猛，又会直接暴露资产负债表里被延后的压力。\n"
    )

    summary = ai_service.normalize_editorial_summary_output(raw)

    assert "这部分长尾价值必须被完整讨论" in summary
    assert "但如果折旧回调过猛，又会直接暴露资产负债表里被延后的压力" in summary


def test_normalize_editorial_summary_output_preserves_closing_paragraph_after_bullets():
    raw = (
        "这篇文章讨论 AI 服务器折旧年限变化如何从财务技术细节演变成资本市场重新定价的触发器。\n\n"
        "- 现象层面：Amazon 缩短折旧年限，直接打破行业对算力资产账面处理的旧默契。\n"
        "- 机制层面：训练时代的线性摊销逻辑，正在被推理时代的长尾利用率逻辑替代。\n"
        "- 影响层面：市场不再只看收入增长，也会追问资产负债表里的技术折旧是否真实。\n\n"
        "总结来看，这篇文章真正要说明的不是一次会计调整本身，而是 AI 基础设施企业以后必须同时对技术生命周期和财务叙事负责。"
    )

    summary = ai_service.normalize_editorial_summary_output(raw)

    assert "总结来看" in summary
    assert "AI 基础设施企业以后必须同时对技术生命周期和财务叙事负责" in summary
    assert summary.count("- **") >= 3


def test_translate_article_to_english_prompt_escapes_json_braces(monkeypatch):
    captured: dict[str, str] = {}

    def fake_invoke(template: str, payload: dict[str, str], *, llm=None) -> str:
        del llm
        captured["template"] = template
        captured["rendered"] = PromptTemplate.from_template(template).format(**payload)
        return (
            '{'
            '"title":"GPU Finance EN",'
            '"excerpt":"English deck",'
            '"summary":"English summary",'
            '"content":"English content"'
            '}'
        )

    monkeypatch.setattr(ai_service, "get_flash_llm", lambda: object())
    monkeypatch.setattr(ai_service, "_invoke_prompt", fake_invoke)

    payload = ai_service.translate_article_to_english(
        "算力账本的悖论",
        "折旧年限变化正在重写 AI 财务判断。",
        "# 算力账本\n\n正文内容",
    )

    assert payload["title"] == "GPU Finance EN"
    assert PromptTemplate.from_template(captured["template"]).input_variables == ["content", "excerpt", "title"]
    assert '"title": "English title"' in captured["rendered"]
    assert '"content": "Full translated content in Markdown"' in captured["rendered"]


def test_translate_editorial_assets_to_english_prompt_escapes_json_braces(monkeypatch):
    captured: dict[str, str] = {}

    def fake_invoke(template: str, payload: dict[str, str], *, llm=None) -> str:
        del llm
        captured["template"] = template
        captured["rendered"] = PromptTemplate.from_template(template).format(**payload)
        return (
            '{'
            '"title":"GPU Editorial EN",'
            '"excerpt":"English editorial deck",'
            '"summary":"English summary markdown",'
            '"content":"# GPU Editorial EN\\n\\nEnglish body markdown"'
            '}'
        )

    monkeypatch.setattr(ai_service, "get_flash_llm", lambda: object())
    monkeypatch.setattr(ai_service, "_invoke_prompt", fake_invoke)

    payload = ai_service.translate_editorial_assets_to_english(
        "算力账本的悖论",
        "折旧年限变化正在重写 AI 财务判断。",
        "- **现象层面：** 摘要内容",
        "# 算力账本\n\n## 正文\n\n正文内容",
    )

    assert payload["title"] == "GPU Editorial EN"
    assert PromptTemplate.from_template(captured["template"]).input_variables == [
        "content_markdown",
        "excerpt",
        "summary_markdown",
        "title",
    ]
    assert '"title": "English title"' in captured["rendered"]
    assert '"content": "Full English markdown body translated from the Chinese body"' in captured["rendered"]
