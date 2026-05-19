import json
import os
import argparse
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import orchestrator.main as main_module
from orchestrator.detector import VersionChange


class MainTest(unittest.TestCase):
    def test_does_not_persist_state_when_experiment_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            versions = root / "versions.json"
            state = root / "state.json"
            versions.write_text(json.dumps({"agp": "9.2.0"}), encoding="utf-8")
            state.write_text(json.dumps({"agp": "9.1.0"}), encoding="utf-8")

            with (
                mock.patch("sys.argv", ["orchestrator", "--versions-file", str(versions), "--state-file", str(state)]),
                mock.patch.object(main_module, "run_experiment", side_effect=RuntimeError("experiment failed")),
            ):
                with self.assertRaises(RuntimeError):
                    main_module.main()

            self.assertEqual({"agp": "9.1.0"}, json.loads(state.read_text(encoding="utf-8")))

    def test_persists_state_after_experiment_succeeds(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            versions = root / "versions.json"
            state = root / "state.json"
            versions.write_text(json.dumps({"agp": "9.2.0"}), encoding="utf-8")
            state.write_text(json.dumps({"agp": "9.1.0"}), encoding="utf-8")

            with (
                mock.patch("sys.argv", ["orchestrator", "--versions-file", str(versions), "--state-file", str(state)]),
                mock.patch.object(main_module, "run_experiment") as run_experiment,
            ):
                main_module.main()

            run_experiment.assert_called_once()
            self.assertEqual({"agp": "9.2.0"}, json.loads(state.read_text(encoding="utf-8")))

    def test_verify_gradle_task_works_with_relative_project_dir(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as tmp:
            root = Path(tmp)
            project = root / "project"
            project.mkdir()
            gradlew = project / "gradlew"
            gradlew.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > verify-args.txt\n', encoding="utf-8")
            gradlew.chmod(0o755)

            relative_project = Path(os.path.relpath(project, Path.cwd()))
            main_module.verify_gradle_task(relative_project, "assembleDebug")

            self.assertEqual(
                ["assembleDebug"],
                (project / "verify-args.txt").read_text(encoding="utf-8").splitlines(),
            )

    def test_push_requires_github_owner_and_token(self):
        args = argparse.Namespace(push=True, dispatch=False, github_owner=None, github_token="token")
        with self.assertRaises(ValueError):
            main_module.validate_args(args)

        args = argparse.Namespace(push=True, dispatch=False, github_owner="cdsap", github_token=None)
        with self.assertRaises(ValueError):
            main_module.validate_args(args)

    def test_dispatch_requires_token(self):
        args = argparse.Namespace(push=False, dispatch=True, github_owner=None, github_token=None)
        with self.assertRaises(ValueError):
            main_module.validate_args(args)

    def test_resolve_changes_supports_direct_component_mode(self):
        args = argparse.Namespace(
            component="agp",
            old_version="9.1.0",
            new_version="9.2.0",
            renovate_base_ref=None,
            renovate_versions_path="versions_to_monitor.json",
            versions_file="unused",
            state_file="unused",
        )

        changes, persist = main_module.resolve_changes(args)

        self.assertIsNone(persist)
        self.assertEqual([VersionChange("agp", "9.1.0", "9.2.0")], changes)

    def test_writes_experiment_metadata_with_renovate_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            args = argparse.Namespace(renovate_pr_number=123, renovate_repo="cdsap/project")

            main_module.write_experiment_metadata(
                root,
                VersionChange("agp", "9.1.0", "9.2.0"),
                args,
                "experiment-agp-9.2.0",
                "baseline",
                "agp-9.2.0",
            )

            metadata = json.loads((root / ".experiment-automation.json").read_text(encoding="utf-8"))
            self.assertEqual(123, metadata["renovate_pr_number"])
            self.assertEqual("cdsap/project", metadata["renovate_repo"])
            self.assertEqual("agp-9.2.0", metadata["variant_branch"])

    def test_apply_baseline_version_only_when_old_version_is_known(self):
        with mock.patch.object(main_module, "Modifier") as modifier:
            main_module.apply_baseline_version(Path("project"), VersionChange("agp", None, "9.2.1"))
            modifier.assert_not_called()

        with mock.patch.object(main_module, "Modifier") as modifier:
            main_module.apply_baseline_version(Path("project"), VersionChange("agp", "9.2.0", "9.2.1"))
            modifier.return_value.apply_change.assert_called_once_with("agp", "9.2.0")

    def test_verify_variants_runs_task_in_baseline_and_variant_after_modification(self):
        args = argparse.Namespace(
            repo_prefix="experiment",
            baseline_branch="baseline",
            work_dir="work",
            repo_base_dir="repos",
            project_generator="projectGenerator",
            verify_baseline=False,
            verify_variants=True,
            task="assembleDebug",
            github_token=None,
            github_owner=None,
            push=False,
            private_repo=False,
            dispatch=False,
            dry_run=False,
            telltale_repo="cdsap/Telltale",
            workflow="experiment.yaml",
            telltale_ref="main",
            os_args="{}",
            java_args="{}",
            extra_build_args="{}",
            extra_report_args="{}",
            iterations=10,
            mode="dependencies cache",
            renovate_pr_number=None,
            renovate_repo=None,
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            args.work_dir = str(root / "work")
            args.repo_base_dir = str(root / "repos")

            def generate_project(output_dir, _options):
                output = Path(output_dir)
                (output / "gradle").mkdir(parents=True)
                (output / "gradle" / "libs.versions.toml").write_text('[versions]\nagp = "9.1.1"\n', encoding="utf-8")
                (output / "gradlew").write_text("#!/bin/sh\n", encoding="utf-8")

            verified_paths: list[Path] = []

            with (
                mock.patch.object(main_module.Generator, "generate_project", side_effect=generate_project),
                mock.patch.object(main_module, "verify_gradle_task", side_effect=lambda path, _task: verified_paths.append(Path(path))),
                mock.patch.object(main_module, "build_dispatch", return_value={"ok": True}),
                mock.patch("builtins.print"),
            ):
                main_module.run_experiment(VersionChange("agp", "9.2.0", "9.2.1"), args, {})

            baseline = root / "work" / "experiment-agp-9.2.1" / "baseline"
            variant = root / "work" / "experiment-agp-9.2.1" / "new-version"
            self.assertEqual([baseline, variant], verified_paths)
            self.assertIn('agp = "9.2.0"', (baseline / "gradle" / "libs.versions.toml").read_text(encoding="utf-8"))
            self.assertIn('agp = "9.2.1"', (variant / "gradle" / "libs.versions.toml").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
