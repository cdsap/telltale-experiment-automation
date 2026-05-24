import argparse
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from orchestrator.detector import Detector, VersionChange
from orchestrator.generator import Generator
from orchestrator.git_manager import GitManager
from orchestrator.modifier import Modifier
from orchestrator.renovate import detect_changes_from_git
from orchestrator.trigger import Trigger, WorkflowDispatch

FOOJAY_TOOLCHAIN_PLUGIN_ID = "org.gradle.toolchains.foojay-resolver-convention"
FOOJAY_TOOLCHAIN_PLUGIN_VERSION = "1.0.0"
DEFAULT_DEVELOCITY_URL = "https://ge.solutions-team.gradle.com/"
COMPONENT_TITLES = {
    "agp": "AGP",
    "gradle": "Gradle",
    "kgp": "KGP",
    "kotlin": "Kotlin",
}


def main() -> None:
    args = parse_args()
    validate_args(args)
    options = parse_project_options(args.project_option)
    changes, persist_after_success = resolve_changes(args)
    if not changes:
        print("No version changes detected.")
        return

    for change in changes:
        run_experiment(change, args, options)

    if persist_after_success and not args.dry_run:
        persist_after_success()


def run_experiment(change: VersionChange, args: argparse.Namespace, project_options: dict[str, object]) -> None:
    experiment_name = safe_name(f"{args.repo_prefix}-{change.component}-{change.new_version}")
    baseline_branch = args.baseline_branch
    variant_branch = safe_name(f"{change.component}-{change.new_version}")
    workspace = Path(args.work_dir) / experiment_name
    baseline_dir = workspace / "baseline"
    variant_dir = workspace / "new-version"

    print(f"Creating experiment {experiment_name}: {change.component} {change.old_version or 'unknown'} -> {change.new_version}")

    if args.dry_run:
        repository = f"{args.github_owner}/{experiment_name}" if args.github_owner else str(Path(args.repo_base_dir) / experiment_name)
        payload = build_dispatch(change, args, repository, baseline_branch, variant_branch)
        print(json.dumps(payload, indent=2, sort_keys=True))
        return

    token = args.github_token or os.environ.get("GITHUB_TOKEN")
    git_manager = GitManager(args.repo_base_dir, github_owner=args.github_owner, token=token)
    if args.push:
        git_manager.ensure_github_repo(experiment_name, private=args.private_repo)

    if workspace.exists():
        shutil.rmtree(workspace)
    workspace.mkdir(parents=True, exist_ok=True)

    Generator(args.project_generator).generate_project(baseline_dir, project_options)
    configure_gradle_toolchain_provisioning(baseline_dir)
    apply_baseline_version(baseline_dir, change)
    shutil.copytree(baseline_dir, variant_dir)
    Modifier(variant_dir).apply_change(change.component, change.new_version)
    if args.verify_baseline or args.verify_variants:
        verify_gradle_task(baseline_dir, args.task)
    if args.verify_variants:
        verify_gradle_task(variant_dir, args.task)
    write_experiment_metadata(baseline_dir, change, args, experiment_name, baseline_branch, variant_branch)
    write_experiment_metadata(variant_dir, change, args, experiment_name, baseline_branch, variant_branch)

    repo_path = git_manager.create_local_repo(experiment_name)

    if args.push:
        git_manager.configure_remote(repo_path, experiment_name)

    git_manager.commit_branch_from_directory(repo_path, baseline_branch, baseline_dir, f"Add baseline for {experiment_name}", push=args.push)
    git_manager.commit_branch_from_directory(repo_path, variant_branch, variant_dir, f"Apply {change.component} {change.new_version}", push=args.push)

    repository = f"{args.github_owner}/{experiment_name}" if args.github_owner else str(repo_path)
    payload = build_dispatch(change, args, repository, baseline_branch, variant_branch, token=token)
    print(json.dumps(payload, indent=2, sort_keys=True))


def build_dispatch(
    change: VersionChange,
    args: argparse.Namespace,
    repository: str,
    baseline_branch: str,
    variant_branch: str,
    token: str | None = None,
) -> dict[str, object]:
    dispatch = WorkflowDispatch(
        repository=repository,
        variant_a=baseline_branch,
        variant_b=variant_branch,
        task=args.task,
        iterations=args.iterations,
        mode=args.mode,
        os_args=args.os_args,
        java_args=args.java_args,
        extra_build_args=args.extra_build_args,
        extra_report_args=args.extra_report_args or default_extra_report_args(change, baseline_branch),
        snapshot_label_a=change.old_version or baseline_branch,
        snapshot_label_b=change.new_version,
    )
    return Trigger(token, telltale_repo=args.telltale_repo, workflow=args.workflow, ref=args.telltale_ref).trigger_experiment(
        dispatch,
        dry_run=args.dry_run or not args.dispatch,
    )


def write_experiment_metadata(
    project_dir: Path,
    change: VersionChange,
    args: argparse.Namespace,
    experiment_name: str,
    baseline_branch: str,
    variant_branch: str,
) -> None:
    metadata = {
        "experiment_name": experiment_name,
        "component": change.component,
        "old_version": change.old_version,
        "new_version": change.new_version,
        "baseline_branch": baseline_branch,
        "variant_branch": variant_branch,
        "renovate_pr_number": args.renovate_pr_number,
        "renovate_repo": args.renovate_repo,
    }
    (project_dir / ".experiment-automation.json").write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create and dispatch Telltale experiments for stack version changes.")
    parser.add_argument("--versions-file", default=os.environ.get("VERSIONS_FILE", "versions_to_monitor.json"))
    parser.add_argument("--state-file", default=os.environ.get("STATE_FILE", ".orchestrator-state/versions.json"))
    parser.add_argument("--component", choices=["agp", "kotlin", "kgp", "gradle"], help="Run one event-specific change instead of reading --versions-file.")
    parser.add_argument("--old-version", help="Previous version for --component runs. Used for labels only.")
    parser.add_argument("--new-version", help="New version for --component runs.")
    parser.add_argument("--renovate-base-ref", help="Detect supported changes by comparing this git ref to --renovate-head-ref.")
    parser.add_argument("--renovate-head-ref", default=os.environ.get("GITHUB_SHA", "HEAD"))
    parser.add_argument("--renovate-repo-dir", default=".")
    parser.add_argument("--renovate-versions-path", default=os.environ.get("RENOVATE_VERSIONS_PATH", os.environ.get("VERSIONS_FILE", "versions_to_monitor.json")))
    parser.add_argument("--renovate-pr-number", type=int, default=parse_optional_int(os.environ.get("RENOVATE_PR_NUMBER")))
    parser.add_argument("--renovate-repo", default=os.environ.get("RENOVATE_REPO"))
    parser.add_argument("--work-dir", default=os.environ.get("WORK_DIR", ".orchestrator-work"))
    parser.add_argument("--repo-base-dir", default=os.environ.get("REPO_BASE_DIR", ".orchestrator-repos"))
    parser.add_argument("--project-generator", default=os.environ.get("PROJECT_GENERATOR_PATH", "projectGenerator"))
    parser.add_argument("--project-option", action="append", default=[], help="ProjectGenerator option as key=value. Repeatable.")
    parser.add_argument("--repo-prefix", default=os.environ.get("REPO_PREFIX", "experiment"))
    parser.add_argument("--github-owner", default=os.environ.get("GITHUB_OWNER"))
    parser.add_argument("--github-token", default=os.environ.get("GITHUB_TOKEN"))
    parser.add_argument("--private-repo", action="store_true")
    parser.add_argument("--push", action="store_true", help="Create/configure the GitHub repo and push variant branches.")
    parser.add_argument("--dispatch", action="store_true", help="Dispatch the Telltale workflow. Requires GITHUB_TOKEN.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verify-baseline", action="store_true")
    parser.add_argument("--verify-variants", action="store_true", help="Run --task in both baseline and new-version projects before creating branches.")
    parser.add_argument("--baseline-branch", default="baseline")
    parser.add_argument("--task", default=os.environ.get("EXPERIMENT_TASK", "assembleDebug"))
    parser.add_argument("--iterations", type=int, default=int(os.environ.get("EXPERIMENT_ITERATIONS", "30")))
    parser.add_argument("--mode", default=os.environ.get("EXPERIMENT_MODE", "dependencies cache"))
    parser.add_argument("--telltale-repo", default=os.environ.get("TELLTALE_REPO", "cdsap/Telltale"))
    parser.add_argument("--workflow", default=os.environ.get("TELLTALE_WORKFLOW", "experiment.yaml"))
    parser.add_argument("--telltale-ref", default=os.environ.get("TELLTALE_REF", "main"))
    parser.add_argument("--os-args", default=os.environ.get("OS_ARGS", '{"variantA":"ubuntu-latest","variantB":"ubuntu-latest"}'))
    parser.add_argument("--java-args", default=os.environ.get("JAVA_ARGS", '{"javaVersionVariantA":"23","javaVersionVariantB":"23","javaVendorVariantA":"zulu","javaVendorVariantB":"zulu"}'))
    parser.add_argument("--extra-build-args", default=os.environ.get("EXTRA_BUILD_ARGS", '{"extraArgsVariantA":" ","extraArgsVariantB":" "}'))
    parser.add_argument("--extra-report-args", default=os.environ.get("EXTRA_REPORT_ARGS"))
    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> None:
    component = getattr(args, "component", None)
    new_version = getattr(args, "new_version", None)
    old_version = getattr(args, "old_version", None)
    renovate_base_ref = getattr(args, "renovate_base_ref", None)
    direct_change = bool(component or new_version or old_version)
    if direct_change and not (component and new_version):
        raise ValueError("--component runs require both --component and --new-version")
    if direct_change and renovate_base_ref:
        raise ValueError("--component and --renovate-base-ref are mutually exclusive")
    if args.push and not args.github_owner:
        raise ValueError("--push requires --github-owner or GITHUB_OWNER")
    if (args.push or args.dispatch) and not args.github_token:
        raise ValueError("--push and --dispatch require --github-token or GITHUB_TOKEN")


def resolve_changes(args: argparse.Namespace) -> tuple[list[VersionChange], object | None]:
    if args.component:
        return [VersionChange(component=args.component, old_version=args.old_version, new_version=args.new_version)], None

    if args.renovate_base_ref:
        changes = detect_changes_from_git(
            args.renovate_base_ref,
            args.renovate_head_ref,
            args.renovate_repo_dir,
            args.renovate_versions_path,
        )
        return changes, None

    detector = Detector(args.versions_file, args.state_file)
    return detector.detect_changes(persist=False), detector.persist_current_versions


def parse_project_options(raw_options: list[str]) -> dict[str, object]:
    options: dict[str, object] = {"modules": 100, "develocity_url": DEFAULT_DEVELOCITY_URL}
    for raw_option in raw_options:
        if "=" not in raw_option:
            options[raw_option] = True
            continue
        key, value = raw_option.split("=", 1)
        options[key] = value
    return options


def parse_optional_int(value: str | None) -> int | None:
    return int(value) if value else None


def default_extra_report_args(change: VersionChange, baseline_label: str) -> str:
    old_version = change.old_version or baseline_label
    title = f"{component_title(change.component)} {change.new_version} vs {old_version}"
    return json.dumps(
        {
            "deploy_results": "true",
            "experiment_title": title,
            "open_ai_request": "true",
            "report_enabled": "true",
            "tasktype_report": "true",
            "taskpath_report": "true",
            "kotlin_build_report": "true",
            "process_report": "true",
            "resource_usage_report": "true",
            "gc_report": "true",
            "only_cacheable_outcome": "false",
            "threshold_task_duration": "1000",
        },
        separators=(",", ":"),
    )


def component_title(component: str) -> str:
    return COMPONENT_TITLES.get(component, component.upper())


def apply_baseline_version(project_dir: Path, change: VersionChange) -> None:
    if change.old_version:
        Modifier(project_dir).apply_change(change.component, change.old_version)


def configure_gradle_toolchain_provisioning(project_dir: Path) -> None:
    settings_file = project_dir / "settings.gradle.kts"
    if not settings_file.exists():
        return

    contents = settings_file.read_text(encoding="utf-8")
    if FOOJAY_TOOLCHAIN_PLUGIN_ID in contents:
        return

    plugin_line = f'    id("{FOOJAY_TOOLCHAIN_PLUGIN_ID}") version "{FOOJAY_TOOLCHAIN_PLUGIN_VERSION}"\n'
    lines = contents.splitlines(keepends=True)

    for index, line in enumerate(lines):
        if line.strip() == "plugins {":
            lines.insert(index + 1, plugin_line)
            settings_file.write_text("".join(lines), encoding="utf-8")
            return

    insert_at = _settings_plugin_block_insert_index(lines)
    plugin_block = [
        "plugins {\n",
        plugin_line,
        "}\n",
        "\n",
    ]
    lines[insert_at:insert_at] = plugin_block
    settings_file.write_text("".join(lines), encoding="utf-8")


def _settings_plugin_block_insert_index(lines: list[str]) -> int:
    for index, line in enumerate(lines):
        if line.strip().startswith("pluginManagement"):
            depth = 0
            for block_index in range(index, len(lines)):
                depth += lines[block_index].count("{")
                depth -= lines[block_index].count("}")
                if depth == 0:
                    return block_index + 1
    return 0


def safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-")
    return cleaned.lower()


def verify_gradle_task(project_dir: Path, task: str) -> None:
    gradlew = project_dir / "gradlew"
    if not gradlew.exists():
        raise FileNotFoundError(f"Cannot verify baseline because gradlew was not generated at {gradlew}")
    subprocess.run([str(gradlew.resolve()), task], cwd=project_dir, check=True)


if __name__ == "__main__":
    main()
