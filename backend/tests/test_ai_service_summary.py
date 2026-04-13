from backend.services import ai_service


def test_normalize_editorial_summary_output_keeps_hybrid_structure():
    raw = (
        "以下是针对该社会现象的商业知识简报：\n\n"
        "朋友区 SBTI 爆火：解构上头下沉的社交救赎\n\n"
        "SBTI 在微信朋友区快速传播，年轻人借助标签化测试重新组织低门槛社交，也把它当作情绪出口与身份识别工具。"
        "熟人网络的背书降低了参与门槛，让这类内容在短时间内跨越圈层扩散，并持续激活围绕人格标签的互动冲动。\n"
        "- **现象层面：** 这种测试把复杂人格压缩成便于传播的标签，既方便自我表达，也方便发起对话和建立连接，天然适合在熟人网络里滚动扩散。\n"
        "- **机制层面：** 它同时满足自我识别、社交破冰和情绪投射三重需求，因此比单纯的娱乐测试更容易形成持续传播，还能不断制造新的参与话题。\n"
        "- **影响层面：** 热度背后反映出关系建立越来越依赖可复制的话术模板，个体也更倾向通过轻量标签寻找安全感与归属感。\n"
        "- **商业判断：** 对内容平台和消费品牌而言，围绕人格标签、情绪认同和低成本互动设计产品，更容易获得分享、停留与转化。\n"
    )

    summary = ai_service.normalize_editorial_summary_output(raw)

    assert "以下是" not in summary
    assert "简报" not in summary
    assert "朋友区 SBTI 爆火" not in summary
    assert 200 <= ai_service.editorial_summary_visible_length(summary) <= ai_service.EDITORIAL_SUMMARY_MAX_CHARS
    assert "**" in summary
    assert "- **" in summary
    assert summary.count("- **") >= 3
    assert summary.count("\n\n") >= 1
    assert not summary.lstrip().startswith("- ")


def test_summarize_article_payload_uses_hybrid_summary_contract(monkeypatch):
    captured: dict[str, str] = {}

    def fake_invoke(template: str, payload: dict[str, str], *, llm=None) -> str:
        del llm
        captured["template"] = template
        captured["content"] = payload["content"]
        return (
            "以下是这篇文章的摘要：\n\n"
            "SBTI 在微信朋友区快速扩散，年轻人把它当作身份识别、社交破冰和情绪表达的轻量入口，也借此完成一轮低成本的群体性社交自救。"
            "它的流行不是单纯跟风，而是说明熟人背书与标签叙事正在重新塑造社交协作的最低成本结构。\n"
            "- **现象层面：** 熟人关系链降低了传播门槛，让标签化表达更容易跨圈层扩散，也让参与者更愿意公开转发与对号入座。\n"
            "- **机制层面：** 这类测试同时提供自我识别、互动脚本和情绪投射，因此比普通娱乐内容更容易形成连续讨论。\n"
            "- **影响层面：** 关系建立正在进一步依赖可复制的话术模板与轻量身份确认，内容平台和品牌都可能围绕这套机制设计增长动作。\n"
        )

    monkeypatch.setattr(ai_service, "is_ai_enabled", lambda: True)
    monkeypatch.setattr(ai_service, "_invoke_prompt", fake_invoke)

    payload = ai_service.summarize_article_payload(
        "朋友区 SBTI 爆火",
        (
            "第一段。SBTI 在微信朋友区快速扩散，年轻人把它当作情绪表达与身份识别的入口。"
            "第二段。熟人背书降低了参与门槛，标签叙事也让传播更容易跨圈层。"
            "第三段。它同时承担社交破冰、自我识别和情绪投射功能。"
            "第四段。内容平台与品牌都可能借此设计互动机制和转化链路。"
        ),
    )

    assert "between 200 and 500 Chinese characters" in captured["template"]
    assert "3 or 4 Markdown bullet points" in captured["template"]
    assert "Do not let the entire answer become only a bullet list" in captured["template"]
    assert "visibly emphasized with Markdown bold" in captured["template"]
    assert payload["model"] == ai_service.GEMINI_CHAT_MODEL
    assert "以下是" not in payload["summary"]
    assert 200 <= ai_service.editorial_summary_visible_length(payload["summary"]) <= ai_service.EDITORIAL_SUMMARY_MAX_CHARS
    assert "**" in payload["summary"]
    assert "- **" in payload["summary"]
    assert payload["summary"].count("- **") >= 3
    assert not payload["summary"].lstrip().startswith("- ")
