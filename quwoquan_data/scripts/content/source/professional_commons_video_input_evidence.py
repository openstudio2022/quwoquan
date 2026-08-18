"""Create-once 落盘、路径安全引用与独立人审证据链（Commons 视频输入）。

Commons 公开视频进入统一 acquisition 链路前，必须留下可复核的准入证据：
create-once 写入保证同一 candidate 不被就地篡改，safe ref/file 保证证据不逃逸
acquisition root，review evidence 把 reviewer 的 request/attempt 与 digest 绑定，
replay 时可逐项校验漂移。
"""
from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from core.io import read_json
from core.runtime_policy import active_runtime_policy

from content.execution.agent.outcome import AgentRunOutcome
from content.execution.model_contract import governed_cursor_grok_model
from content.source.professional_safety_evidence import file_sha256

REVIEW_FIELDS = frozenset(
    {
        "status",
        "entityMatch",
        "privacyRisk",
        "minorRisk",
        "maliciousMediaRisk",
        "watermarkStatus",
        "qualityStatus",
        "findings",
    }
)


class CommonsVideoInputError(RuntimeError):
    """Commons 公开视频输入无法形成可复核准入的 typed failure。"""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        super().__init__(f"{code}: {detail}")


def digest(value: object) -> str:
    body = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(body).hexdigest()


def write_once(path: Path, value: Mapping[str, Any]) -> Path:
    body = json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        if path.is_symlink() or not path.is_file() or path.read_bytes() != body:
            raise CommonsVideoInputError(
                "DATA.SOURCE.REVIEW_CREATE_ONCE_CONFLICT",
                f"create-once collision: {path}",
            ) from None
        return path
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(body)
        handle.flush()
        os.fsync(handle.fileno())
    return path


def safe_ref(path: Path, root: Path) -> str:
    resolved_root = root.resolve()
    resolved = path.resolve()
    if resolved == resolved_root or resolved_root not in resolved.parents:
        raise CommonsVideoInputError(
            "DATA.SOURCE.REVIEW_EVIDENCE_UNSAFE",
            f"evidence escapes Commons acquisition root: {path}",
        )
    return resolved.relative_to(resolved_root).as_posix()


def safe_file(root: Path, ref: str) -> Path:
    relative = Path(str(ref or ""))
    resolved_root = root.resolve()
    candidate = (resolved_root / relative).resolve()
    if (
        not str(relative)
        or relative.is_absolute()
        or ".." in relative.parts
        or resolved_root not in candidate.parents
        or candidate.is_symlink()
        or not candidate.is_file()
    ):
        raise CommonsVideoInputError(
            "DATA.SOURCE.REVIEW_EVIDENCE_UNSAFE",
            f"review evidence reference is unsafe: {ref}",
        )
    return candidate


def source_runner(prompt: str) -> AgentRunOutcome:
    """在不构造 executionId 的前提下运行有硬时限的 Cursor Grok reviewer。"""
    from content.execution.agent.agent_worker import (
        run_source_review_agent_isolated,
    )

    policy = active_runtime_policy()
    selection = policy.explicit_semantic_selection("cursor_grok").binding
    return run_source_review_agent_isolated(
        runtime=policy.explicit_semantic_selection("cursor_grok").runtime,
        model_selection=selection.selection,
        prompt=prompt,
    )


def parse_judgment(text: str) -> dict[str, Any] | None:
    candidates = [text.strip()]
    first, last = text.find("{"), text.rfind("}")
    if first >= 0 and last > first:
        candidates.append(text[first : last + 1])
    for value in candidates:
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            continue
        if isinstance(parsed, dict) and set(parsed) == REVIEW_FIELDS:
            return parsed
    return None


def review_evidence(
    *,
    root: Path,
    source_review: Mapping[str, str],
    journal: Mapping[str, Any],
) -> dict[str, Any]:
    outcome = journal.get("outcome")
    if not isinstance(outcome, AgentRunOutcome) or not outcome.succeeded:
        kind = (
            outcome.failure_kind.value
            if isinstance(outcome, AgentRunOutcome) and outcome.failure_kind
            else "unknown"
        )
        code = (
            outcome.error_code
            if isinstance(outcome, AgentRunOutcome) and outcome.error_code
            else "no_code"
        )
        raise CommonsVideoInputError(
            "DATA.AGENT.REVIEW_FAILED", f"{kind}:{code}"
        )
    request_path = journal["requestPath"]
    attempt_path = journal["attemptPath"]
    attempt = journal["attempt"]
    evidence = {
        "sourceReview": dict(source_review),
        "sourceReviewRequestRef": safe_ref(request_path, root),
        "sourceReviewRequestSha256": file_sha256(request_path),
        "sourceReviewAttemptRef": safe_ref(attempt_path, root),
        "sourceReviewAttemptSha256": file_sha256(attempt_path),
        "provider": outcome.provider.value,
        "model": governed_cursor_grok_model(),
        "runId": outcome.run_id,
        "resultSha256": str(attempt["resultSha256"]),
    }
    return evidence


def validate_review_evidence(
    safety: Mapping[str, Any], *, root: Path
) -> None:
    evidence = safety.get("reviewEvidence")
    if not isinstance(evidence, Mapping):
        raise CommonsVideoInputError(
            "DATA.SOURCE.REVIEW_EVIDENCE_MISSING",
            "Commons source safety evidence lacks source-scoped independent review",
        )
    pairs = (
        ("sourceReviewRequestRef", "sourceReviewRequestSha256"),
        ("sourceReviewAttemptRef", "sourceReviewAttemptSha256"),
    )
    for ref_field, digest_field in pairs:
        path = safe_file(root, str(evidence.get(ref_field) or ""))
        if file_sha256(path) != str(evidence.get(digest_field) or ""):
            raise CommonsVideoInputError(
                "DATA.SOURCE.REVIEW_REPLAY_DRIFT",
                f"source review evidence drift: {ref_field}",
            )
    attempt = read_json(
        safe_file(root, str(evidence["sourceReviewAttemptRef"]))
    )
    if (
        not isinstance(attempt, Mapping)
        or attempt.get("status") != "finished"
        or attempt.get("runId") != evidence.get("runId")
        or attempt.get("resultSha256") != evidence.get("resultSha256")
        or attempt.get("recordedAt") != safety.get("reviewedAt")
    ):
        raise CommonsVideoInputError(
            "DATA.SOURCE.REVIEW_REPLAY_DRIFT",
            "source review attempt no longer binds the recorded review result",
        )
