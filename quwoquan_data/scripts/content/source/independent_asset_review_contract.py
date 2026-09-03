"""Storage and digest primitives for independent asset-review receipts."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from core.io import read_json
from core.schema import assert_valid


class IndependentAssetReviewError(ValueError):
    """One independent asset-review input is absent, drifted, or self-issued."""


def asset_snapshot(asset: Mapping[str, Any]) -> dict[str, Any]:
    snapshot = {
        "assetId": str(asset.get("assetId") or "").strip(),
        "entityId": str(asset.get("entityId") or "").strip(),
        "observedEntityId": str(asset.get("observedEntityId") or "").strip(),
        "contentSha256": str(asset.get("contentSha256") or "").strip(),
        "casRef": str(asset.get("assetRef") or "").strip(),
        "sourceUrl": str(asset.get("sourceUrl") or "").strip(),
        "platform": str(asset.get("platform") or "").strip(),
        "creator": str(asset.get("creator") or "").strip(),
        "capturedAt": str(asset.get("capturedAt") or "").strip(),
        "license": str(asset.get("license") or "").strip(),
        "termsUrl": str(asset.get("termsUrl") or "").strip(),
        "authorizationProof": str(asset.get("authorizationProof") or "").strip(),
        "rightsIssues": [
            str(item).strip()
            for item in (asset.get("rightsIssues") or [])
            if str(item).strip()
        ],
        "acquisitionStatus": str(asset.get("acquisitionStatus") or "").strip(),
        "rightsStatus": str(asset.get("rightsStatus") or "").strip(),
        "authorizationRequired": asset.get("authorizationRequired"),
        "distributionDecision": str(
            asset.get("distributionDecision") or ""
        ).strip(),
    }
    for field in ("licenseSnapshot", "usageScope", "modelReleaseStatus"):
        if field in asset:
            snapshot[field] = str(asset.get(field) or "").strip()
    for field in ("mediaProbe", "popularitySignals"):
        value = asset.get(field)
        if isinstance(value, Mapping):
            snapshot[field] = dict(value)
    poster_rights = asset.get("posterRights")
    if isinstance(poster_rights, Mapping):
        snapshot["poster"] = {
            "contentSha256": str(asset.get("posterContentSha256") or "").strip(),
            "casRef": str(asset.get("posterAssetRef") or "").strip(),
            "bytes": asset.get("posterBytes"),
            "mimeType": str(asset.get("posterMimeType") or "").strip(),
            "rights": dict(poster_rights),
        }
    return snapshot


def project_research_judgment_to_acquisition_truth(
    judgment: Mapping[str, Any],
    *,
    snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    """Keep Research rights as acquisition truth; semantic review owns safety."""
    projected = dict(judgment)
    if snapshot.get("distributionDecision") != "research_allowed":
        return projected
    projected.update(
        {
            "rightsStatus": snapshot.get("rightsStatus"),
            "authorizationRequired": snapshot.get("authorizationRequired"),
        }
    )
    safety_passed = (
        projected.get("safetyStatus") == "passed"
        and projected.get("entityMatch") == "matched"
        and projected.get("qualityStatus") == "passed"
        and projected.get("privacyRisk") == "none"
        and projected.get("minorRisk") == "none"
        and projected.get("maliciousMediaRisk") == "none"
        and projected.get("watermarkStatus") == "absent"
    )
    if safety_passed:
        projected["distributionDecision"] = "research_allowed"
    return projected


def assert_video_asset_snapshot_publishable(snapshot: Mapping[str, Any]) -> None:
    poster = snapshot.get("poster")
    poster = poster if isinstance(poster, Mapping) else {}
    poster_rights = poster.get("rights")
    poster_rights = poster_rights if isinstance(poster_rights, Mapping) else {}
    inherited = {
        "sourceUrl": snapshot.get("sourceUrl"),
        "license": snapshot.get("license"),
        "termsUrl": snapshot.get("termsUrl"),
        "authorizationProof": snapshot.get("authorizationProof"),
        "rightsStatus": snapshot.get("rightsStatus"),
        "authorizationRequired": snapshot.get("authorizationRequired"),
        "distributionDecision": snapshot.get("distributionDecision"),
        "rightsIssues": snapshot.get("rightsIssues"),
    }
    if (
        not str(poster.get("contentSha256") or "").startswith("sha256:")
        or not str(poster.get("casRef") or "").strip()
        or not isinstance(poster.get("bytes"), int)
        or int(poster["bytes"]) < 1
        or poster.get("mimeType") != "image/png"
        or poster_rights.get("derivation") != "frame_from_licensed_video"
        or any(poster_rights.get(key) != value for key, value in inherited.items())
    ):
        raise IndependentAssetReviewError(
            "independent video review lacks exact poster CAS and inherited rights evidence"
        )
    probe = snapshot.get("mediaProbe")
    if not isinstance(probe, Mapping) or not all(
        (
            probe.get("playable") is True,
            probe.get("motionVideo") is True,
            probe.get("staticImageSequence") is False,
            probe.get("premiumPlayableEligible") is True,
        )
    ):
        raise IndependentAssetReviewError(
            "independent video review lacks playable motion-media evidence"
        )
    from content.source.professional_video_receipt import (
        assert_observed_popularity_signals,
    )

    assert_observed_popularity_signals(
        snapshot.get("popularitySignals"),
        asset_id=str(snapshot.get("assetId") or "<missing>"),
    )


def canonical_digest(value: Mapping[str, Any], *, excluded: str | None = None) -> str:
    payload = dict(value)
    if excluded is not None:
        payload.pop(excluded, None)
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def audited_path(path: Path, *, output_root: Path, label: str) -> tuple[Path, str]:
    root = output_root.resolve()
    resolved = path.resolve()
    if path.is_symlink() or not resolved.is_file():
        raise IndependentAssetReviewError(f"{label} must be one regular audited file: {path}")
    try:
        relative = resolved.relative_to(root).as_posix()
    except ValueError as exc:
        raise IndependentAssetReviewError(
            f"{label} must be below QWQ_OUTPUT_ROOT: {path}"
        ) from exc
    return resolved, relative


def resolve_ref(ref: str, *, output_root: Path, label: str) -> Path:
    relative = Path(str(ref or "").strip())
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise IndependentAssetReviewError(f"{label} is unsafe: {ref}")
    path = output_root.resolve() / relative
    audited, _ = audited_path(path, output_root=output_root, label=label)
    return audited


def load_document(
    path: Path,
    *,
    output_root: Path,
    schema_group: str,
    schema_name: str,
    label: str,
) -> tuple[dict[str, Any], str, str]:
    audited, ref = audited_path(path, output_root=output_root, label=label)
    payload = read_json(audited)
    if not isinstance(payload, dict):
        raise IndependentAssetReviewError(f"{label} must be an object")
    try:
        assert_valid(payload, schema_group, schema_name, label=label)
    except (FileNotFoundError, TypeError, ValueError) as exc:
        raise IndependentAssetReviewError(str(exc)) from exc
    return payload, ref, file_digest(audited)


def write_create_once(path: Path, document: Mapping[str, Any]) -> None:
    body = json.dumps(document, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = ""
    try:
        with tempfile.NamedTemporaryFile(
            "wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = handle.name
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            existing = read_json(path)
            existing_stable = {
                key: value
                for key, value in existing.items()
                if key not in {"recordedAt", "receiptDigest"}
            }
            document_stable = {
                key: value
                for key, value in document.items()
                if key not in {"recordedAt", "receiptDigest"}
            }
            if existing_stable != document_stable:
                raise IndependentAssetReviewError(
                    f"independent asset review create-once collision: {path}"
                )
    finally:
        if temporary:
            Path(temporary).unlink(missing_ok=True)


__all__ = [
    "IndependentAssetReviewError",
    "assert_video_asset_snapshot_publishable",
    "asset_snapshot",
    "audited_path",
    "canonical_digest",
    "file_digest",
    "load_document",
    "project_research_judgment_to_acquisition_truth",
    "resolve_ref",
    "write_create_once",
]
