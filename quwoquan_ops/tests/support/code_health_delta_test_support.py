"""Code Health Delta 合约测试共享 fixture。

提供临时 Git 仓库、提交与写文件 helper，以及从 canonical policy 派生阈值可控的
临时 policy；多个 code-health 测试文件共用，避免每个文件复制同一套 Git 脚手架。
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[3]
POLICY = ROOT / "quwoquan_ops/policies/code_health_policy.yaml"


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


def init_repo(tmp_path: Path, *, policy_text: str | None = None) -> tuple[Path, str]:
    """一个带 canonical policy 副本与 README 的干净仓库，返回 (repo, base_sha)。"""
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "fixture@example.invalid")
    git(repo, "config", "user.name", "Fixture")
    (repo / "quwoquan_ops/policies").mkdir(parents=True)
    (repo / "quwoquan_ops/policies/code_health_policy.yaml").write_text(
        policy_text if policy_text is not None else POLICY.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (repo / "README.md").write_text("base\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "base")
    return repo, git(repo, "rev-parse", "HEAD")


def commit(repo: Path, message: str = "candidate") -> str:
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", message)
    return git(repo, "rev-parse", "HEAD")


def write(repo: Path, relative: str, body: str) -> Path:
    path = repo / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def policy_text_with(**overrides: dict[str, Any]) -> str:
    """从 canonical policy 派生临时 policy 文本；overrides 按 thresholds 分节覆盖。"""
    document = yaml.safe_load(POLICY.read_text(encoding="utf-8"))
    for section, values in overrides.items():
        document["thresholds"][section].update(values)
    return yaml.safe_dump(document, allow_unicode=True, sort_keys=False)


def policy_path(repo: Path) -> Path:
    return repo / "quwoquan_ops/policies/code_health_policy.yaml"
