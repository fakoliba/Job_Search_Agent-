from __future__ import annotations

import unittest

from modules.company_intelligence import (
    CompanyPrepRequest,
    build_company_interview_profile,
    infer_company_type,
    infer_role_family,
)


class CompanyIntelligenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.resume = {
            "summary": "Senior platform engineer focused on AI systems and infrastructure.",
            "skills": ["Python", "Kubernetes", "Terraform", "OpenAI", "RAG"],
            "leadership": ["Led a cross-functional platform migration."],
            "impact_metrics": ["Reduced cloud costs by 30%."],
        }

    def test_unknown_company_still_generates_full_profile(self) -> None:
        profile = build_company_interview_profile(
            CompanyPrepRequest(
                company="ExampleCo",
                role_title="Senior Platform Engineer",
                job_description="Build Kubernetes developer platforms and reliable infrastructure.",
                resume=self.resume,
            )
        )

        self.assertEqual(profile["role_family"], "Platform Engineer")
        self.assertIn(profile["confidence"], {"Company-type inferred", "Role-family inferred"})
        self.assertTrue(profile["rounds"])
        self.assertTrue(profile["technical_questions"])
        self.assertGreater(profile["readiness"]["overall"], 0)

    def test_known_company_overlay_enhances_profile_without_required_branching(self) -> None:
        profile = build_company_interview_profile(
            CompanyPrepRequest(
                company="Apple",
                role_title="Software Engineer, Platform",
                job_description="Build privacy-focused systems and product infrastructure.",
                resume=self.resume,
            )
        )

        self.assertEqual(profile["company_type"], "Big Tech")
        self.assertEqual(profile["confidence"], "Company-specific")
        self.assertIn("Company-specific overlay", profile["sources"])
        self.assertTrue(any("privacy" in theme.lower() for theme in profile["themes"]))

    def test_inference_helpers_detect_company_type_and_role_family(self) -> None:
        self.assertEqual(
            infer_company_type("Acme Observability", "Build monitoring and observability infrastructure."),
            "Infrastructure SaaS",
        )
        self.assertEqual(
            infer_role_family("Machine Learning Engineer", "Build LLM evaluation pipelines."),
            "AI Engineer",
        )


if __name__ == "__main__":
    unittest.main()
