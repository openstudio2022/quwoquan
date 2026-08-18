"""Run and bind independent managed-SDK reviews for professional post assets."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from core.data_issue import (
    DataIssue,
    DataIssueCode,
    DataIssueStage,
    DataRecoveryAction,
    data_issue,
)
from core.io import read_json, write_json
from core.prompt_render import render as render_prompt
from core.runtime_policy import active_runtime_policy
from core.schema import assert_valid

from content.execution.context import ExecutionContext
from content.execution.workspace import execution_root
from content.post import object_index as content_object


def _asset_judgment_from_text(text: str) -> dict[str, Any] | None:
    candidates = [text.strip()]
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fenced:
        candidates.insert(0, fenced.group(1))
    first, last = text.find("{"), text.rfind("}")
    if first >= 0 and last > first:
        candidates.append(text[first : last + 1])
    required = {
        "rightsStatus",
        "authorizationRequired",
        "distributionDecision",
        "safetyStatus",
        "entityMatch",
        "qualityStatus",
        "privacyRisk",
        "minorRisk",
        "maliciousMediaRisk",
        "watermarkStatus",
        "findings",
    }
    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except (TypeError, ValueError):
            continue
        if isinstance(payload, dict) and set(payload) == required:
            return payload
    return None


def _professional_asset_review_candidates(
    ctx: ExecutionContext,
    ref: str,
) -> list[dict[str, str]]:
    from core.paths import OUTPUT_ROOT

    from content.release.canonical.asset_review_adoption import (
        _professional_identity,
    )
    from content.release.canonical.post_transaction import (
        _asset_sources,
        _media_dimensions,
        _post_asset_path,
        _source_assets,
    )

    root = execution_root(ctx.execution_id)
    object_dir = content_object.content_object_dir(ctx.execution_id, ref)
    manifest = read_json(object_dir / "manifest.json")
    source_assets = _source_assets(root)
    candidates: list[dict[str, str]] = []
    for raw in manifest.get("assets") or []:
        if not isinstance(raw, Mapping):
            continue
        asset_path = _post_asset_path(object_dir, raw)
        _width, _height, mime = _media_dimensions(asset_path, raw)
        asset_kind = "video" if mime.startswith("video/") else "image"
        related_sources = _asset_sources(raw, source_assets)
        identity = _professional_identity(
            raw,
            related_sources,
            asset_kind=asset_kind,
        )
        if identity is None:
            continue
        receipt_ref, asset_id, content_sha256 = identity
        acquisition_receipt = (
            OUTPUT_ROOT
            / "data/local/workspace/source-acquisition"
            / asset_kind
            / receipt_ref
        )
        candidates.append(
            {
                "assetKind": asset_kind,
                "assetId": asset_id,
                "contentSha256": content_sha256,
                "acquisitionReceiptPath": acquisition_receipt.as_posix(),
            }
        )
    unique = {
        (item["assetKind"], item["assetId"], item["contentSha256"]): item
        for item in candidates
    }
    return [unique[key] for key in sorted(unique)]


def _existing_asset_review_is_accepted(
    ctx: ExecutionContext,
    *,
    ref: str,
    candidate: Mapping[str, str],
) -> bool:
    from core.paths import OUTPUT_ROOT

    from content.source.independent_asset_review import (
        assert_asset_review_accepted,
        load_independent_asset_review_receipt,
    )

    root = execution_root(ctx.execution_id)
    receipt_root = root / "evidence/asset_reviews/receipts"
    matches: list[Path] = []
    for path in sorted(receipt_root.glob("*.json")) if receipt_root.is_dir() else ():
        try:
            payload = read_json(path)
        except (OSError, TypeError, ValueError):
            continue
        snapshot = payload.get("assetSnapshot") if isinstance(payload, Mapping) else {}
        if (
            isinstance(snapshot, Mapping)
            and payload.get("objectRef") == ref
            and payload.get("assetKind") == candidate["assetKind"]
            and snapshot.get("assetId") == candidate["assetId"]
            and snapshot.get("contentSha256") == candidate["contentSha256"]
        ):
            matches.append(path)
    if len(matches) != 1:
        return False
    manifest = read_json(root / "execution_manifest.json")
    source_identity = manifest.get("sourceDigest")
    source_identity = source_identity if isinstance(source_identity, Mapping) else {}
    receipt = load_independent_asset_review_receipt(
        matches[0].relative_to(OUTPUT_ROOT).as_posix(),
        output_root=OUTPUT_ROOT,
    )
    assert_asset_review_accepted(
        receipt,
        content_sha256=candidate["contentSha256"],
        source_digest=str(source_identity.get("digest") or ""),
        asset_id=candidate["assetId"],
    )
    return True


def run_professional_asset_independent_reviews(
    ctx: ExecutionContext,
    refs: list[str],
) -> list[DataIssue]:
    """Produce one distinct semantic-review receipt for each professional asset."""
    from core.paths import OUTPUT_ROOT

    from content.execution.agent.agent_worker import (
        _default_managed_agent_runner_isolated,
    )
    from content.execution.model_contract import execution_model_pair_for_execution
    from content.source.independent_asset_review import (
        _load_acquisition,
        _one_asset,
        _review_decision,
        write_independent_asset_review_receipt,
    )
    from content.source.independent_asset_review_contract import (
        asset_snapshot,
        canonical_digest,
    )

    pair = execution_model_pair_for_execution(ctx.execution_id)
    model = pair.reviewer.model_id
    model_family = pair.reviewer.family.value
    root = execution_root(ctx.execution_id)
    issues: list[DataIssue] = []
    for ref in refs:
        object_dir = content_object.content_object_dir(ctx.execution_id, ref)
        author_evidence = object_dir / "4.draft/agent_result_envelope.json"
        for candidate in _professional_asset_review_candidates(ctx, ref):
            try:
                if _existing_asset_review_is_accepted(
                    ctx,
                    ref=ref,
                    candidate=candidate,
                ):
                    continue
            except (OSError, TypeError, ValueError):
                pass
            token = hashlib.sha256(
                (
                    f"{ref}|{candidate['assetKind']}|{candidate['assetId']}|"
                    f"{candidate['contentSha256']}"
                ).encode()
            ).hexdigest()[:20]
            pending = root / "evidence/asset_reviews/pending" / f"{token}.json"
            reviewer_evidence = (
                root / "evidence/asset_reviews/reviewers" / f"{token}.json"
            )
            pending.parent.mkdir(parents=True, exist_ok=True)
            pending.unlink(missing_ok=True)
            prompt = render_prompt(
                "professional_asset_independent_review",
                task_vars={
                    "execution_id": ctx.execution_id,
                    "object_ref": ref,
                    "asset_kind": candidate["assetKind"],
                    "asset_id": candidate["assetId"],
                    "acquisition_receipt_path": candidate["acquisitionReceiptPath"],
                    "author_evidence_path": author_evidence,
                    "object_dir": object_dir,
                    "output_path": pending,
                },
            )
            review_ctx = ExecutionContext(
                execution_id=ctx.execution_id,
                entity_ids=list(ctx.entity_ids),
                spec=ctx.spec.to_dict(),
                managed=True,
                runtime=ctx.runtime,
                max_workers=active_runtime_policy().reviewer_workers,
                model=model,
                model_parameters=pair.reviewer.parameters,
                agent_provider=ctx.agent_provider,
                semantic_role="reviewer",
                release_only=ctx.release_only,
            )
            outcome = _default_managed_agent_runner_isolated(review_ctx, prompt)
            judgment: dict[str, Any] | None = None
            if pending.is_file():
                try:
                    raw_judgment = read_json(pending)
                except (OSError, TypeError, ValueError):
                    raw_judgment = None
                if isinstance(raw_judgment, dict):
                    judgment = _asset_judgment_from_text(
                        json.dumps(raw_judgment, ensure_ascii=False)
                    )
            if judgment is None and outcome.succeeded:
                judgment = _asset_judgment_from_text(outcome.result_text)
            pending.unlink(missing_ok=True)
            if not outcome.succeeded or judgment is None:
                issues.append(
                    data_issue(
                        DataIssueCode.AGENT_REVIEW_INVALID,
                        stage=DataIssueStage.POST_REVIEW,
                        ref=ref,
                        message=(
                            "professional asset reviewer did not produce "
                            f"valid evidence: {candidate['assetId']}"
                        ),
                        recovery=DataRecoveryAction.RETRY_AGENT,
                    )
                )
                continue
            try:
                acquisition, _receipt_ref, _receipt_sha = _load_acquisition(
                    Path(candidate["acquisitionReceiptPath"]),
                    asset_kind=candidate["assetKind"],
                    output_root=OUTPUT_ROOT,
                )
                acquired_asset = _one_asset(
                    acquisition,
                    asset_id=candidate["assetId"],
                )
                safety = acquired_asset.get("safetyReview")
                safety = safety if isinstance(safety, Mapping) else {}
                decision = _review_decision(
                    judgment,
                    snapshot=asset_snapshot(acquired_asset),
                    acquisition_safety=safety,
                )
                reviewer_result = {
                    "schema": "quwoquan_data.reviewer_result",
                    "stage": "5.review",
                    "executionId": ctx.execution_id,
                    "executionBinding": "frozen",
                    "objectRef": ref,
                    "provider": outcome.provider.value,
                    "model": model,
                    "modelFamily": model_family,
                    "runId": outcome.run_id,
                    "verdict": "passed" if decision == "accepted" else "failed",
                    "issues": (
                        []
                        if decision == "accepted"
                        else list(judgment.get("findings") or [])
                    ),
                    "findings": list(judgment.get("findings") or []),
                    "resultHash": canonical_digest(judgment),
                }
                assert_valid(
                    reviewer_result,
                    "content",
                    "reviewer_result",
                    label=f"asset_reviewer_result:{ref}:{candidate['assetId']}",
                )
                reviewer_evidence.parent.mkdir(parents=True, exist_ok=True)
                write_json(reviewer_evidence, reviewer_result)
                receipt, _path = write_independent_asset_review_receipt(
                    acquisition_receipt_path=Path(candidate["acquisitionReceiptPath"]),
                    asset_kind=candidate["assetKind"],
                    asset_id=candidate["assetId"],
                    execution_manifest_path=root / "execution_manifest.json",
                    author_evidence_path=author_evidence,
                    reviewer_evidence_path=reviewer_evidence,
                    object_ref=ref,
                    judgment=judgment,
                )
                if receipt.get("reviewDecision") != "accepted":
                    raise ValueError(
                        f"professional asset review blocked: {candidate['assetId']}"
                    )
            except (OSError, TypeError, ValueError) as exc:
                issues.append(
                    data_issue(
                        DataIssueCode.CONTRACT_INVALID,
                        stage=DataIssueStage.POST_REVIEW,
                        ref=ref,
                        message=f"professional asset review invalid: {exc}",
                        recovery=DataRecoveryAction.STOP,
                    )
                )
    return issues


__all__ = ["run_professional_asset_independent_reviews"]
