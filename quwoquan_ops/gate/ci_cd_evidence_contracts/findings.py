"""CI/CD 证据合同门禁共享的 Finding 与 workflow 文本辅助。"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

NEGATIVE_LANGUAGE = re.compile(
    r"(?:禁止|不得|不存在|拒绝|阻断|移除|退役|forbidden|reject|must not|"
    r"never|non[-_ ]promotable|no compat|no fallback|without rebuilding)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    detail: str


def negative_line(line: str) -> bool:
    """Ignore comments and explicit diagnostic assertions, not executable suffixes."""

    stripped = line.strip()
    return (
        not stripped
        or stripped.startswith("#")
        or ("echo" in stripped and NEGATIVE_LANGUAGE.search(stripped) is not None)
    )


def workflow_on(workflow: Mapping[object, object]) -> object:
    return workflow.get("on", workflow.get(True))


def job_commands(job: object) -> str:
    if not isinstance(job, Mapping):
        return ""
    steps = job.get("steps")
    if not isinstance(steps, list):
        return ""
    return "\n".join(
        str(step.get("run") or "")
        for step in steps
        if isinstance(step, Mapping)
    )


def job_checkout_ref(job: object) -> object:
    if not isinstance(job, Mapping):
        return None
    steps = job.get("steps")
    if not isinstance(steps, list):
        return None
    for step in steps:
        if isinstance(step, Mapping) and isinstance(step.get("uses"), str):
            configuration = step.get("with")
            return configuration.get("ref") if isinstance(configuration, Mapping) else None
    return None
