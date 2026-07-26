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
    for workflow in sorted([*WORKFLOWS.glob("*.yml"), *WORKFLOWS.glob("*.yaml")]):
        text = workflow.read_text(encoding="utf-8")
        for match in UPLOAD_PATTERN.finditer(text):
            block = _upload_block(text, match)
            line = text.count("\n", 0, match.start()) + 1
            prefix = f"{workflow.relative_to(ROOT)}:{line}"
            if "retention-days:" not in block:
                issues.append(f"{prefix}: artifact uploads require explicit retention-days")
            if re.search(r"(?:^|\n)\s*if:\s*always\(\)", block):
                issues.append(f"{prefix}: cancelled runs must not upload artifacts")
            if re.search(r"/runs/\*\*(?:\s|$)", block):
                issues.append(f"{prefix}: broad runs/** upload is forbidden; select report.json/summary.json")
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
            "--failed-retention-days 7",
            "--success-retention-days 14",
        ):
            if token not in lifecycle:
                issues.append(f"artifact lifecycle workflow missing {token!r}")
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
