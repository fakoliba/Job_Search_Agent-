from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from modules import resume_store


class ResumeStoreTests(unittest.TestCase):
    def test_update_resume_metadata_updates_version_notes_and_roles(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            structured_dir = Path(tmp_dir)
            resume_path = structured_dir / "resume.json"
            resume_path.write_text(
                json.dumps(
                    {
                        "source_file": "resume.pdf",
                        "metadata": {"version_name": "Old", "candidate_name": "Cherif"},
                        "target_roles": [],
                    }
                ),
                encoding="utf-8",
            )

            with patch.object(resume_store, "STRUCTURED_DIR", structured_dir):
                updated = resume_store.update_resume_metadata(
                    resume_path,
                    version_name="AI Platform Resume",
                    notes="Best for AI platform roles.",
                    target_roles=["AI Engineer", " Platform Engineer "],
                )

            self.assertEqual(updated["metadata"]["version_name"], "AI Platform Resume")
            self.assertEqual(updated["metadata"]["notes"], "Best for AI platform roles.")
            self.assertEqual(updated["target_roles"], ["AI Engineer", "Platform Engineer"])

            saved = json.loads(resume_path.read_text(encoding="utf-8"))
            self.assertNotIn("_source_path", saved)


if __name__ == "__main__":
    unittest.main()
