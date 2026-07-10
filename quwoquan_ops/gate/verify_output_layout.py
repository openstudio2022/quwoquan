#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = ROOT / ".qwq_output"
ALLOWED_TOP_LEVEL = frozenset({"env", "data"})
ALLOWED_ENVS = frozenset({"alpha", "beta", "gamma", "prod", "repo"})
ALLOWED_ENV_CHILDREN = frozenset({"runs", "observability", "release", "local"})
ALLOWED_DATA_CHILDREN = frozenset({"runs", "observability", "release", "local"})
ALLOWED_RELEASE_CHILDREN = frozenset({"app", "service", "legal-static"})
FORBIDDEN_OLD_TOP_LEVEL = frozenset({"local", "runs", "release", "observability"})


def _rel(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def output_layout_issues(root: Path = OUTPUT_ROOT) -> list[str]:
    issues: list[str] = []
    if not root.exists():
        return issues
    if not root.is_dir():
        return [f"{_rel(root)}: output root must be a directory"]

    for entry in sorted(root.iterdir()):
        if entry.name in FORBIDDEN_OLD_TOP_LEVEL:
            issues.append(f"{_rel(entry)}: retired output top-level; use .qwq_output/env/** or .qwq_output/data/**")
            continue
        if entry.name not in ALLOWED_TOP_LEVEL:
            issues.append(f"{_rel(entry)}: unknown .qwq_output top-level; only env/ and data/ are allowed")

    env_root = root / "env"
    if env_root.exists():
        if not env_root.is_dir():
            issues.append(f"{_rel(env_root)}: env must be a directory")
        else:
            issues.extend(_env_issues(env_root))

    data_root = root / "data"
    if data_root.exists():
        if not data_root.is_dir():
            issues.append(f"{_rel(data_root)}: data must be a directory")
        else:
            issues.extend(_data_issues(data_root))
    return issues


def _env_issues(env_root: Path) -> list[str]:
    issues: list[str] = []
    for env_dir in sorted(env_root.iterdir()):
        if not env_dir.is_dir():
            issues.append(f"{_rel(env_dir)}: env/ only allows environment directories")
            continue
        if env_dir.name not in ALLOWED_ENVS:
            issues.append(f"{_rel(env_dir)}: unknown environment segment")
        for child in sorted(env_dir.iterdir()):
            if child.name not in ALLOWED_ENV_CHILDREN:
                issues.append(f"{_rel(child)}: environment output only allows local/, runs/, release/ and observability/")
        release_root = env_dir / "release"
        if release_root.is_dir():
            for child in sorted(release_root.iterdir()):
                if child.name not in ALLOWED_RELEASE_CHILDREN:
                    issues.append(f"{_rel(child)}: env release only allows app/, service/ and legal-static/")
    return issues


def _data_issues(data_root: Path) -> list[str]:
    issues: list[str] = []
    for child in sorted(data_root.iterdir()):
        if child.name not in ALLOWED_DATA_CHILDREN:
            issues.append(f"{_rel(child)}: data output only allows local/, runs/, release/ and observability/")
    local_root = data_root / "local"
    if local_root.exists():
        for child in sorted(local_root.iterdir()):
            if child.name != "runtime":
                issues.append(f"{_rel(child)}: data local output only allows runtime/")
    return issues


def main() -> int:
    issues = output_layout_issues()
    if issues:
        print("[verify_output_layout] FAIL")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    print("[verify_output_layout] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
