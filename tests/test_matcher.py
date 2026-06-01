from __future__ import annotations

import unittest

from modules.matcher import score_resume_for_job, token_semantic_similarity


class MatcherTests(unittest.TestCase):
    def test_scores_strong_ai_platform_match_with_breakdown(self) -> None:
        resume = {
            "summary": "Senior AI platform engineer focused on LLM systems and developer productivity.",
            "skills": ["Python", "OpenAI", "Kubernetes", "Terraform", "FastAPI"],
            "leadership": ["Led roadmap and stakeholder alignment for a platform team."],
            "impact_metrics": ["Reduced infrastructure cost by 30%."],
            "seniority_signals": ["Senior engineer", "Led architecture"],
            "target_roles": ["AI Engineer", "Platform Engineer"],
        }
        job = """
        Senior AI Platform Engineer needed for Python, OpenAI, LLM, Kubernetes, Terraform,
        roadmap ownership, stakeholder communication, and platform reliability.
        """

        result = score_resume_for_job(resume, job)

        self.assertGreaterEqual(result.match_score, 75)
        self.assertIn("python", result.matching_skills)
        self.assertIn("ai", result.matching_domains)
        self.assertGreaterEqual(result.score_breakdown.skills, 70)
        self.assertGreaterEqual(result.score_breakdown.seniority, 70)
        self.assertGreater(result.semantic_score, 0)
        self.assertEqual(result.semantic_method, "token_overlap")

    def test_scores_missing_high_priority_skills_as_gaps(self) -> None:
        resume = {
            "summary": "Backend engineer with Python and SQL experience.",
            "skills": ["Python", "SQL"],
            "leadership": [],
            "impact_metrics": [],
        }
        job = "Staff SRE role requiring Kubernetes, Terraform, AWS, observability, roadmap, and incident leadership."

        result = score_resume_for_job(resume, job)

        self.assertLess(result.match_score, 70)
        self.assertIn("kubernetes", result.missing_skills)
        self.assertTrue(result.resume_gaps)
        self.assertGreater(result.score_breakdown.gap_penalty, 0)

    def test_token_semantic_similarity_scores_related_text_higher(self) -> None:
        resume = "Python Kubernetes platform reliability automation observability"
        related_job = "Build Python Kubernetes platforms with strong observability"
        unrelated_job = "Own sales pipeline marketing campaigns and account forecasts"

        self.assertGreater(
            token_semantic_similarity(resume, related_job),
            token_semantic_similarity(resume, unrelated_job),
        )


if __name__ == "__main__":
    unittest.main()
