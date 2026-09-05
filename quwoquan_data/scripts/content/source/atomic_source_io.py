"""Atomic, non-semantic I/O for one explicit source candidate."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import urllib.error
import urllib.request
import mimetypes
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.content_library import library_root_for_output, link_bytes_from_library
from core.io import read_json
from core.image_variants import derive_budget_compliant_variant
from core.object_storage_budget import source_unit_asset_budget_bytes
from core.paths import execution_root, execution_source_unit_dir
from core.schema import assert_valid
from content.execution.identity import parse_execution_id
from content.execution.runtime_contract import stage_execution_context

_SOURCE_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")
_ALLOWED_RECEIPT_SCHEMAS = {
    "image": "quwoquan_data.professional_image_acquisition_receipt",
    "video": "quwoquan_data.professional_video_acquisition_receipt",
}
_ACCEPTED_DECISIONS = {"research_allowed", "commercial_allowed"}
_MAX_SOURCE_BYTES = 32 * 1024 * 1024


def _stable_bytes(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _sha256(body: bytes) -> str:
    return "sha256:" + hashlib.sha256(body).hexdigest()


def _safe_source_id(value: object) -> str:
    source_id = str(value or "").strip()
    if not _SOURCE_ID_RE.fullmatch(source_id):
        raise ValueError("candidate.sourceId must be one safe path segment")
    return source_id


def _target_object_dir(execution_id: str, target_ref: str) -> Path:
    raw = str(target_ref or "").strip().strip("/")
    parts = Path(raw).parts
    if not raw or ".." in parts or "." in parts:
        raise ValueError("targetRef is empty or unsafe")
    if raw.startswith("entity/"):
        raw = "entities/" + raw.removeprefix("entity/")
    normalized = Path(raw)
    parts = normalized.parts
    valid_entity = len(parts) == 4 and parts[0] == "entities"
    valid_post = len(parts) >= 5 and parts[0] == "posts" and parts[1] in {"article", "image", "video"}
    if not (valid_entity or valid_post):
        raise ValueError("targetRef must identify one entities/... or posts/... object")
    return execution_root(execution_id) / normalized


def _write_locked_bytes(path: Path, body: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = ""
    try:
        with tempfile.NamedTemporaryFile(
            "wb", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False
        ) as handle:
            temporary = handle.name
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = ""
    finally:
        if temporary:
            Path(temporary).unlink(missing_ok=True)


def _fsync_tree(root: Path) -> None:
    for path in sorted(root.rglob("*")):
        if path.is_file():
            with path.open("rb") as handle:
                os.fsync(handle.fileno())
    descriptor = os.open(root, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _lock(path: Path):
    import fcntl

    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
    return handle


def _read_https(url: str) -> tuple[bytes, str]:
    if not url.startswith("https://"):
        raise ValueError("source candidate URL must use HTTPS")
    request = urllib.request.Request(url, headers={"User-Agent": "quwoquan-source-atomic/1"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 - HTTPS checked above.
            final_url = response.geturl()
            if not final_url.startswith("https://"):
                raise ValueError("source fetch redirected outside HTTPS")
            length = response.headers.get("Content-Length")
            if length and int(length) > _MAX_SOURCE_BYTES:
                raise ValueError("source snapshot exceeds byte limit")
            body = response.read(_MAX_SOURCE_BYTES + 1)
    except urllib.error.URLError as exc:
        raise ValueError(f"source HTTPS fetch failed: {exc}") from exc
    if len(body) > _MAX_SOURCE_BYTES:
        raise ValueError("source snapshot exceeds byte limit")
    return body, final_url


def _read_manual_file(candidate: Mapping[str, Any], *, manual_root: Path | None) -> tuple[bytes, str]:
    manual_file = str(candidate.get("manualFile") or "").strip()
    rights_clue = str(candidate.get("rightsClue") or "").strip()
    expected = str(candidate.get("contentSha256") or "").strip()
    if not manual_file or not rights_clue or not expected:
        raise ValueError("manual source requires manualFile, rightsClue, and contentSha256")
    if manual_root is None:
        raise ValueError("manual source requires --manual-root")
    relative = Path(manual_file)
    root = manual_root.expanduser().resolve()
    source = (root / relative).resolve()
    if relative.is_absolute() or ".." in relative.parts or (source != root and root not in source.parents):
        raise ValueError("manualFile escapes --manual-root")
    if source.is_symlink() or not source.is_file():
        raise ValueError("manualFile must be one regular file")
    body = source.read_bytes()
    if not body or len(body) > _MAX_SOURCE_BYTES or _sha256(body) != expected:
        raise ValueError("manualFile digest mismatch or byte limit violation")
    if b"\x00" in body:
        raise ValueError("manual source file must be textual; image/video require atomic acquisition")
    return body, str(candidate.get("url") or "")


def _read_receipt_asset(
    receipt_path: Path,
    *,
    asset_id: str,
    acquisition_root: Path | None,
) -> tuple[bytes, dict[str, Any], str, str, dict[str, bytes]]:
    path = receipt_path.expanduser().resolve()
    receipt = read_json(path)
    if not isinstance(receipt, dict):
        raise TypeError("acquisition receipt must be an object")
    schema = str(receipt.get("schema") or "")
    kind = next((name for name, value in _ALLOWED_RECEIPT_SCHEMAS.items() if value == schema), "")
    if not kind:
        raise ValueError("unsupported acquisition receipt schema")
    root = acquisition_root.expanduser().resolve() if acquisition_root else None
    if root is None:
        raise ValueError("acquisition receipt consumption requires --acquisition-root")
    if root not in path.parents:
        raise ValueError("acquisition receipt is outside --acquisition-root")
    receipt_ref = path.relative_to(root).as_posix()
    if not receipt_ref.startswith("receipts/"):
        raise ValueError("acquisition receipt must use the canonical receipts/ layout")
    try:
        if kind == "image":
            from content.source.professional_image_acquisition import (
                load_professional_image_acquisition_receipt,
            )
            verified = load_professional_image_acquisition_receipt(receipt_ref, root=root)
        else:
            from content.source.professional_video_receipt import (
                load_professional_video_acquisition_receipt,
            )
            verified = load_professional_video_acquisition_receipt(receipt_ref, root=root)
    except ModuleNotFoundError as exc:
        raise ValueError(f"acquisition receipt dependency is unavailable: {exc.name}") from exc
    matches = [row for row in verified["assets"] if str(row.get("assetId") or "") == asset_id]
    if len(matches) != 1:
        raise ValueError("acquisition receipt asset binding is missing or ambiguous")
    row = dict(matches[0])
    if row.get("acquisitionStatus") != "acquired" or row.get("distributionDecision") not in _ACCEPTED_DECISIONS:
        raise ValueError("acquisition receipt asset is not admitted")
    relative = Path(str(row.get("assetRef") or ""))
    asset = (root / relative).resolve()
    if relative.is_absolute() or ".." in relative.parts or root not in asset.parents or asset.is_symlink() or not asset.is_file():
        raise ValueError("acquisition receipt CAS ref is unsafe or missing")
    body = asset.read_bytes()
    if _sha256(body) != str(row.get("contentSha256") or ""):
        raise ValueError("acquisition receipt CAS digest mismatch")
    related_bodies: dict[str, bytes] = {}
    if kind == "video":
        poster_relative = Path(str(row.get("posterAssetRef") or ""))
        poster = (root / poster_relative).resolve()
        if (
            poster_relative.is_absolute()
            or ".." in poster_relative.parts
            or root not in poster.parents
            or poster.is_symlink()
            or not poster.is_file()
        ):
            raise ValueError("acquisition receipt poster CAS ref is unsafe or missing")
        poster_body = poster.read_bytes()
        if _sha256(poster_body) != str(row.get("posterContentSha256") or ""):
            raise ValueError("acquisition receipt poster CAS digest mismatch")
        if len(poster_body) != int(row.get("posterBytes") or 0):
            raise ValueError("acquisition receipt poster CAS byte count mismatch")
        related_bodies["poster"] = poster_body
    return body, row, kind, receipt_ref, related_bodies


def _candidate_bytes(
    candidate: Mapping[str, Any],
    *,
    manual_root: Path | None,
    receipt_path: Path | None,
    receipt_asset_id: str,
    acquisition_root: Path | None,
) -> tuple[bytes, str, dict[str, Any] | None, str, dict[str, bytes]]:
    if receipt_path is not None and candidate.get("manualFile"):
        raise ValueError("acquisition receipt candidate cannot also declare manualFile")
    supplied = sum(bool(value) for value in (candidate.get("url"), candidate.get("manualFile")))
    if receipt_path is None and supplied != 1:
        raise ValueError("candidate must select exactly one of url or manualFile")
    if receipt_path is not None:
        body, row, kind, receipt_ref, related_bodies = _read_receipt_asset(
            receipt_path,
            asset_id=receipt_asset_id,
            acquisition_root=acquisition_root,
        )
        row["_receiptRef"] = receipt_ref
        return body, str(row.get("sourceUrl") or ""), row, kind, related_bodies
    if candidate.get("manualFile"):
        body, url = _read_manual_file(candidate, manual_root=manual_root)
        return body, url, None, "", {}
    body, final_url = _read_https(str(candidate["url"]))
    if b"\x00" in body:
        raise ValueError("network source snapshot must be textual; image/video require atomic acquisition")
    return body, final_url, None, "", {}


def _source_unit_id(
    execution_id: str,
    target_ref: str,
    candidate: Mapping[str, Any],
    raw_sha: str,
    *,
    acquisition_identity: str = "",
) -> str:
    seed = "\n".join((
        execution_id, target_ref, str(candidate["sourceId"]),
        str(candidate.get("url") or ""), raw_sha, acquisition_identity,
    ))
    return f"{_safe_source_id(candidate['sourceId'])}__{hashlib.sha256(seed.encode()).hexdigest()[:16]}"


def _budget_media_body(
    body: bytes,
    *,
    acquisition_kind: str,
    research_lane: str,
) -> tuple[bytes, dict[str, Any] | None]:
    """Apply only policy-declared deterministic image renditions at download."""
    if not acquisition_kind:
        return body, None
    try:
        budget = source_unit_asset_budget_bytes(research_lane)
    except ValueError as exc:
        raise ValueError(f"DATA.MEDIA.ASSET_OVER_BUDGET: {exc}") from exc
    if len(body) <= budget:
        return body, None
    if acquisition_kind != "image":
        raise ValueError(
            "DATA.MEDIA.ASSET_OVER_BUDGET: "
            f"carrier={research_lane} bytes={len(body)} budget={budget}"
        )
    variant = derive_budget_compliant_variant(body, budget_bytes=budget)
    if variant is None or len(variant["bytes"]) > budget:
        raise ValueError(
            "DATA.MEDIA.ASSET_OVER_BUDGET: "
            f"carrier={research_lane} bytes={len(body)} budget={budget}"
        )
    return bytes(variant["bytes"]), {
        "operation": "policy_declared_image_rendition",
        "sourceSha256": _sha256(body),
        "sourceBytes": len(body),
        "resultSha256": _sha256(bytes(variant["bytes"])),
        "resultBytes": len(variant["bytes"]),
        "width": int(variant["width"]),
        "height": int(variant["height"]),
        "mimeType": str(variant["mimeType"]),
        "budgetBytes": budget,
    }


def _render_source_markdown(candidate: Mapping[str, Any], body: bytes, *, acquisition_kind: str) -> str:
    if acquisition_kind:
        return f"# {candidate['title']}\n\nBinary media is bound through the acquisition receipt; semantic description is AI-owned.\n"
    return body.decode("utf-8", errors="replace")


def _receipt_media_identity_fields(
    receipt_row: Mapping[str, Any],
    *,
    acquisition_kind: str,
) -> dict[str, Any]:
    if acquisition_kind == "image":
        source_attribution = receipt_row["sourceAttribution"]
        return {
            "creator": receipt_row["creator"],
            "platform": receipt_row["platform"],
            "collectionPageUrl": source_attribution["sourcePostUrl"],
            "originalAssetUrl": source_attribution["originalAssetUrl"],
            "capturedAt": receipt_row["capturedAt"],
            "licenseSnapshot": receipt_row["licenseSnapshot"],
            "usageScope": receipt_row["usageScope"],
            "modelReleaseStatus": receipt_row["modelReleaseStatus"],
            "propertyReleaseStatus": source_attribution["propertyReleaseStatus"],
            "sourceAttribution": dict(source_attribution),
        }
    plan_spec = receipt_row["planVideoSpec"]
    return {
        "creator": receipt_row["creator"],
        "platform": receipt_row["platform"],
        "collectionPageUrl": plan_spec["sourcePostUrl"],
        "originalAssetUrl": plan_spec["originalAssetUrl"],
        "capturedAt": receipt_row["capturedAt"],
        "modelReleaseStatus": receipt_row["modelReleaseStatus"],
        "propertyReleaseStatus": receipt_row["propertyReleaseStatus"],
    }


def _build_meta(
    *,
    execution_id: str,
    target_ref: str,
    candidate: Mapping[str, Any],
    source_unit_id: str,
    raw_sha: str,
    source_sha: str,
    canonical_url: str,
    receipt_row: Mapping[str, Any] | None,
    receipt_ref: str,
    asset_ref: str,
) -> dict[str, Any]:
    identity = parse_execution_id(execution_id)
    candidate = {**candidate, "chosenCandidateDigest": _sha256(_stable_bytes(candidate))}
    fetched_at = str(candidate.get("fetchedAt") or "").strip() or datetime.now(timezone.utc).isoformat()
    meta: dict[str, Any] = {
        "schema": "quwoquan_data.atomic_source_unit",
        "stage": "1.download",
        **stage_execution_context(execution_id),
        "sourceUnitId": source_unit_id,
        "sourcePlanRef": str(candidate["sourcePlanRef"]),
        "sourcePlanDigest": str(candidate["sourcePlanDigest"]),
        "chosenCandidateDigest": str(candidate["chosenCandidateDigest"]),
        "sourceId": str(candidate["sourceId"]),
        "targetRef": target_ref,
        "carrier": identity.content_type.value,
        "title": str(candidate["title"]),
        "sourceClass": str(candidate["sourceClass"]),
        "sourceUseMode": str(candidate["sourceUseMode"]),
        "purpose": str(candidate["purpose"]),
        "rightsClue": str(candidate["rightsClue"]),
        "canonicalUrl": canonical_url,
        "fetchedAt": fetched_at,
        "rawSha256": raw_sha,
        "sourceMarkdownSha256": source_sha,
    }
    if receipt_row is not None:
        meta["acquisition"] = {
            "receiptRef": receipt_ref,
            "assetId": str(receipt_row["assetId"]),
            "assetRef": asset_ref,
            "contentSha256": str(receipt_row["contentSha256"]),
            "bytes": int(receipt_row.get("bytes") or 0),
            "mimeType": str(receipt_row.get("mimeType") or ""),
        }
        if receipt_row.get("derivativeBinding"):
            meta["acquisition"]["derivativeBinding"] = dict(receipt_row["derivativeBinding"])
        if receipt_row.get("posterAssetRef"):
            safe_asset_id = _safe_source_id(str(receipt_row["assetId"]))
            meta["acquisition"].update({
                "posterAssetRef": f"assets/002_{safe_asset_id}_poster.png",
                "posterContentSha256": str(receipt_row["posterContentSha256"]),
            })
    return meta


def materialize_source_candidate(
    candidate_path: Path,
    *,
    execution_id: str,
    target_ref: str,
    manual_root: Path | None = None,
    receipt_path: Path | None = None,
    receipt_asset_id: str = "",
    acquisition_root: Path | None = None,
) -> tuple[dict[str, Any], Path]:
    """Materialize exactly one explicit candidate and append one object ref."""
    candidate = read_json(candidate_path.expanduser().resolve())
    if not isinstance(candidate, dict):
        raise TypeError("source candidate must be an object")
    assert_valid(candidate, "source", "source_candidate", label=str(candidate_path))
    root = execution_root(execution_id)
    source_plan_ref = str(candidate["sourcePlanRef"])
    source_plan_path = root / source_plan_ref
    if source_plan_path.is_symlink() or not source_plan_path.is_file():
        raise ValueError("sourcePlanRef must resolve to a regular execution file")
    source_plan_raw = source_plan_path.read_bytes()
    source_plan_digest = _sha256(source_plan_raw)
    if source_plan_digest != candidate["sourcePlanDigest"]:
        raise ValueError("source candidate sourcePlanDigest drift")
    source_plan = read_json(source_plan_path)
    assert_valid(source_plan, "source", "source_plan", label=source_plan_ref)
    if source_plan.get("executionId") != execution_id or source_plan.get("targetRef") != target_ref:
        raise ValueError("source candidate source plan identity drift")
    candidate_identity = {
        key: value
        for key, value in candidate.items()
        if key not in {"schema", "sourcePlanRef", "sourcePlanDigest", "fetchedAt"}
    }
    matching = [
        item for item in source_plan.get("candidates", [])
        if isinstance(item, dict) and item == candidate_identity
    ]
    if len(matching) != 1:
        raise ValueError("chosen source candidate is not exactly one source plan candidate")
    chosen_candidate_digest = _sha256(_stable_bytes(candidate))
    if receipt_path is not None and not receipt_asset_id:
        raise ValueError("--receipt-asset-id is required with --acquisition-receipt")
    if receipt_path is None and receipt_asset_id:
        raise ValueError("--receipt-asset-id requires --acquisition-receipt")
    body, canonical_url, receipt_row, acquisition_kind, related_bodies = _candidate_bytes(
        candidate,
        manual_root=manual_root,
        receipt_path=receipt_path,
        receipt_asset_id=receipt_asset_id,
        acquisition_root=acquisition_root,
    )
    if canonical_url and not canonical_url.startswith("https://"):
        raise ValueError("source canonical URL must use HTTPS")
    research_lane = parse_execution_id(execution_id).content_type.value
    body, budget_derivation = _budget_media_body(
        body,
        acquisition_kind=acquisition_kind,
        research_lane=research_lane,
    )
    source_md = _render_source_markdown(candidate, body, acquisition_kind=acquisition_kind)
    raw_sha = _sha256(body)
    source_sha = _sha256(source_md.encode("utf-8"))
    acquisition_identity = (
        f"{receipt_row.get('_receiptRef')}#{receipt_row.get('assetId')}"
        if receipt_row is not None
        else ""
    )
    unit_id = _source_unit_id(
        execution_id, target_ref, candidate, raw_sha,
        acquisition_identity=acquisition_identity,
    )
    object_dir = _target_object_dir(execution_id, target_ref)
    unit = execution_source_unit_dir(execution_id, unit_id)
    output_root = execution_root(execution_id).parents[2]
    library_root = library_root_for_output(output_root)
    refs_path = object_dir / "1.download/source_refs.json"
    unit_lock = _lock(unit.parent / f".{unit_id}.lock")
    refs_lock = _lock(refs_path.with_suffix(".lock"))
    temporary: Path | None = None
    try:
        if not unit.exists():
            unit.parent.mkdir(parents=True, exist_ok=True)
            temporary = Path(tempfile.mkdtemp(prefix=f".{unit_id}.", dir=unit.parent))
            asset_ref = ""
            materialized_assets: list[dict[str, Any]] = []
            if acquisition_kind:
                assert receipt_row is not None
                safe_asset_id = _safe_source_id(str(receipt_row["assetId"]))
                materialized_mime = (
                    str(budget_derivation["mimeType"])
                    if budget_derivation is not None
                    else str(receipt_row.get("mimeType") or "")
                )
                suffix = mimetypes.guess_extension(materialized_mime, strict=False) or Path(
                    str(receipt_row.get("assetRef") or "")
                ).suffix
                if not suffix:
                    suffix = ".bin"
                asset_path = temporary / "assets" / f"001_{safe_asset_id}{suffix}"
                asset_path.parent.mkdir(parents=True, exist_ok=True)
                link_bytes_from_library(body, asset_path, kind="media", library_root=library_root)
                asset_ref = f"assets/{asset_path.name}"
                rights_fields = {
                    key: receipt_row[key]
                    for key in (
                        "sourceUrl",
                        "license",
                        "termsUrl",
                        "authorizationProof",
                        "rightsStatus",
                        "authorizationRequired",
                        "distributionDecision",
                        "rightsIssues",
                    )
                }
                media_identity_fields = _receipt_media_identity_fields(
                    receipt_row,
                    acquisition_kind=acquisition_kind,
                )
                if budget_derivation is not None:
                    if (
                        budget_derivation.get("sourceSha256") != receipt_row.get("contentSha256")
                        or budget_derivation.get("sourceBytes") != receipt_row.get("bytes")
                    ):
                        raise ValueError("derived image does not bind acquisition receipt identity")
                materialized_assets.append({
                    "sourceAssetId": f"{safe_asset_id}:video" if acquisition_kind == "video" else safe_asset_id,
                    "fileName": asset_path.name,
                    "assetRole": "video" if acquisition_kind == "video" else "image",
                    "mimeType": materialized_mime,
                    "bytes": len(body),
                    "sha256": _sha256(body),
                    "contentSha256": _sha256(body),
                    "acquisitionReceiptRef": str(receipt_row.get("_receiptRef") or ""),
                    "professionalAssetId": str(receipt_row["assetId"]),
                    **({"derivativeBinding": {
                        "originalSha256": str(receipt_row["contentSha256"]),
                        "originalBytes": int(receipt_row["bytes"]),
                        "originalMimeType": str(receipt_row["mimeType"]),
                        "policy": "source_unit_asset_budget",
                        "profile": research_lane,
                        "derivedSha256": _sha256(body),
                        "derivedBytes": len(body),
                        "derivedMimeType": materialized_mime,
                        "derivedExtension": suffix,
                    }} if budget_derivation is not None else {}),
                    **media_identity_fields,
                    **rights_fields,
                })
                if acquisition_kind == "video":
                    poster_body = related_bodies["poster"]
                    poster_path = temporary / "assets" / f"002_{safe_asset_id}_poster.png"
                    link_bytes_from_library(
                        poster_body,
                        poster_path,
                        kind="media",
                        library_root=library_root,
                    )
                    poster_rights = receipt_row["posterRights"]
                    materialized_assets.append({
                        "sourceAssetId": f"{safe_asset_id}:poster",
                        "fileName": poster_path.name,
                        "assetRole": "poster",
                        "mimeType": str(receipt_row["posterMimeType"]),
                        "bytes": len(poster_body),
                        "sha256": str(receipt_row["posterContentSha256"]),
                        "contentSha256": str(receipt_row["posterContentSha256"]),
                        "acquisitionReceiptRef": str(receipt_row.get("_receiptRef") or ""),
                        "professionalAssetId": str(receipt_row["assetId"]),
                        "derivedFromSourceAssetId": f"{safe_asset_id}:video",
                        "derivation": poster_rights["derivation"],
                        "posterRights": dict(poster_rights),
                        **media_identity_fields,
                        **{
                            key: poster_rights[key]
                            for key in (
                                "sourceUrl", "license", "termsUrl",
                                "authorizationProof", "rightsStatus",
                                "authorizationRequired", "distributionDecision",
                                "rightsIssues",
                            )
                        },
                    })
            snapshot_name = "snapshot.bin" if acquisition_kind else "snapshot.raw"
            link_bytes_from_library(body, temporary / snapshot_name, kind="source", library_root=library_root)
            (temporary / "source.md").write_text(source_md, encoding="utf-8")
            (temporary / "assets").mkdir(exist_ok=True)
            (temporary / "assets/index.json").write_bytes(
                _stable_bytes({"assets": materialized_assets})
            )
            receipt_ref = str(receipt_row.get("_receiptRef") or "") if receipt_row else ""
            meta_receipt_row = receipt_row
            if receipt_row is not None and budget_derivation is not None:
                meta_receipt_row = {**receipt_row, "derivativeBinding": materialized_assets[0]["derivativeBinding"]}
            meta = _build_meta(
                execution_id=execution_id,
                target_ref=target_ref,
                candidate=candidate,
                source_unit_id=unit_id,
                raw_sha=raw_sha,
                source_sha=source_sha,
                canonical_url=canonical_url,
                receipt_row=meta_receipt_row,
                receipt_ref=receipt_ref,
                asset_ref=asset_ref,
            )
            assert_valid(meta, "source", "atomic_source_unit_meta", label=unit_id)
            (temporary / "meta.json").write_bytes(_stable_bytes(meta))
            _fsync_tree(temporary)
            os.rename(temporary, unit)
            parent_descriptor = os.open(unit.parent, os.O_RDONLY)
            try:
                os.fsync(parent_descriptor)
            finally:
                os.close(parent_descriptor)
            temporary = None
        else:
            meta = read_json(unit / "meta.json")
            if (
                not isinstance(meta, dict)
                or meta.get("rawSha256") != raw_sha
                or meta.get("targetRef") != target_ref
                or meta.get("sourceUseMode") != candidate.get("sourceUseMode")
                or (
                    receipt_row is not None
                    and meta.get("acquisition") != {
                        "receiptRef": str(receipt_row.get("_receiptRef") or ""),
                        "assetId": str(receipt_row["assetId"]),
                        "assetRef": str(meta.get("acquisition", {}).get("assetRef") or ""),
                        "contentSha256": str(receipt_row["contentSha256"]),
                        "bytes": int(receipt_row["bytes"]),
                        "mimeType": str(receipt_row["mimeType"]),
                        **(
                            {"derivativeBinding": meta["acquisition"]["derivativeBinding"]}
                            if meta.get("acquisition", {}).get("derivativeBinding")
                            else {}
                        ),
                        **(
                            {
                                "posterAssetRef": f"assets/002_{_safe_source_id(str(receipt_row['assetId']))}_poster.png",
                                "posterContentSha256": str(receipt_row["posterContentSha256"]),
                            }
                            if receipt_row.get("posterAssetRef")
                            else {}
                        ),
                    }
                )
            ):
                raise ValueError(f"source unit create-once collision: {unit}")
        execution_dir = execution_root(execution_id).resolve()
        source_ref = (unit / "source.md").resolve().relative_to(execution_dir).as_posix()
        meta_ref = (unit / "meta.json").resolve().relative_to(execution_dir).as_posix()
        row = {
            "sourceUnitId": unit_id,
            "sourceRef": source_ref,
            "metaRef": meta_ref,
            "sourcePlanRef": str(meta["sourcePlanRef"]),
            "sourcePlanDigest": str(meta["sourcePlanDigest"]),
            "chosenCandidateDigest": str(meta["chosenCandidateDigest"]),
            "sourceId": str(candidate["sourceId"]),
            "sourceClass": str(candidate["sourceClass"]),
            "targetRefs": [target_ref],
        }
        existing = read_json(refs_path) if refs_path.is_file() else {
            "schema": "quwoquan_data.object_source_refs",
            "executionId": execution_id,
            "objectRef": object_dir.resolve().relative_to(execution_dir).as_posix(),
            "sources": [],
        }
        if not isinstance(existing, dict) or existing.get("executionId") != execution_id:
            raise ValueError("source_refs identity drift")
        rows = [value for value in existing.get("sources", []) if isinstance(value, dict)]
        conflicts = [value for value in rows if value.get("sourceUnitId") == unit_id and value != row]
        if conflicts:
            raise ValueError("source_refs create-once collision")
        if row not in rows:
            rows.append(row)
        payload = {**existing, "sources": sorted(rows, key=lambda value: str(value.get("sourceUnitId") or ""))}
        assert_valid(payload, "source", "object_source_refs", label=str(refs_path))
        body_out = _stable_bytes(payload)
        if not refs_path.is_file() or refs_path.read_bytes() != body_out:
            _write_locked_bytes(refs_path, body_out)
        return {**meta, "sourceRef": source_ref, "metaRef": meta_ref}, unit
    finally:
        if temporary is not None:
            shutil.rmtree(temporary, ignore_errors=True)
        unit_lock.close()
        refs_lock.close()


__all__ = ["materialize_source_candidate"]
