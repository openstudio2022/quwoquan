"""Dynamic S4 admission derived solely from canonical branch policy."""
from __future__ import annotations

import hashlib
from typing import Any

from quwoquan_ops.gate.verify_git_branch_policy import load_policy_bytes

from .contract import BRANCH_POLICY_PATH, admission_readback


def _blocked_detail(error: BaseException) -> str:
    return " ".join(str(error).replace("\x00", "\\x00").split()) or type(error).__name__


def temporary_execution_admitted_from_policy_bytes(raw: bytes) -> bool:
    """Pure fixture/parser helper; it does not construct an authority readback."""
    policy = load_policy_bytes(raw)
    return (
        bool(policy.pull_request_prefixes)
        and policy.temporary_execution_admission is not None
    )


def inspect_admission() -> dict[str, Any]:
    """Read exactly the canonical branch-policy bytes and project S4 admission."""
    try:
        raw = BRANCH_POLICY_PATH.read_bytes()
        admitted = temporary_execution_admitted_from_policy_bytes(raw)
        return admission_readback(
            "admitted" if admitted else "not_admitted",
            branch_policy_digest="sha256:" + hashlib.sha256(raw).hexdigest(),
        )
    except Exception as error:
        return admission_readback("blocked", detail=_blocked_detail(error))
