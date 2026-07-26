#!/usr/bin/env python3
"""阻断 Actions artifact 重新成为长期发布仓或无界运行输出。"""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"
LIFECYCLE_WORKFLOW = WORKFLOWS / "artifact-lifecycle.yml"
LIFECYCLE_SCRIPT = ROOT / "quwoquan_ops" / "ci" / "manage_actions_artifacts.py"
UPLOAD_PATTERN = re.compile(
    r"^(?P<indent>\s*)uses:\s*actions/upload-artifact@[0-9a-f]{40}\s*$",
    re.MULTILINE,
)
DOWNLOAD_PATTERN = re.compile(
    r"^\s*uses:\s*actions/download-artifact@[0-9a-f]{40}\s*$",
    re.MULTILINE,
)
CACHE_PATTERN = re.compile(
    r"^(?P<indent>\s*)uses:\s*actions/cache@[0-9a-f]{40}\s*$",
    re.MULTILINE,
)
SETUP_GO_PATTERN = re.compile(
    r"^(?P<indent>\s*)uses:\s*actions/setup-go@[0-9a-f]{40}\s*$",
    re.MULTILINE,
)
FAILURE_ONLY_CONDITION = "failure() && !cancelled()"


def _upload_block(text: str, match: re.Match[str]) -> str:
    # ``uses`` is indented two spaces below the YAML list marker. Include the
    # complete owning step so an ``if`` placed before ``uses`` is checked too.
    step_prefix = match.group("indent")[:-2] + "- "
    start = text.rfind("\n" + step_prefix, 0, match.start())
    start = 0 if start < 0 else start + 1
    following = re.search(
        rf"^{re.escape(step_prefix)}",
        text[match.end() :],
        re.MULTILINE,
    )
    end = len(text) if following is None else match.end() + following.start()
    return text[start:end]


def verify() -> list[str]:
    issues: list[str] = []
    uploaded_workflow_names: set[str] = set()
    for workflow in sorted([*WORKFLOWS.glob("*.yml"), *WORKFLOWS.glob("*.yaml")]):
        text = workflow.read_text(encoding="utf-8")
        name_match = re.search(r"^name:\s*(.+?)\s*$", text, re.MULTILINE)
        workflow_name = name_match.group(1).strip().strip("\"'") if name_match else ""
        for match in UPLOAD_PATTERN.finditer(text):
            uploaded_workflow_names.add(workflow_name)
            block = _upload_block(text, match)
            line = text.count("\n", 0, match.start()) + 1
            prefix = f"{workflow.relative_to(ROOT)}:{line}"
            if "retention-days:" not in block:
                issues.append(f"{prefix}: artifact uploads require explicit retention-days")
            if FAILURE_ONLY_CONDITION not in block:
                issues.append(
                    f"{prefix}: Actions artifacts are failure diagnostics only; "
                    f"require {FAILURE_ONLY_CONDITION}"
                )
            if re.search(r"/runs/\*\*(?:\s|$)", block):
                issues.append(f"{prefix}: broad runs/** upload is forbidden; select report.json/summary.json")
        if DOWNLOAD_PATTERN.search(text):
            issues.append(
                f"{workflow.relative_to(ROOT)}: Actions Artifact job exchange is forbidden; "
                "use OCI, canonical runtime evidence, or the producing job directly"
            )
        for match in CACHE_PATTERN.finditer(text):
            block = _upload_block(text, match)
            if "steps.flutter.outputs.cache_path" in block or "RUNNER_TOOL_CACHE" in block:
                line = text.count("\n", 0, match.start()) + 1
                issues.append(
                    f"{workflow.relative_to(ROOT)}:{line}: Actions cache must not retain "
                    "an SDK/toolchain tree; install the checksum-verified toolchain on the runner"
                )
        for match in SETUP_GO_PATTERN.finditer(text):
            block = _upload_block(text, match)
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
            "workflow_run:",
            "--run-id",
        ):
            if token not in lifecycle:
                issues.append(f"artifact lifecycle workflow missing {token!r}")
        triggered_names = {
            item.strip()
            for item in re.findall(r"^\s+-\s+(.+?)\s*$", lifecycle, re.MULTILINE)
        }
        for workflow_name in sorted(uploaded_workflow_names):
            if not workflow_name:
                issues.append("artifact-uploading workflow has no name")
            elif workflow_name not in triggered_names:
                issues.append(
                    "artifact lifecycle workflow must observe every artifact-producing "
                    f"workflow: {workflow_name!r}"
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
