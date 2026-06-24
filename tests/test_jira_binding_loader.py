import os
import tempfile
import unittest
from pathlib import Path

from extensions.twoa_programme.jira_binding_loader import (
    JiraBindingLoadError,
    load_jira_binding,
    resolve_binding_path,
    try_load_jira_binding,
)


class JiraBindingLoaderTests(unittest.TestCase):
    def test_resolve_prefers_profiles_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            profiles = Path(tmp) / "profiles"
            profiles.mkdir()
            binding = profiles / "jira-binding.json"
            binding.write_text(
                '{"statusMap": {"Open": "Dream"}, "fieldAliases": {}}',
                encoding="utf-8",
            )
            prev = os.environ.get("ARTIFACT_PROFILES_DIR")
            os.environ["ARTIFACT_PROFILES_DIR"] = str(profiles)
            try:
                self.assertEqual(resolve_binding_path(), binding)
            finally:
                if prev is None:
                    os.environ.pop("ARTIFACT_PROFILES_DIR", None)
                else:
                    os.environ["ARTIFACT_PROFILES_DIR"] = prev

    def test_load_raises_on_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing-binding.json"
            with self.assertRaises(JiraBindingLoadError):
                load_jira_binding(missing)

    def test_try_load_returns_none_when_unconfigured(self):
        prev = os.environ.pop("ARTIFACT_PROFILES_DIR", None)
        try:
            if resolve_binding_path() is None:
                self.assertIsNone(try_load_jira_binding())
        finally:
            if prev is not None:
                os.environ["ARTIFACT_PROFILES_DIR"] = prev

    def test_parse_error_fails_loud(self):
        with tempfile.TemporaryDirectory() as tmp:
            profiles = Path(tmp) / "profiles"
            profiles.mkdir()
            binding = profiles / "jira-binding.json"
            binding.write_text("{not-json", encoding="utf-8")
            prev = os.environ.get("ARTIFACT_PROFILES_DIR")
            os.environ["ARTIFACT_PROFILES_DIR"] = str(profiles)
            try:
                with self.assertRaises(JiraBindingLoadError):
                    try_load_jira_binding()
            finally:
                if prev is None:
                    os.environ.pop("ARTIFACT_PROFILES_DIR", None)
                else:
                    os.environ["ARTIFACT_PROFILES_DIR"] = prev


if __name__ == "__main__":
    unittest.main()
