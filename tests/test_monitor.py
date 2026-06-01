from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from modules import monitor


class DummyJob:
    def __init__(self, url: str) -> None:
        self.url = url


class MonitorTests(unittest.TestCase):
    def test_add_monitor_and_identify_new_jobs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            original_file = monitor.MONITORS_FILE
            original_dir = monitor.DATA_DIR
            monitor.DATA_DIR = Path(tmpdir)
            monitor.MONITORS_FILE = Path(tmpdir) / "job_monitors.json"
            try:
                created = monitor.add_monitor(
                    username="cherif",
                    name="AI roles",
                    target_companies="OpenAI | https://openai.com/careers/search/",
                    job_query="AI engineering",
                    resume_label="Senior AI Resume",
                )

                jobs = [DummyJob("https://example.com/jobs/1"), DummyJob("https://example.com/jobs/2")]
                new_jobs = monitor.identify_new_jobs(created, jobs)
                monitor.update_monitor_run(created["id"], jobs, new_jobs)
                updated = monitor.load_monitors("cherif")[0]

                self.assertEqual(created["username"], "cherif")
                self.assertEqual(len(new_jobs), 2)
                self.assertEqual(updated["last_new_count"], 2)
                self.assertEqual(updated["seen_urls"], ["https://example.com/jobs/1", "https://example.com/jobs/2"])
                self.assertEqual(monitor.identify_new_jobs(updated, jobs), [])
            finally:
                monitor.DATA_DIR = original_dir
                monitor.MONITORS_FILE = original_file


if __name__ == "__main__":
    unittest.main()
