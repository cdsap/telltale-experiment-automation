import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from orchestrator.renovate import detect_changes_from_git


class RenovateTest(unittest.TestCase):
    def test_detects_supported_version_manifest_changes_from_git_refs(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            self._git(repo, "init")
            self._git(repo, "config", "user.name", "test")
            self._git(repo, "config", "user.email", "test@example.invalid")
            versions = repo / "versions_to_monitor.json"
            versions.write_text(json.dumps({"agp": "9.1.0", "kotlin": "2.3.10", "gradle": "9.4.0"}), encoding="utf-8")
            self._git(repo, "add", ".")
            self._git(repo, "commit", "-m", "base")
            base = self._git(repo, "rev-parse", "HEAD").stdout.strip()

            versions.write_text(json.dumps({"agp": "9.2.0", "kotlin": "2.3.10", "gradle": "9.5.0"}), encoding="utf-8")
            self._git(repo, "commit", "-am", "renovate stack versions")
            head = self._git(repo, "rev-parse", "HEAD").stdout.strip()

            changes = detect_changes_from_git(base, head, repo, "versions_to_monitor.json")

            self.assertEqual(
                [("agp", "9.1.0", "9.2.0"), ("gradle", "9.4.0", "9.5.0")],
                [(change.component, change.old_version, change.new_version) for change in changes],
            )

    def test_supports_custom_version_manifest_path_and_kgp_alias(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            self._git(repo, "init")
            self._git(repo, "config", "user.name", "test")
            self._git(repo, "config", "user.email", "test@example.invalid")
            versions = repo / "config" / "stack-versions.json"
            versions.parent.mkdir()
            versions.write_text(json.dumps({"kgp": "2.3.10", "other": "1.0.0"}), encoding="utf-8")
            self._git(repo, "add", ".")
            self._git(repo, "commit", "-m", "base")
            base = self._git(repo, "rev-parse", "HEAD").stdout.strip()

            versions.write_text(json.dumps({"kgp": "2.3.20", "other": "2.0.0"}), encoding="utf-8")
            self._git(repo, "commit", "-am", "renovate kgp")
            head = self._git(repo, "rev-parse", "HEAD").stdout.strip()

            changes = detect_changes_from_git(base, head, repo, "config/stack-versions.json")

            self.assertEqual(1, len(changes))
            self.assertEqual("kotlin", changes[0].component)
            self.assertEqual("2.3.10", changes[0].old_version)
            self.assertEqual("2.3.20", changes[0].new_version)

    @staticmethod
    def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["git", *args], cwd=repo, check=True, text=True, capture_output=True)


if __name__ == "__main__":
    unittest.main()
