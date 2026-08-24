"""Create fresh author/reviewer evidence for exact acquired video bytes."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from core.content_library import (
    MEDIA_KIND,
    file_sha256 as library_file_sha256,
    link_from_library,
    normalize_library_digest,
)
from core.control_types import AgentProvider
from core.paths import OUTPUT_ROOT
from core.schema import assert_valid

from content.execution import store
from content.execution.agent.outcome import AgentRunOutcome
from content.execution.context import ExecutionContext
from content.execution.model_contract import (
    cursor_grok_binding_mismatch,
    semantic_execution_binding_for_execution,
)
from content.execution.production_contracts import (
    build_agent_result_envelope,
    build_gate_verdict,
    sha256_file,
    sha256_text,
    stable_failure_fingerprint,
    validate_agent_result_envelope,
)
from content.execution.workspace import execution_root, load_frozen_execution_manifest
from content.execution.controller.execute.video_acquisition_agent_prompts import (
    author_prompt as _author_prompt,
    review_prompt as _review_prompt,
)
from content.execution.controller.execute.video_acquisition_agent_evidence import (
    AUTHOR_FIELDS as _AUTHOR_FIELDS,
    JUDGMENT_FIELDS as _JUDGMENT_FIELDS,
    exact_json_object as _json_object,
    write_agent_evidence_once,
)
from content.source.independent_asset_review_contract import canonical_digest
from content.source.professional_video_receipt import (
    ACCEPTED_DECISIONS,
    canonical_child,
    load_professional_video_acquisition_receipt,
)


class VideoAcquisitionAgentInputError(RuntimeError):
    """One global execution binding or one asset result is invalid."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


def _fail(code: str, detail: str) -> None:
    raise VideoAcquisitionAgentInputError(code, detail)


def _write_create_once(path: Path, payload: Mapping[str, Any]) -> Path:
    return write_agent_evidence_once(path, payload, fail=_fail)


def _execution_context(
    execution_id: str,
    *,
    role: str,
) -> tuple[dict[str, Any], Any, ExecutionContext, Path]:
    manifest = load_frozen_execution_manifest(execution_id)
    binding = semantic_execution_binding_for_execution(execution_id)
    model = binding.pair.author if role == "author" else binding.pair.reviewer
    mismatch = cursor_grok_binding_mismatch(binding, role=role)
    if mismatch:
        _fail(
            "DATA.SOURCE.AGENT_MODEL_BINDING_INVALID",
            f"video acquisition evidence requires the frozen cursor_grok binding: {mismatch}",
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
        model=model.model_id,
        model_parameters=model.parameters,
        agent_provider=model.provider,
        semantic_role=role,
    )
    return manifest, model, context, execution_root(execution_id).resolve()


def _acquired_rows(
    *,
    execution_manifest: Mapping[str, Any],
    acquisition_root: Path,
    acquisition_receipt_ref: str,
) -> dict[str, dict[str, Any]]:
    receipt = load_professional_video_acquisition_receipt(
        acquisition_receipt_ref,
        root=acquisition_root,
    )
    source = execution_manifest.get("sourceDigest")
    source = source if isinstance(source, Mapping) else {}
    if receipt["sourceDigest"] != source.get("digest"):
        _fail(
            "DATA.SOURCE.AGENT_IDENTITY_DRIFT",
            "video acquisition and execution source digests differ",
        )
    return {
        str(row["assetId"]): dict(row)
        for row in receipt["assets"]
        if row.get("acquisitionStatus") == "acquired"
        and row.get("distributionDecision") in ACCEPTED_DECISIONS
    }


def _link_acquired_asset(
    *,
    row: Mapping[str, Any],
    source: Path,
    destination: Path,
    suffix: str,
) -> Path:
    """按 receipt 里的 ``contentSha256`` 从内容库硬链接入位，不复制视频字节。

    入库前必须先按来源文件自身的字节核对 digest：内容库命中已有条目时不会再读
    来源，如果只依赖入库校验，来源侧的字节漂移会被一个恰好同名的旧条目掩盖掉。
    """
    if source.is_symlink():
        _fail(
            "DATA.SOURCE.AGENT_STAGING_CONFLICT",
            f"acquired video asset must not be a symlink: {source}",
        )
    declared = str(row["contentSha256"])
    if library_file_sha256(source) != normalize_library_digest(declared):
        _fail(
            "DATA.SOURCE.AGENT_INPUT_DRIFT",
            f"acquired video differs from acquisition receipt: {row['assetId']}",
        )
    if destination.is_symlink():
        _fail(
            "DATA.SOURCE.AGENT_STAGING_CONFLICT",
            f"staged video path must not be a symlink: {destination}",
        )
    try:
        link_from_library(
            source,
            destination,
            kind=MEDIA_KIND,
            expected_sha256=declared,
            suffix=suffix,
        )
    except (OSError, ValueError) as exc:
        _fail(
            "DATA.SOURCE.AGENT_STAGING_CONFLICT",
            f"acquired video could not be referenced from the content library: "
            f"{row['assetId']}: {exc}",
        )
    return destination


def _stage_asset(
    *,
    row: Mapping[str, Any],
    acquisition_root: Path,
    object_root: Path,
) -> tuple[Path, Path]:
    source = canonical_child(
        acquisition_root,
        str(row["assetRef"]),
        label=f"{row['assetId']}.assetRef",
    )
    suffix = source.suffix.lower()
    staged = _link_acquired_asset(
        row=row,
        source=source,
        destination=object_root / f"input/asset{suffix}",
        suffix=suffix,
    )
    if sha256_file(staged) != row["contentSha256"]:
        _fail(
            "DATA.SOURCE.AGENT_INPUT_DRIFT",
            f"staged video differs from acquisition receipt: {row['assetId']}",
        )
    probe = row.get("mediaProbe")
    if not isinstance(probe, Mapping) or not (
        probe.get("playable") is True and probe.get("motionVideo") is True
    ):
        _fail(
            "DATA.SOURCE.AGENT_INPUT_INVALID",
            f"acquired video lacks a passing media probe: {row['assetId']}",
        )
    contact = object_root / "input/contact-sheet.jpg"
    if not contact.is_file():
        from content.source.professional_video_manual_input_media import (
            render_contact_sheet,
        )

        render_contact_sheet(
            staged,
            contact,
            frame_count=int(probe["frameCount"]),
            fail=lambda detail: _fail(
                "DATA.SOURCE.MEDIA_PROBE_FAILED", str(detail)
            ),
        )
    return staged, contact


def _author_one(
    *,
    row: Mapping[str, Any],
    acquisition_root: Path,
    workspace: Path,
    context: ExecutionContext,
    model: Any,
    runner: Callable[[ExecutionContext, str], AgentRunOutcome],
    object_ref: str = "",
) -> dict[str, Any]:
    asset_id = str(row["assetId"])
    token = hashlib.sha256(asset_id.encode()).hexdigest()[:20]
    object_root = workspace / "evidence/source_authors/video/objects" / token
    staged, contact = _stage_asset(
        row=row, acquisition_root=acquisition_root, object_root=object_root
    )
    prompt = _author_prompt(row, staged=staged, contact=contact, object_root=object_root)
    outcome = runner(context, prompt)
    if not outcome.succeeded or outcome.provider is not AgentProvider.CURSOR_SDK:
        kind = outcome.failure_kind.value if outcome.failure_kind else "provider_mismatch"
        _fail("DATA.AGENT.AUTHOR_FAILED", f"{asset_id}: {kind}")
    if not outcome.run_id:
        _fail("DATA.AGENT.AUTHOR_INVALID", f"author runId is empty: {asset_id}")
    result = _json_object(outcome.result_text, fields=_AUTHOR_FIELDS)
    expected_identity = {
        "candidateId": row["assetId"],
        "contentSha256": row["contentSha256"],
        "entityId": row["entityId"],
    }
    if result is None or any(
        result.get(field) != value for field, value in expected_identity.items()
    ):
        _fail("DATA.AGENT.AUTHOR_INVALID", f"author result identity drift: {asset_id}")
    assert_valid(
        result,
        "source",
        "professional_video_acquisition_author_result",
        label=f"professional video acquisition author result:{asset_id}",
    )
    passed = all(
        (
            result["status"] == "passed",
            result["entityMatch"] == "matched",
            result["attributionMatch"] == "matched",
            result["qualityStatus"] == "passed",
        )
    )
    result_path = _write_create_once(object_root / "4.draft/author-result.json", result)
    prompt_sha = sha256_text(prompt)
    output_sha = sha256_file(result_path)
    gate = build_gate_verdict(
        gate_id="professional_video_source_author",
        decision="passed" if passed else "failed",
        input_hash=prompt_sha,
        output_hash=output_sha,
        issues=[] if passed else ["professional video author result did not pass"],
    )
    envelope = build_agent_result_envelope(
        job={
            "jobId": stable_failure_fingerprint([context.execution_id, asset_id, "author"]),
            "executionId": context.execution_id,
            "ref": object_ref or f"posts/video/{asset_id}",
            "stage": "author",
        },
        files=[
            {"path": "author-result.json", "sha256": output_sha, "role": "video_author_result"}
        ],
        gates=[gate],
        provider=outcome.provider.value,
        model=model.model_id,
        run_id=outcome.run_id,
        prompt_sha256=prompt_sha,
        agent_id=outcome.agent_id or None,
    )
    errors = validate_agent_result_envelope(
        envelope, workspace_root=result_path.parent
    )
    if errors:
        _fail(
            "DATA.SOURCE.AUTHOR_ENVELOPE_INVALID",
            f"{asset_id}: {'; '.join(errors[:3])}",
        )
    assert_valid(
        envelope,
        "content",
        "agent_result_envelope",
        label=f"professional video author envelope:{asset_id}",
    )
    envelope_path = _write_create_once(
        object_root / "4.draft/agent_result_envelope.json", envelope
    )
    if not passed:
        _fail("DATA.SOURCE.AUTHOR_GATE_BLOCKED", f"author rejected asset: {asset_id}")
    return {
        "assetId": asset_id,
        "objectRef": envelope["ref"],
        "runId": outcome.run_id,
        "envelopeRef": envelope_path.relative_to(OUTPUT_ROOT).as_posix(),
        "envelopeSha256": sha256_file(envelope_path),
    }


def _review_one(
    *,
    row: Mapping[str, Any],
    acquisition_root: Path,
    workspace: Path,
    context: ExecutionContext,
    model: Any,
    runner: Callable[[ExecutionContext, str], AgentRunOutcome],
    object_ref: str = "",
) -> dict[str, Any]:
    asset_id = str(row["assetId"])
    token = hashlib.sha256(asset_id.encode()).hexdigest()[:20]
    object_root = workspace / "evidence/source_reviewers/video/objects" / token
    staged, contact = _stage_asset(
        row=row, acquisition_root=acquisition_root, object_root=object_root
    )
    prompt = _review_prompt(row, staged=staged, contact=contact, object_root=object_root)
    outcome = runner(context, prompt)
    if not outcome.succeeded or outcome.provider is not AgentProvider.CURSOR_SDK:
        kind = outcome.failure_kind.value if outcome.failure_kind else "provider_mismatch"
        _fail("DATA.AGENT.REVIEW_FAILED", f"{asset_id}: {kind}")
    if not outcome.run_id:
        _fail("DATA.AGENT.REVIEW_INVALID", f"reviewer runId is empty: {asset_id}")
    judgment = _json_object(outcome.result_text, fields=_JUDGMENT_FIELDS)
    if judgment is None:
        _fail("DATA.AGENT.REVIEW_INVALID", f"review judgment shape drift: {asset_id}")
    assert_valid(
        judgment,
        "source",
        "professional_video_acquisition_review_judgment",
        label=f"professional video acquisition review judgment:{asset_id}",
    )
    if (
        judgment["rightsStatus"] != row["rightsStatus"]
        or judgment["authorizationRequired"] is not row["authorizationRequired"]
    ):
        _fail("DATA.AGENT.REVIEW_INVALID", f"reviewer upgraded rights: {asset_id}")
    passed = all(
        (
            judgment["distributionDecision"] == row["distributionDecision"],
            judgment["safetyStatus"] == "passed",
            judgment["entityMatch"] == "matched",
            judgment["qualityStatus"] == "passed",
            judgment["privacyRisk"] == "none",
            judgment["minorRisk"] == "none",
            judgment["maliciousMediaRisk"] == "none",
            judgment["watermarkStatus"] == "absent",
        )
    )
    findings = [str(value).strip() for value in judgment["findings"] if str(value).strip()]
    if not passed and (
        judgment["distributionDecision"] != "blocked" or not findings
    ):
        _fail(
            "DATA.AGENT.REVIEW_INVALID",
            f"blocked review must remain blocked with findings: {asset_id}",
        )
    judgment_path = _write_create_once(
        object_root / "5.review/judgment.json", judgment
    )
    reviewer = {
        "schema": "quwoquan_data.reviewer_result",
        "stage": "5.review",
        "executionId": context.execution_id,
        "executionBinding": "frozen",
        "objectRef": object_ref or f"posts/video/{asset_id}",
        "provider": outcome.provider.value,
        "model": model.model_id,
        "modelFamily": model.family.value,
        "runId": outcome.run_id,
        "verdict": "passed" if passed else "failed",
        "issues": [] if passed else findings,
        "findings": findings,
        "resultHash": canonical_digest(judgment),
    }
    assert_valid(
        reviewer,
        "content",
        "reviewer_result",
        label=f"professional video acquisition reviewer result:{asset_id}",
    )
    reviewer_path = _write_create_once(
        object_root / "5.review/reviewer-result.json", reviewer
    )
    return {
        "assetId": asset_id,
        "objectRef": reviewer["objectRef"],
        "runId": outcome.run_id,
        "verdict": reviewer["verdict"],
        "reviewerResultRef": reviewer_path.relative_to(OUTPUT_ROOT).as_posix(),
        "reviewerResultSha256": sha256_file(reviewer_path),
        "judgmentRef": judgment_path.relative_to(OUTPUT_ROOT).as_posix(),
        "judgmentSha256": sha256_file(judgment_path),
    }


def _exclusion(asset_id: str, exc: BaseException) -> dict[str, str]:
    code = getattr(exc, "code", "DATA.SOURCE.AGENT_ASSET_EXCLUDED")
    detail = getattr(exc, "detail", f"{type(exc).__name__} while processing exact asset")
    return {"assetId": asset_id, "failureCode": str(code), "failure": str(detail)}


def _run_batch(
    *,
    role: str,
    execution_id: str,
    acquisition_root: Path,
    acquisition_receipt_ref: str,
    asset_ids: Sequence[str],
    runner: Callable[[ExecutionContext, str], AgentRunOutcome] | None,
    object_ref: str = "",
) -> dict[str, Any]:
    selected = tuple(str(value).strip() for value in asset_ids)
    if not selected or any(not value for value in selected) or len(selected) != len(set(selected)):
        _fail(
            "DATA.SOURCE.AGENT_INPUT_INVALID",
            "distinct non-empty asset ids are required",
        )
    # receipt 协议对象根（posts/video/<角度>/<标题>/<序号>）与 asset 一一对应，
    # 显式 object_ref 只允许绑定恰好一个 asset。
    if object_ref and len(selected) != 1:
        _fail(
            "DATA.SOURCE.AGENT_INPUT_INVALID",
            "explicit --object-ref requires exactly one asset id",
        )
    manifest, model, context, workspace = _execution_context(execution_id, role=role)
    root = acquisition_root.expanduser().resolve()
    rows = _acquired_rows(
        execution_manifest=manifest,
        acquisition_root=root,
        acquisition_receipt_ref=acquisition_receipt_ref,
    )
    invoke = runner
    if invoke is None:
        from content.execution.agent.agent_worker import (
            _default_managed_agent_runner_isolated,
        )

        invoke = _default_managed_agent_runner_isolated
    results: dict[str, dict[str, Any]] = {}
    exclusions: list[dict[str, str]] = []
    work = [asset_id for asset_id in selected if asset_id in rows]
    for asset_id in selected:
        if asset_id not in rows:
            exclusions.append(
                {
                    "assetId": asset_id,
                    "failureCode": "DATA.SOURCE.AGENT_INPUT_INVALID",
                    "failure": "asset is missing, unacquired, or not admitted",
                }
            )
    worker = _author_one if role == "author" else _review_one
    if work:
        with ThreadPoolExecutor(
            max_workers=len(work), thread_name_prefix=f"video-{role}"
        ) as executor:
            futures = [
                (
                    asset_id,
                    executor.submit(
                        worker,
                        row=rows[asset_id],
                        acquisition_root=root,
                        workspace=workspace,
                        context=context,
                        model=model,
                        runner=invoke,
                        object_ref=object_ref,
                    ),
                )
                for asset_id in work
            ]
            for asset_id, future in futures:
                try:
                    results[asset_id] = future.result()
                except Exception as exc:  # noqa: BLE001 - isolate one asset.
                    exclusions.append(_exclusion(asset_id, exc))
    ordered = [results[value] for value in selected if value in results]
    return {
        "schema": f"quwoquan_data.video_acquisition_{role}_input_result",
        "executionId": execution_id,
        "requestedCount": len(selected),
        "completedCount": len(ordered),
        "excludedCount": len(exclusions),
        "results": ordered,
        "exclusions": exclusions,
    }


def author_video_acquisition_inputs(**kwargs: Any) -> dict[str, Any]:
    return _run_batch(role="author", **kwargs)


def review_video_acquisition_inputs(**kwargs: Any) -> dict[str, Any]:
    return _run_batch(role="reviewer", **kwargs)


def _handle(args: argparse.Namespace, *, role: str) -> None:
    function = (
        author_video_acquisition_inputs
        if role == "author"
        else review_video_acquisition_inputs
    )
    try:
        result = function(
            execution_id=str(args.execution_id),
            acquisition_root=Path(args.acquisition_root).expanduser().resolve(),
            acquisition_receipt_ref=str(args.acquisition_receipt_ref),
            asset_ids=tuple(args.asset_id or ()),
            runner=None,
            object_ref=str(getattr(args, "object_ref", "") or ""),
        )
    except (
        FileNotFoundError,
        OSError,
        TypeError,
        ValueError,
        VideoAcquisitionAgentInputError,
    ) as exc:
        raise SystemExit(
            f"[task {'review' if role == 'reviewer' else role}-video-acquisition-input] "
            f"GATE_BLOCK {exc}"
        ) from exc
    print(json.dumps(result, ensure_ascii=False, indent=2))


def register_video_acquisition_agent_input_parsers(
    sub: argparse._SubParsersAction,
) -> None:
    for role in ("author", "review"):
        parser = sub.add_parser(
            f"{role}-video-acquisition-input",
            help=f"用fresh cursor_grok {role}处理exact acquired video bytes",
        )
        parser.add_argument("--execution-id", required=True)
        parser.add_argument("--acquisition-root", required=True)
        parser.add_argument("--acquisition-receipt-ref", required=True)
        parser.add_argument("--asset-id", action="append", required=True)
        parser.add_argument(
            "--object-ref",
            default="",
            help="receipt 协议对象根（posts/video/<角度>/<标题>/<序号>）；仅允许单 asset",
        )
        parser.set_defaults(
            handler=lambda args, selected_role=role: _handle(
                args,
                role="reviewer" if selected_role == "review" else "author",
            )
        )


__all__ = [
    "VideoAcquisitionAgentInputError",
    "author_video_acquisition_inputs",
    "register_video_acquisition_agent_input_parsers",
    "review_video_acquisition_inputs",
]
