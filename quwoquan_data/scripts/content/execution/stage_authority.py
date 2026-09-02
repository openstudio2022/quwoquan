"""宿主十阶段的确定性 open / gate / close authority 边界。"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from content.execution.operational_fingerprint import POLICY_PATH, operational_fingerprint
from content.execution.stage_semantic_recorder import (
    SEMANTIC_STAGES,
    StageSemanticError,
    derive_stage_semantic_issues,
    read_stage_semantic_result,
)
from content.execution.stage_authority_io import (
    StageAuthorityConflict,
    StageAuthorityError,
    artifact_bindings as _artifact_bindings,
    binding as _binding,
    canonical_bytes as _canonical_bytes,
    execution_root as _execution_root,
    resolve_binding as _resolve_binding,
    sha256 as _sha256,
    write_create_once as _write_create_once,
)
from content.execution.stage_receipt import (
    RECEIPT_STAGES,
    list_receipt_files,
    load_receipt,
    _stage_authority_writer_token,
    _write_current_receipt_create_once,
)
from core import paths
from core.schema import assert_valid

OPEN_SCHEMA = "quwoquan_data.stage_open_request"
GATE_SCHEMA = "quwoquan_data.stage_gate_receipt"
RECEIPT_SCHEMA = "quwoquan_data.stage_receipt"
AUTHORITY_ROOT_REF = "_shared/stage-authority"
_INIT_REFS = ("execution_manifest.json", "0.plan/request.json", "0.plan/target_set.json")
_STAGE_INDEX = {stage: index for index, stage in enumerate(RECEIPT_STAGES)}

def _authority_dir(execution_id: str, sequence: int, stage: str) -> Path:
    return _execution_root(execution_id) / AUTHORITY_ROOT_REF / f"{sequence:03d}-{stage}"

def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")

def _workflow_binding() -> dict[str, str]:
    return {
        "scope": "repo",
        "ref": POLICY_PATH.relative_to(paths.REPO_ROOT).as_posix(),
        # 该 digest 是 policy 全部 inputs 的 operational fingerprint，不是 policy 文件摘要。
        "digest": operational_fingerprint(repo_root=paths.REPO_ROOT),
    }

def _validate_workflow(binding: Mapping[str, Any]) -> None:
    expected = _workflow_binding()
    if dict(binding) != expected:
        raise StageAuthorityError(
            f"workflow contract digest drift: expected {binding.get('digest')}, got {expected['digest']}"
        )

def _validate_receipt_chain(execution_id: str) -> list[tuple[int, str, Path, dict[str, Any]]]:
    rows: list[tuple[int, str, Path, dict[str, Any]]] = []
    entries = list_receipt_files(execution_id)
    for index, (sequence, stage, path) in enumerate(entries):
        receipt = load_receipt(path)
        assert_valid(receipt, "execution", "stage_receipt", label=f"stage receipt:{path}")
        expected_stage = RECEIPT_STAGES[index] if index < len(RECEIPT_STAGES) else None
        if (
            sequence != index + 1
            or receipt.get("sequence") != sequence
            or stage != expected_stage
            or receipt.get("stage") != stage
            or receipt.get("executionId") != execution_id
        ):
            raise StageAuthorityError(f"stage receipt chain order/identity drift: {path}")
        if index < len(entries) - 1 and receipt.get("verdict") != "pass":
            raise StageAuthorityError("blocked stage receipt may not have a successor")
        if receipt.get("verdict") == "pass":
            expected_next = RECEIPT_STAGES[index + 1] if index + 1 < len(RECEIPT_STAGES) else "END"
            if receipt.get("next") != expected_next:
                raise StageAuthorityError(f"stage receipt fixed successor drift: {path}")
        elif receipt.get("next") == "END":
            raise StageAuthorityError("blocked stage receipt may not point to END")
        authority = receipt.get("authority") if isinstance(receipt.get("authority"), Mapping) else {}
        if stage in {"release", "ship"}:
            release_binding = authority.get("releaseBinding")
            machine_gate = authority.get("machineGate")
            if not isinstance(release_binding, Mapping) or not isinstance(machine_gate, Mapping):
                raise StageAuthorityError(f"{stage} receipt lacks release authority binding")
            gate_document = _load_json(
                _resolve_binding(execution_id, machine_gate), label=f"{stage} receipt machine gate"
            )
            if gate_document.get("releaseBinding") != release_binding:
                raise StageAuthorityError(f"{stage} receipt releaseBinding differs from its machine gate")
            if stage == "ship":
                if not rows or rows[-1][1] != "release":
                    raise StageAuthorityError("ship receipt lacks immediate release predecessor")
                predecessor_release = (rows[-1][3].get("authority") or {}).get("releaseBinding")
                if release_binding != predecessor_release:
                    raise StageAuthorityError("ship releaseBinding differs from release predecessor authority")
        rows.append((sequence, stage, path, receipt))
    return rows

def _current_stage(execution_id: str) -> tuple[str, int, dict[str, Any] | None, Path | None]:
    rows = _validate_receipt_chain(execution_id)
    if not rows:
        return RECEIPT_STAGES[0], 1, None, None
    _, _, latest_path, latest = rows[-1]
    if latest["verdict"] != "pass":
        raise StageAuthorityError(
            f"latest predecessor is blocked at {latest['stage']}; create retryOf instead of jumping stages"
        )
    if latest["next"] == "END":
        raise StageAuthorityError("execution already reached END")
    return str(latest["next"]), int(latest["sequence"]) + 1, latest, latest_path

def _load_json(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise StageAuthorityError(f"{label} is not readable UTF-8 JSON: {path}") from exc
    if not isinstance(value, dict):
        raise StageAuthorityError(f"{label} must contain one JSON object: {path}")
    return value

def _validate_init_artifacts(execution_id: str) -> list[dict[str, str]]:
    root = _execution_root(execution_id)
    documents: dict[str, dict[str, Any]] = {}
    schemas = {
        "execution_manifest.json": "content_execution_manifest",
        "0.plan/request.json": "task_init_request",
        "0.plan/target_set.json": "target_set",
    }
    bindings: list[dict[str, str]] = []
    for ref in _INIT_REFS:
        path = root / ref
        document = _load_json(path, label=f"task init artifact {ref}")
        assert_valid(document, "execution", schemas[ref], label=f"task init artifact:{ref}")
        if document.get("executionId") != execution_id:
            raise StageAuthorityError(f"task init artifact executionId drift: {ref}")
        documents[ref] = document
        bindings.append(_binding(path, scope="execution", root=root))
    manifest = documents["execution_manifest.json"]
    request = documents["0.plan/request.json"]
    target_set = documents["0.plan/target_set.json"]
    target_digest = hashlib.sha256(
        json.dumps(
            target_set, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()
    if (
        manifest.get("requestRef") != "0.plan/request.json"
        or manifest.get("targetSetRef") != "0.plan/target_set.json"
        or manifest.get("targetSetDigest") != target_digest
        or not isinstance(target_set.get("candidateBinding"), Mapping)
        or any(
            request.get("candidateBinding", {}).get(field)
            != target_set.get("candidateBinding", {}).get(field)
            for field in ("ref", "digest")
        )
    ):
        raise StageAuthorityError("task init three-file identity/digest closure drifted")
    for field in ("carrierDemand", "candidateBinding"):
        exact = request.get(field)
        if not isinstance(exact, Mapping):
            raise StageAuthorityError(f"task init request lacks {field} binding")
        ref = str(exact.get("ref") or "")
        digest = str(exact.get("digest") or "")
        bound = paths.OUTPUT_ROOT / ref
        if not bound.is_file() or _sha256(bound.read_bytes()) != digest:
            raise StageAuthorityError(f"task init bound input missing or drifted: {field}")
    return bindings

def _open_core(execution_id: str, stage: str) -> dict[str, Any]:
    expected_stage, sequence, predecessor, predecessor_path = _current_stage(execution_id)
    if stage != expected_stage:
        raise StageAuthorityError(
            f"illegal stage jump: requested {stage}, current unique next is {expected_stage}"
        )
    init_artifacts = _validate_init_artifacts(execution_id) if stage == "0.plan" else []
    predecessor_binding = None
    if predecessor is not None and predecessor_path is not None:
        predecessor_binding = _binding(
            predecessor_path,
            scope="execution",
            root=_execution_root(execution_id),
        )
    release_binding = None
    if stage == "ship" and predecessor is not None:
        release_binding = (predecessor.get("authority") or {}).get("releaseBinding")
        if not isinstance(release_binding, Mapping):
            raise StageAuthorityError("ship open predecessor lacks releaseBinding")
    return {
        "schema": OPEN_SCHEMA,
        "executionId": execution_id,
        "stage": stage,
        "sequence": sequence,
        "workflowContract": _workflow_binding(),
        "predecessor": predecessor_binding,
        "initArtifacts": init_artifacts,
        "releaseBinding": release_binding,
    }

def open_stage(execution_id: str, stage: str) -> Path:
    """冻结当前唯一合法 stage 的 open request；不选择候选且不执行 stage。"""
    if stage not in _STAGE_INDEX:
        raise StageAuthorityError(f"unknown stage: {stage}")
    rows = _validate_receipt_chain(execution_id)
    if rows and rows[-1][1] == stage:
        sequence = rows[-1][0]
        target = _authority_dir(execution_id, sequence, stage) / "open.json"
        existing = _load_json(target, label="stage open request")
        assert_valid(existing, "execution", "stage_open_request", label="stage open request")
        _validate_workflow(existing["workflowContract"])
        for binding in existing["initArtifacts"]:
            _resolve_binding(execution_id, binding)
        if existing["predecessor"] is not None:
            _resolve_binding(execution_id, existing["predecessor"])
        return target
    core = _open_core(execution_id, stage)
    target = _authority_dir(execution_id, int(core["sequence"]), stage) / "open.json"
    if target.is_file():
        existing = _load_json(target, label="stage open request")
        assert_valid(existing, "execution", "stage_open_request", label="stage open request")
        comparable = {key: value for key, value in existing.items() if key != "openedAt"}
        if comparable != core:
            raise StageAuthorityConflict(f"stage open create-once conflict: {target}")
        _validate_workflow(existing["workflowContract"])
        for binding in existing["initArtifacts"]:
            _resolve_binding(execution_id, binding)
        if existing["predecessor"] is not None:
            _resolve_binding(execution_id, existing["predecessor"])
        return target
    payload = {**core, "openedAt": _now_iso()}
    assert_valid(payload, "execution", "stage_open_request", label="stage open request")
    return _write_create_once(target, payload)

def _validate_acceptance(context: Mapping[str, Any]) -> dict[str, str]:
    from quwoquan_ops.cli.lib.environment_acceptance_fact import (
        EnvironmentAcceptanceFactError,
        load_environment_acceptance_fact,
    )

    ref = str(context["environmentAcceptanceFactRef"])
    relative = Path(ref)
    if relative.is_absolute() or ".." in relative.parts:
        raise StageAuthorityError("ship EnvironmentAcceptanceFact ref must be output-relative")
    try:
        fact, digest = load_environment_acceptance_fact(
            ref, evidence_root=paths.OUTPUT_ROOT,
            required_target_profiles=context["requiredTargetProfiles"],
            verify_references=True,
        )
    except EnvironmentAcceptanceFactError as exc:
        raise StageAuthorityError(f"ship EnvironmentAcceptanceFact rejected: {exc}") from exc
    if digest != context["environmentAcceptanceFactDigest"]:
        raise StageAuthorityError("ship EnvironmentAcceptanceFact exact-byte digest drifted")
    if (
        fact.get("acceptanceProfile") != context["acceptanceProfile"]
        or fact.get("releaseId") != context["releaseId"]
        or fact.get("releaseDigest") != context["releaseDigest"]
        or fact.get("environment") != context["environment"]
        or fact.get("target") != context["target"]
        or fact.get("importRunId") != context["importRunId"]
        or fact.get("verifyRunId") != context["verifyRunId"]
    ):
        raise StageAuthorityError("ship EnvironmentAcceptanceFact release/environment identity drifted")
    return {"scope": "output", "ref": ref, "digest": digest, "environment": str(fact["environment"])}

def _release_binding(execution_id: str, context: Mapping[str, Any]) -> dict[str, str]:
    release_id = str(context["releaseId"])
    sample = paths.RELEASE_ROOT / release_id / "payload/uat/sample_plan.json"
    plan = _load_json(sample, label="release UAT sample plan")
    if plan.get("releaseId") != release_id or plan.get("releaseDigest") != context["releaseDigest"]:
        raise StageAuthorityError("releaseId/releaseDigest drifted from immutable sample plan")
    return _validate_release_authority(execution_id, context)

def _semantic_binding(
    execution_id: str, stage: str, context: Mapping[str, Any]
) -> tuple[dict[str, str] | None, list[dict[str, str]]]:
    if stage not in SEMANTIC_STAGES:
        return None, []
    root = _execution_root(execution_id)
    ref = str(context.get("semanticResultRef") or "")
    digest = str(context.get("semanticResultDigest") or "")
    candidate = _binding(root / ref, scope="execution", root=root)
    if candidate["digest"] != digest:
        raise StageAuthorityError("semantic result context digest differs from exact bytes")
    try:
        wrapper = read_stage_semantic_result(execution_id, stage, binding=candidate)
    except StageSemanticError as exc:
        raise StageAuthorityError(f"semantic result rejected: {exc}") from exc
    return candidate, [dict(item) for item in wrapper["resultBindings"]]

def _validate_ship_predecessor_release(
    execution_id: str, release_binding: Mapping[str, Any]
) -> None:
    rows = _validate_receipt_chain(execution_id)
    if not rows or rows[-1][1] != "release" or rows[-1][3].get("verdict") != "pass":
        raise StageAuthorityError("ship requires immediate passed release predecessor")
    predecessor_release = (rows[-1][3].get("authority") or {}).get("releaseBinding")
    if dict(release_binding) != predecessor_release:
        raise StageAuthorityError("ship releaseBinding differs from release predecessor authority")

def _default_runner(argv: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        list(argv), cwd=paths.REPO_ROOT, env=environment,
        capture_output=True, text=True, check=False,
    )

def run_stage_gate(
    execution_id: str,
    stage: str,
    *,
    close_context: Mapping[str, Any] | None = None,
    runner: Callable[[tuple[str, ...]], Any] | None = None,
) -> Path:
    """只执行 registry argv，冻结真实 exits/output 摘要与 artifact exact refs。"""
    from content.execution.stage_gate_registry import normalize_context

    if stage not in _STAGE_INDEX:
        raise StageAuthorityError(f"unknown stage: {stage}")
    try:
        context = normalize_context(stage, close_context)
    except ValueError as exc:
        raise StageAuthorityError(str(exc)) from exc
    context_digest = _sha256(_canonical_bytes(context))
    rows = _validate_receipt_chain(execution_id)
    replay_sequence = rows[-1][0] if rows and rows[-1][1] == stage else None
    if replay_sequence is not None:
        target = _authority_dir(execution_id, replay_sequence, stage) / "gate.json"
        existing = _load_json(target, label="machine gate receipt")
        assert_valid(existing, "execution", "stage_gate_receipt", label="machine gate receipt")
        if (
            existing.get("gateContext") != context
            or existing.get("gateContextDigest") != context_digest
        ):
            raise StageAuthorityConflict(f"stage gate create-once conflict: {target}")
        _validate_workflow(existing["workflowContract"])
        _resolve_binding(execution_id, existing["openRequest"])
        if existing["semanticResult"] is not None:
            try:
                read_stage_semantic_result(execution_id, stage, binding=existing["semanticResult"])
            except StageSemanticError as exc:
                raise StageAuthorityError(f"semantic result replay rejected: {exc}") from exc
        for binding in existing["artifacts"]:
            _resolve_binding(execution_id, binding)
        if stage == "ship":
            _validate_ship_predecessor_release(execution_id, existing["releaseBinding"])
            if existing["releaseBinding"] != _load_json(
                _authority_dir(execution_id, replay_sequence, stage) / "open.json",
                label="ship open request",
            ).get("releaseBinding"):
                raise StageAuthorityError("ship gate releaseBinding differs from ship open authority")
        return target
    open_path = open_stage(execution_id, stage)
    open_request = _load_json(open_path, label="stage open request")
    _validate_workflow(open_request["workflowContract"])
    expected_stage, sequence, _, _ = _current_stage(execution_id)
    if stage != expected_stage or sequence != open_request["sequence"]:
        raise StageAuthorityError("stage state changed after open request")
    target = _authority_dir(execution_id, sequence, stage) / "gate.json"
    if target.is_file():
        existing = _load_json(target, label="machine gate receipt")
        assert_valid(existing, "execution", "stage_gate_receipt", label="machine gate receipt")
        if (
            existing.get("gateContext") != context
            or existing.get("gateContextDigest") != context_digest
        ):
            raise StageAuthorityConflict(f"stage gate create-once conflict: {target}")
        _validate_workflow(existing["workflowContract"])
        _resolve_binding(execution_id, existing["openRequest"])
        if existing["semanticResult"] is not None:
            try:
                read_stage_semantic_result(execution_id, stage, binding=existing["semanticResult"])
            except StageSemanticError as exc:
                raise StageAuthorityError(f"semantic result replay rejected: {exc}") from exc
        for binding in existing["artifacts"]:
            _resolve_binding(execution_id, binding)
        if stage == "ship":
            _validate_ship_predecessor_release(execution_id, existing["releaseBinding"])
            if existing["releaseBinding"] != open_request.get("releaseBinding"):
                raise StageAuthorityError("ship gate releaseBinding differs from ship open authority")
        return target
    acceptance = _validate_acceptance(context) if stage == "ship" else None
    semantic_result, semantic_artifacts = _semantic_binding(execution_id, stage, context)
    execute = runner or _default_runner
    commands: list[dict[str, Any]] = []
    from content.execution.stage_gate_registry import registry_argv

    for command_id, argv in registry_argv(execution_id, stage, context):
        completed = execute(argv)
        stdout = str(getattr(completed, "stdout", "") or "")
        stderr = str(getattr(completed, "stderr", "") or "")
        exit_code = int(getattr(completed, "returncode"))
        commands.append({
            "commandId": command_id,
            "argv": list(argv),
            "exitCode": exit_code,
            "stdoutDigest": _sha256(stdout.encode("utf-8")),
            "stderrDigest": _sha256(stderr.encode("utf-8")),
        })
        if exit_code != 0:
            break
    artifacts = _artifact_bindings(execution_id, stage, context["artifactRefs"])
    artifacts.extend(semantic_artifacts)
    deduplicated: dict[tuple[str, str], dict[str, str]] = {}
    for item in artifacts:
        key = (item["scope"], item["ref"])
        existing = deduplicated.get(key)
        if existing is not None and existing != item:
            raise StageAuthorityError("gate artifact duplicate has conflicting digest")
        deduplicated[key] = item
    artifacts = sorted(deduplicated.values(), key=lambda item: (item["scope"], item["ref"]))
    _validate_required_artifact_closure(execution_id, stage, artifacts)
    release = _release_binding(execution_id, context) if stage in {"release", "ship"} else None
    if stage == "ship" and release is not None:
        _validate_ship_predecessor_release(execution_id, release)
        if release != open_request.get("releaseBinding"):
            raise StageAuthorityError("ship gate releaseBinding differs from ship open authority")
    open_binding = _binding(open_path, scope="execution", root=_execution_root(execution_id))
    payload = {
        "schema": GATE_SCHEMA,
        "executionId": execution_id,
        "stage": stage,
        "sequence": sequence,
        "openRequest": open_binding,
        "workflowContract": dict(open_request["workflowContract"]),
        "semanticResult": semantic_result,
        "gateContext": context,
        "gateContextDigest": context_digest,
        "commands": commands,
        "artifacts": artifacts,
        "releaseBinding": release,
        "acceptanceBinding": acceptance,
        "gatedAt": _now_iso(),
    }
    assert_valid(payload, "execution", "stage_gate_receipt", label="machine gate receipt")
    return _write_create_once(target, payload)

from content.execution.stage_authority_close import (
    close_stage,
    normalize_typed_issues as _normalize_typed_issues,
    validate_required_artifact_closure as _validate_required_artifact_closure,
)

from content.execution.stage_authority_validation import (
    validate_release_authority as _validate_release_authority,
    validate_stage_receipt_authority,
)

__all__ = [
    "StageAuthorityConflict", "StageAuthorityError", "close_stage", "open_stage",
    "run_stage_gate", "validate_stage_receipt_authority",
]
