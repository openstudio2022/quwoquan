"""Fail-closed promotion evidence for travel image/video M100 to M1000."""
from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from core import paths
from core.io import read_json, write_json
from core.schema import assert_valid
from content.execution.identity import parse_execution_id, validate_execution_id
from content.execution.workspace import (
    execution_root,
    load_frozen_execution_manifest,
    load_frozen_target_set,
)


PROMOTION_SCHEMA = "quwoquan_data.video_scale_promotion"
IMAGE_PROMOTION_SCHEMA = "quwoquan_data.image_scale_promotion"
_PROMOTION_SCHEMA_BY_CARRIER = {
    "image": IMAGE_PROMOTION_SCHEMA,
    "video": PROMOTION_SCHEMA,
}
_M100_QUOTA = 100
_M100_SOURCE_READY_MINIMUM = 120
_M100_CANDIDATE_MINIMUM = 180
_GROK_FAST_PARAMETERS = (
    {"id": "effort", "value": "high"},
    {"id": "fast", "value": "true"},
)


def _promotion_schema(carrier: str) -> str:
    try:
        return _PROMOTION_SCHEMA_BY_CARRIER[carrier]
    except KeyError as exc:
        raise ValueError(
            f"scale promotion carrier must be image or video: {carrier}"
        ) from exc


def _sha256(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def promotion_root(
    *,
    carrier: str = "video",
    root: Path | None = None,
) -> Path:
    _promotion_schema(carrier)
    return (
        (root or paths.DATA_LOCAL_ROOT)
        / "workspace"
        / f"{carrier}-scale-promotions"
    )


def promotion_path(
    predecessor_execution_id: str,
    *,
    carrier: str = "video",
    root: Path | None = None,
) -> Path:
    return promotion_root(
        carrier=carrier,
        root=root,
    ) / f"{validate_execution_id(predecessor_execution_id)}.json"


def _require_m100_execution(execution_id: str, *, carrier: str) -> None:
    identity = parse_execution_id(validate_execution_id(execution_id))
    if (
        identity.vertical != "travel"
        or identity.content_type.value != carrier
        or identity.intent != "m100"
        or identity.phase.value != "scale"
    ):
        raise ValueError(
            f"{carrier} scale promotion predecessor must be a "
            f"travel/{carrier} M100 scale execution"
        )


def _load_json(path: Path, *, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"{label} is missing: {path}")
    payload = read_json(path)
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be an object: {path}")
    return payload


def _require_clean_source_inputs(
    source_document: Mapping[str, Any],
) -> None:
    inputs = [str(item) for item in (source_document.get("inputs") or [])]
    if not inputs:
        raise ValueError("M100 promotion sourceDigest inputs are missing")
    dirty = subprocess.run(
        ["git", "status", "--porcelain", "--", *inputs],
        cwd=paths.REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if dirty:
        raise ValueError(
            "M100 promotion requires clean sourceDigest inputs; "
            "freeze the reviewed baseline before approving M1000"
        )


def _validate_m100_envelope(
    payload: Mapping[str, Any],
    *,
    execution_id: str,
    carrier: str,
    manifest: Mapping[str, Any],
    target_set: Mapping[str, Any],
) -> None:
    assert_valid(
        dict(payload),
        "execution",
        "content_campaign_request_envelope",
        label=f"{carrier} M100 promotion envelope",
    )
    if (
        payload.get("scale") != "M100"
        or payload.get("carrier") != carrier
        or payload.get("vertical") != "travel"
        or payload.get("familyRef") != f"content/travel/{carrier}/{carrier}"
        or payload.get("executionId") != execution_id
        or int(payload.get("quota") or 0) != _M100_QUOTA
        or int(payload.get("count") or 0) < _M100_CANDIDATE_MINIMUM
    ):
        raise ValueError(
            f"{carrier} M100 promotion envelope identity or capacity drift"
        )
    if payload.get("sourceDigest") != manifest.get("sourceDigest"):
        raise ValueError(f"{carrier} M100 promotion envelope sourceDigest drift")
    if payload.get("entityCatalogDigest") != target_set.get("entityCatalogDigest"):
        raise ValueError(
            f"{carrier} M100 promotion envelope entityCatalogDigest drift"
        )


def _direct_m100_input(
    *,
    execution_id: str,
    carrier: str,
    root: Path,
    manifest: Mapping[str, Any],
    target_set: Mapping[str, Any],
) -> dict[str, Any]:
    """Freeze direct current-worktree M100 inputs when no campaign envelope exists."""

    request = _load_json(
        root / "0.plan" / "request.json",
        label=f"{carrier} M100 request",
    )
    if (
        str(request.get("familyRef") or "")
        != f"content/travel/{carrier}/{carrier}"
        or int(request.get("quota") or 0) != _M100_QUOTA
        or int(request.get("count") or 0) < _M100_CANDIDATE_MINIMUM
    ):
        raise ValueError(
            f"direct {carrier} M100 request identity or capacity drift"
        )
    source_digest = manifest.get("sourceDigest")
    if not isinstance(source_digest, Mapping) or not source_digest.get("digest"):
        raise ValueError(
            f"direct {carrier} M100 manifest sourceDigest is missing"
        )
    if not str(target_set.get("entityCatalogDigest") or ""):
        raise ValueError(
            f"direct {carrier} M100 target-set entityCatalogDigest is missing"
        )
    branch = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=paths.REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=paths.REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if not branch or not commit:
        raise ValueError(
            f"direct {carrier} M100 promotion requires a named current git branch"
        )
    return {
        "predecessorInputMode": "direct_execution",
        "gitBranch": branch,
        "gitCommitSha": commit,
        "predecessorInputDigest": _sha256(
            {
                "executionManifest": dict(manifest),
                "targetSet": dict(target_set),
                "request": request,
            }
        ),
    }


def _model_readiness(
    execution_id: str,
    *,
    carrier: str,
    root: Path,
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    payload = _load_json(root / "evidence" / "model_readiness.json", label="model readiness")
    assert_valid(
        payload,
        "execution",
        "model_readiness",
        label=f"model_readiness:{execution_id}",
    )
    author = payload.get("author") if isinstance(payload.get("author"), Mapping) else {}
    reviewer = payload.get("reviewer") if isinstance(payload.get("reviewer"), Mapping) else {}
    binding = manifest.get("modelBinding") if isinstance(manifest.get("modelBinding"), Mapping) else {}
    if (
        payload.get("executionId") != execution_id
        or not payload.get("ready")
        or payload.get("runtime") != "local"
        or author.get("model") != binding.get("authorModel")
        or author.get("modelFamily") != binding.get("authorModelFamily")
        or author.get("modelParameters") != binding.get("authorModelParameters")
        or reviewer.get("model") != binding.get("reviewerModel")
        or reviewer.get("modelFamily") != binding.get("reviewerModelFamily")
        or reviewer.get("modelParameters") != binding.get("reviewerModelParameters")
        or not isinstance(author.get("startup"), Mapping)
        or not author["startup"].get("ready")
        or not isinstance(reviewer.get("startup"), Mapping)
        or not reviewer["startup"].get("ready")
    ):
        raise ValueError(
            f"{carrier} M100 model readiness does not match the frozen model binding"
        )
    if (
        binding.get("provider") != "cursor_sdk"
        or binding.get("authorModel") != "grok-4.5"
        or binding.get("authorModelFamily") != "grok"
        or binding.get("authorModelParameters") != list(_GROK_FAST_PARAMETERS)
    ):
        raise ValueError(
            f"{carrier} M100 author is not the verified Grok Fast binding"
        )
    return payload


def _source_availability(
    execution_id: str,
    *,
    carrier: str,
    root: Path,
) -> dict[str, int]:
    payload = _load_json(
        root / "_shared" / "source_unavailable_targets.json",
        label="source availability",
    )
    if payload.get("executionId") != execution_id:
        raise ValueError(
            f"{carrier} M100 source availability executionId drift"
        )
    ready = int(payload.get("readyTargetCount") or 0)
    ineligible = int(payload.get("ineligibleTargetCount") or 0)
    candidate_count = ready + ineligible
    if ready < _M100_SOURCE_READY_MINIMUM or candidate_count < _M100_CANDIDATE_MINIMUM:
        raise ValueError(
            f"{carrier} M100 source readiness is below promotion minimum "
            f"(ready={ready}/{_M100_SOURCE_READY_MINIMUM}, candidates={candidate_count}/{_M100_CANDIDATE_MINIMUM})"
        )
    return {
        "sourceReadyCount": ready,
        "sourceIneligibleCount": ineligible,
        "candidateCount": candidate_count,
    }


def _review_and_publish(
    execution_id: str,
    *,
    carrier: str,
    root: Path,
) -> tuple[dict[str, int], dict[str, Any], dict[str, Any]]:
    from content.execution.post_review_closure import load_post_review_closure

    closure = load_post_review_closure(
        execution_id,
        root=root,
        require_quota_milestone=True,
    )
    if closure.carrier != carrier or closure.approved_quota != _M100_QUOTA:
        raise ValueError(
            f"{carrier} M100 post-review closure identity or quota drift"
        )
    if closure.qualified_count < _M100_QUOTA:
        raise ValueError(f"{carrier} M100 is not review-qualified")
    publish = _load_json(root / "publish_ref.json", label="canonical publish receipt")
    assert_valid(
        publish,
        "execution",
        "publish_ref",
        label=f"publish_ref:{execution_id}",
    )
    posts = list((publish.get("publishedRefs") or {}).get("posts") or [])
    if publish.get("executionId") != execution_id or len(posts) != closure.qualified_count:
        raise ValueError(
            f"{carrier} M100 canonical publish closure differs from review closure"
        )
    return (
        {
            "approvedQuota": closure.approved_quota,
            "qualifiedCount": closure.qualified_count,
            "finalizedCount": len(posts),
            "discardedCount": len(closure.discarded),
            "shortfallCount": max(0, closure.approved_quota - closure.qualified_count),
        },
        closure.to_payload(),
        publish,
    )


def write_scale_promotion(
    *,
    predecessor_execution_id: str,
    carrier: str,
    predecessor_envelope: Mapping[str, Any] | None = None,
    root: Path | None = None,
) -> Path:
    """Write the immutable receipt that is the sole M1000 promotion input."""

    execution_id = validate_execution_id(predecessor_execution_id)
    schema_name = _promotion_schema(carrier)
    _require_m100_execution(execution_id, carrier=carrier)
    package_root = execution_root(execution_id)
    manifest = load_frozen_execution_manifest(execution_id)
    target_set = load_frozen_target_set(execution_id)
    source_digest = manifest.get("sourceDigest")
    if not isinstance(source_digest, Mapping):
        raise ValueError(f"{carrier} M100 manifest sourceDigest is missing")
    _require_clean_source_inputs(source_digest)
    if predecessor_envelope is not None:
        _validate_m100_envelope(
            predecessor_envelope,
            execution_id=execution_id,
            carrier=carrier,
            manifest=manifest,
            target_set=target_set,
        )
        predecessor_input = {
            "predecessorInputMode": "campaign_envelope",
            "gitBranch": str(predecessor_envelope["gitBranch"]),
            "gitCommitSha": str(predecessor_envelope["gitCommitSha"]),
            "predecessorInputDigest": str(predecessor_envelope["requestDigest"]),
        }
    else:
        predecessor_input = _direct_m100_input(
            execution_id=execution_id,
            carrier=carrier,
            root=package_root,
            manifest=manifest,
            target_set=target_set,
        )
    readiness = _model_readiness(
        execution_id,
        carrier=carrier,
        root=package_root,
        manifest=manifest,
    )
    availability = _source_availability(
        execution_id,
        carrier=carrier,
        root=package_root,
    )
    review, closure, publish = _review_and_publish(
        execution_id,
        carrier=carrier,
        root=package_root,
    )
    stable: dict[str, Any] = {
        "schema": schema_name,
        "status": "approved",
        "predecessorExecutionId": execution_id,
        "vertical": "travel",
        "carrier": carrier,
        **predecessor_input,
        "sourceDigest": dict(source_digest),
        "entityCatalogDigest": str(target_set["entityCatalogDigest"]),
        "targetSetDigest": str(manifest["targetSetDigest"]),
        "modelBinding": dict(manifest["modelBinding"]),
        "modelReadinessDigest": _sha256(readiness),
        "postReviewClosureDigest": _sha256(closure),
        "publishReceiptDigest": _sha256(publish),
        **availability,
        **review,
    }
    receipt = {**stable, "receiptDigest": _sha256(stable)}
    assert_valid(
        receipt,
        "execution",
        schema_name.removeprefix("quwoquan_data."),
        label=f"{carrier} scale promotion:{execution_id}",
    )
    path = promotion_path(execution_id, carrier=carrier, root=root)
    if path.is_file():
        existing = _load_json(path, label=f"{carrier} scale promotion")
        if existing != receipt:
            raise ValueError(f"{carrier} scale promotion receipt collision: {path}")
        return path
    write_json(path, receipt)
    return path


def load_scale_promotion(
    path: Path,
    *,
    carrier: str,
) -> dict[str, Any]:
    schema_name = _promotion_schema(carrier)
    payload = _load_json(path, label=f"{carrier} scale promotion")
    assert_valid(
        payload,
        "execution",
        schema_name.removeprefix("quwoquan_data."),
        label=f"{carrier} scale promotion:{path}",
    )
    digest = _sha256(
        {
            key: value
            for key, value in payload.items()
            if key != "receiptDigest"
        }
    )
    if payload.get("receiptDigest") != digest:
        raise ValueError(f"{carrier} scale promotion receipt digest drift: {path}")
    return payload


def require_m1000_promotion(
    receipt: Mapping[str, Any] | None,
    *,
    carrier: str,
    git_branch: str,
    git_commit_sha: str,
    source_digest: Mapping[str, Any],
    entity_catalog_digest: str,
) -> dict[str, Any]:
    """Revalidate a promoted M100 result against the M1000 frozen inputs."""

    if not isinstance(receipt, Mapping):
        article = "an" if carrier == "image" else "a"
        raise ValueError(
            f"GATE_BLOCK travel/{carrier} M1000 requires {article} "
            f"{carrier} scale promotion receipt"
        )
    schema_name = _promotion_schema(carrier)
    payload = dict(receipt)
    assert_valid(
        payload,
        "execution",
        schema_name.removeprefix("quwoquan_data."),
        label=f"travel/{carrier} M1000 promotion receipt",
    )
    expected_digest = _sha256(
        {key: value for key, value in payload.items() if key != "receiptDigest"}
    )
    if payload.get("receiptDigest") != expected_digest:
        raise ValueError(
            f"GATE_BLOCK travel/{carrier} M100 promotion receipt digest drift"
        )
    if (
        payload.get("status") != "approved"
        or payload.get("vertical") != "travel"
        or payload.get("carrier") != carrier
        or int(payload.get("approvedQuota") or 0) != _M100_QUOTA
        or int(payload.get("qualifiedCount") or 0) < _M100_QUOTA
        or int(payload.get("finalizedCount") or 0) != int(payload.get("qualifiedCount") or -1)
        or int(payload.get("sourceReadyCount") or 0) < _M100_SOURCE_READY_MINIMUM
        or int(payload.get("candidateCount") or 0) < _M100_CANDIDATE_MINIMUM
    ):
        raise ValueError(
            f"GATE_BLOCK travel/{carrier} M100 promotion receipt is not scale-eligible"
        )
    if (
        payload.get("gitBranch") != git_branch
        or payload.get("gitCommitSha") != git_commit_sha
        or payload.get("sourceDigest") != dict(source_digest)
        or payload.get("entityCatalogDigest") != entity_catalog_digest
    ):
        raise ValueError(
            f"GATE_BLOCK travel/{carrier} M1000 inputs drift from the approved "
            "M100 promotion receipt"
        )
    return payload


def write_video_scale_promotion(
    *,
    predecessor_execution_id: str,
    predecessor_envelope: Mapping[str, Any] | None = None,
    root: Path | None = None,
) -> Path:
    return write_scale_promotion(
        predecessor_execution_id=predecessor_execution_id,
        carrier="video",
        predecessor_envelope=predecessor_envelope,
        root=root,
    )


def write_image_scale_promotion(
    *,
    predecessor_execution_id: str,
    predecessor_envelope: Mapping[str, Any] | None = None,
    root: Path | None = None,
) -> Path:
    return write_scale_promotion(
        predecessor_execution_id=predecessor_execution_id,
        carrier="image",
        predecessor_envelope=predecessor_envelope,
        root=root,
    )


def load_video_scale_promotion(path: Path) -> dict[str, Any]:
    return load_scale_promotion(path, carrier="video")


def load_image_scale_promotion(path: Path) -> dict[str, Any]:
    return load_scale_promotion(path, carrier="image")


def require_video_m1000_promotion(
    receipt: Mapping[str, Any] | None,
    *,
    git_branch: str,
    git_commit_sha: str,
    source_digest: Mapping[str, Any],
    entity_catalog_digest: str,
) -> dict[str, Any]:
    return require_m1000_promotion(
        receipt,
        carrier="video",
        git_branch=git_branch,
        git_commit_sha=git_commit_sha,
        source_digest=source_digest,
        entity_catalog_digest=entity_catalog_digest,
    )


def require_image_m1000_promotion(
    receipt: Mapping[str, Any] | None,
    *,
    git_branch: str,
    git_commit_sha: str,
    source_digest: Mapping[str, Any],
    entity_catalog_digest: str,
) -> dict[str, Any]:
    return require_m1000_promotion(
        receipt,
        carrier="image",
        git_branch=git_branch,
        git_commit_sha=git_commit_sha,
        source_digest=source_digest,
        entity_catalog_digest=entity_catalog_digest,
    )


__all__ = [
    "IMAGE_PROMOTION_SCHEMA",
    "PROMOTION_SCHEMA",
    "load_image_scale_promotion",
    "load_scale_promotion",
    "load_video_scale_promotion",
    "promotion_path",
    "promotion_root",
    "require_image_m1000_promotion",
    "require_m1000_promotion",
    "require_video_m1000_promotion",
    "write_image_scale_promotion",
    "write_scale_promotion",
    "write_video_scale_promotion",
]
