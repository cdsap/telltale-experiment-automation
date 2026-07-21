# Experiment Automation

Automation for creating [Telltale](https://github.com/cdsap/Telltale) experiments when monitored Gradle stack versions change.

The intended workflow is:

1. Detect that Renovate or another source changed a stack version.
2. Generate a baseline Gradle project with [ProjectGenerator](https://github.com/cdsap/ProjectGenerator).
3. Copy the baseline into a new-version variant.
4. Apply the detected change to the variant.
5. Create an experiment repository with two branches.
6. Push the branches to GitHub.
7. Dispatch Telltale's `experiment.yaml` workflow with the repository, variants, task, iterations, and report settings.
8. Merge the original Renovate PR only after the experiment succeeds.

## Current State

Implemented:

- JSON version detection with persisted state.
- ProjectGenerator CLI execution.
- Baseline and new-version project creation.
- AGP updates in `gradle/libs.versions.toml`.
- Kotlin Gradle Plugin updates in `gradle/libs.versions.toml` plus inline Kotlin plugin declarations in `*.gradle.kts`.
- Gradle wrapper updates through `./gradlew wrapper --gradle-version ...`.
- Optional baseline/new-version build verification before branch creation.
- Local experiment repositories with `baseline` and new-version branches.
- Optional GitHub repository creation and branch push.
- Optional Telltale workflow dispatch.
- Renovate PR-triggered detection from git base/head refs.
- GitHub Actions workflow for Renovate PR creation/update events.
- Guarded Renovate PR merge helper.

Not automated yet:

- Waiting for the Telltale workflow result.
- Automatically deciding when to call the Renovate PR merge helper.

## Version File

The orchestrator reads a JSON object where keys are stack components and values are versions.

```json
{
  "agp": "9.2.0",
  "kotlin": "2.3.20",
  "gradle": "9.5.0"
}
```

Supported component keys:

- `agp`
- `kotlin` or `kgp`
- `gradle`

By default the current versions are read from `versions_to_monitor.json`, and the last processed state is written to `.orchestrator-state/versions.json`.

## Renovate PR Trigger

The repository includes `.github/workflows/renovate-experiment.yml`. It runs on Renovate pull request `opened`, `synchronize`, and `reopened` events, compares the version manifest in the PR base SHA to the PR head SHA, and creates experiments for supported stack updates.

Renovate should update the Telltale version manifest, not a generated experiment project. By default the workflow expects:

```json
{
  "agp": "9.2.0",
  "kotlin": "2.3.20",
  "gradle": "9.5.0"
}
```

at `versions_to_monitor.json`. Set `RENOVATE_VERSIONS_PATH` or pass `--renovate-versions-path` if the file lives elsewhere.

The workflow needs a repository/org secret named `EXPERIMENT_GITHUB_TOKEN` with permission to create experiment repositories, push branches, and dispatch the Telltale workflow.

The same mode can be run locally against git refs:

```bash
GITHUB_TOKEN=... python3 -m orchestrator.main \
  --renovate-base-ref origin/main \
  --renovate-head-ref HEAD \
  --renovate-repo-dir . \
  --renovate-versions-path versions_to_monitor.json \
  --renovate-pr-number 123 \
  --renovate-repo cdsap/source-repo \
  --project-generator ./projectGenerator \
  --github-owner cdsap \
  --push \
  --dispatch
```

For event-specific callers that already know the changed component, bypass git diff detection:

```bash
python3 -m orchestrator.main \
  --component agp \
  --old-version 9.1.0 \
  --new-version 9.2.0 \
  --project-generator ./projectGenerator
```

Each generated branch includes `.experiment-automation.json` with the component, old/new versions, branch names, and Renovate PR context. The later merge gate can use that metadata to verify exactly which Renovate PR the experiment belongs to.

## ProjectGenerator Setup

Install the ProjectGenerator binary and either put it on `PATH` or pass it with `--project-generator`.

```bash
curl -L https://github.com/cdsap/ProjectGenerator/releases/latest/download/projectGenerator --output projectGenerator
chmod 0757 projectGenerator
```

ProjectGenerator options can be passed repeatedly with `--project-option key=value`. The orchestrator converts underscores to dashed CLI flags.

Example:

```bash
--project-option modules=100 \
--project-option shape=rectangle \
--project-option type=android \
--project-option language=kts
```

If no project options are provided, `modules=100` and `develocity_url=https://ge.solutions-team.gradle.com/` are used. Override the Develocity URL with `--project-option develocity_url=<url>`.

## Dry Run

Dry run detects changes and prints the Telltale workflow payload. It does not run ProjectGenerator, create repositories, persist state, push branches, or dispatch GitHub Actions.

```bash
python3 -m orchestrator.main \
  --versions-file versions_to_monitor.json \
  --dry-run
```

Use this first to confirm:

- The component key is recognized.
- The branch names are correct.
- The Telltale workflow inputs look right.
- The repository target is what you expect.

## Local Experiment Run

This generates the project, creates the baseline and new-version branches in a local repo, and prints the dispatch payload. It does not push or dispatch unless `--push` or `--dispatch` are included.

```bash
python3 -m orchestrator.main \
  --versions-file versions_to_monitor.json \
  --project-generator ./projectGenerator \
  --repo-base-dir .orchestrator-repos \
  --work-dir .orchestrator-work \
  --project-option modules=100 \
  --task assembleDebug
```

The local experiment repo will be created under `.orchestrator-repos/<experiment-name>`.

## GitHub + Telltale Run

Set a token with permission to create/push repositories and dispatch workflows.

```bash
GITHUB_TOKEN=... python3 -m orchestrator.main \
  --versions-file versions_to_monitor.json \
  --project-generator ./projectGenerator \
  --github-owner cdsap \
  --repo-prefix experiment \
  --project-option modules=100 \
  --task assembleDebug \
  --iterations 30 \
  --mode "dependencies cache" \
  --push \
  --dispatch
```

With `--push`, the orchestrator creates/configures `https://github.com/<github-owner>/<experiment-name>` and pushes:

- `baseline`
- `<component>-<new-version>`, for example `agp-9.2.0`

`--push` requires both `--github-owner`/`GITHUB_OWNER` and `--github-token`/`GITHUB_TOKEN`. The local `origin` remote is stored as a clean GitHub HTTPS URL without embedding the token; push authentication is provided only to the `git push` process.

With `--dispatch`, it calls:

```text
POST /repos/cdsap/Telltale/actions/workflows/experiment.yaml/dispatches
```

## Telltale Inputs

The dispatch payload includes the inputs required by Telltale's `experiment.yaml` workflow:

- `repository`
- `variantA`
- `variantB`
- `task`
- `iterations`
- `mode`
- `os_args`
- `java_args`
- `extra_build_args`
- `extra_report_args`
- `snapshot_label_a`
- `snapshot_label_b`

When `--extra-report-args`/`EXTRA_REPORT_ARGS` is not set, the orchestrator enables result deployment, OpenAI report generation, Kotlin/process/resource/GC report sections, and uses a dynamic report title such as `AGP 9.2.1 vs 9.2.0`.

Defaults:

```text
task: assembleDebug
iterations: 30
mode: dependencies cache
telltale repo: cdsap/Telltale
workflow: experiment.yaml
ref: main
variantA: baseline
variantB: <component>-<new-version>
```

The JSON-string inputs can be overridden:

```bash
--os-args '{"variantA":"ubuntu-latest","variantB":"ubuntu-latest"}' \
--java-args '{"javaVersionVariantA":"23","javaVersionVariantB":"23","javaVendorVariantA":"zulu","javaVendorVariantB":"zulu"}' \
--extra-build-args '{"extraArgsVariantA":" ","extraArgsVariantB":" "}' \
--extra-report-args '{"deploy_results":"true","experiment_title":"AGP 9.2.1 vs 9.2.0","open_ai_request":"true","report_enabled":"true","tasktype_report":"true","taskpath_report":"true","kotlin_build_report":"true","process_report":"true","resource_usage_report":"true","gc_report":"true","only_cacheable_outcome":"false","threshold_task_duration":"1000"}'
```

## Environment Variables

Most flags have environment variable equivalents:

```text
VERSIONS_FILE
STATE_FILE
WORK_DIR
REPO_BASE_DIR
PROJECT_GENERATOR_PATH
REPO_PREFIX
GITHUB_OWNER
GITHUB_TOKEN
EXPERIMENT_TASK
EXPERIMENT_ITERATIONS
EXPERIMENT_MODE
TELLTALE_REPO
TELLTALE_WORKFLOW
TELLTALE_REF
OS_ARGS
JAVA_ARGS
EXTRA_BUILD_ARGS
EXTRA_REPORT_ARGS
RENOVATE_PR_NUMBER
RENOVATE_REPO
RENOVATE_VERSIONS_PATH
```

CLI flags take precedence over environment variables.

## Baseline Verification

Pass `--verify-baseline` to run the requested Gradle task on the generated baseline before creating the variant:

```bash
python3 -m orchestrator.main \
  --versions-file versions_to_monitor.json \
  --project-generator ./projectGenerator \
  --task assembleDebug \
  --verify-baseline
```

This requires ProjectGenerator to produce a runnable Gradle wrapper at `gradlew`.

Pass `--verify-variants` to run the requested Gradle task in both the baseline and new-version projects before branch creation, push, or dispatch. If the triggering change includes an old version, the baseline is first normalized to that old version; otherwise the generated ProjectGenerator baseline is used as-is.

## Renovate PR Merge

Renovate PR merge is deliberately not automatic in the CLI. The merge API helper exists at:

```python
from orchestrator.trigger import Trigger

Trigger(github_token).merge_renovate_pr(
    renovate_pr_number=123,
    renovate_repo="cdsap/Telltale",
)
```

Call it only after the dispatched Telltale workflow has completed successfully and the experiment result is acceptable.

## Tests

Run the unit tests with the standard library test runner:

```bash
python3 -m unittest discover -v
```

No runtime third-party Python dependencies are required.
