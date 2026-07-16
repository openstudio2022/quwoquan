"""Production content-supply contracts shared by queues, runners and gates.

The key rule is intentionally simple: an Agent cannot advance workflow state
with prose.  It must submit an AgentResultEnvelope that names every produced
file, includes sha256 hashes, and carries final gate verdicts.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping


OBJECT_JOB_SCHEMA = "quwoquan.object_job"
AGENT_RESULT_ENVELOPE_SCHEMA = "quwoquan.agent_result_envelope"
GATE_VERDICT_SCHEMA = "quwoquan.gate_verdict"
TOKEN_LEDGER_SCHEMA = "quwoquan.token_ledger"

PASSING_GATE_DECISIONS = {"passed", "approved"}
FINAL_GATE_DECISIONS = {"passed", "approved", "failed", "manual_required", "rejected"}


def sha256_bytes(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def stable_failure_fingerprint(issues: Iterable[str]) -> str:
    normalized = sorted({str(issue).strip() for issue in issues if str(issue).strip()})
    return hashlib.sha1("\u0000".join(normalized).encode("utf-8")).hexdigest()[:16]


def _is_relative_safe(path: Path) -> bool:
    if path.is_absolute():
        return False
    return ".." not in path.parts


def _expect_string(payload: Mapping[str, Any], key: str, issues: list[str], *, prefix: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        issues.append(f"{prefix}.{key} is required")
        return ""
    return value


def validate_gate_verdict(verdict: Mapping[str, Any], *, require_passing: bool = False) -> list[str]:
    issues: list[str] = []
    if verdict.get("schemaVersion") != GATE_VERDICT_SCHEMA:
        issues.append("gate.schemaVersion must be quwoquan.gate_verdict")
    gate_id = verdict.get("gateId") or verdict.get("gate")
    if not isinstance(gate_id, str) or not gate_id.strip():
        issues.append("gate.gateId is required")
    decision = str(verdict.get("decision") or "")
    if decision not in FINAL_GATE_DECISIONS:
        issues.append(f"gate.decision unsupported: {decision or '<empty>'}")
    if require_passing and decision not in PASSING_GATE_DECISIONS:
        issues.append(f"gate.decision must pass for completion: {gate_id or '<unknown>'}={decision or '<empty>'}")
    if verdict.get("final") is not True:
        issues.append(f"gate.final must be true: {gate_id or '<unknown>'}")
    for key in ("inputHash", "outputHash"):
        value = verdict.get(key)
        if not isinstance(value, str) or not value.startswith("sha256:"):
            issues.append(f"gate.{key} must be sha256:<hex>: {gate_id or '<unknown>'}")
    return issues


def validate_agent_result_envelope(
    envelope: Mapping[str, Any],
    *,
    workspace_root: str | Path | None = None,
    require_passing_gates: bool = True,
) -> list[str]:
    issues: list[str] = []
    if envelope.get("schemaVersion") != AGENT_RESULT_ENVELOPE_SCHEMA:
        issues.append("envelope.schemaVersion must be quwoquan.agent_result_envelope")
    for key in ("executionId", "jobId", "ref", "stage"):
        _expect_string(envelope, key, issues, prefix="envelope")

    # P4 审计链补强：envelope 必须携带 provider/model/runId/promptSha256，
    # 否则产物无法回放归因（哪个模型/哪次 run/哪份 prompt 生成）。
    agent = envelope.get("agent")
    if not isinstance(agent, Mapping):
        issues.append("envelope.agent is required (provider/model/runId/promptSha256)")
    else:
        for key in ("provider", "model", "runId"):
            value = agent.get(key)
            if not isinstance(value, str) or not value.strip():
                issues.append(f"envelope.agent.{key} is required")
        prompt_hash = agent.get("promptSha256")
        if not isinstance(prompt_hash, str) or not prompt_hash.startswith("sha256:"):
            issues.append("envelope.agent.promptSha256 must be sha256:<hex>")

    files = envelope.get("files")
    if not isinstance(files, list) or not files:
        issues.append("envelope.files must be a non-empty array")
        files = []
    root = Path(workspace_root) if workspace_root is not None else None
    for idx, item in enumerate(files):
        if not isinstance(item, Mapping):
            issues.append(f"envelope.files[{idx}] must be object")
            continue
        raw_path = item.get("path")
        expected_hash = item.get("sha256")
        if not isinstance(raw_path, str) or not raw_path.strip():
            issues.append(f"envelope.files[{idx}].path is required")
            continue
        rel = Path(raw_path)
        if not _is_relative_safe(rel):
            issues.append(f"envelope.files[{idx}].path must be safe relative path: {raw_path}")
            continue
        if not isinstance(expected_hash, str) or not expected_hash.startswith("sha256:"):
            issues.append(f"envelope.files[{idx}].sha256 must be sha256:<hex>")
            continue
        if root is None:
            continue
        actual_path = root / rel
        if not actual_path.is_file():
            issues.append(f"envelope.files[{idx}] missing file: {raw_path}")
            continue
        actual_hash = sha256_file(actual_path)
        if actual_hash != expected_hash:
            issues.append(f"envelope.files[{idx}] hash mismatch: {raw_path}")

    gates = envelope.get("gates")
    if not isinstance(gates, list) or not gates:
        issues.append("envelope.gates must be a non-empty array")
        gates = []
    seen_gate_ids: set[str] = set()
    for idx, gate in enumerate(gates):
        if not isinstance(gate, Mapping):
            issues.append(f"envelope.gates[{idx}] must be object")
            continue
        gate_id = str(gate.get("gateId") or gate.get("gate") or "")
        if gate_id in seen_gate_ids:
            issues.append(f"envelope.gates has duplicate final gate verdict: {gate_id}")
        if gate_id:
            seen_gate_ids.add(gate_id)
        issues.extend(validate_gate_verdict(gate, require_passing=require_passing_gates))

    return issues


def assert_envelope_matches_job(envelope: Mapping[str, Any], job: Mapping[str, Any]) -> list[str]:
    issues: list[str] = []
    for key in ("executionId", "jobId", "ref", "stage"):
        if str(envelope.get(key) or "") != str(job.get(key) or ""):
            issues.append(f"envelope.{key} does not match job.{key}")
    return issues


def build_gate_verdict(
    *,
    gate_id: str,
    decision: str,
    input_hash: str,
    output_hash: str,
    issues: Iterable[str] | None = None,
    retryable: bool = False,
) -> dict[str, Any]:
    issue_list = [str(issue) for issue in (issues or []) if str(issue).strip()]
    return {
        "schemaVersion": GATE_VERDICT_SCHEMA,
        "gateId": gate_id,
        "decision": decision,
        "final": True,
        "inputHash": input_hash,
        "outputHash": output_hash,
        "issues": issue_list,
        "failureFingerprint": stable_failure_fingerprint(issue_list) if issue_list else None,
        "retryable": bool(retryable),
    }


def build_agent_result_envelope(
    *,
    job: Mapping[str, Any],
    files: list[Mapping[str, Any]],
    gates: list[Mapping[str, Any]],
    provider: str,
    model: str,
    run_id: str,
    prompt_sha256: str,
    agent_id: str | None = None,
) -> dict[str, Any]:
    """审计链契约（P4）：provider/model/runId/promptSha256 必填，产物可回放归因。"""
    from content.execution.identity import validate_execution_id

    execution_id = validate_execution_id(str(job.get("executionId") or ""))
    payload = {
        "schemaVersion": AGENT_RESULT_ENVELOPE_SCHEMA,
        "executionId": execution_id,
        "jobId": job.get("jobId"),
        "ref": job.get("ref"),
        "stage": job.get("stage"),
        "agent": {
            "agentId": agent_id,
            "runId": run_id,
            "provider": provider,
            "model": model,
            "promptSha256": prompt_sha256,
        },
        "files": [dict(item) for item in files],
        "gates": [dict(item) for item in gates],
    }
    payload["envelopeId"] = stable_failure_fingerprint([json.dumps(payload, sort_keys=True, ensure_ascii=False)])
    return payload


def build_token_ledger_entry(
    *,
    execution_id: str,
    job_id: str,
    run_id: str,
    creator_profile_id: str,
    content_type: str,
    budget_tokens: int,
    used_tokens: int,
    cache_hits: Mapping[str, bool] | None = None,
    cost_usd: float = 0.0,
    provider: str = "",
    model: str = "",
) -> dict[str, Any]:
    """账本条目（P4 补强）：runId 必填，token 用量必须能关联到具体 agent run。"""
    exceeded = int(budget_tokens) > 0 and int(used_tokens) > int(budget_tokens)
    return {
        "schemaVersion": TOKEN_LEDGER_SCHEMA,
        "executionId": execution_id,
        "jobId": job_id,
        "runId": run_id,
        "provider": provider,
        "model": model,
        "creatorProfileId": creator_profile_id,
        "contentType": content_type,
        "budgetTokens": int(budget_tokens),
        "usedTokens": int(used_tokens),
        "costUsd": float(cost_usd),
        "cacheHits": dict(cache_hits or {}),
        "budgetExceeded": exceeded,
        "unitPassedCostUsd": None,
    }


def validate_token_ledger_entry(entry: Mapping[str, Any]) -> list[str]:
    issues: list[str] = []
    if entry.get("schemaVersion") != TOKEN_LEDGER_SCHEMA:
        issues.append("tokenLedger.schemaVersion must be quwoquan.token_ledger")
    for key in ("executionId", "jobId", "runId", "creatorProfileId", "contentType"):
        _expect_string(entry, key, issues, prefix="tokenLedger")
    budget = int(entry.get("budgetTokens") or 0)
    used = int(entry.get("usedTokens") or 0)
    if budget < 0 or used < 0:
        issues.append("tokenLedger budgetTokens/usedTokens must be >= 0")
    if budget > 0 and used > budget and entry.get("budgetExceeded") is not True:
        issues.append("tokenLedger.budgetExceeded must be true when usedTokens exceeds budgetTokens")
    return issues
