from __future__ import annotations

import unittest

from backend.services.clustering_rules import derive_column_slugs
from backend.services.topic_engine import cluster_match_score


class ClusteringRulesTest(unittest.TestCase):
    def test_industry_column_requires_real_industry_signal(self) -> None:
        columns = derive_column_slugs(
            word_count=1800,
            article_type="研究/论文解读",
            series_or_column=None,
            tag_entries=[
                ("AI/人工智能", "topic", 0.92),
                ("人机协同", "topic", 0.81),
            ],
            fdsm_hits=[],
        )
        self.assertNotIn("industry", columns)
        self.assertIn("research", columns)

    def test_deans_view_is_not_triggered_by_org_name_alone(self) -> None:
        columns = derive_column_slugs(
            word_count=1500,
            article_type="活动/预告",
            series_or_column=None,
            tag_entries=[("案例教学", "topic", 0.84)],
            fdsm_hits=[],
        )
        self.assertNotIn("deans-view", columns)

    def test_deans_view_requires_specific_fdsm_role_signal(self) -> None:
        columns = derive_column_slugs(
            word_count=2100,
            article_type="评论/观点",
            series_or_column=None,
            tag_entries=[("领导力", "topic", 0.86)],
            fdsm_hits=["教授"],
        )
        self.assertIn("deans-view", columns)
        self.assertIn("insights", columns)

    def test_cluster_recipe_requires_all_required_tags(self) -> None:
        cluster = {
            "required_tags": ["金融投资", "资本市场"],
            "support_tags": ["公司治理"],
        }
        score, required_hits = cluster_match_score({"金融投资", "公司治理"}, cluster)
        self.assertEqual(score, 0)
        self.assertEqual(required_hits, 1)

        score, required_hits = cluster_match_score({"金融投资", "资本市场", "公司治理"}, cluster)
        self.assertGreaterEqual(score, 8)
        self.assertEqual(required_hits, 2)


if __name__ == "__main__":
    unittest.main()
