import base64
import json
import os
import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path


class GitManager:
    def __init__(self, base_dir: str | os.PathLike[str], github_owner: str | None = None, token: str | None = None):
        self.base_dir = Path(base_dir)
        self.github_owner = github_owner
        self.token = token

    def create_local_repo(self, repo_name: str) -> Path:
        repo_path = self.base_dir / repo_name
        repo_path.mkdir(parents=True, exist_ok=True)
        if not (repo_path / ".git").exists():
            subprocess.run(["git", "init"], cwd=repo_path, check=True, text=True, capture_output=True)
        self._ensure_local_identity(repo_path)
        return repo_path

    def create_github_repo(self, repo_name: str, private: bool = False) -> str:
        self._require_github_config()

        payload = json.dumps({"name": repo_name, "private": private, "auto_init": False}).encode("utf-8")
        try:
            self._post_create_repo(f"https://api.github.com/orgs/{self.github_owner}/repos", payload)
        except urllib.error.HTTPError as error:
            if error.code != 404:
                raise
            self._post_create_repo("https://api.github.com/user/repos", payload)

        return f"https://github.com/{self.github_owner}/{repo_name}.git"

    def ensure_github_repo(self, repo_name: str, private: bool = False) -> str:
        self._require_github_config()

        if not self.github_repo_exists(repo_name):
            self.create_github_repo(repo_name, private=private)
        if not self.github_repo_exists(repo_name):
            raise RuntimeError(f"GitHub repository {self.github_owner}/{repo_name} was not found after creation attempt")

        return f"https://github.com/{self.github_owner}/{repo_name}.git"

    def github_repo_exists(self, repo_name: str) -> bool:
        self._require_github_config()

        request = urllib.request.Request(
            f"https://api.github.com/repos/{self.github_owner}/{repo_name}",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=30):
                return True
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return False
            raise

    def _post_create_repo(self, api_url: str, payload: bytes) -> None:
        request = urllib.request.Request(
            api_url,
            data=payload,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=30):
                pass
        except urllib.error.HTTPError as error:
            if error.code != 422:
                raise

    def configure_remote(self, repo_path: Path, repo_name: str) -> None:
        self._require_github_config()

        remote_url = f"https://github.com/{self.github_owner}/{repo_name}.git"
        existing = subprocess.run(["git", "remote"], cwd=repo_path, check=True, text=True, capture_output=True).stdout.splitlines()
        if "origin" in existing:
            subprocess.run(["git", "remote", "set-url", "origin", remote_url], cwd=repo_path, check=True)
        else:
            subprocess.run(["git", "remote", "add", "origin", remote_url], cwd=repo_path, check=True)

    def commit_branch_from_directory(self, repo_path: Path, branch: str, source_dir: Path, message: str, push: bool) -> None:
        subprocess.run(["git", "checkout", "-B", branch], cwd=repo_path, check=True, text=True, capture_output=True)
        self._replace_worktree(repo_path, source_dir)
        subprocess.run(["git", "add", "."], cwd=repo_path, check=True)

        diff = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=repo_path)
        if diff.returncode not in {0, 1}:
            diff.check_returncode()

        if diff.returncode == 1:
            subprocess.run(["git", "commit", "-m", message], cwd=repo_path, check=True, text=True, capture_output=True)
        if push:
            self._push_branch(repo_path, branch)

    def _push_branch(self, repo_path: Path, branch: str) -> None:
        self._require_github_config()
        env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
        config_index = self._next_git_config_index(env)
        encoded_credentials = base64.b64encode(f"x-access-token:{self.token}".encode("utf-8")).decode("ascii")
        env["GIT_CONFIG_COUNT"] = str(config_index + 1)
        env[f"GIT_CONFIG_KEY_{config_index}"] = "http.https://github.com/.extraheader"
        env[f"GIT_CONFIG_VALUE_{config_index}"] = f"Authorization: Basic {encoded_credentials}"
        subprocess.run(["git", "push", "-u", "origin", branch, "--force-with-lease"], cwd=repo_path, check=True, env=env)

    @staticmethod
    def _replace_worktree(repo_path: Path, source_dir: Path) -> None:
        for child in repo_path.iterdir():
            if child.name == ".git":
                continue
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()

        for child in source_dir.iterdir():
            destination = repo_path / child.name
            if child.is_dir():
                shutil.copytree(child, destination)
            else:
                shutil.copy2(child, destination)

    @staticmethod
    def _ensure_local_identity(repo_path: Path) -> None:
        name = subprocess.run(["git", "config", "--get", "user.name"], cwd=repo_path, text=True, capture_output=True)
        email = subprocess.run(["git", "config", "--get", "user.email"], cwd=repo_path, text=True, capture_output=True)
        if name.returncode != 0:
            subprocess.run(["git", "config", "user.name", "experiment-automation"], cwd=repo_path, check=True)
        if email.returncode != 0:
            subprocess.run(["git", "config", "user.email", "experiment-automation@example.invalid"], cwd=repo_path, check=True)

    def _require_github_config(self) -> None:
        if not self.github_owner:
            raise ValueError("github_owner is required for GitHub repository operations")
        if not self.token:
            raise ValueError("token is required for GitHub repository operations")

    @staticmethod
    def _next_git_config_index(env: dict[str, str]) -> int:
        try:
            return int(env.get("GIT_CONFIG_COUNT", "0"))
        except ValueError:
            return 0
