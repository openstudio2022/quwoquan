#!/usr/bin/env python3
"""阻断 Make/Actions 对失效脚本或退役环境入口的引用。"""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_ROOT = ROOT / ".github" / "workflows"
REPO_SCRIPT_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_.-])"
    r"((?:quwoquan_(?:app|service|data|ops)/)[A-Za-z0-9_./-]+\.(?:py|sh))"
    r"(?![A-Za-z0-9_.-])"
)
RETIRED_PREFIXES = (
    "quwoquan_service/services/chat-service/tests/ops/",
    "quwoquan_service/services/assistant-service/tests/ops/",
    "quwoquan_service/scripts/deploy/",
)
RETIRED_WORKFLOW_TOKENS = (
    "cloud-gamma",
    "GAMMA_ECS_",
    "GAMMA_MONGODB_URI",
    "GAMMA_REC_MODEL_URL",
    "/v1/model/reload",
    "use_ecs_deploy",
)
RETIRED_APP_HELP_PATTERNS = (
    re.compile(r"python3 scripts/"),
    re.compile(r"(?m)^\s{2}scripts/(?:start|stop|list)_[A-Za-z0-9_./-]+\.sh"),
)


def entrypoint_script_path_issues() -> list[str]:
    issues: list[str] = []
    workflow_paths = sorted(WORKFLOW_ROOT.glob("*.yml")) + sorted(
        WORKFLOW_ROOT.glob("*.yaml")
    )
    entrypoint_paths = [
        ROOT / "Makefile",
        ROOT / "quwoquan_service/Makefile",
        *sorted((ROOT / "quwoquan_service/services").glob("*/Makefile")),
        ROOT / "quwoquan_ops/gate/gate_repo.sh",
        *workflow_paths,
    ]
    for entrypoint in entrypoint_paths:
        text = entrypoint.read_text(encoding="utf-8")
        if entrypoint in workflow_paths:
            for token in RETIRED_WORKFLOW_TOKENS:
                if token not in text:
                    continue
                line_number = text.count("\n", 0, text.index(token)) + 1
                issues.append(
                    f"{entrypoint.relative_to(ROOT)}:{line_number}: "
                    f"retired workflow token {token}"
                )
        for match in REPO_SCRIPT_PATTERN.finditer(text):
            script_path = match.group(1)
            line_number = text.count("\n", 0, match.start()) + 1
            location = f"{entrypoint.relative_to(ROOT)}:{line_number}"
            if script_path.startswith(RETIRED_PREFIXES):
                issues.append(f"{location}: retired script path {script_path}")
                continue
            if not (ROOT / script_path).is_file():
                issues.append(f"{location}: script does not exist {script_path}")
    script_sources = sorted((ROOT / "quwoquan_app" / "scripts").rglob("*.py"))
    script_sources += sorted((ROOT / "quwoquan_app" / "scripts").rglob("*.sh"))
    for source in script_sources:
        text = source.read_text(encoding="utf-8")
        for pattern in RETIRED_APP_HELP_PATTERNS:
            for match in pattern.finditer(text):
                line_number = text.count("\n", 0, match.start()) + 1
                issues.append(
                    f"{source.relative_to(ROOT)}:{line_number}: "
                    f"retired app script help path {match.group(0).strip()}"
                )
        for match in REPO_SCRIPT_PATTERN.finditer(text):
            script_path = match.group(1)
            if (ROOT / script_path).is_file():
                continue
            line_number = text.count("\n", 0, match.start()) + 1
            issues.append(
                f"{source.relative_to(ROOT)}:{line_number}: "
                f"script does not exist {script_path}"
            )
    return issues


def main() -> int:
    issues = entrypoint_script_path_issues()
    if issues:
        print("[verify_entrypoint_script_paths] FAIL")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    print("[verify_entrypoint_script_paths] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
