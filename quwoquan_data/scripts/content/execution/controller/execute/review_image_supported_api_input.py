"""Run independent governed semantic reviews for supported-API image inputs."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.control_types import AgentProvider
from core.io import read_json
from core.paths import OUTPUT_ROOT
from core.runtime_policy import active_runtime_policy
from core.schema import assert_valid

from content.execution import store
from content.execution.agent.outcome import AgentRunOutcome
from content.execution.context import ExecutionContext
from content.execution.model_contract import (
    cursor_grok_binding_mismatch,
    governed_cursor_grok_model,
    semantic_execution_binding_for_execution,
)
from content.execution.workspace import execution_root, load_frozen_execution_manifest
from content.execution.controller.execute.image_supported_api_batch import (
    image_batch_result,
    run_isolated_image_objects,
)
from content.execution.controller.execute.image_supported_api_review_storage import (
    canonical_digest as _digest,
    copy_review_file_once as _copy_create_once,
    portable_review_ref,
    safe_review_file as _safe_file,
    safe_review_ref as _safe_ref,
    validate_review_dependencies as _validate_review_dependencies,
    write_review_json_once as _write_create_once,
)
from content.execution.controller.execute.image_supported_api_review_result import (
    image_review_judgment,
    image_review_passed as _review_passed,
    image_review_summary,
)
from content.source.pre_acquisition_handoff import (
    guard_acquisition_source_identity,
)
from content.source.professional_image_supported_api_contract import load_document
from content.source.professional_safety_evidence import file_sha256
from content.source.source_review_journal import run_source_review


class ProfessionalImageSupportedApiReviewError(RuntimeError):
    """Typed review admission or provider-result failure."""

    def __init__(
        self,
        message: str,
        *,
        batch_fatal: bool = False,
        batch_result: Mapping[str, Any] | None = None,
        evidence_ref: str = "",
        evidence_sha256: str = "",
    ) -> None:
        code, separator, detail = message.partition(":")
        self.code = code.strip() if separator else "DATA.SOURCE.REVIEW_ASSET_EXCLUDED"
        self.detail = detail.strip() if separator else message
        self.batch_fatal = batch_fatal
        self.batch_result = dict(batch_result) if batch_result is not None else None
        self.evidence_ref = evidence_ref
        self.evidence_sha256 = evidence_sha256
        super().__init__(message)


def _portable_ref(path: Path) -> str:
    return portable_review_ref(path, output_root=OUTPUT_ROOT)


def _review_request_with_current_contract(
    source: Path, *, source_mode: bool = False,
) -> dict[str, Any]:
    """Derive today's immutable reviewer request from frozen physical inputs."""
    del source_mode
    request = read_json(source)
    if not isinstance(request, dict):
        raise ProfessionalImageSupportedApiReviewError(
            "DATA.SOURCE.REVIEW_INPUT_INVALID: request must be an object"
        )
    assert_valid(
        request,
        "source",
        "professional_image_supported_api_review_request",
        label=f"supported API reviewer request:{source}",
    )
    return request


def _source_review_identity(
    *, handoff: Mapping[str, Any], request: Mapping[str, Any], handoff_ref: Path,
) -> dict[str, str]:
    source = handoff.get("sourceDigest")
    bundle = handoff.get("executionBundle")
    if not isinstance(source, Mapping) or not isinstance(bundle, Mapping):
        raise ProfessionalImageSupportedApiReviewError(
            "DATA.SOURCE.REVIEW_HANDOFF_INVALID: frozen source/bundle identity is missing"
        )
    identity = {
        "sourceRevision": str(handoff.get("sourceRevision") or ""),
        "sourceDigest": str(source.get("digest") or ""),
        "entityCatalogDigest": str(handoff.get("entityCatalogDigest") or ""),
        "executionBundleDigest": str(bundle.get("digest") or ""),
        "handoffDigest": file_sha256(handoff_ref),
        "requestDigest": str(request.get("requestDigest") or ""),
    }
    if any(not value.startswith("sha256:") for value in identity.values()):
        raise ProfessionalImageSupportedApiReviewError(
            "DATA.SOURCE.REVIEW_HANDOFF_INVALID: source review identity is malformed"
        )
    return identity


def _source_runner(prompt: str) -> AgentRunOutcome:
    """Run the governed Cursor reviewer without inventing an execution identity."""
    from content.execution.agent.agent_worker import run_source_review_agent_isolated

    policy = active_runtime_policy()
    selection = policy.explicit_semantic_selection("cursor_grok").binding
    return run_source_review_agent_isolated(
        runtime=policy.explicit_semantic_selection("cursor_grok").runtime,
        model_selection=selection.selection,
        prompt=prompt,
    )


def _review_summary(result: Mapping[str, Any], path: Path) -> dict[str, Any]:
    return image_review_summary(result, path, output_root=OUTPUT_ROOT)


def _raise_if_review_blocked(result: Mapping[str, Any], path: Path) -> None:
    judgment = result["judgment"]
    if isinstance(judgment, Mapping) and _review_passed(judgment):
        return
    findings = "; ".join(str(value) for value in (judgment.get("findings") or []))
    raise ProfessionalImageSupportedApiReviewError(
        "DATA.SOURCE.REVIEW_GATE_BLOCKED: "
        + (findings or "review judgment did not pass"),
        evidence_ref=_portable_ref(path),
        evidence_sha256=file_sha256(path),
    )


def _source_review_one(
    _candidate_id: str,
    work: Mapping[str, Any],
    *,
    root: Path,
    model: str,
    runner: Callable[[str], AgentRunOutcome],
) -> dict[str, Any]:
    request_path = work["requestPath"]
    request = work["request"]
    identity = work["identity"]
    token = hashlib.sha256(str(request["candidateId"]).encode()).hexdigest()[:20]
    result_path = root / "source-reviews" / "results" / f"{token}.json"
    if result_path.is_file():
        try:
            existing = load_document(
                result_path,
                group="source",
                name="professional_image_supported_api_reviewer_result",
            )
        except (OSError, TypeError, ValueError) as exc:
            raise ProfessionalImageSupportedApiReviewError(
                f"DATA.SOURCE.REVIEW_CREATE_ONCE_CONFLICT: {exc}",
                batch_fatal=True,
            ) from exc
        if (
            existing.get("sourceReview") != identity
            or existing.get("reviewRequestSha256") != file_sha256(request_path)
            or existing.get("contentSha256") != request["contentSha256"]
        ):
            raise ProfessionalImageSupportedApiReviewError(
                "DATA.SOURCE.REVIEW_CREATE_ONCE_CONFLICT: existing result identity drift",
                batch_fatal=True,
            )
        _raise_if_review_blocked(existing, result_path)
        return _review_summary(existing, result_path)
    journal, _attempt_path = run_source_review(
        source_evidence_root=root,
        source_review=identity,
        model=model,
        prompt=request_path.read_text(encoding="utf-8"),
        runner=runner,
    )
    outcome = journal["outcome"]
    if not outcome.succeeded or outcome.provider is not AgentProvider.CURSOR_SDK:
        kind = outcome.failure_kind.value if outcome.failure_kind else "provider_mismatch"
        raise ProfessionalImageSupportedApiReviewError(
            f"DATA.AGENT.REVIEW_FAILED: {kind}:{outcome.error_code or 'no_code'}"
        )
    if not outcome.run_id:
        raise ProfessionalImageSupportedApiReviewError(
            "DATA.AGENT.REVIEW_INVALID: provider runId is empty"
        )
    judgment = image_review_judgment(outcome.result_text)
    if judgment is None:
        raise ProfessionalImageSupportedApiReviewError(
            "DATA.AGENT.REVIEW_INVALID: reviewer did not return the exact judgment object"
        )
    attempt = journal["attempt"]
    result = {
        "schema": "quwoquan_data.professional_image_supported_api_reviewer_result",
        "candidateId": request["candidateId"],
        "contentSha256": request["contentSha256"],
        "reviewRequestRef": _safe_ref(request_path, root),
        "reviewRequestSha256": file_sha256(request_path),
        "sourceReview": identity,
        "sourceReviewRequestRef": _safe_ref(journal["requestPath"], root),
        "sourceReviewRequestSha256": file_sha256(journal["requestPath"]),
        "sourceReviewAttemptRef": _safe_ref(journal["attemptPath"], root),
        "sourceReviewAttemptSha256": file_sha256(journal["attemptPath"]),
        "provider": outcome.provider.value,
        "model": model,
        "runId": outcome.run_id,
        "reviewedAt": str(attempt["recordedAt"]),
        "resultSha256": str(attempt["resultSha256"]),
        "judgment": judgment,
        "judgmentDigest": _digest(judgment),
    }
    assert_valid(
        result, "source", "professional_image_supported_api_reviewer_result",
        label=f"source supported API reviewer result:{request['candidateId']}",
    )
    result_path = _write_create_once(result_path, result)
    _raise_if_review_blocked(result, result_path)
    return _review_summary(result, result_path)


def review_supported_api_inputs_from_source(
    *,
    handoff_ref: Path,
    source_evidence_root: Path,
    review_request_refs: Sequence[str],
    runner: Callable[[str], AgentRunOutcome] | None = None,
) -> dict[str, Any]:
    """Review all source objects; one failed object does not cancel siblings."""
    refs = tuple(str(value).strip() for value in review_request_refs)
    if not refs or any(not value for value in refs) or len(refs) != len(set(refs)):
        raise ProfessionalImageSupportedApiReviewError(
            "DATA.SOURCE.REVIEW_INPUT_MISSING: distinct review request refs are required"
        )
    root = source_evidence_root.expanduser().resolve()
    handoff_path = handoff_ref.expanduser().resolve()
    if not root.is_relative_to(OUTPUT_ROOT.resolve()):
        raise ProfessionalImageSupportedApiReviewError(
            "DATA.SOURCE.REVIEW_EVIDENCE_UNSAFE: source evidence escapes output root"
        )
    catalog = read_json(root / "inputs" / "metadata-catalog.json")
    if not isinstance(catalog, Mapping):
        raise ProfessionalImageSupportedApiReviewError(
            "DATA.SOURCE.REVIEW_INPUT_INVALID: metadata catalog is missing"
        )
    handoff = guard_acquisition_source_identity(
        catalog, handoff_ref=handoff_path, frozen_external_input=True
    )
    objects: list[tuple[str, dict[str, Any]]] = []
    candidate_ids: list[str] = []
    for ref in refs:
        request_path = _safe_file(root, ref)
        request = _review_request_with_current_contract(request_path, source_mode=True)
        stable = {key: value for key, value in request.items() if key != "requestDigest"}
        request_digest = "sha256:" + hashlib.sha256(
            json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
        ).hexdigest()
        if request["requestDigest"] != request_digest:
            raise ProfessionalImageSupportedApiReviewError(
                "DATA.SOURCE.REVIEW_INPUT_INVALID: request digest drift"
            )
        identity = _source_review_identity(
            handoff=handoff, request=request, handoff_ref=handoff_path
        )
        _validate_review_dependencies(request_path.parents[2], request)
        candidate_id = str(request["candidateId"])
        candidate_ids.append(candidate_id)
        objects.append(
            (
                candidate_id,
                {"requestPath": request_path, "request": request, "identity": identity},
            )
        )
    if len(candidate_ids) != len(set(candidate_ids)):
        raise ProfessionalImageSupportedApiReviewError(
            "DATA.SOURCE.REVIEW_INPUT_INVALID: candidate ids must be unique"
        )
    invoke = runner or _source_runner
    model = governed_cursor_grok_model()
    results, exclusions = run_isolated_image_objects(
        objects,
        worker=lambda candidate_id, work: _source_review_one(
            candidate_id, work, root=root, model=model, runner=invoke
        ),
        default_failure_code="DATA.SOURCE.REVIEW_ASSET_EXCLUDED",
    )
    batch = image_batch_result(
        schema="quwoquan_data.professional_image_supported_api_review_batch_result",
        execution_id="",
        requested_ids=candidate_ids,
        results=results,
        exclusions=exclusions,
    )
    if not results:
        raise ProfessionalImageSupportedApiReviewError(
            "DATA.SOURCE.REVIEW_NO_SUCCESS: no source image review completed",
            batch_result=batch,
        )
    return batch


def _journal_pair(root: Path, *, prompt_sha256: str) -> tuple[Path, Path, dict[str, Any]]:
    matches: list[tuple[Path, Path, dict[str, Any]]] = []
    journal_root = root / "_shared/semantic_tasks"
    for request_path in sorted(journal_root.glob("*/request.json")):
        request = read_json(request_path)
        if not isinstance(request, dict):
            continue
        if request.get("stage") != "reviewer" or request.get("promptSha256") != prompt_sha256:
            continue
        attempts = sorted((request_path.parent / "attempts").glob("*.json"))
        if attempts:
            matches.append((request_path, attempts[-1], request))
    if len(matches) != 1:
        raise ProfessionalImageSupportedApiReviewError(
            "DATA.SOURCE.REVIEW_JOURNAL_MISSING: exact reviewer request/attempt not found"
        )
    return matches[0]


def _execution_review_one(
    _candidate_id: str,
    work: Mapping[str, Any],
    *,
    workspace: Path,
    output_root: Path,
    context: ExecutionContext,
    runner: Callable[[ExecutionContext, str], AgentRunOutcome],
) -> dict[str, Any]:
    physical_request_path = work["requestPath"]
    request = work["request"]
    token = hashlib.sha256(str(request["candidateId"]).encode()).hexdigest()[:20]
    request_path = _write_create_once(
        workspace / "evidence/source_reviews/requests" / f"{token}.json",
        request,
    )
    preparation_root = physical_request_path.parents[2]
    for field in ("originalAssetRef", "apiResponseRef", "machineAssessmentRef"):
        dependency = _safe_file(preparation_root, request[field])
        destination = workspace / str(request[field])
        _copy_create_once(dependency, destination)
        expected_sha = request[field.removesuffix("Ref") + "Sha256"]
        if file_sha256(destination) != expected_sha:
            raise ProfessionalImageSupportedApiReviewError(
                f"DATA.SOURCE.REVIEW_STAGING_DIGEST_DRIFT: {field}",
                batch_fatal=True,
            )
    prompt = request_path.read_text(encoding="utf-8")
    prompt_sha = file_sha256(request_path)
    outcome = runner(context, prompt)
    if not outcome.succeeded or outcome.provider is not AgentProvider.CURSOR_SDK:
        kind = outcome.failure_kind.value if outcome.failure_kind else "provider_mismatch"
        raise ProfessionalImageSupportedApiReviewError(
            f"DATA.AGENT.REVIEW_FAILED: {kind}:{outcome.error_code or 'no_code'}"
        )
    if not outcome.run_id:
        raise ProfessionalImageSupportedApiReviewError(
            "DATA.AGENT.REVIEW_INVALID: provider runId is empty"
        )
    judgment = image_review_judgment(outcome.result_text)
    if judgment is None:
        raise ProfessionalImageSupportedApiReviewError(
            "DATA.AGENT.REVIEW_INVALID: reviewer did not return the exact judgment object"
        )
    request_journal_path, attempt_path, task_request = _journal_pair(
        workspace, prompt_sha256=prompt_sha
    )
    attempt = read_json(attempt_path)
    if not isinstance(attempt, Mapping) or attempt.get("runId") != outcome.run_id:
        raise ProfessionalImageSupportedApiReviewError(
            "DATA.SOURCE.REVIEW_JOURNAL_DRIFT: provider run does not match attempt"
        )
    reviewed_at = str(attempt.get("recordedAt") or "")
    if not reviewed_at:
        reviewed_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    result = {
        "schema": "quwoquan_data.professional_image_supported_api_reviewer_result",
        "candidateId": request["candidateId"],
        "contentSha256": request["contentSha256"],
        "reviewRequestRef": _portable_ref(request_path),
        "reviewRequestSha256": prompt_sha,
        "semanticTaskRequestRef": request_journal_path.relative_to(output_root).as_posix(),
        "semanticTaskRequestSha256": file_sha256(request_journal_path),
        "semanticTaskAttemptRef": attempt_path.relative_to(output_root).as_posix(),
        "semanticTaskAttemptSha256": file_sha256(attempt_path),
        "provider": outcome.provider.value,
        "model": str(task_request["model"]),
        "runId": outcome.run_id,
        "reviewedAt": reviewed_at,
        "resultSha256": str(attempt["resultSha256"]),
        "judgment": judgment,
        "judgmentDigest": _digest(judgment),
    }
    assert_valid(
        result,
        "source",
        "professional_image_supported_api_reviewer_result",
        label=f"supported API reviewer result:{request['candidateId']}",
    )
    result_path = _write_create_once(
        workspace / "evidence/source_reviews/results" / f"{token}.json",
        result,
    )
    _raise_if_review_blocked(result, result_path)
    return _review_summary(result, result_path)


def review_supported_api_inputs(
    *,
    execution_id: str,
    reviewer_root: Path,
    review_request_refs: Sequence[str],
    runner: Callable[[ExecutionContext, str], AgentRunOutcome] | None = None,
) -> dict[str, Any]:
    """Run every exact execution review and isolate object-level failures."""
    refs = tuple(str(value).strip() for value in review_request_refs)
    if not refs or any(not value for value in refs) or len(refs) != len(set(refs)):
        raise ProfessionalImageSupportedApiReviewError(
            "DATA.SOURCE.REVIEW_INPUT_MISSING: distinct review request refs are required"
        )
    root = reviewer_root.expanduser().resolve()
    workspace = execution_root(execution_id).resolve()
    output_root = OUTPUT_ROOT.resolve()
    if not workspace.is_relative_to(output_root):
        raise ProfessionalImageSupportedApiReviewError(
            "DATA.SOURCE.REVIEW_WORKSPACE_UNSAFE: execution workspace escapes output root"
        )
    load_frozen_execution_manifest(execution_id)
    binding = semantic_execution_binding_for_execution(execution_id)
    reviewer_model = binding.pair.reviewer
    mismatch = cursor_grok_binding_mismatch(binding, role="reviewer")
    if mismatch:
        raise ProfessionalImageSupportedApiReviewError(
            f"DATA.SOURCE.REVIEW_MODEL_BINDING_INVALID: {mismatch}"
        )
    spec = store.load_spec(execution_id)
    entity_ids = tuple(
        str(row.get("name") or "").strip()
        for row in ((spec.get("scope") or {}).get("coverageTargets") or [])
        if str(row.get("name") or "").strip()
    )
    context = ExecutionContext(
        execution_id=execution_id,
        entity_ids=entity_ids,
        spec=spec,
        managed=True,
        runtime=binding.runtime,
        model=reviewer_model.model_id,
        model_parameters=reviewer_model.parameters,
        agent_provider=reviewer_model.provider,
        semantic_role="reviewer",
    )
    objects: list[tuple[str, dict[str, Any]]] = []
    candidate_ids: list[str] = []
    for ref in refs:
        request_path = _safe_file(root, ref)
        request = _review_request_with_current_contract(request_path)
        stable = {key: value for key, value in request.items() if key != "requestDigest"}
        # requestDigest 由 prepare 端以无换行 canonical JSON 计算；journal/judgment
        # 系才使用带换行的 _digest，两者不可混用。
        request_digest = "sha256:" + hashlib.sha256(
            json.dumps(
                stable, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
        ).hexdigest()
        if request["requestDigest"] != request_digest:
            raise ProfessionalImageSupportedApiReviewError(
                "DATA.SOURCE.REVIEW_INPUT_INVALID: request digest drift"
            )
        _validate_review_dependencies(request_path.parents[2], request)
        candidate_id = str(request["candidateId"])
        candidate_ids.append(candidate_id)
        objects.append((candidate_id, {"requestPath": request_path, "request": request}))
    if len(candidate_ids) != len(set(candidate_ids)):
        raise ProfessionalImageSupportedApiReviewError(
            "DATA.SOURCE.REVIEW_INPUT_INVALID: candidate ids must be unique"
        )
    if runner is None:
        from content.execution.agent.agent_worker import _default_managed_agent_runner_isolated

        runner = _default_managed_agent_runner_isolated
    results, exclusions = run_isolated_image_objects(
        objects,
        worker=lambda candidate_id, work: _execution_review_one(
            candidate_id,
            work,
            workspace=workspace,
            output_root=output_root,
            context=context,
            runner=runner,
        ),
        default_failure_code="DATA.SOURCE.REVIEW_ASSET_EXCLUDED",
    )
    batch = image_batch_result(
        schema="quwoquan_data.professional_image_supported_api_review_batch_result",
        execution_id=execution_id,
        requested_ids=candidate_ids,
        results=results,
        exclusions=exclusions,
    )
    if not results:
        raise ProfessionalImageSupportedApiReviewError(
            "DATA.SOURCE.REVIEW_NO_SUCCESS: no execution image review completed",
            batch_result=batch,
        )
    return batch


def handle_review_image_supported_api_input(args: argparse.Namespace) -> None:
    try:
        if args.source_evidence_root:
            if not args.handoff_ref or args.execution_id:
                raise ProfessionalImageSupportedApiReviewError(
                    "DATA.SOURCE.REVIEW_MODE_INVALID: source mode requires handoffRef and forbids executionId"
                )
            result = review_supported_api_inputs_from_source(
                handoff_ref=Path(args.handoff_ref),
                source_evidence_root=Path(args.source_evidence_root),
                review_request_refs=tuple(args.review_request_ref or ()),
            )
        else:
            if not args.execution_id or args.handoff_ref:
                raise ProfessionalImageSupportedApiReviewError(
                    "DATA.SOURCE.REVIEW_MODE_INVALID: execution mode requires executionId only"
                )
            result = review_supported_api_inputs(
                execution_id=str(args.execution_id),
                reviewer_root=Path(args.reviewer_root or OUTPUT_ROOT),
                review_request_refs=tuple(args.review_request_ref or ()),
            )
    except (FileNotFoundError, OSError, TypeError, ValueError, ProfessionalImageSupportedApiReviewError) as exc:
        batch = getattr(exc, "batch_result", None)
        detail = json.dumps(batch, ensure_ascii=False, sort_keys=True) if batch else str(exc)
        raise SystemExit(
            f"[task review-image-supported-api-input] GATE_BLOCK {detail}"
        ) from exc
    print(json.dumps(result, ensure_ascii=False, indent=2))


def register_review_image_supported_api_input_parser(
    sub: argparse._SubParsersAction,
) -> None:
    parser = sub.add_parser(
        "review-image-supported-api-input",
        help="用冻结 cursor_grok reviewer 和本地 semantic journal 独立复核 supported-API 图片",
    )
    parser.add_argument("--execution-id")
    parser.add_argument("--handoff-ref")
    parser.add_argument("--source-evidence-root")
    parser.add_argument("--reviewer-root")
    parser.add_argument("--review-request-ref", action="append", default=[])
    parser.set_defaults(handler=handle_review_image_supported_api_input)


__all__ = [
    "ProfessionalImageSupportedApiReviewError",
    "register_review_image_supported_api_input_parser",
    "review_supported_api_inputs_from_source",
    "review_supported_api_inputs",
]
