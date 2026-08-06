"""Create a fail-closed research-to-commercial object migration receipt."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from content.release.canonical.commercial_transition_evidence import (
    CommercialTransitionEvidenceError,
    document_digest,
    load_commercial_transition_evidence,
)
from content.release.canonical.object_transaction_contract import _read_json
from core.io import write_json
from core.paths import OUTPUT_ROOT, RELEASE_ROOT
from core.release_layout import payload_digest, payload_file
from core.schema import assert_valid


class CommercialTransitionError(RuntimeError):
    pass


def _safe_segment(value: str, *, label: str) -> str:
    normalized = str(value or "").strip()
    path = Path(normalized)
    if (
        not normalized
        or normalized in {".", ".."}
        or path.is_absolute()
        or len(path.parts) != 1
        or "/" in normalized
        or "\\" in normalized
    ):
        raise CommercialTransitionError(f"{label} must be one safe segment")
    return normalized


def _evidence_ref(path: Path, *, output_root: Path) -> str:
    try:
        return path.resolve().relative_to(output_root.resolve()).as_posix()
    except ValueError as exc:
        raise CommercialTransitionError(
            "cleanup evidence must be an audited file below QWQ_OUTPUT_ROOT"
        ) from exc


def _assets(admission: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    rows = admission.get("assets")
    if not isinstance(rows, list):
        raise CommercialTransitionError("release asset admission lacks assets")
    result = {
        str(row.get("assetId") or ""): dict(row)
        for row in rows
        if isinstance(row, Mapping)
    }
    if "" in result or len(result) != len(rows):
        raise CommercialTransitionError("release asset admission IDs are invalid")
    return result


def write_commercial_transition(
    *,
    research_release_id: str,
    commercial_release_id: str,
    transition_run_id: str,
    cleanup_evidence_path: Path,
    release_root: Path = RELEASE_ROOT,
    output_root: Path = OUTPUT_ROOT,
) -> tuple[dict[str, Any], Path]:
    research_release_id = _safe_segment(
        research_release_id, label="researchReleaseId"
    )
    commercial_release_id = _safe_segment(
        commercial_release_id, label="commercialReleaseId"
    )
    transition_run_id = _safe_segment(
        transition_run_id, label="transitionRunId"
    )
    if research_release_id == commercial_release_id:
        raise CommercialTransitionError(
            "commercial transition requires a new immutable release"
        )
    research_release = release_root / research_release_id
    commercial_release = release_root / commercial_release_id
    research_header = _read_json(payload_file(research_release, "release.json"))
    commercial_header = _read_json(payload_file(commercial_release, "release.json"))
    research = _read_json(payload_file(research_release, "asset_admission.json"))
    commercial = _read_json(payload_file(commercial_release, "asset_admission.json"))
    research_digest = payload_digest(research_release)
    commercial_digest = payload_digest(commercial_release)
    if (
        research.get("releaseClass") != "research"
        or research_header.get("releaseClass") != "research"
    ):
        raise CommercialTransitionError("source release is not research")
    if (
        commercial.get("releaseClass") != "commercial"
        or commercial_header.get("releaseClass") != "commercial"
        or commercial.get("productLifecycleState") != "commercial"
        or commercial.get("containsUnverifiedAssets") is not False
        or commercial.get("authorizationRequiredAssetIds") != []
    ):
        raise CommercialTransitionError(
            "target commercial release contains non-commercial assets"
        )
    research_sources = research_header.get("sourceDigests")
    commercial_sources = commercial_header.get("sourceDigests")
    if (
        not isinstance(research_sources, list)
        or len(research_sources) != 1
        or not isinstance(research_sources[0], Mapping)
        or not isinstance(commercial_sources, list)
        or len(commercial_sources) != 1
        or not isinstance(commercial_sources[0], Mapping)
    ):
        raise CommercialTransitionError(
            "commercial transition requires one frozen sourceDigest per release"
        )
    research_source_digest = str(research_sources[0].get("digest") or "")
    commercial_source_digest = str(commercial_sources[0].get("digest") or "")
    if (
        not research_source_digest.startswith("sha256:")
        or not commercial_source_digest.startswith("sha256:")
        or research_source_digest == commercial_source_digest
    ):
        raise CommercialTransitionError(
            "commercial transition requires a new commercial sourceDigest"
        )
    research_assets = _assets(research)
    commercial_assets = _assets(commercial)
    commercial_by_object: dict[str, list[str]] = {}
    for asset_id, asset in commercial_assets.items():
        if asset.get("distributionDecision") != "commercial_allowed":
            raise CommercialTransitionError(
                f"commercial asset is not commercial_allowed: {asset_id}"
            )
        commercial_by_object.setdefault(str(asset.get("objectRef") or ""), []).append(
            asset_id
        )
    authorization_ids = research.get("authorizationRequiredAssetIds")
    if not isinstance(authorization_ids, list):
        raise CommercialTransitionError(
            "research authorizationRequiredAssetIds are missing"
        )
    migrations: list[dict[str, Any]] = []
    for asset_id in sorted(str(item) for item in authorization_ids):
        research_asset = research_assets.get(asset_id)
        if research_asset is None:
            raise CommercialTransitionError(
                f"research authorization asset is absent: {asset_id}"
            )
        object_ref = str(research_asset.get("objectRef") or "")
        if asset_id in commercial_assets:
            action = "verified_preserved"
            commercial_ids = [asset_id]
        else:
            commercial_ids = sorted(commercial_by_object.get(object_ref, []))
            action = "replaced" if commercial_ids else "removed"
        migrations.append(
            {
                "researchAssetId": asset_id,
                "objectRef": object_ref,
                "action": action,
                "commercialAssetIds": commercial_ids,
            }
        )
    try:
        verified_evidence = load_commercial_transition_evidence(
            cleanup_evidence_path,
            research_release_id=research_release_id,
            research_manifest_digest=research_digest,
            commercial_release_id=commercial_release_id,
            commercial_manifest_digest=commercial_digest,
            output_root=output_root,
        )
    except CommercialTransitionEvidenceError as exc:
        raise CommercialTransitionError(str(exc)) from exc
    environment_cleanup = [dict(row) for row in verified_evidence.environments]
    document: dict[str, Any] = {
        "schema": "quwoquan_data.commercial_transition",
        "transitionRunId": transition_run_id,
        "researchReleaseId": research_release_id,
        "researchManifestDigest": research_digest,
        "researchSourceDigest": research_source_digest,
        "commercialReleaseId": commercial_release_id,
        "commercialManifestDigest": commercial_digest,
        "commercialSourceDigest": commercial_source_digest,
        "objectMigrations": migrations,
        "environmentCleanup": sorted(
            environment_cleanup, key=lambda row: str(row["environment"])
        ),
        "unauthorizedReadbackCount": 0,
        "cleanupEvidenceRef": _evidence_ref(
            cleanup_evidence_path, output_root=output_root
        ),
        "cleanupEvidenceDigest": verified_evidence.evidence_digest,
        "passed": True,
        "recordedAt": datetime.now(timezone.utc).isoformat(),
    }
    document["receiptDigest"] = document_digest(
        document,
        excluded="receiptDigest",
    )
    assert_valid(
        document,
        "release",
        "commercial_transition",
        label="commercial transition",
    )
    path = (
        output_root
        / "data/commercial-transitions"
        / commercial_release_id
        / transition_run_id
        / "receipt.json"
    )
    try:
        path.parent.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise CommercialTransitionError(
            f"append-only commercial transition already exists: {path.parent}"
        ) from exc
    write_json(path, document)
    return document, path


__all__ = ["CommercialTransitionError", "write_commercial_transition"]
