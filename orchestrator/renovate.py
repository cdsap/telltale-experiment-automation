import json
import subprocess
from pathlib import Path
from typing import Any

from orchestrator.detector import SUPPORTED_COMPONENTS, VersionChange


def detect_changes_from_git(
    base_ref: str,
    head_ref: str = "HEAD",
    repo_dir: str | Path = ".",
    versions_path: str = "versions_to_monitor.json",
) -> list[VersionChange]:
    old_text = _git_show(base_ref, versions_path, Path(repo_dir))
    new_text = _git_show(head_ref, versions_path, Path(repo_dir))
    if old_text is None or new_text is None:
        return []

    old_versions = _load_versions_json(old_text, versions_path)
    new_versions = _load_versions_json(new_text, versions_path)
    changes: list[VersionChange] = []

    for key, raw_new_version in new_versions.items():
        component = SUPPORTED_COMPONENTS.get(key.lower())
        if not component:
            continue

        new_version = str(raw_new_version)
        old_value = old_versions.get(key)
        old_version = str(old_value) if old_value is not None else None
        if old_version != new_version:
            changes.append(VersionChange(component=component, old_version=old_version, new_version=new_version))

    return changes


def _git_show(ref: str, path: str, repo_dir: Path) -> str | None:
    result = subprocess.run(
        ["git", "show", f"{ref}:{path}"],
        cwd=repo_dir,
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout


def _load_versions_json(text: str, path: str) -> dict[str, Any]:
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError(f"Version file must contain a JSON object: {path}")
    return {str(key): value for key, value in data.items()}
