#!/usr/bin/env python3
"""阻断 Actions artifact 重新成为长期发布仓或无界运行输出。"""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"
LIFECYCLE_WORKFLOW = WORKFLOWS / "artifact-lifecycle.yml"
LIFECYCLE_SCRIPT = ROOT / "quwoquan_ops" / "ci" / "manage_actions_artifacts.py"
SERVICE_PIPELINE = WORKFLOWS / "service_pipeline.yml"
WEEKLY_REPORT_WORKFLOW = WORKFLOWS / "code-health-weekly.yml"
WEEKLY_REPORT_NAME = (
    "code-health-weekly-report-${{ github.run_id }}-${{ github.run_attempt }}"
)
WEEKLY_REPORT_PATH = (
    "${{ env.QWQ_OUTPUT_ROOT }}/env/repo/runs/code-health/weekly/**/report.json"
)
WEEKLY_REPORT_RETENTION_DAYS = "14"
WEEKLY_REPORT_IF_NO_FILES_FOUND = "error"
WEEKLY_REPORT_FORBIDDEN_TOKENS = (
    "actions/download-artifact@",
    "create-open",
    "create_open",
    "promotion",
    "mutation",
)


def _uses_pattern(action: str) -> re.Pattern[str]:
    return re.compile(
        rf"^(?P<indent>[ \t]*)(?P<list_marker>-\s+)?uses:\s*"
        rf"(?P<quote>[\"']?)actions/{re.escape(action)}@[0-9a-f]{{40}}"
        rf"(?P=quote)(?:\s+with:\s*.*)?(?:\s+#.*)?$",
        re.MULTILINE,
    )


UPLOAD_PATTERN = _uses_pattern("upload-artifact")
DOWNLOAD_PATTERN = _uses_pattern("download-artifact")
CACHE_PATTERN = _uses_pattern("cache")
SETUP_GO_PATTERN = _uses_pattern("setup-go")
FAILURE_ONLY_CONDITION = "failure() && !cancelled()"


def _step_block(text: str, match: re.Match[str]) -> str:
    indent = match.group("indent")
    if match.group("list_marker"):
        step_prefix = indent + "- "
        start = match.start()
    else:
        if len(indent) < 2:
            return text[match.start() : match.end()]
        step_prefix = indent[:-2] + "- "
        start = text.rfind("\n" + step_prefix, 0, match.start())
        start = 0 if start < 0 else start + 1
    following = re.search(
        rf"^{re.escape(step_prefix)}",
        text[match.end() :],
        re.MULTILINE,
    )
    end = len(text) if following is None else match.end() + following.start()
    return text[start:end]


def _scalar_value(block: str, key: str) -> str | None:
    match = re.search(rf"^\s*{re.escape(key)}:\s*(.+?)\s*$", block, re.MULTILINE)
    if match is None:
        return None
    return match.group(1).strip().strip("\"'")


def _is_bounded_weekly_report_upload(workflow: Path, block: str) -> bool:
    if workflow != WEEKLY_REPORT_WORKFLOW:
        return False
    if _scalar_value(block, "if") != "success()":
        return False
    if _scalar_value(block, "name") != WEEKLY_REPORT_NAME:
        return False
    if _scalar_value(block, "path") != WEEKLY_REPORT_PATH:
        return False
    if _scalar_value(block, "if-no-files-found") != WEEKLY_REPORT_IF_NO_FILES_FOUND:
        return False
    if _scalar_value(block, "retention-days") != WEEKLY_REPORT_RETENTION_DAYS:
        return False
    return True


def _weekly_report_workflow_is_report_only(text: str) -> bool:
    casefolded = text.casefold()
    return all(token not in casefolded for token in WEEKLY_REPORT_FORBIDDEN_TOKENS)


def verify() -> list[str]:
    issues: list[str] = []
    for workflow in sorted([*WORKFLOWS.glob("*.yml"), *WORKFLOWS.glob("*.yaml")]):
        text = workflow.read_text(encoding="utf-8")
        upload_matches = list(UPLOAD_PATTERN.finditer(text))
        bounded_weekly_uploads = [
            match
            for match in upload_matches
            if _is_bounded_weekly_report_upload(workflow, _step_block(text, match))
        ]
        weekly_report_only = _weekly_report_workflow_is_report_only(text)
        allow_bounded_weekly_upload = (
            workflow == WEEKLY_REPORT_WORKFLOW
            and len(bounded_weekly_uploads) == 1
            and weekly_report_only
        )
        for match in upload_matches:
            block = _step_block(text, match)
            line = text.count("\n", 0, match.start()) + 1
            prefix = f"{workflow.relative_to(ROOT)}:{line}"
            if "retention-days:" not in block:
                issues.append(f"{prefix}: artifact uploads require explicit retention-days")
            bounded_weekly_report = (
                allow_bounded_weekly_upload
                and match is bounded_weekly_uploads[0]
            )
            if FAILURE_ONLY_CONDITION not in block and not bounded_weekly_report:
                issues.append(
                    f"{prefix}: Actions artifacts are failure diagnostics only; "
                    f"require {FAILURE_ONLY_CONDITION}"
                )
            if re.search(r"/runs/\*\*(?:\s|$)", block):
                issues.append(f"{prefix}: broad runs/** upload is forbidden; select report.json/summary.json")
        if workflow == WEEKLY_REPORT_WORKFLOW and (
            len(bounded_weekly_uploads) != 1 or not weekly_report_only
        ):
            issues.append(
                f"{workflow.relative_to(ROOT)}: code-health weekly requires exactly one "
                "bounded successful weekly report in a report-only workflow"
            )
        if DOWNLOAD_PATTERN.search(text):
            issues.append(
                f"{workflow.relative_to(ROOT)}: Actions Artifact job exchange is forbidden; "
                "use OCI, canonical runtime evidence, or the producing job directly"
            )
        for match in CACHE_PATTERN.finditer(text):
            block = _step_block(text, match)
            if "steps.flutter.outputs.cache_path" in block or "RUNNER_TOOL_CACHE" in block:
                line = text.count("\n", 0, match.start()) + 1
                issues.append(
                    f"{workflow.relative_to(ROOT)}:{line}: Actions cache must not retain "
                    "an SDK/toolchain tree; install the checksum-verified toolchain on the runner"
                )
        for match in SETUP_GO_PATTERN.finditer(text):
            block = _step_block(text, match)
            if "cache: false" not in block:
                line = text.count("\n", 0, match.start()) + 1
                issues.append(
                    f"{workflow.relative_to(ROOT)}:{line}: setup-go must disable its implicit "
                    "cache; use a reviewed explicit Go module cache when one is justified"
                )
    if not LIFECYCLE_SCRIPT.is_file():
        issues.append("missing quwoquan_ops/ci/manage_actions_artifacts.py")
    if not LIFECYCLE_WORKFLOW.is_file():
        issues.append("missing .github/workflows/artifact-lifecycle.yml")
    else:
        lifecycle = LIFECYCLE_WORKFLOW.read_text(encoding="utf-8")
        for token in (
            "actions: write",
            "manage_actions_artifacts.py",
            "--apply",
            "--failed-retention-days 3",
            "schedule:",
            "workflow_dispatch:",
            "pull_request:",
            "types: [closed]",
            "Reclaim closed pull-request caches",
            "refs/pull/${{ github.event.pull_request.number }}/merge",
            "actions/caches/${cache_id}",
            "runs-on: ubuntu-latest",
        ):
            if token not in lifecycle:
                issues.append(f"artifact lifecycle workflow missing {token!r}")
        lifecycle_runners = re.findall(
            r"^\s*runs-on:\s*(.+?)\s*$", lifecycle, re.MULTILINE
        )
        if any(
            all(label in runner.casefold() for label in ("self-hosted", "macos", "arm64"))
            for runner in lifecycle_runners
        ):
            issues.append(
                "artifact lifecycle workflow must not use a self-hosted macOS ARM64 runner"
            )
        # GC is periodic and PR-close driven; per-workflow completion fan-out is forbidden.
        if "workflow_run:" in lifecycle or "github.event.workflow_run" in lifecycle:
            issues.append("artifact lifecycle workflow must not fan out on workflow_run")
    if not SERVICE_PIPELINE.is_file():
        issues.append("missing .github/workflows/service_pipeline.yml")
    else:
        service_pipeline = SERVICE_PIPELINE.read_text(encoding="utf-8")
        if 'DOCKER_BUILD_RECORD_UPLOAD: "false"' not in service_pipeline:
            issues.append(
                "service pipeline must disable automatic docker build record artifact uploads"
            )
        if "cache-from: type=gha" in service_pipeline or "cache-to: type=gha" in service_pipeline:
            issues.append(
                "service pipeline must not consume or export unbounded Buildx GHA layer caches"
            )
    return issues


def main() -> int:
    issues = verify()
    if issues:
        print("[verify_github_artifact_lifecycle] FAIL")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    print("[verify_github_artifact_lifecycle] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
