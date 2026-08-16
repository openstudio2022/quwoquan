"""Run independent governed semantic reviews for supported-API image inputs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from core.control_types import AgentProvider
from core.io import read_json
from core.paths import OUTPUT_ROOT
from core.runtime_policy import active_runtime_policy
from core.schema import assert_valid

from content.execution import store
from content.execution.agent.capacity_broker import SemanticCapacityBroker
from content.execution.agent.outcome import AgentRunOutcome
from content.execution.context import ExecutionContext
from content.execution.controller.execute.pre_acquisition_handoff import (
    guard_acquisition_source_identity,
)
from content.execution.model_contract import semantic_execution_binding_for_execution
from content.execution.workspace import execution_root, load_frozen_execution_manifest
from content.source.professional_image_supported_api_contract import load_document
from content.source.professional_safety_evidence import file_sha256
from content.source.source_review_journal import run_source_review


class ProfessionalImageSupportedApiReviewError(RuntimeError):
    """Typed review admission or provider-result failure."""


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(
            dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        + "\n"
    ).encode("utf-8")


def _digest(value: Mapping[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _write_create_once(path: Path, payload: Mapping[str, Any]) -> Path:
    body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        if path.is_symlink() or not path.is_file() or path.read_bytes() != body:
            raise ProfessionalImageSupportedApiReviewError(
                f"DATA.SOURCE.REVIEW_CREATE_ONCE_CONFLICT: {path}"
            ) from None
        return path
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(body)
        handle.flush()
        os.fsync(handle.fileno())
    return path


def _safe_file(root: Path, ref: object, *, require_file: bool = True) -> Path:
    relative = Path(str(ref or ""))
    candidate = (root / relative).resolve()
    if (
        relative.is_absolute()
        or ".." in relative.parts
        or candidate == root
        or root not in candidate.parents
        or (require_file and not candidate.is_file())
        or (candidate.exists() and candidate.is_symlink())
    ):
        raise ProfessionalImageSupportedApiReviewError(
            f"DATA.SOURCE.REVIEW_INPUT_UNSAFE: {ref}"
        )
    return candidate


def _safe_ref(path: Path, root: Path) -> str:
    resolved = path.resolve()
    if resolved == root.resolve() or root.resolve() not in resolved.parents:
        raise ProfessionalImageSupportedApiReviewError(
            f"DATA.SOURCE.REVIEW_EVIDENCE_UNSAFE: {path}"
        )
    return resolved.relative_to(root.resolve()).as_posix()


def _portable_ref(path: Path) -> str:
    root = OUTPUT_ROOT.resolve()
    candidate = path.resolve()
    if not candidate.is_relative_to(root):
        raise ProfessionalImageSupportedApiReviewError(
            "DATA.SOURCE.REVIEW_EVIDENCE_UNSAFE: evidence escapes output root"
        )
    return candidate.relative_to(root).as_posix()


def _read_nofollow(path: Path) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        with os.fdopen(descriptor, "rb") as handle:
            return handle.read()
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        raise


def _copy_create_once(source: Path, destination: Path) -> None:
    body = _read_nofollow(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(
            destination,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
    except FileExistsError:
        if (
            destination.is_symlink()
            or not destination.is_file()
            or destination.read_bytes() != body
        ):
            raise ProfessionalImageSupportedApiReviewError(
                f"DATA.SOURCE.REVIEW_STAGING_CONFLICT: {destination}"
            ) from None
        return
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(body)
        handle.flush()
        os.fsync(handle.fileno())


def _review_request_with_current_contract(
    source: Path,
    *,
    source_mode: bool = False,
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


def _source_review_identity(*args: Any, **kwargs: Any) -> Any:
    from content.execution.controller.execute.review_image_supported_api_identity import (
        _source_review_identity as implementation,
    )

    return implementation(*args, **kwargs)


def _source_runner(prompt: str) -> AgentRunOutcome:
    from core.cursor_model import CursorModelSelection

    from content.execution.agent.agent_runner import _default_managed_agent_runner

    policy = active_runtime_policy()
    selection = policy.explicit_semantic_selection("cursor_grok").binding
    context = SimpleNamespace(
        runtime=policy.explicit_semantic_selection("cursor_grok").runtime,
        model_selection=CursorModelSelection.from_config(
            selection.model, selection.model_parameters, label="source reviewer"
        ),
        agent_provider=AgentProvider.CURSOR_SDK,
        max_workers=policy.reviewer_workers,
    )
    return _default_managed_agent_runner(context, prompt)


def _copy_source_receipt(source: Path, root: Path) -> Path:
    destination = root / "source-reviews" / "capacity-receipts" / source.name
    _copy_create_once(source, destination)
    return destination


def review_supported_api_inputs_from_source(
    *,
    handoff_ref: Path,
    source_evidence_root: Path,
    review_request_refs: Sequence[str],
    runner: Callable[[str], AgentRunOutcome] | None = None,
) -> list[tuple[dict[str, Any], Path]]:
    """Review pre-acquisition evidence without requiring an execution workspace."""
    if not review_request_refs:
        raise ProfessionalImageSupportedApiReviewError(
            "DATA.SOURCE.REVIEW_INPUT_MISSING: review request refs are required"
        )
    root = source_evidence_root.expanduser().resolve()
    handoff_path = handoff_ref.expanduser().resolve()
    if not root.is_relative_to(OUTPUT_ROOT.resolve()):
        raise ProfessionalImageSupportedApiReviewError(
            "DATA.SOURCE.REVIEW_EVIDENCE_UNSAFE: source evidence escapes output root"
        )
    if runner is None:
        runner = _source_runner
    results: list[tuple[dict[str, Any], Path]] = []
    for ref in review_request_refs:
        request_path = _safe_file(root, ref)
        request = _review_request_with_current_contract(request_path, source_mode=True)
        stable = {
            key: value for key, value in request.items() if key != "requestDigest"
        }
        request_digest = (
            "sha256:"
            + hashlib.sha256(
                json.dumps(
                    stable, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                ).encode("utf-8")
            ).hexdigest()
        )
        if request["requestDigest"] != request_digest:
            raise ProfessionalImageSupportedApiReviewError(
                "DATA.SOURCE.REVIEW_INPUT_INVALID: request digest drift"
            )
        catalog_path = root / "inputs" / "metadata-catalog.json"
        catalog = read_json(catalog_path)
        if not isinstance(catalog, Mapping):
            raise ProfessionalImageSupportedApiReviewError(
                "DATA.SOURCE.REVIEW_INPUT_INVALID: metadata catalog is missing"
            )
        handoff = guard_acquisition_source_identity(
            catalog, handoff_ref=handoff_path, frozen_external_input=True
        )
        identity = _source_review_identity(
            handoff=handoff, request=request, handoff_ref=handoff_path
        )
        token = hashlib.sha256(str(request["candidateId"]).encode()).hexdigest()[:20]
        existing_result_path = root / "source-reviews" / "results" / f"{token}.json"
        if existing_result_path.is_file():
            existing = load_document(
                existing_result_path,
                group="source",
                name="professional_image_supported_api_reviewer_result",
            )
            if (
                existing.get("sourceReview") != identity
                or existing.get("reviewRequestSha256") != file_sha256(request_path)
                or existing.get("contentSha256") != request["contentSha256"]
            ):
                raise ProfessionalImageSupportedApiReviewError(
                    "DATA.SOURCE.REVIEW_CREATE_ONCE_CONFLICT: existing result identity drift"
                )
            results.append((existing, existing_result_path))
            continue
        preparation_root = request_path.parents[2]
        for field in ("originalAssetRef", "apiResponseRef", "machineAssessmentRef"):
            dependency = _safe_file(preparation_root, request[field])
            if file_sha256(dependency) != request[field.removesuffix("Ref") + "Sha256"]:
                raise ProfessionalImageSupportedApiReviewError(
                    f"DATA.SOURCE.REVIEW_STAGING_DIGEST_DRIFT: {field}"
                )
        journal, _attempt_path = run_source_review(
            source_evidence_root=root,
            source_review=identity,
            model="grok-4.5",
            runtime_profile_id=active_runtime_policy().profile_id,
            prompt=request_path.read_text(encoding="utf-8"),
            broker=SemanticCapacityBroker(),
            runner=runner,
        )
        outcome = journal["outcome"]
        if not outcome.succeeded:
            kind = outcome.failure_kind.value if outcome.failure_kind else "unknown"
            raise ProfessionalImageSupportedApiReviewError(
                f"DATA.AGENT.REVIEW_FAILED: {kind}:{outcome.error_code or 'no_code'}"
            )
        judgment = _judgment(outcome.result_text)
        if judgment is None:
            raise ProfessionalImageSupportedApiReviewError(
                "DATA.AGENT.REVIEW_INVALID: reviewer did not return the exact judgment object"
            )
        attempt = journal["attempt"]
        receipt_path = _copy_source_receipt(journal["capacityReceiptPath"], root)
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
            "sourceCapacityReceiptRef": _safe_ref(receipt_path, root),
            "sourceCapacityReceiptSha256": file_sha256(receipt_path),
            "provider": outcome.provider.value,
            "model": "grok-4.5",
            "runId": outcome.run_id,
            "reviewedAt": str(journal["capacityReceipt"]["recordedAt"]),
            "resultSha256": str(attempt["resultSha256"]),
            "judgment": judgment,
            "judgmentDigest": _digest(judgment),
        }
        assert_valid(
            result,
            "source",
            "professional_image_supported_api_reviewer_result",
            label=f"source supported API reviewer result:{request['candidateId']}",
        )
        result_path = _write_create_once(
            root / "source-reviews" / "results" / f"{token}.json", result
        )
        results.append((result, result_path))
    return results


def _judgment(text: str) -> dict[str, Any] | None:
    candidates = [text.strip()]
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fenced:
        candidates.insert(0, fenced.group(1))
    first, last = text.find("{"), text.rfind("}")
    if first >= 0 and last > first:
        candidates.append(text[first : last + 1])
    expected = {
        "status",
        "entityMatch",
        "privacyRisk",
        "minorRisk",
        "maliciousMediaRisk",
        "watermarkStatus",
        "qualityStatus",
        "findings",
    }
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except (TypeError, ValueError):
            continue
        if isinstance(parsed, dict) and set(parsed) == expected:
            return parsed
    return None


def _journal_pair(
    root: Path, *, prompt_sha256: str
) -> tuple[Path, Path, dict[str, Any]]:
    matches: list[tuple[Path, Path, dict[str, Any]]] = []
    journal_root = root / "_shared/semantic_tasks"
    for request_path in sorted(journal_root.glob("*/request.json")):
        request = read_json(request_path)
        if not isinstance(request, dict):
            continue
        if (
            request.get("stage") != "reviewer"
            or request.get("promptSha256") != prompt_sha256
        ):
            continue
        attempts = sorted((request_path.parent / "attempts").glob("*.json"))
        if attempts:
            matches.append((request_path, attempts[-1], request))
    if len(matches) != 1:
        raise ProfessionalImageSupportedApiReviewError(
            "DATA.SOURCE.REVIEW_JOURNAL_MISSING: exact reviewer request/attempt not found"
        )
    return matches[0]


def review_supported_api_inputs(
    *,
    execution_id: str,
    reviewer_root: Path,
    review_request_refs: Sequence[str],
    runner: Callable[[ExecutionContext, str], AgentRunOutcome] | None = None,
) -> list[tuple[dict[str, Any], Path]]:
    """Stage exact evidence, run Grok-bound reviews, and write create-once results."""
    if not review_request_refs:
        raise ProfessionalImageSupportedApiReviewError(
            "DATA.SOURCE.REVIEW_INPUT_MISSING: review request refs are required"
        )
    root = reviewer_root.expanduser().resolve()
    workspace = execution_root(execution_id).resolve()
    output_root = OUTPUT_ROOT.resolve()
    if not workspace.is_relative_to(output_root):
        raise ProfessionalImageSupportedApiReviewError(
            "DATA.SOURCE.REVIEW_WORKSPACE_UNSAFE: execution workspace escapes output root"
        )
    manifest = load_frozen_execution_manifest(execution_id)
    source = manifest.get("sourceDigest")
    source = source if isinstance(source, Mapping) else {}
    binding = semantic_execution_binding_for_execution(execution_id)
    reviewer_model = binding.pair.reviewer
    if (
        binding.selection_id != "cursor_grok"
        or reviewer_model.provider is not AgentProvider.CURSOR_SDK
        or reviewer_model.model_id != "grok-4.5"
    ):
        raise ProfessionalImageSupportedApiReviewError(
            "DATA.SOURCE.REVIEW_MODEL_BINDING_INVALID: exact cursor_grok/grok-4.5 required"
        )
    spec = store.load_spec(execution_id)
    entity_ids = tuple(
        str(row.get("name") or "").strip()
        for row in ((spec.get("scope") or {}).get("coverageTargets") or [])
        if str(row.get("name") or "").strip()
    )
    review_ctx = ExecutionContext(
        execution_id=execution_id,
        entity_ids=entity_ids,
        spec=spec,
        managed=True,
        runtime=binding.runtime,
        max_workers=active_runtime_policy().reviewer_workers,
        model=reviewer_model.model_id,
        model_parameters=reviewer_model.parameters,
        agent_provider=reviewer_model.provider,
        semantic_role="reviewer",
    )
    if runner is None:
        from content.execution.agent.agent_worker import (
            _default_managed_agent_runner_isolated,
        )

        runner = _default_managed_agent_runner_isolated
    results: list[tuple[dict[str, Any], Path]] = []
    for ref in review_request_refs:
        physical_request_path = _safe_file(root, ref)
        request = _review_request_with_current_contract(physical_request_path)
        stable = {
            key: value for key, value in request.items() if key != "requestDigest"
        }
        if request["requestDigest"] != _digest(stable):
            raise ProfessionalImageSupportedApiReviewError(
                "DATA.SOURCE.REVIEW_INPUT_INVALID: request digest drift"
            )
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
                    f"DATA.SOURCE.REVIEW_STAGING_DIGEST_DRIFT: {field}"
                )
        prompt = request_path.read_text(encoding="utf-8")
        prompt_sha = file_sha256(request_path)
        outcome = runner(review_ctx, prompt)
        if not outcome.succeeded:
            kind = outcome.failure_kind.value if outcome.failure_kind else "unknown"
            raise ProfessionalImageSupportedApiReviewError(
                f"DATA.AGENT.REVIEW_FAILED: {kind}:{outcome.error_code or 'no_code'}"
            )
        judgment = _judgment(outcome.result_text)
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
            "semanticTaskRequestRef": request_journal_path.relative_to(
                output_root
            ).as_posix(),
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
        results.append((result, result_path))
    return results


def handle_review_image_supported_api_input(args: argparse.Namespace) -> None:
    try:
        if args.source_evidence_root:
            if not args.handoff_ref or args.execution_id:
                raise ProfessionalImageSupportedApiReviewError(
                    "DATA.SOURCE.REVIEW_MODE_INVALID: source mode requires handoffRef and forbids executionId"
                )
            results = review_supported_api_inputs_from_source(
                handoff_ref=Path(args.handoff_ref),
                source_evidence_root=Path(args.source_evidence_root),
                review_request_refs=tuple(args.review_request_ref or ()),
            )
        else:
            if not args.execution_id or args.handoff_ref:
                raise ProfessionalImageSupportedApiReviewError(
                    "DATA.SOURCE.REVIEW_MODE_INVALID: execution mode requires executionId only"
                )
            results = review_supported_api_inputs(
                execution_id=str(args.execution_id),
                reviewer_root=Path(args.reviewer_root or OUTPUT_ROOT),
                review_request_refs=tuple(args.review_request_ref or ()),
            )
    except (
        FileNotFoundError,
        OSError,
        TypeError,
        ValueError,
        ProfessionalImageSupportedApiReviewError,
    ) as exc:
        raise SystemExit(
            f"[task review-image-supported-api-input] GATE_BLOCK {exc}"
        ) from exc
    print(
        json.dumps(
            {
                "executionId": args.execution_id or "",
                "reviewedCount": len(results),
                "results": [
                    {
                        "candidateId": result["candidateId"],
                        "status": result["judgment"]["status"],
                        "resultRef": path.relative_to(OUTPUT_ROOT).as_posix(),
                        "resultSha256": file_sha256(path),
                    }
                    for result, path in results
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


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
    "review_supported_api_inputs",
    "review_supported_api_inputs_from_source",
]
