from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from modules.parser import structure_resume


class ResumeParserTests(unittest.TestCase):
    def test_structure_resume_falls_back_without_openai_key(self) -> None:
        resume_text = """
        Cherif Example
        Summary
        AI platform engineer with Python, OpenAI, and Kubernetes experience.
        Experience
        - Led a platform team that reduced infrastructure cost by 30%.
        """

        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}):
            structured = structure_resume(
                raw_text=resume_text,
                source_file="sample.txt",
                version_name="AI Resume",
                use_llm=True,
            )

        self.assertEqual(structured["metadata"]["parser"], "heuristic-v1")
        self.assertIn("parser_warning", structured["metadata"])
        self.assertIn("AI Engineer", structured["target_roles"])
        self.assertTrue(structured["impact_metrics"])


if __name__ == "__main__":
    unittest.main()
