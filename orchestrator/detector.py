import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class VersionChange:
    component: str
    old_version: str | None
    new_version: str


class Detector:
    def __init__(self, versions_file_path: str | os.PathLike[str], state_file_path: str | os.PathLike[str] | None = None):
        self.versions_file_path = Path(versions_file_path)
        self.state_file_path = Path(state_file_path) if state_file_path else None

    def detect_changes(self, persist: bool = True) -> list[VersionChange]:
        current_versions = self._load_versions(self.versions_file_path)
        last_seen_versions = self._load_versions(self.state_file_path) if self.state_file_path else {}

        changes = [
            VersionChange(component=component, old_version=last_seen_versions.get(component), new_version=str(version))
            for component, version in current_versions.items()
            if str(last_seen_versions.get(component)) != str(version)
        ]

        if changes and persist and self.state_file_path:
            self._write_state(current_versions)

        return changes

    def persist_current_versions(self) -> None:
        if not self.state_file_path:
            return
        self._write_state(self._load_versions(self.versions_file_path))

    def _write_state(self, versions: dict[str, str]) -> None:
        if not self.state_file_path:
            return
        self.state_file_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_file_path.write_text(json.dumps(versions, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    @staticmethod
    def _load_versions(path: Path | None) -> dict[str, str]:
        if not path or not path.exists():
            return {}

        with path.open("r", encoding="utf-8") as handle:
            data: Any = json.load(handle)

        if not isinstance(data, dict):
            raise ValueError(f"Version file must contain a JSON object: {path}")

        return {str(key): str(value) for key, value in data.items()}
