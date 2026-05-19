import os
import tempfile
import unittest
from pathlib import Path

from orchestrator.modifier import Modifier


class ModifierTest(unittest.TestCase):
    def test_updates_only_versions_section_exact_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            versions = root / "gradle" / "libs.versions.toml"
            versions.parent.mkdir()
            versions.write_text(
                '\n'.join(
                    [
                        "[versions]",
                        'agp = "9.1.0"',
                        'agpPluginAlias = "do-not-change"',
                        "",
                        "[plugins]",
                        'android-application = { id = "com.android.application", version.ref = "agp" }',
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            Modifier(root).update_agp("9.2.0")

            updated = versions.read_text(encoding="utf-8")
            self.assertIn('agp = "9.2.0"', updated)
            self.assertIn('agpPluginAlias = "do-not-change"', updated)
            self.assertIn('version.ref = "agp"', updated)

    def test_updates_inline_kotlin_plugin_versions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            versions = root / "gradle" / "libs.versions.toml"
            versions.parent.mkdir()
            versions.write_text('[versions]\nkotlin = "2.3.10"\n', encoding="utf-8")
            build_file = root / "build.gradle.kts"
            build_file.write_text('plugins { id("org.jetbrains.kotlin.android") version "2.3.10" }\n', encoding="utf-8")

            Modifier(root).update_kgp("2.3.20")

            self.assertIn('kotlin = "2.3.20"', versions.read_text(encoding="utf-8"))
            self.assertIn('version "2.3.20"', build_file.read_text(encoding="utf-8"))

    def test_gradle_wrapper_update_works_with_relative_working_dir(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as tmp:
            root = Path(tmp)
            project = root / "project"
            project.mkdir()
            gradlew = project / "gradlew"
            gradlew.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > wrapper-args.txt\n', encoding="utf-8")
            gradlew.chmod(0o755)

            relative_project = Path(os.path.relpath(project, Path.cwd()))
            Modifier(relative_project).update_gradle_wrapper("9.5.0")

            self.assertEqual(
                ["wrapper", "--gradle-version", "9.5.0"],
                (project / "wrapper-args.txt").read_text(encoding="utf-8").splitlines(),
            )


if __name__ == "__main__":
    unittest.main()
