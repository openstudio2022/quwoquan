#!/usr/bin/env python3
"""阻断 Make/Actions 对失效脚本或退役环境入口的引用。"""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REPO_SCRIPT_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_.-])"
    r"((?:quwoquan_(?:app|service|data|ops)/)[A-Za-z0-9_./-]+\.(?:py|sh))"
    r"(?![A-Za-z0-9_.-])"
)
RELATIVE_SCRIPTS_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_./-])"
    r"(scripts/[A-Za-z0-9_./-]+\.(?:py|sh))"
    r"(?![A-Za-z0-9_.-])"
)
PACKAGE_SCRIPT_ROOTS = {
    "quwoquan_app": "quwoquan_app",
    "quwoquan_service": "quwoquan_service",
    "quwoquan_data": "quwoquan_data",
}
RETIRED_PREFIXES = (
    "quwoquan_service/services/chat-service/tests/ops/",
    "quwoquan_service/services/assistant-service/tests/ops/",
    "quwoquan_service/scripts/deploy/",
    "quwoquan_service/scripts/contract/",
    "quwoquan_service/scripts/recommendation/",
    "quwoquan_service/scripts/persona/",
    "quwoquan_service/scripts/media/",
    "quwoquan_service/scripts/search/",
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


def _entrypoint_paths(root: Path) -> tuple[list[Path], set[Path]]:
    workflow_root = root / ".github" / "workflows"
    workflow_paths = sorted(workflow_root.glob("*.yml")) + sorted(
        workflow_root.glob("*.yaml")
    )
    candidates = [
        root / "Makefile",
        root / "quwoquan_service/Makefile",
        *sorted((root / "quwoquan_service/services").glob("*/Makefile")),
        root / "quwoquan_ops/gate/gate_repo.sh",
        root / "quwoquan_ops/gate/commit_gate.sh",
        root / "quwoquan_ops/gate/gate_runtime_media.sh",
        root / "quwoquan_ops/cli/stackctl.py",
        root / "quwoquan_app/scripts/cli.py",
        root / "quwoquan_data/scripts/cli.py",
        *workflow_paths,
    ]
    return (
        sorted(path for path in candidates if path.is_file()),
        set(workflow_paths),
    )


def _managed_script_sources(root: Path) -> list[Path]:
    # App + Service executable trees participate in entrypoint closure.
    # Data keeps its own architecture gate and may mention intentional
    # negative-path examples, so it is not scanned here.
    roots = (
        root / "quwoquan_app/scripts",
        root / "quwoquan_service/scripts",
    )
    sources: set[Path] = set()
    for source_root in roots:
        if not source_root.is_dir():
            continue
        sources.update(source_root.rglob("*.py"))
        sources.update(source_root.rglob("*.sh"))
    return sorted(
        path for path in sources if "__pycache__" not in path.parts
    )


def _makefile_scripts_prefix(root: Path, source: Path) -> str | None:
    relative = source.relative_to(root).as_posix()
    if relative == "quwoquan_service/Makefile":
        return "quwoquan_service"
    if relative == "quwoquan_app/Makefile":
        return "quwoquan_app"
    if relative == "quwoquan_data/Makefile":
        return "quwoquan_data"
    if relative.startswith("quwoquan_service/services/") and relative.endswith(
        "/Makefile"
    ):
        return str(Path(relative).parent.as_posix())
    return None


def _relative_scripts_prefix(root: Path, source: Path) -> str | None:
    makefile_prefix = _makefile_scripts_prefix(root, source)
    if makefile_prefix is not None:
        return makefile_prefix
    relative = source.relative_to(root).as_posix()
    for package, prefix in PACKAGE_SCRIPT_ROOTS.items():
        if relative.startswith(f"{package}/"):
            return prefix
    return None


def _iter_script_path_matches(
    root: Path,
    source: Path,
    text: str,
):
    for match in REPO_SCRIPT_PATTERN.finditer(text):
        yield match.start(), match.group(1)
    prefix = _relative_scripts_prefix(root, source)
    if prefix is None:
        return
    # App scripts still use retired bare ``python3 scripts/...`` help forms;
    # those are covered by RETIRED_APP_HELP_PATTERNS instead of existence checks.
    if source.is_relative_to(root / "quwoquan_app/scripts"):
        return
    for match in RELATIVE_SCRIPTS_PATTERN.finditer(text):
        yield match.start(), f"{prefix}/{match.group(1)}"


def entrypoint_script_path_issues(root: Path = ROOT) -> list[str]:
    root = root.resolve()
    issues: list[str] = []
    entrypoint_paths, workflow_paths = _entrypoint_paths(root)
    for entrypoint in entrypoint_paths:
        text = entrypoint.read_text(encoding="utf-8")
        if entrypoint in workflow_paths:
            for token in RETIRED_WORKFLOW_TOKENS:
                if token not in text:
                    continue
                line_number = text.count("\n", 0, text.index(token)) + 1
                issues.append(
                    f"{entrypoint.relative_to(root)}:{line_number}: "
                    f"retired workflow token {token}"
                )
        for start, script_path in _iter_script_path_matches(
            root, entrypoint, text
        ):
            line_number = text.count("\n", 0, start) + 1
            location = f"{entrypoint.relative_to(root)}:{line_number}"
            if script_path.startswith(RETIRED_PREFIXES):
                issues.append(f"{location}: retired script path {script_path}")
                continue
            if not (root / script_path).is_file():
                issues.append(f"{location}: script does not exist {script_path}")
    script_sources = _managed_script_sources(root)
    for source in script_sources:
        text = source.read_text(encoding="utf-8")
        if source.is_relative_to(root / "quwoquan_app/scripts"):
            for pattern in RETIRED_APP_HELP_PATTERNS:
                for match in pattern.finditer(text):
                    line_number = text.count("\n", 0, match.start()) + 1
                    issues.append(
                        f"{source.relative_to(root)}:{line_number}: "
                        f"retired app script help path {match.group(0).strip()}"
                    )
        for start, script_path in _iter_script_path_matches(root, source, text):
            if (root / script_path).is_file():
                continue
            if script_path.startswith(RETIRED_PREFIXES):
                line_number = text.count("\n", 0, start) + 1
                issues.append(
                    f"{source.relative_to(root)}:{line_number}: "
                    f"retired script path {script_path}"
                )
                continue
            line_number = text.count("\n", 0, start) + 1
            issues.append(
                f"{source.relative_to(root)}:{line_number}: "
                f"script does not exist {script_path}"
            )
    return sorted(set(issues))


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
