from backend.services.article_visibility_service import is_hidden_low_value_article


def test_placeholder_only_article_is_hidden():
    article = {
        "title": "封面专题",
        "content": "此页面触发全局图片搜索模式，共找到 1 张图片。",
    }

    assert is_hidden_low_value_article(article)


def test_real_article_is_not_hidden():
    article = {
        "title": "正常文章",
        "content": "文\n作者\n这里有真实正文，而不是图片占位提示。",
    }

    assert not is_hidden_low_value_article(article)


def test_short_promotional_article_is_hidden():
    article = {
        "title": "假期补完计划丨年度书单互动赠礼",
        "content": (
            "春节将近\n"
            "别着急划走，文末还有惊喜赠礼掉落哦！\n"
            "留\n言\n赠\n礼\n"
            "快来评论区留言分享你的书单吧！\n"
            "点赞数前两名可获亲笔签名版。\n"
            "本次活动有效期截至 2024 年 2 月 18 日。\n"
            "扫码订阅杂志\n"
            "全年四期优惠征订\n"
            "关注公众号｜复旦商业知识\n"
            "转载｜请后台留言\n"
        ),
    }

    assert is_hidden_low_value_article(article)


def test_long_event_article_is_not_hidden():
    article = {
        "title": "出海：真问题与解决方案丨论坛报名",
        "content": (
            "中国企业出海这一话题的热度已无需多加赘述，许多前人的成功经验被反复拆解分析，"
            "希望从中提取出适合中国企业的出海秘籍。为了回答这些问题，《管理视野》新一期杂志"
            "以“出海：真问题与解决方案”为封面专题，并由此衍生出此次论坛活动。"
            "我们将邀请复旦大学管理学院和国际问题研究院的学者、企业家代表共同深入探讨企业出海的共性问题。"
            "论坛议程包括市场选择、品牌出海、人才管理与现场互动提问等多个环节，"
            "并会结合墨西哥、中东与东南亚等不同市场的真实案例展开讨论。"
            "现场还将安排圆桌讨论，围绕品牌出海、组织协同、人才管理和本地化运营进行拆解。"
            "我们希望给出的不是标准答案，而是一份可供企业家与管理者参考的思考框架。"
            "主办方还会邀请已经完成品牌出海和组织出海的企业管理者分享复盘，"
            "包括如何搭建海外团队、如何处理供应链与本地化之间的张力、如何根据不同市场调整品牌与渠道策略。"
            "这部分内容会结合多个国家市场的真实案例展开，帮助参会者理解问题结构，而不是只给出碎片化经验。"
            "除了主题演讲和圆桌讨论，现场还会设置问答环节，围绕品牌、组织与市场进入节奏进行深入交流。"
            "活动信息：2024 年 11 月 14 日，复旦大学管理学院政立院区。"
            "扫码报名或点击阅读原文。扫码订阅杂志，全年四期优惠征订，关注公众号。"
        ),
    }

    assert not is_hidden_low_value_article(article)
