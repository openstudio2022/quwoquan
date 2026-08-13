"""orphan Compose teardown 的 schema、目标闭集、失败类型与规范化原语。

原单文件 ``orphan_compose_teardown.py`` 拆分出的共享常量子模块。
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone


SCHEMA = "stackctl-orphan-compose-teardown-attestation"
CONSUMPTION_SCHEMA = "stackctl-orphan-compose-teardown-consumption"
JOURNAL_SCHEMA = "stackctl-orphan-compose-teardown-journal"
STEP_SCHEMA = "stackctl-orphan-compose-teardown-step"
CONVERGENCE_SCHEMA = "stackctl-orphan-compose-teardown-convergence"
LOCAL_TARGETS = frozenset({"alpha-local", "beta-local", "gamma-local"})
ATTESTATION_TTL_SECONDS = 300
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
_SAFE_LABEL = re.compile(r"[a-zA-Z0-9_.:/@+,-]+")


class OrphanComposeTeardownError(RuntimeError):
    """Fail-closed contract error; callers must surface it as GATE_BLOCK."""


def canonical_project(target: str) -> str:
    if target not in LOCAL_TARGETS:
        raise OrphanComposeTeardownError(
            "orphan Compose teardown supports only Alpha/Beta/Gamma local targets"
        )
    return f"quwoquan_{target.removesuffix('-local')}_release"


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _digest(value: object) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise OrphanComposeTeardownError(
            "orphan Compose attestation timestamp is invalid"
        ) from exc
    if parsed.tzinfo is None:
        raise OrphanComposeTeardownError(
            "orphan Compose attestation timestamp has no timezone"
        )
    return parsed.astimezone(timezone.utc)


def _utc_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
