"""通用语义 stage 的确定性 prepare / validate / create-once recorder。"""
from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from content.execution.operational_fingerprint import POLICY_PATH, operational_fingerprint
from content.execution.production_contracts import validate_agent_result_envelope
from content.execution.stage_receipt import list_receipt_files
from core import paths
from core.rubric_judge import review_rigor_issues
from core.schema import assert_valid
from core.stage_artifact_contract import SOURCE_UNIT_ARTIFACTS

SEMANTIC_STAGES = ("sources", "2.quality", "3.compose", "4.draft", "5.review")
SEMANTIC_ROOT_REF = "_shared/stage-semantics"
REQUEST_SCHEMA = "quwoquan_data.stage_semantic_request"
RESULT_INPUT_SCHEMA = "quwoquan_data.stage_semantic_result_input"
RESULT_SCHEMA = "quwoquan_data.stage_semantic_result"


class StageSemanticError(ValueError):
    """语义 request/result 输入拒绝；公开 CLI 映射退出码 2。"""


class StageSemanticConflict(StageSemanticError):
    """create-once slot 存在不同字节；公开 CLI 映射退出码 3。"""


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _sha256(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _execution_root(execution_id: str) -> Path:
    return paths.DATA_EXECUTIONS_ROOT / execution_id


def _semantic_dir(execution_id: str, sequence: int, stage: str) -> Path:
    return _execution_root(execution_id) / SEMANTIC_ROOT_REF / f"{sequence:03d}-{stage}"


def _safe_path(root: Path, ref: object, *, label: str, require_file: bool = True) -> Path:
    relative = Path(str(ref or ""))
    if not str(relative) or relative.is_absolute() or ".." in relative.parts:
        raise StageSemanticError(f"{label} must be a safe execution-relative ref")
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise StageSemanticError(f"{label} traverses a symlink: {ref}")
    resolved = current.resolve(strict=require_file)
    try:
        resolved.relative_to(root.resolve(strict=True))
    except ValueError as exc:
        raise StageSemanticError(f"{label} escapes execution root: {ref}") from exc
    if require_file and not resolved.is_file():
        raise StageSemanticError(f"{label} must be a regular file: {ref}")
    return resolved


def _binding(root: Path, path: Path) -> dict[str, str]:
    resolved = _safe_path(root, path.relative_to(root).as_posix(), label="binding")
    return {
        "scope": "execution",
        "ref": resolved.relative_to(root).as_posix(),
        "digest": _sha256(resolved.read_bytes()),
    }


def _resolve_binding(execution_id: str, value: Mapping[str, Any], *, label: str) -> Path:
    if set(value) != {"scope", "ref", "digest"} or value.get("scope") != "execution":
        raise StageSemanticError(f"{label} must be one execution exact binding")
    root = _execution_root(execution_id)
    path = _safe_path(root, value.get("ref"), label=label)
    actual = _sha256(path.read_bytes())
    if actual != value.get("digest"):
        raise StageSemanticError(
            f"{label} exact-byte digest drift: {value.get('ref')}; expected {value.get('digest')}, got {actual}"
        )
    return path


def _write_create_once(
    path: Path, payload: Mapping[str, Any], *, replay_ignored: frozenset[str] = frozenset()
) -> Path:
    body = _canonical_bytes(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        if path.is_file() and not path.is_symlink():
            if path.read_bytes() == body:
                return path
            if replay_ignored:
                existing = _load_json(path, label="create-once semantic document")
                left = {key: value for key, value in existing.items() if key not in replay_ignored}
                right = {key: value for key, value in payload.items() if key not in replay_ignored}
                if left == right:
                    return path
        raise StageSemanticConflict(f"create-once conflict: {path}") from None
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return path


def _load_json(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise StageSemanticError(f"{label} is not readable UTF-8 JSON: {path}") from exc
    if not isinstance(value, dict):
        raise StageSemanticError(f"{label} must contain one JSON object: {path}")
    return value


def _workflow_binding() -> dict[str, str]:
    return {
        "scope": "repo",
        "ref": POLICY_PATH.relative_to(paths.REPO_ROOT).as_posix(),
        "digest": operational_fingerprint(repo_root=paths.REPO_ROOT),
    }


def _validate_workflow(binding: Mapping[str, Any]) -> None:
    expected = _workflow_binding()
    if dict(binding) != expected:
        raise StageSemanticError(
            f"workflow contract digest drift: expected {binding.get('digest')}, got {expected['digest']}"
        )


def _stage_open(
    execution_id: str, stage: str, *, verify_current_workflow: bool = True
) -> tuple[dict[str, Any], Path]:
    if stage not in SEMANTIC_STAGES:
        raise StageSemanticError(f"stage has no semantic recorder: {stage}")
    entries = list_receipt_files(execution_id)
    matching = next((row for row in entries if row[1] == stage), None)
    sequence = matching[0] if matching is not None else len(entries) + 1
    path = _execution_root(execution_id) / "_shared/stage-authority" / f"{sequence:03d}-{stage}" / "open.json"
    value = _load_json(path, label="stage open request")
    assert_valid(value, "execution", "stage_open_request", label="stage open request")
    if (
        value.get("executionId") != execution_id
        or value.get("stage") != stage
        or value.get("sequence") != sequence
    ):
        raise StageSemanticError("stage open execution/stage/sequence identity drift")
    if verify_current_workflow:
        _validate_workflow(value["workflowContract"])
    return value, path


def _files(root: Path, patterns: Sequence[str]) -> set[Path]:
    found: set[Path] = set()
    excluded_roots = {"stage-authority", "stage-semantics", "receipts"}
    for pattern in patterns:
        for path in root.glob(pattern):
            relative = path.relative_to(root)
            if (
                path.is_symlink()
                or any(parent.is_symlink() for parent in path.parents if parent != root.parent)
            ):
                raise StageSemanticError(f"semantic input closure contains symlink: {path}")
            if "_shared" in relative.parts and excluded_roots & set(relative.parts):
                continue
            if path.is_file():
                _safe_path(root, relative.as_posix(), label="semantic input")
                found.add(path.resolve())
    return found


def _source_unit_closure(root: Path) -> set[Path]:
    units = sorted(root.glob("sources/*"))
    if not units:
        raise StageSemanticError("sources semantic closure requires at least one source unit")
    found: set[Path] = set()
    for unit in units:
        if unit.is_symlink() or not unit.is_dir():
            raise StageSemanticError(f"sources entry must be a real directory: {unit}")
        for relative in SOURCE_UNIT_ARTIFACTS:
            path = unit / relative
            found.add(_safe_path(root, path.relative_to(root).as_posix(), label="source unit input"))
    return found


def _semantic_input_paths(execution_id: str, stage: str) -> list[Path]:
    root = _execution_root(execution_id)
    init = {root / ref for ref in ("execution_manifest.json", "0.plan/request.json", "0.plan/target_set.json")}
    if stage == "sources":
        paths_found = init
    elif stage == "2.quality":
        download = _files(root, ("**/1.download/*", "**/1.download/**/*"))
        if not download:
            raise StageSemanticError("2.quality semantic closure lacks 1.download inputs")
        paths_found = _source_unit_closure(root) | download
    elif stage == "3.compose":
        quality = _files(root, ("**/2.quality/*", "**/2.quality/**/*"))
        if not quality:
            raise StageSemanticError("3.compose semantic closure lacks 2.quality inputs")
        paths_found = quality | _source_unit_closure(root)
    elif stage == "4.draft":
        compose = _files(root, ("**/3.compose/*", "**/3.compose/**/*"))
        writing = _files(root, (
            "**/4.draft/prompt.md", "**/4.draft/prompt_snapshot.json",
            "**/4.draft/author_job_packet.json",
        ))
        if not compose or not writing:
            raise StageSemanticError("4.draft semantic closure lacks compose or prompt writing inputs")
        paths_found = compose | writing
    else:
        draft = _files(root, ("**/4.draft/*", "**/4.draft/**/*"))
        compose = _files(root, ("**/3.compose/*", "**/3.compose/**/*"))
        quality = _files(root, ("**/2.quality/*", "**/2.quality/**/*"))
        if not draft or not compose or not quality:
            raise StageSemanticError("5.review semantic closure lacks draft/compose/quality inputs")
        paths_found = draft | compose | quality
    normalized = sorted({_safe_path(root, path.relative_to(root).as_posix(), label="semantic input") for path in paths_found}, key=lambda item: item.relative_to(root).as_posix())
    if not normalized:
        raise StageSemanticError(f"{stage} semantic input closure is empty")
    return normalized


def _stable_request(
    execution_id: str, stage: str, *, verify_current_workflow: bool = True
) -> tuple[dict[str, Any], Path]:
    open_request, open_path = _stage_open(
        execution_id, stage, verify_current_workflow=verify_current_workflow
    )
    root = _execution_root(execution_id)
    stable = {
        "schema": REQUEST_SCHEMA,
        "executionId": execution_id,
        "stage": stage,
        "sequence": int(open_request["sequence"]),
        "workflowContract": dict(open_request["workflowContract"]),
        "openRequest": _binding(root, open_path),
        "inputBindings": [_binding(root, path) for path in _semantic_input_paths(execution_id, stage)],
    }
    return stable, _semantic_dir(execution_id, int(open_request["sequence"]), stage) / "request.json"


def prepare_stage_semantic_request(execution_id: str, stage: str) -> Path:
    """从 stage registry 规则确定性发现输入闭包并 create-once 冻结 request。"""
    stable, target = _stable_request(execution_id, stage)
    if target.is_file():
        existing = _load_json(target, label="stage semantic request")
        assert_valid(existing, "execution", "stage_semantic_request", label="stage semantic request")
        comparable = {key: value for key, value in existing.items() if key not in {"requestDigest", "preparedAt"}}
        if comparable != stable:
            raise StageSemanticConflict(f"stage semantic request create-once conflict: {target}")
        expected_digest = _sha256(_canonical_bytes(stable))
        if existing.get("requestDigest") != expected_digest:
            raise StageSemanticConflict(f"stage semantic request digest conflict: {target}")
        read_stage_semantic_request(execution_id, stage)
        return target
    payload = {**stable, "requestDigest": _sha256(_canonical_bytes(stable)), "preparedAt": _now_iso()}
    assert_valid(payload, "execution", "stage_semantic_request", label="stage semantic request")
    return _write_create_once(target, payload)


def read_stage_semantic_request(
    execution_id: str, stage: str, *, verify_current_workflow: bool = True
) -> dict[str, Any]:
    stable, target = _stable_request(
        execution_id, stage, verify_current_workflow=verify_current_workflow
    )
    value = _load_json(target, label="stage semantic request")
    assert_valid(value, "execution", "stage_semantic_request", label="stage semantic request")
    comparable = {key: item for key, item in value.items() if key not in {"requestDigest", "preparedAt"}}
    if comparable != stable or value.get("requestDigest") != _sha256(_canonical_bytes(stable)):
        raise StageSemanticError("stage semantic request closure/digest drift")
    _resolve_binding(execution_id, value["openRequest"], label="semantic request openRequest")
    for binding in value["inputBindings"]:
        _resolve_binding(execution_id, binding, label="semantic request input")
    return value


def _is_stage_ref(stage: str, ref: str) -> bool:
    parts = Path(ref).parts
    try:
        index = parts.index(stage)
    except ValueError:
        return False
    return index >= 1 and index == len(parts) - 2


def _allowed_result_schema(stage: str, path: Path) -> tuple[str, str] | None:
    name = path.name
    allowed = {
        "2.quality": {"quality_analysis.json": ("content", "quality_analysis")},
        "3.compose": {
            "writing_pack.json": ("content", "writing_pack"),
            "entity_page_input.json": ("content", "entity_page_input"),
        },
        "4.draft": {"agent_result_envelope.json": ("content", "agent_result_envelope")},
        "5.review": {
            "reviewer_result.json": ("content", "reviewer_result"),
            "rubric_review.json": ("content", "rubric_review"),
        },
    }
    return allowed.get(stage, {}).get(name)


def _validate_source_results(execution_id: str, refs: Sequence[str]) -> list[Path]:
    root = _execution_root(execution_id)
    expected = sorted(path.relative_to(root).as_posix() for path in _source_unit_closure(root))
    if sorted(refs) != expected:
        raise StageSemanticError("sources resultRefs must equal the canonical source unit closure")
    paths_out = [_safe_path(root, ref, label="sources resultRef") for ref in refs]
    meta_paths = [path for path in paths_out if path.name == "meta.json"]
    for path in meta_paths:
        document = _load_json(path, label="source unit meta")
        assert_valid(document, "source", "source_unit_meta", label=f"source unit meta:{path}")
        if document.get("executionId") != execution_id:
            raise StageSemanticError(f"source unit executionId drift: {path}")
    return paths_out


def _validate_result_paths(execution_id: str, stage: str, refs: Sequence[str], actor: Mapping[str, Any]) -> list[Path]:
    if sorted(refs) != list(refs) or len(set(refs)) != len(refs):
        raise StageSemanticError("resultRefs must be unique and sorted by path")
    if stage == "sources":
        return _validate_source_results(execution_id, refs)
    root = _execution_root(execution_id)
    paths_out: list[Path] = []
    schemas_seen: set[str] = set()
    for ref in refs:
        if not _is_stage_ref(stage, ref):
            raise StageSemanticError(f"resultRef is outside {stage} allowlist: {ref}")
        path = _safe_path(root, ref, label="resultRef")
        schema = _allowed_result_schema(stage, path)
        if schema is None:
            raise StageSemanticError(f"resultRef is not a canonical {stage} semantic output: {ref}")
        document = _load_json(path, label=f"{stage} semantic result")
        assert_valid(document, *schema, label=f"{stage} semantic result:{ref}")
        if path.name != "rubric_review.json" and document.get("executionId") != execution_id:
            raise StageSemanticError(f"semantic result executionId drift: {ref}")
        if stage == "4.draft":
            envelope_issues = validate_agent_result_envelope(document, workspace_root=path.parent)
            if envelope_issues:
                raise StageSemanticError(f"agent result envelope invalid: {envelope_issues[0]}")
            agent = document.get("agent") if isinstance(document.get("agent"), Mapping) else {}
            invocation = actor.get("invocation") if isinstance(actor.get("invocation"), Mapping) else {}
            if (
                agent.get("provider") != invocation.get("provider")
                or agent.get("model") != invocation.get("model")
                or agent.get("runId") != invocation.get("runId")
            ):
                raise StageSemanticError("agent_result_envelope actor differs from canonical actor attestation")
        if stage == "5.review" and path.name == "reviewer_result.json":
            invocation = actor.get("invocation") if isinstance(actor.get("invocation"), Mapping) else {}
            if (
                document.get("provider") != invocation.get("provider")
                or document.get("model") != invocation.get("model")
                or document.get("modelFamily") != actor.get("modelFamily")
                or document.get("runId") != invocation.get("runId")
            ):
                raise StageSemanticError("reviewer_result actor differs from canonical actor attestation")
        schemas_seen.add(path.name)
        paths_out.append(path)
    required = {
        "2.quality": {"quality_analysis.json"},
        "4.draft": {"agent_result_envelope.json"},
        "5.review": {"reviewer_result.json", "rubric_review.json"},
    }
    if stage == "3.compose":
        if not schemas_seen or not schemas_seen <= {"writing_pack.json", "entity_page_input.json"}:
            raise StageSemanticError("3.compose requires writing_pack.json or entity_page_input.json")
    elif not required[stage] <= schemas_seen:
        raise StageSemanticError(f"{stage} resultRefs miss required semantic output: {sorted(required[stage] - schemas_seen)}")
    return paths_out


def _draft_actor(
    execution_id: str, *, verify_current_workflow: bool = True
) -> dict[str, Any]:
    rows = list_receipt_files(execution_id)
    draft = next((row for row in rows if row[1] == "4.draft"), None)
    if draft is None:
        raise StageSemanticError("5.review requires completed 4.draft receipt")
    receipt = _load_json(draft[2], label="4.draft receipt")
    authority = receipt.get("authority") if isinstance(receipt.get("authority"), Mapping) else {}
    semantic = authority.get("semanticResult") if isinstance(authority, Mapping) else None
    if not isinstance(semantic, Mapping):
        raise StageSemanticError("5.review requires named 4.draft semantic result binding")
    wrapper = read_stage_semantic_result(
        execution_id, "4.draft", binding=semantic,
        verify_current_workflow=verify_current_workflow,
    )
    actor = wrapper.get("actor")
    if not isinstance(actor, Mapping):
        raise StageSemanticError("5.review requires canonical 4.draft actor")
    family = str(actor.get("modelFamily") or "").strip()
    if not family or family.lower() == "auto":
        raise StageSemanticError("5.review requires named 4.draft modelFamily")
    return dict(actor)


def _draft_model_family(
    execution_id: str, *, verify_current_workflow: bool = True
) -> str:
    return str(_draft_actor(
        execution_id, verify_current_workflow=verify_current_workflow
    )["modelFamily"])


def _validate_review_independence(
    execution_id: str, actor: Mapping[str, Any], paths_in: Sequence[Path], *,
    verify_current_workflow: bool = True,
) -> None:
    draft_actor = _draft_actor(
        execution_id, verify_current_workflow=verify_current_workflow
    )
    generation_family = str(draft_actor["modelFamily"])
    review_family = str(actor.get("modelFamily") or "").strip()
    draft_invocation = draft_actor.get("invocation") if isinstance(draft_actor.get("invocation"), Mapping) else {}
    review_invocation = actor.get("invocation") if isinstance(actor.get("invocation"), Mapping) else {}
    if actor.get("sessionId") == draft_actor.get("sessionId"):
        raise StageSemanticError("5.review host sessionId must differ from 4.draft")
    if review_invocation.get("runId") == draft_invocation.get("runId"):
        raise StageSemanticError("5.review invocation.runId must differ from 4.draft")
    if review_family == generation_family:
        raise StageSemanticError(
            f"5.review modelFamily must differ from 4.draft: {review_family}"
        )
    for path in paths_in:
        if path.name != "rubric_review.json":
            continue
        review = _load_json(path, label="rubric review")
        issues = review_rigor_issues(review, generation_model_family=generation_family)
        if issues:
            raise StageSemanticError(f"rubric independence rejected: {issues[0]}")


def _request_from_input(execution_id: str, stage: str, result_input: Mapping[str, Any]) -> dict[str, Any]:
    request = read_stage_semantic_request(execution_id, stage)
    canonical_ref = _semantic_dir(execution_id, int(request["sequence"]), stage).relative_to(_execution_root(execution_id)) / "request.json"
    if result_input.get("requestRef") != canonical_ref.as_posix():
        raise StageSemanticError("result input requestRef differs from canonical request")
    if result_input.get("requestDigest") != request.get("requestDigest"):
        raise StageSemanticError("result input requestDigest differs from frozen request")
    return request


def record_stage_semantic_result(execution_id: str, stage: str, result_input: Mapping[str, Any]) -> Path:
    """校验 actor 与 stage outputs，create-once 写 canonical result wrapper。"""
    try:
        assert_valid(dict(result_input), "execution", "stage_semantic_result_input", label="stage semantic result input")
    except (FileNotFoundError, TypeError, ValueError) as exc:
        raise StageSemanticError(str(exc)) from exc
    actor = dict(result_input["actor"])
    request = _request_from_input(execution_id, stage, result_input)
    refs = [str(ref) for ref in result_input["resultRefs"]]
    result_paths = _validate_result_paths(execution_id, stage, refs, actor)
    if stage == "5.review":
        _validate_review_independence(execution_id, actor, result_paths)
    root = _execution_root(execution_id)
    stable = {
        "schema": RESULT_SCHEMA,
        "executionId": execution_id,
        "stage": stage,
        "sequence": int(request["sequence"]),
        "workflowContract": dict(request["workflowContract"]),
        "requestRef": str(result_input["requestRef"]),
        "requestDigest": str(result_input["requestDigest"]),
        "actor": actor,
        "resultBindings": [_binding(root, path) for path in result_paths],
    }
    payload = {
        **stable,
        "recordedAt": _now_iso(),
        "resultDigest": _sha256(_canonical_bytes(stable)),
    }
    assert_valid(payload, "execution", "stage_semantic_result", label="stage semantic result")
    target = _semantic_dir(execution_id, int(request["sequence"]), stage) / "result.json"
    path = _write_create_once(target, payload, replay_ignored=frozenset({"recordedAt", "resultDigest"}))
    read_stage_semantic_result(execution_id, stage)
    return path


def read_stage_semantic_result(
    execution_id: str,
    stage: str,
    *,
    binding: Mapping[str, Any] | None = None,
    verify_current_workflow: bool = True,
) -> dict[str, Any]:
    request = read_stage_semantic_request(
        execution_id, stage, verify_current_workflow=verify_current_workflow
    )
    target = _semantic_dir(execution_id, int(request["sequence"]), stage) / "result.json"
    if binding is not None:
        resolved = _resolve_binding(execution_id, binding, label="semantic result")
        if resolved != target.resolve(strict=True):
            raise StageSemanticError("semantic result binding is not canonical for stage")
    value = _load_json(target, label="stage semantic result")
    assert_valid(value, "execution", "stage_semantic_result", label="stage semantic result")
    if (
        value.get("executionId") != execution_id
        or value.get("stage") != stage
        or value.get("sequence") != request.get("sequence")
        or value.get("workflowContract") != request.get("workflowContract")
        or value.get("requestDigest") != request.get("requestDigest")
    ):
        raise StageSemanticError("stage semantic result request/workflow/identity drift")
    expected_request_ref = target.parent.relative_to(_execution_root(execution_id)) / "request.json"
    if value.get("requestRef") != expected_request_ref.as_posix():
        raise StageSemanticError("stage semantic result requestRef drift")
    stable = {key: item for key, item in value.items() if key not in {"recordedAt", "resultDigest"}}
    if value.get("resultDigest") != _sha256(_canonical_bytes(stable)):
        raise StageSemanticError("stage semantic resultDigest drift")
    actor = value["actor"]
    paths_in = [_resolve_binding(execution_id, item, label="semantic result binding") for item in value["resultBindings"]]
    _validate_result_paths(execution_id, stage, [item.relative_to(_execution_root(execution_id)).as_posix() for item in paths_in], actor)
    if stage == "5.review":
        _validate_review_independence(
            execution_id, actor, paths_in,
            verify_current_workflow=verify_current_workflow,
        )
    return value


def derive_stage_semantic_issues(
    execution_id: str, stage: str, *, binding: Mapping[str, Any],
    verify_current_workflow: bool = True,
) -> list[dict[str, str]]:
    """从 canonical semantic outputs 派生不可被调用者抵消的 stage issues。"""
    wrapper = read_stage_semantic_result(
        execution_id, stage, binding=binding,
        verify_current_workflow=verify_current_workflow,
    )
    root = _execution_root(execution_id)
    documents = {
        Path(str(item["ref"])).name: _load_json(
            root / str(item["ref"]), label=f"{stage} semantic verdict input"
        )
        for item in wrapper["resultBindings"]
        if str(item["ref"]).endswith(".json")
    }
    issues: list[dict[str, str]] = []
    if stage == "2.quality":
        quality = documents.get("quality_analysis.json", {})
        if quality.get("recommendation") != "proceed":
            issues.append({
                "code": "DATA.STAGE.QUALITY_NOT_PROCEED",
                "message": f"quality recommendation is {quality.get('recommendation')!r}",
                "recoveryStage": "2.quality",
            })
    if stage == "5.review":
        reviewer = documents.get("reviewer_result.json", {})
        rubric = documents.get("rubric_review.json", {})
        if reviewer.get("verdict") != "passed":
            issues.append({
                "code": "DATA.STAGE.REVIEW_NOT_PASSED",
                "message": f"review verdict is {reviewer.get('verdict')!r}",
                "recoveryStage": "4.draft",
            })
        if rubric.get("decision") != "approved" or any(
            isinstance(item, Mapping) and item.get("verdict") != "pass"
            for item in rubric.get("dimensions", [])
        ):
            issues.append({
                "code": "DATA.STAGE.RUBRIC_NOT_APPROVED",
                "message": f"rubric decision is {rubric.get('decision')!r}",
                "recoveryStage": "4.draft",
            })
    return issues


__all__ = [
    "SEMANTIC_STAGES", "StageSemanticConflict", "StageSemanticError",
    "prepare_stage_semantic_request", "read_stage_semantic_request",
    "read_stage_semantic_result", "record_stage_semantic_result",
    "derive_stage_semantic_issues",
]
