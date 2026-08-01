"""Immutable carrier request envelopes for copy-session operators."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from core import paths
from core.io import read_json, write_json
from core.schema import assert_valid
from core.source_digest import current_source_digest
from content.execution.campaign_process import CAMPAIGN_CARRIERS
from content.execution.campaign_scale import (
    CampaignScaleError,
    resolve_campaign_scale,
)
from content.execution.identity import build_execution_id
from content.execution.request import resolve_candidate_pool
from content.execution.scale_promotion import (
    load_image_scale_promotion,
    load_video_scale_promotion,
    require_image_m1000_promotion,
    require_video_m1000_promotion,
)
from content.execution.workspace import entity_catalog_digest


ENVELOPE_SCHEMA = "quwoquan_data.content_campaign_request_envelope"

_OPERATIONS = {
    "homepage": "homepage.generate",
    "article": "article.generate",
    "image": "image.generate",
    "video": "video.generate",
}
_SELECTORS = {
    "homepage": "source-ready-priority",
    "article": "priority",
    "image": "priority",
    "video": "source-ready-priority",
}
_OPERATOR_PROMPTS = {
    "homepage": "执行实体内容生成",
    "article": "执行文章内容生成",
    "image": "执行图片内容生成",
    "video": "执行视频内容生成",
}
_SCOPE_TOKEN_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_VERTICAL_RE = re.compile(r"^[a-z][a-z0-9-]*$")


def envelopes_root(*, root: Path | None = None) -> Path:
    return (root or paths.DATA_LOCAL_ROOT) / "workspace" / "content-campaign-envelopes"


def scale_root(
    scale: str,
    *,
    vertical: str = "travel",
    root: Path | None = None,
) -> Path:
    resolved = resolve_campaign_scale(scale=scale)
    vertical_id = _normalize_vertical(vertical)
    return envelopes_root(root=root) / vertical_id / resolved.scale


def envelope_path(
    scale: str,
    carrier: str,
    *,
    vertical: str = "travel",
    root: Path | None = None,
) -> Path:
    if carrier not in _OPERATIONS:
        raise ValueError(f"unsupported carrier: {carrier}")
    return scale_root(scale, vertical=vertical, root=root) / f"{carrier}.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _git_commit(repo_root: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _git_branch(repo_root: Path) -> str:
    branch = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if not branch:
        raise ValueError("campaign envelope requires a named frozen main branch")
    return branch


def _require_clean_source_inputs(
    source_document: dict[str, object],
    *,
    repo_root: Path,
) -> None:
    inputs = [str(item) for item in source_document.get("inputs") or []]
    dirty = subprocess.run(
        ["git", "status", "--porcelain", "--", *inputs],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if dirty:
        raise ValueError(
            "campaign envelope requires clean sourceDigest inputs; "
            "freeze the reviewed baseline before writing envelopes"
        )


def _normalize_vertical(vertical: str) -> str:
    value = str(vertical or "").strip().lower()
    if not _VERTICAL_RE.fullmatch(value):
        raise ValueError(f"GATE_BLOCK unsupported campaign vertical: {vertical}")
    return value


def _slug_token(value: str, *, label: str) -> str:
    token = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower()).strip("-")
    if not token or not _SCOPE_TOKEN_RE.fullmatch(token):
        raise ValueError(f"GATE_BLOCK campaign {label} is not a valid scope token: {value}")
    return token


def normalize_execution_scope(
    region_ref: str,
    topic: str | None = None,
) -> str:
    parts = [part for part in str(region_ref or "").strip().strip("/").split("/") if part]
    if not parts:
        raise ValueError("GATE_BLOCK regionRef must be non-empty")
    base = None
    for part in parts:
        candidate = part.strip().lower()
        if _SCOPE_TOKEN_RE.fullmatch(candidate):
            base = candidate
            break
    if base is None:
        base = _slug_token(parts[0], label="regionRef")
    if topic is None or not str(topic).strip():
        return base
    return f"{base}-{_slug_token(str(topic), label='topic')}"


def default_family_ref(*, vertical: str, carrier: str) -> str:
    if carrier not in _OPERATIONS:
        raise ValueError(f"unsupported carrier: {carrier}")
    return f"content/{vertical}/{carrier}/{carrier}"


def _execution_ids(
    *,
    scale: str,
    vertical: str,
    scope: str,
    day: str,
    sequence: int = 1,
) -> dict[str, str]:
    intent = scale.lower()
    return {
        carrier: build_execution_id(
            run_date=day,
            vertical=vertical,
            content_type=carrier,
            intent=intent,
            scope=scope,
            phase="scale",
            sequence=sequence,
        )
        for carrier in CAMPAIGN_CARRIERS
    }


def build_envelope(
    *,
    scale: str | None = None,
    quota: int | None = None,
    carrier: str,
    region_ref: str,
    vertical: str = "travel",
    topic: str | None = None,
    target_names: Iterable[str] | None = None,
    source_providers: Iterable[str] | None = None,
    family_ref: str | None = None,
    repo_root: Path | None = None,
    day: str | None = None,
    sequence: int = 1,
    promotion_receipt: Mapping[str, Any] | Path | None = None,
) -> dict[str, Any]:
    if carrier not in _OPERATIONS:
        raise ValueError(f"unsupported carrier: {carrier}")
    resolved = resolve_campaign_scale(scale=scale, quota=quota)
    vertical_id = _normalize_vertical(vertical)
    source_repo = (repo_root or paths.REPO_ROOT).resolve()
    try:
        quota_value, count = resolve_candidate_pool(quota=resolved.quota, count=None)
    except SystemExit as exc:
        raise CampaignScaleError(str(exc)) from exc
    source = current_source_digest(repo_root=source_repo).to_document()
    _require_clean_source_inputs(source, repo_root=source_repo)
    discovery = (
        source_repo
        / "quwoquan_data"
        / "reference"
        / vertical_id
        / "entities"
        / region_ref
    )
    if not discovery.is_dir():
        raise ValueError(f"region reference does not exist: {region_ref}")
    catalog_digest = entity_catalog_digest(
        discovery.relative_to(source_repo).as_posix()
    )
    stamp = day or datetime.now(timezone.utc).strftime("%Y%m%d")
    scope = normalize_execution_scope(region_ref, topic)
    ids = _execution_ids(
        scale=resolved.scale,
        vertical=vertical_id,
        scope=scope,
        day=stamp,
        sequence=sequence,
    )
    names = sorted({str(item).strip() for item in (target_names or []) if str(item).strip()})
    providers = sorted(
        {str(item).strip() for item in (source_providers or []) if str(item).strip()}
    )
    topic_value = str(topic).strip() if topic is not None and str(topic).strip() else None
    git_branch = _git_branch(source_repo)
    git_commit_sha = _git_commit(source_repo)
    promotion_reference: dict[str, Any] | None = None
    if (
        resolved.scale == "M1000"
        and vertical_id == "travel"
        and carrier in {"image", "video"}
    ):
        if isinstance(promotion_receipt, Path):
            promotion = (
                load_image_scale_promotion(promotion_receipt)
                if carrier == "image"
                else load_video_scale_promotion(promotion_receipt)
            )
        elif isinstance(promotion_receipt, Mapping):
            promotion = dict(promotion_receipt)
        else:
            promotion = None
        approved = (
            require_image_m1000_promotion(
                promotion,
                git_branch=git_branch,
                git_commit_sha=git_commit_sha,
                source_digest=source,
                entity_catalog_digest=catalog_digest,
            )
            if carrier == "image"
            else require_video_m1000_promotion(
                promotion,
                git_branch=git_branch,
                git_commit_sha=git_commit_sha,
                source_digest=source,
                entity_catalog_digest=catalog_digest,
            )
        )
        promotion_reference = {
            "predecessorExecutionId": approved["predecessorExecutionId"],
            "receiptDigest": approved["receiptDigest"],
            "gitBranch": approved["gitBranch"],
            "gitCommitSha": approved["gitCommitSha"],
            "sourceDigest": approved["sourceDigest"],
            "entityCatalogDigest": approved["entityCatalogDigest"],
            "qualifiedCount": approved["qualifiedCount"],
            "finalizedCount": approved["finalizedCount"],
        }
    stable: dict[str, Any] = {
        "schema": ENVELOPE_SCHEMA,
        "scale": resolved.scale,
        "carrier": carrier,
        "operation": _OPERATIONS[carrier],
        "vertical": vertical_id,
        "familyRef": family_ref or default_family_ref(
            vertical=vertical_id,
            carrier=carrier,
        ),
        "regionRef": region_ref,
        "selector": _SELECTORS[carrier],
        "quota": quota_value,
        "count": count,
        "topic": topic_value,
        "targetNames": names,
        "sourceProviders": providers,
        "retryOf": None,
        "rootExecutionId": ids["homepage"],
        "executionId": ids[carrier],
        "gitBranch": git_branch,
        "gitCommitSha": git_commit_sha,
        "sourceDigest": source,
        "entityCatalogDigest": catalog_digest,
        "allowedStage": "submit-only",
        "operatorPrompt": _OPERATOR_PROMPTS[carrier],
    }
    if promotion_reference is not None:
        stable[f"{carrier}ScalePromotion"] = promotion_reference
    return {
        **stable,
        "requestDigest": _sha256(stable),
        "frozenAt": _utc_now(),
    }


def write_scale_envelopes(
    scale: str | None = None,
    *,
    quota: int | None = None,
    region_ref: str = "china",
    vertical: str = "travel",
    topic: str | None = None,
    target_names: Iterable[str] | None = None,
    source_providers: Iterable[str] | None = None,
    family_ref: str | None = None,
    carriers: Iterable[str] = CAMPAIGN_CARRIERS,
    repo_root: Path | None = None,
    output_root: Path | None = None,
    day: str | None = None,
    sequence: int = 1,
    promotion_receipt: Mapping[str, Any] | Path | None = None,
) -> dict[str, Path]:
    """Write immutable envelopes for selected carriers at one resolved scale."""

    resolved = resolve_campaign_scale(scale=scale, quota=quota)
    selected = tuple(carriers) or CAMPAIGN_CARRIERS
    unknown = [carrier for carrier in selected if carrier not in _OPERATIONS]
    if unknown:
        raise ValueError(f"unsupported carriers: {unknown}")
    written: dict[str, Path] = {}
    for carrier in selected:
        payload = build_envelope(
            scale=resolved.scale,
            quota=resolved.quota,
            carrier=carrier,
            region_ref=region_ref,
            vertical=vertical,
            topic=topic,
            target_names=target_names,
            source_providers=source_providers,
            family_ref=family_ref,
            repo_root=repo_root,
            day=day,
            sequence=sequence,
            promotion_receipt=promotion_receipt,
        )
        assert_valid(
            payload,
            "execution",
            "content_campaign_request_envelope",
            label=f"campaign envelope:{resolved.scale}:{carrier}",
        )
        path = envelope_path(
            resolved.scale,
            carrier,
            vertical=vertical,
            root=output_root,
        )
        if path.is_file():
            existing = read_json(path)
            if existing != payload and (
                str(existing.get("requestDigest") or "")
                != str(payload.get("requestDigest") or "")
            ):
                raise ValueError(
                    f"campaign envelope already frozen with different digest: {path}"
                )
            written[carrier] = path
            continue
        write_json(path, payload)
        written[carrier] = path
    return written


def write_campaign_envelopes(
    *,
    scales: Iterable[str] | None = None,
    quota: int | None = None,
    region_ref: str = "china",
    vertical: str = "travel",
    topic: str | None = None,
    target_names: Iterable[str] | None = None,
    source_providers: Iterable[str] | None = None,
    family_ref: str | None = None,
    carriers: Iterable[str] = CAMPAIGN_CARRIERS,
    repo_root: Path | None = None,
    output_root: Path | None = None,
    day: str | None = None,
    sequence: int = 1,
    promotion_receipt: Mapping[str, Any] | Path | None = None,
) -> dict[str, dict[str, Path]]:
    """Write envelopes for one or more scales (named or M{n}) or a single quota."""

    scale_list = [str(item).strip() for item in (scales or []) if str(item).strip()]
    if scale_list and quota is not None and len(scale_list) != 1:
        raise CampaignScaleError(
            "GATE_BLOCK write_campaign_envelopes cannot combine quota= with multiple scales"
        )
    if not scale_list:
        if quota is None:
            raise CampaignScaleError(
                "GATE_BLOCK write_campaign_envelopes requires scales= or quota="
            )
        resolved = resolve_campaign_scale(quota=quota)
        scale_list = [resolved.scale]
    written: dict[str, dict[str, Path]] = {}
    for scale in scale_list:
        resolved = resolve_campaign_scale(
            scale=scale,
            quota=quota if len(scale_list) == 1 else None,
        )
        written[resolved.scale] = write_scale_envelopes(
            resolved.scale,
            quota=resolved.quota,
            region_ref=region_ref,
            vertical=vertical,
            topic=topic,
            target_names=target_names,
            source_providers=source_providers,
            family_ref=family_ref,
            carriers=carriers,
            repo_root=repo_root,
            output_root=output_root,
            day=day,
            sequence=sequence,
            promotion_receipt=promotion_receipt,
        )
    return written


__all__ = [
    "build_envelope",
    "default_family_ref",
    "envelope_path",
    "envelopes_root",
    "normalize_execution_scope",
    "scale_root",
    "write_campaign_envelopes",
    "write_scale_envelopes",
]
