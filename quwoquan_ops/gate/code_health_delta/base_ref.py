"""Resolve the canonical comparison base for local left-shift runs.

本地 L1/L2 与 `make verify-code-health-delta` 需要看到整条 lane 相对 dev1.0 的分歧，
而不是只看未提交改动；`auto` 解析为 HEAD 与 dev1.0 的 merge-base，缺失引用时
fail-closed 并给出唯一恢复命令，绝不静默退回 HEAD。
"""
from __future__ import annotations

import subprocess
from pathlib import Path

AUTO_BASE = "auto"
_INTEGRATION_REFS = ("refs/remotes/origin/dev1.0", "refs/heads/dev1.0")
RECOVERY_COMMAND = "git fetch origin dev1.0"


class BaseResolutionError(ValueError):
    """Raised when no integration reference exists to derive the merge-base."""


def _git(repo: Path, *args: str) -> str | None:
    result = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def resolve_auto_base(repo: Path) -> dict[str, str]:
    """Return ``{"ref", "sha"}`` for the merge-base of HEAD and the first live dev1.0 ref."""
    head = _git(repo, "rev-parse", "--verify", "--quiet", "HEAD^{commit}")
    if not head:
        raise BaseResolutionError("code-health --base auto 需要一个可解析的 HEAD commit")
    for ref in _INTEGRATION_REFS:
        if _git(repo, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}") is None:
            continue
        merge_base = _git(repo, "merge-base", "HEAD", ref)
        if not merge_base:
            raise BaseResolutionError(
                f"code-health --base auto：HEAD 与 {ref} 没有共同祖先；恢复：{RECOVERY_COMMAND}"
            )
        return {"ref": ref, "sha": merge_base}
    raise BaseResolutionError(
        "code-health --base auto 无法解析：缺少 refs/remotes/origin/dev1.0 与本地 dev1.0；"
        f"恢复：{RECOVERY_COMMAND}"
    )
