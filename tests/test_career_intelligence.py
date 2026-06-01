from __future__ import annotations

import unittest

from modules.career_intelligence import (
    build_career_coaching,
    build_market_intelligence,
    recommend_target_companies,
)


class CareerIntelligenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.resume = {
            "summary": "Senior AI platform engineer building LLM systems and infrastructure.",
            "skills": ["Python", "OpenAI", "RAG", "Kubernetes", "Terraform", "Observability"],
            "leadership": ["Led roadmap alignment for a platform migration."],
            "impact_metrics": ["Reduced cloud spend by 30%."],
            "target_roles": ["AI Engineer", "Platform Engineer"],
        }

    def test_career_coaching_returns_positioning_and_actions(self) -> None:
        coaching = build_career_coaching(
            [self.resume],
            [{"status": "Applied", "match_score": 84}, {"status": "Rejected", "match_score": 70}],
        )

        self.assertGreaterEqual(coaching["readiness_score"], 70)
        self.assertIn("AI", coaching["positioning"])
        self.assertTrue(coaching["next_actions"])
        self.assertEqual(coaching["recommended_roles"][0]["role"], "Platform Engineer")

    def test_company_targeting_prioritizes_ai_platform_companies(self) -> None:
        targets = recommend_target_companies(self.resume, preferred_role="AI Engineer", preferred_stage="AI lab / product")

        self.assertGreaterEqual(targets[0]["target_score"], targets[-1]["target_score"])
        self.assertIn(targets[0]["company"], {"OpenAI", "Anthropic"})
        self.assertTrue(targets[0]["matching_signals"])

    def test_market_intelligence_estimates_salary_and_trend_coverage(self) -> None:
        intelligence = build_market_intelligence(
            self.resume,
            role_family="AI Engineer",
            location="San Francisco Bay Area",
            seniority="Senior",
        )

        self.assertGreater(intelligence["salary_band"].mid, 185000)
        self.assertTrue(intelligence["trends"])
        self.assertIn("heuristic", intelligence["disclaimer"])


if __name__ == "__main__":
    unittest.main()
