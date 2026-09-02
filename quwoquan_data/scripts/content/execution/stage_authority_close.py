"""Stage authority 的 close 派生与 current receipt writer。"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def normalize_typed_issues(stage: str, value: object) -> list[dict[str, str]]:
    from content.execution import stage_authority as kernel

    if value is None:
        return []
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise kernel.StageAuthorityError("typedIssues must be an array")
    issues: list[dict[str, str]] = []
    allowed = set(kernel.RECEIPT_STAGES[: kernel._STAGE_INDEX[stage] + 1])
    for index, raw in enumerate(value):
        if not isinstance(raw, Mapping) or not {"code", "message", "recoveryStage"} <= set(raw):
            raise kernel.StageAuthorityError(f"typedIssues[{index}] lacks code/message/recoveryStage")
        if set(raw) - {"code", "message", "recoveryStage", "ref"}:
            raise kernel.StageAuthorityError(f"typedIssues[{index}] has unknown fields")
        recovery = str(raw["recoveryStage"])
        if recovery not in allowed:
            raise kernel.StageAuthorityError(
                f"typedIssues[{index}].recoveryStage is not completed/current: {recovery}"
            )
        issue = {
            "code": str(raw["code"]),
            "message": str(raw["message"]),
            "recoveryStage": recovery,
        }
        if raw.get("ref") is not None:
            issue["ref"] = str(raw["ref"])
        issues.append(issue)
    if len({item["recoveryStage"] for item in issues}) > 1:
        raise kernel.StageAuthorityError("all typed issues must select one deterministic recoveryStage")
    return issues

def validate_required_artifact_closure(
    execution_id: str, stage: str, artifacts: Sequence[Mapping[str, Any]]
) -> None:
    from content.execution import stage_authority as kernel

    if stage in {"release", "ship"}:
        if not artifacts:
            raise kernel.StageAuthorityError(f"{stage} requires non-empty exact artifact closure")
        return
    if stage in {"1.download", "2.quality", "3.compose", "4.draft", "5.review"}:
        from core.stage_artifact_contract import required_stage_artifacts
        request = kernel._load_json(kernel._execution_root(execution_id) / "0.plan/request.json", label="task init request")
        lane = str(request.get("carrier") or "")
        required_names = set(required_stage_artifacts(lane).get(stage, ()))
        refs = {str(item.get("ref") or "") for item in artifacts}
        missing = sorted(name for name in required_names if not any(ref.endswith(f"/{stage}/{name}") for ref in refs))
        if missing:
            raise kernel.StageAuthorityError(f"{stage} exact artifact closure missing required outputs: {missing}")


def _actor_from_semantic_result(kernel: Any, 
    execution_id: str,
    stage: str,
    semantic_result: Mapping[str, Any] | None,
    gate_digest: str,
) -> dict[str, Any]:
    if stage in kernel.SEMANTIC_STAGES:
        if not isinstance(semantic_result, Mapping):
            raise kernel.StageAuthorityError(f"{stage} close requires canonical semantic result")
        try:
            wrapper = kernel.read_stage_semantic_result(execution_id, stage, binding=semantic_result)
        except kernel.StageSemanticError as exc:
            raise kernel.StageAuthorityError(f"semantic result close rejected: {exc}") from exc
        return dict(wrapper["actor"])
    return {
        "host": "qwq-data-stage-authority",
        "modelFamily": "deterministic",
        "sessionId": gate_digest,
        "invocation": None,
    }

def close_stage(
    execution_id: str,
    stage: str,
    *,
    close_context: Mapping[str, Any] | None = None,
) -> Path:
    """从同一 open + machine gate 派生 verdict/next，并写 receipt/reducer。"""
    from content.execution import stage_authority as kernel

    if stage not in kernel._STAGE_INDEX:
        raise kernel.StageAuthorityError(f"unknown stage: {stage}")
    context = dict(close_context or {})
    if set(context) - {"typedIssues"}:
        raise kernel.StageAuthorityError("stage close context only accepts typedIssues")
    rows = kernel._validate_receipt_chain(execution_id)
    replay_receipt = rows[-1][3] if rows and rows[-1][1] == stage else None
    if replay_receipt is not None:
        sequence = int(replay_receipt["sequence"])
    else:
        expected_stage, sequence, _, _ = kernel._current_stage(execution_id)
        if stage != expected_stage:
            raise kernel.StageAuthorityError(f"stage close requested {stage}, current unique next is {expected_stage}")
    authority = kernel._authority_dir(execution_id, sequence, stage)
    open_path = authority / "open.json"
    gate_path = authority / "gate.json"
    open_request = kernel._load_json(open_path, label="stage open request")
    gate = kernel._load_json(gate_path, label="machine gate receipt")
    kernel.assert_valid(open_request, "execution", "stage_open_request", label="stage open request")
    kernel.assert_valid(gate, "execution", "stage_gate_receipt", label="machine gate receipt")
    if (
        open_request.get("executionId") != execution_id
        or gate.get("executionId") != execution_id
        or open_request.get("stage") != stage
        or gate.get("stage") != stage
        or open_request.get("sequence") != sequence
        or gate.get("sequence") != sequence
    ):
        raise kernel.StageAuthorityError("open/gate stage identity drifted")
    kernel._validate_workflow(open_request["workflowContract"])
    if gate["workflowContract"] != open_request["workflowContract"]:
        raise kernel.StageAuthorityError("open/gate workflow contract digest drifted")
    kernel._resolve_binding(execution_id, gate["openRequest"])
    if gate["semanticResult"] is not None:
        try:
            kernel.read_stage_semantic_result(execution_id, stage, binding=gate["semanticResult"])
        except kernel.StageSemanticError as exc:
            raise kernel.StageAuthorityError(f"semantic result close rejected: {exc}") from exc
    for binding in gate["artifacts"]:
        kernel._resolve_binding(execution_id, binding)
    if gate["acceptanceBinding"] is not None:
        kernel._resolve_binding(execution_id, gate["acceptanceBinding"])
    issues = normalize_typed_issues(stage, context.get("typedIssues"))
    if gate["semanticResult"] is not None:
        issues.extend(kernel.derive_stage_semantic_issues(
            execution_id, stage, binding=gate["semanticResult"]
        ))
    # Caller issues只能增加；机器派生 issues 的恢复阶段拥有最终优先级。
    issues.sort(key=lambda item: (str(item["recoveryStage"]), str(item["code"]), str(item.get("ref") or "")))
    failed = [item for item in gate["commands"] if int(item["exitCode"]) != 0]
    if failed:
        recovery = issues[0]["recoveryStage"] if issues else stage
        issues.append({
            "code": "DATA.STAGE.GATE_COMMAND_FAILED",
            "message": f"canonical gate command failed: {failed[0]['commandId']} exit={failed[0]['exitCode']}",
            "recoveryStage": recovery,
        })
    verdict = "blocked" if issues else "pass"
    if verdict == "pass":
        next_stage = kernel.RECEIPT_STAGES[sequence] if sequence < len(kernel.RECEIPT_STAGES) else "END"
    else:
        next_stage = issues[0]["recoveryStage"]
    if stage == "ship":
        if gate.get("releaseBinding") != open_request.get("releaseBinding"):
            raise kernel.StageAuthorityError("ship close releaseBinding differs from ship open authority")
        if gate.get("releaseBinding") is None or gate.get("acceptanceBinding") is None:
            raise kernel.StageAuthorityError("ship requires release and EnvironmentAcceptanceFact authority")
        kernel._validate_ship_predecessor_release(execution_id, gate["releaseBinding"])
    if stage == "release" and gate.get("releaseBinding") is None:
        raise kernel.StageAuthorityError("release close requires its own releaseBinding")
    gate_binding = kernel._binding(gate_path, scope="execution", root=kernel._execution_root(execution_id))
    open_binding = kernel._binding(open_path, scope="execution", root=kernel._execution_root(execution_id))
    actor = _actor_from_semantic_result(
        kernel, execution_id, stage, gate["semanticResult"], gate_binding["digest"]
    )
    payload = {
        "schema": kernel.RECEIPT_SCHEMA,
        "executionId": execution_id,
        "stage": stage,
        "sequence": sequence,
        "verdict": verdict,
        "actor": actor,
        "typedIssues": issues,
        "next": next_stage,
        "authority": {
            "openRequest": open_binding,
            "machineGate": gate_binding,
            "workflowContract": dict(open_request["workflowContract"]),
            "semanticResult": gate["semanticResult"],
            "artifacts": list(gate["artifacts"]),
            "releaseBinding": gate["releaseBinding"],
            "acceptanceBinding": gate["acceptanceBinding"],
        },
        "recordedAt": kernel._now_iso(),
    }
    kernel.assert_valid(payload, "execution", "stage_receipt", label="stage close receipt")
    receipt_target = kernel._execution_root(execution_id) / "_shared/receipts" / f"{sequence:03d}-{stage}.json"
    if receipt_target.is_file():
        existing = kernel._load_json(receipt_target, label="stage receipt")
        comparable = {key: value for key, value in existing.items() if key != "recordedAt"}
        expected = {key: value for key, value in payload.items() if key != "recordedAt"}
        if comparable != expected:
            raise kernel.StageAuthorityConflict(f"stage close create-once conflict: {receipt_target}")
        from content.execution.receipt_state_reducer import reduce_receipt_projection
        reduce_receipt_projection(execution_id)
        return receipt_target
    target = kernel._write_current_receipt_create_once(
        execution_id, payload, writer_token=kernel._stage_authority_writer_token()
    )
    from content.execution.receipt_state_reducer import reduce_receipt_projection
    reduce_receipt_projection(execution_id)
    return target


__all__ = ["close_stage", "normalize_typed_issues", "validate_required_artifact_closure"]
