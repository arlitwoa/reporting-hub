import os
import subprocess
import sys
import unittest
from pathlib import Path


class RefreshReportsScriptSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo_root = Path(__file__).resolve().parents[1]
        cls.script_path = cls.repo_root / "scripts" / "quarterly" / "refresh_quarter_pipeline.py"

    def _run(self, *args: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        return subprocess.run(
            [sys.executable, str(self.script_path), *args],
            cwd=self.repo_root,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_dry_run_lists_pipeline_steps(self):
        result = self._run("--dry-run")
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("fetch_quarter_goal:", result.stdout)
        self.assertIn("publish_dashboard_pages:", result.stdout)
        self.assertIn("with ARTIFACT_DYNAMIC_DATES=1", result.stdout)

    def test_dry_run_does_not_execute_stage_commands(self):
        result = self._run("--dry-run")
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertNotIn("Done. Commit docs/quarter/index.html", result.stdout)


if __name__ == "__main__":
    unittest.main()
