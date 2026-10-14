import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

def _find_bash() -> str | None:
    found = shutil.which("bash")
    if sys.platform != "win32":
        return found
    # The WSL launchers (System32 / WindowsApps) cannot run scripts addressed by Windows paths,
    # so on Windows prefer a real Git Bash even when a launcher is first on PATH.
    launcher_dirs = ("\\system32\\", "\\sysnative\\", "\\windowsapps\\")
    if found and not any(part in os.path.normcase(found) for part in launcher_dirs):
        return found
    for root in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")):
        candidate = Path(root) / "Git" / "bin" / "bash.exe" if root else None
        if candidate and candidate.is_file():
            return str(candidate)
    return None


_BASH = _find_bash()


@unittest.skipUnless(_BASH, "bash is not available on this host (e.g. native Windows without Git Bash)")
class RefreshReportsScriptSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo_root = Path(__file__).resolve().parents[1]
        cls.script_path = cls.repo_root / "scripts" / "refresh_github_pages_reports.sh"

    def _run(self, *args: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        return subprocess.run(
            [_BASH, str(self.script_path), *args],
            cwd=self.repo_root,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_list_stages(self):
        result = self._run("--list-stages")
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        self.assertEqual(lines, ["quarterly", "sef", "sefk", "delivery-health", "site-index"])

    def test_site_index_preflight_only(self):
        result = self._run("--stage", "site-index", "--preflight-only")
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("Preflight passed.", result.stdout)
        self.assertIn("Preflight-only mode complete.", result.stdout)

    def test_quarterly_preflight_only(self):
        result = self._run("--stage", "quarterly", "--preflight-only")
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("Preflight passed.", result.stdout)
        self.assertIn("Preflight-only mode complete.", result.stdout)


if __name__ == "__main__":
    unittest.main()
