import json
import urllib.request
from dataclasses import dataclass


@dataclass(frozen=True)
class WorkflowDispatch:
    repository: str
    variant_a: str
    variant_b: str
    task: str = "assembleDebug"
    iterations: int = 10
    mode: str = "dependencies cache"
    os_args: str = '{"variantA":"ubuntu-latest","variantB":"ubuntu-latest"}'
    java_args: str = '{"javaVersionVariantA":"23","javaVersionVariantB":"23","javaVendorVariantA":"zulu","javaVendorVariantB":"zulu"}'
    extra_build_args: str = '{"extraArgsVariantA":" ","extraArgsVariantB":" "}'
    extra_report_args: str = '{"deploy_results":"false","experiment_title":"","open_ai_request":"false","report_enabled":"true","tasktype_report":"true","taskpath_report":"true","kotlin_build_report":"false","process_report":"false","resource_usage_report":"true","gc_report":"false","only_cacheable_outcome":"false","threshold_task_duration":"1000"}'
    snapshot_label_a: str = ""
    snapshot_label_b: str = ""

    def inputs(self) -> dict[str, str]:
        return {
            "repository": self.repository,
            "variantA": self.variant_a,
            "variantB": self.variant_b,
            "task": self.task,
            "iterations": str(self.iterations),
            "mode": self.mode,
            "os_args": self.os_args,
            "java_args": self.java_args,
            "extra_build_args": self.extra_build_args,
            "extra_report_args": self.extra_report_args,
            "snapshot_label_a": self.snapshot_label_a,
            "snapshot_label_b": self.snapshot_label_b,
        }


class Trigger:
    def __init__(self, github_token: str | None, telltale_repo: str = "cdsap/Telltale", workflow: str = "experiment.yaml", ref: str = "main"):
        self.github_token = github_token
        self.telltale_repo = telltale_repo
        self.workflow = workflow
        self.ref = ref

    def trigger_experiment(self, dispatch: WorkflowDispatch, dry_run: bool = False) -> dict[str, object]:
        payload = {"ref": self.ref, "inputs": dispatch.inputs()}
        if dry_run:
            return payload
        if not self.github_token:
            raise ValueError("GITHUB_TOKEN is required to dispatch the Telltale workflow")

        url = f"https://api.github.com/repos/{self.telltale_repo}/actions/workflows/{self.workflow}/dispatches"
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.github_token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=30):
            return payload

    def merge_renovate_pr(self, renovate_pr_number: int | None, renovate_repo: str | None = None, dry_run: bool = False) -> bool:
        if renovate_pr_number is None:
            return False
        if dry_run:
            return True
        if not self.github_token:
            raise ValueError("GITHUB_TOKEN is required to merge the Renovate PR")

        repo = renovate_repo or self.telltale_repo
        url = f"https://api.github.com/repos/{repo}/pulls/{renovate_pr_number}/merge"
        request = urllib.request.Request(
            url,
            data=json.dumps({"merge_method": "squash"}).encode("utf-8"),
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.github_token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "Content-Type": "application/json",
            },
            method="PUT",
        )
        with urllib.request.urlopen(request, timeout=30):
            return True
