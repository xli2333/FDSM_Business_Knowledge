from __future__ import annotations

import unittest

from backend.config import TOPIC_SEEDS
from backend.services.tag_engine import _derive_tag_entries
from backend.services.taxonomy_service import build_tag_entries
from backend.services.topic_engine import topic_match_score


class TaxonomyRulesTest(unittest.TestCase):
    def test_generic_org_language_does_not_force_org_management(self) -> None:
        entries = build_tag_entries(
            title="AI赋能的人力资源管理",
            main_topic="AI在人力资源管理中的应用现状与挑战",
            excerpt="文章讨论人工智能在HR流程中的效率提升。",
            content="围绕招聘、绩效与培训等环节展开。",
            article_type="研究/论文解读",
            raw_keywords=["人工智能", "人力资源管理"],
        )
        names = {name for name, category, _ in entries if category in {"topic", "industry"}}
        self.assertIn("AI/人工智能", names)
        self.assertNotIn("组织管理", names)

    def test_low_priority_ai_keywords_do_not_drag_article_into_family_business(self) -> None:
        row = {
            "title": "线索征集丨你是对“潮流”说“不”的人吗？",
            "main_topic": "征集对“潮流”说“不”的个体故事",
            "excerpt": "征集消费、工作和技术选择上的反潮流经历。",
            "content": "文章主要讨论消费主义、数字技术与个体选择。",
            "article_type": "活动/预告",
            "series_or_column": None,
            "people_text": "",
            "org_text": "",
        }
        ai_row = {
            "model_output": {
                "topic_keywords": [
                    "液态现代性",
                    "脱嵌",
                    "可持续消费",
                    "数字游民",
                    "AI伦理",
                    "逆城市化",
                    "家族企业传承",
                ]
            }
        }
        entries = _derive_tag_entries(row, {}, ai_row=ai_row)
        names = {name for name, category, _ in entries if category in {"topic", "industry"}}
        self.assertIn("AI/人工智能", names)
        self.assertNotIn("家族企业", names)
        self.assertNotIn("家族企业传承", names)

    def test_family_business_topic_requires_primary_family_signal(self) -> None:
        seed = next(item for item in TOPIC_SEEDS if item["slug"] == "family-business")
        score, primary_hits = topic_match_score({"组织管理", "领导力"}, seed)
        self.assertEqual(score, 0)
        self.assertEqual(primary_hits, 0)

    def test_globalization_topic_is_not_triggered_by_capital_market_alone(self) -> None:
        seed = next(item for item in TOPIC_SEEDS if item["slug"] == "globalization-outbound")
        score, primary_hits = topic_match_score({"资本市场", "供应链"}, seed)
        self.assertEqual(primary_hits, 0)
        self.assertLess(score, 3)


if __name__ == "__main__":
    unittest.main()
