import base64
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from orchestrator.git_manager import GitManager


class GitManagerTest(unittest.TestCase):
    def test_creates_local_repo_branches_from_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_a = root / "source-a"
            source_b = root / "source-b"
            source_a.mkdir()
            source_b.mkdir()
            (source_a / "value.txt").write_text("baseline\n", encoding="utf-8")
            (source_b / "value.txt").write_text("variant\n", encoding="utf-8")

            manager = GitManager(root / "repos")
            repo = manager.create_local_repo("experiment-agp-9.2.0")

            manager.commit_branch_from_directory(repo, "baseline", source_a, "Add baseline", push=False)
            manager.commit_branch_from_directory(repo, "agp-9.2.0", source_b, "Apply AGP", push=False)

            branches = subprocess.check_output(
                ["git", "branch", "--format", "%(refname:short)"],
                cwd=repo,
                text=True,
            ).splitlines()
            baseline_value = subprocess.check_output(["git", "show", "baseline:value.txt"], cwd=repo, text=True)
            variant_value = subprocess.check_output(["git", "show", "agp-9.2.0:value.txt"], cwd=repo, text=True)

            self.assertIn("baseline", branches)
            self.assertIn("agp-9.2.0", branches)
            self.assertEqual("baseline\n", baseline_value)
            self.assertEqual("variant\n", variant_value)

    def test_configure_remote_does_not_store_token(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = GitManager(Path(tmp) / "repos", github_owner="cdsap", token="secret-token")
            repo = manager.create_local_repo("experiment-agp-9.2.0")

            manager.configure_remote(repo, "experiment-agp-9.2.0")

            remote = subprocess.check_output(["git", "remote", "get-url", "origin"], cwd=repo, text=True).strip()
            config = (repo / ".git" / "config").read_text(encoding="utf-8")
            self.assertEqual("https://github.com/cdsap/experiment-agp-9.2.0.git", remote)
            self.assertNotIn("secret-token", config)

    def test_push_runs_even_when_branch_has_no_new_commit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            source.mkdir()
            (source / "value.txt").write_text("baseline\n", encoding="utf-8")

            manager = GitManager(root / "repos", github_owner="cdsap", token="secret-token")
            repo = manager.create_local_repo("experiment-agp-9.2.0")

            with mock.patch.object(manager, "_push_branch") as push_branch:
                manager.commit_branch_from_directory(repo, "baseline", source, "Add baseline", push=True)
                manager.commit_branch_from_directory(repo, "baseline", source, "Add baseline", push=True)

            self.assertEqual(2, push_branch.call_count)

    def test_push_auth_uses_ephemeral_header_not_command_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = GitManager(Path(tmp) / "repos", github_owner="cdsap", token="secret-token")
            repo = manager.create_local_repo("experiment-agp-9.2.0")

            with mock.patch("orchestrator.git_manager.subprocess.run") as run:
                manager._push_branch(repo, "baseline")

            command = run.call_args.args[0]
            env = run.call_args.kwargs["env"]
            header_index = int(env["GIT_CONFIG_COUNT"]) - 1
            self.assertNotIn("secret-token", " ".join(command))
            self.assertEqual("http.https://github.com/.extraheader", env[f"GIT_CONFIG_KEY_{header_index}"])
            expected_credentials = base64.b64encode(b"x-access-token:secret-token").decode("ascii")
            self.assertEqual(f"Authorization: Basic {expected_credentials}", env[f"GIT_CONFIG_VALUE_{header_index}"])
            self.assertEqual("0", env["GIT_TERMINAL_PROMPT"])

    def test_github_operations_require_owner_and_token(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = GitManager(Path(tmp) / "repos")
            repo = manager.create_local_repo("experiment-agp-9.2.0")

            with self.assertRaises(ValueError):
                manager.configure_remote(repo, "experiment-agp-9.2.0")
            with self.assertRaises(ValueError):
                manager.create_github_repo("experiment-agp-9.2.0")

    def test_ensure_github_repo_creates_missing_repo_and_verifies_it_exists(self):
        manager = GitManager("repos", github_owner="cdsap", token="secret-token")

        with (
            mock.patch.object(manager, "github_repo_exists", side_effect=[False, True]) as exists,
            mock.patch.object(manager, "create_github_repo") as create,
        ):
            remote = manager.ensure_github_repo("experiment-agp-9.2.0", private=True)

        self.assertEqual("https://github.com/cdsap/experiment-agp-9.2.0.git", remote)
        self.assertEqual(2, exists.call_count)
        create.assert_called_once_with("experiment-agp-9.2.0", private=True)

    def test_ensure_github_repo_fails_when_repo_is_still_missing_after_create(self):
        manager = GitManager("repos", github_owner="cdsap", token="secret-token")

        with (
            mock.patch.object(manager, "github_repo_exists", side_effect=[False, False]),
            mock.patch.object(manager, "create_github_repo"),
        ):
            with self.assertRaises(RuntimeError):
                manager.ensure_github_repo("experiment-agp-9.2.0")


if __name__ == "__main__":
    unittest.main()
