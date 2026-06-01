from __future__ import annotations

import unittest

from modules.generator import DraftRequest
from modules.interview import fallback_interview_prep


class InterviewPrepTests(unittest.TestCase):
    def test_fallback_interview_prep_contains_core_sections(self) -> None:
        prep = fallback_interview_prep(
            DraftRequest(
                resume={"skills": ["Python", "Kubernetes"], "leadership": ["Led a platform migration."]},
                job_description="Senior platform engineer role.",
                company="Example",
                role_title="Senior Platform Engineer",
            )
        )

        self.assertIn("Technical Questions", prep)
        self.assertIn("Behavioral Questions", prep)
        self.assertIn("7-Day Study Plan", prep)
        self.assertIn("Senior Platform Engineer", prep)


if __name__ == "__main__":
    unittest.main()
