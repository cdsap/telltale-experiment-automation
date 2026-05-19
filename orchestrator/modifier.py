import os
import re
import subprocess
from pathlib import Path


class Modifier:
    def __init__(self, working_dir: str | os.PathLike[str]):
        self.working_dir = Path(working_dir)

    def apply_change(self, component: str, new_version: str) -> None:
        normalized = component.lower().replace("-", "_")
        if normalized in {"agp", "android_gradle_plugin"}:
            self.update_agp(new_version)
            return
        if normalized in {"kgp", "kotlin", "kotlin_gradle_plugin"}:
            self.update_kgp(new_version)
            return
        if normalized == "gradle":
            self.update_gradle_wrapper(new_version)
            return
        raise ValueError(f"Unsupported component: {component}")

    def update_agp(self, new_version: str) -> None:
        self._update_toml_version("agp", new_version)

    def update_kgp(self, new_version: str) -> None:
        self._update_toml_version("kotlin", new_version)
        self._update_inline_kotlin_plugin_versions(new_version)

    def update_gradle_wrapper(self, new_version: str) -> None:
        gradlew = self.working_dir / "gradlew"
        if not gradlew.exists():
            raise FileNotFoundError(f"Gradle wrapper not found: {gradlew}")

        subprocess.run(
            [str(gradlew.resolve()), "wrapper", "--gradle-version", new_version],
            cwd=self.working_dir,
            check=True,
            text=True,
            capture_output=True,
        )

    def _versions_toml_path(self) -> Path:
        candidates = [
            self.working_dir / "gradle" / "libs.versions.toml",
            self.working_dir / "libs.versions.toml",
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        raise FileNotFoundError(f"Could not find libs.versions.toml under {self.working_dir}")

    def _update_toml_version(self, key: str, new_value: str) -> None:
        toml_path = self._versions_toml_path()
        lines = toml_path.read_text(encoding="utf-8").splitlines(keepends=True)
        updated_lines: list[str] = []
        in_versions = False
        found = False
        pattern = re.compile(rf'^(\s*{re.escape(key)}\s*=\s*)(".*?"|\'.*?\')(\s*(?:#.*)?\n?)$')

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("[") and stripped.endswith("]"):
                in_versions = stripped == "[versions]"

            match = pattern.match(line) if in_versions else None
            if match:
                updated_lines.append(f'{match.group(1)}"{new_value}"{match.group(3)}')
                found = True
            else:
                updated_lines.append(line)

        if not found:
            raise ValueError(f"Key '{key}' not found in [versions] of {toml_path}")

        toml_path.write_text("".join(updated_lines), encoding="utf-8")

    def _update_inline_kotlin_plugin_versions(self, new_version: str) -> None:
        plugin_id = re.compile(r'id\("org\.jetbrains\.kotlin(?:\.[^"]+)?"\)\s+version\s+"[^"]+"')
        for path in self.working_dir.rglob("*.gradle.kts"):
            original = path.read_text(encoding="utf-8")
            updated = plugin_id.sub(lambda match: re.sub(r'version\s+"[^"]+"', f'version "{new_version}"', match.group(0)), original)
            if updated != original:
                path.write_text(updated, encoding="utf-8")
