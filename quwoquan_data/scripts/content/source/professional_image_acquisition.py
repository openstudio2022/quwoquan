"""Governed Pinterest/Tuchong image acquisition into a local content CAS.

The connector accepts only three explicit paths: anonymous public HTTPS,
platform-supported API output expressed as an HTTPS asset URL, or a file under
an operator-provided manual root.  It never accepts cookies, credentials,
browser state, custom headers, DRM or access-control bypass instructions.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from core.io import read_json
from core.paths import SOURCE_ACQUISITION_ROOT
from core.schema import assert_valid

from content.execution.controller.execute.pre_acquisition_handoff import (
    guard_acquisition_source_identity,
    load_pre_acquisition_handoff,
)
from content.source.image_payload import sniff_image_ext
from content.source.professional_image_admission import pre_acquisition_block
from content.source.professional_image_acquisition_item import (
    acquire_professional_image_item,
    validate_professional_image_item,
)
from content.source.professional_image_discovery_binding import (
    load_discovery_candidates,
    validate_discovery_binding,
)
from content.source.professional_image_receipt_counts import (
    provider_counts as _provider_counts,
)
from content.source.professional_image_receipt_validation import (
    validate_image_receipt_inventory,
)
from content.source.professional_image_transport import fetch_public_image
from content.source.professional_safety_evidence import (
    file_sha256,
    load_bound_safety_evidence,
    validate_image_safety_payload,
)

ACQUISITION_ROOT = SOURCE_ACQUISITION_ROOT
_MAX_IMAGE_BYTES = 64 * 1024 * 1024
_MIN_IMAGE_BYTES = 3_000


class ProfessionalImageAcquisitionError(ValueError):
    """A zero-success batch with its immutable typed-exclusion receipt."""

    def __init__(
        self,
        code: str,
        detail: str,
        *,
        receipt_ref: str,
    ) -> None:
        self.code = code
        self.detail = detail
        self.receipt_ref = receipt_ref
        super().__init__(f"{code}: {detail}; receiptRef={receipt_ref}")


def _digest(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _content_digest(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _manual_payload(relative_ref: str, *, manual_root: Path) -> dict[str, Any] | None:
    if not relative_ref or Path(relative_ref).is_absolute():
        raise ValueError("manualFile must be a non-empty relative path")
    root = manual_root.resolve()
    path = (root / relative_ref).resolve()
    if path != root and root not in path.parents:
        raise ValueError("manualFile escapes the declared manual root")
    if not path.is_file():
        return None
    body = path.read_bytes()
    if len(body) < _MIN_IMAGE_BYTES or len(body) > _MAX_IMAGE_BYTES:
        return None
    ext = sniff_image_ext(body, "")
    if ext is None:
        return None
    return {
        "bytes": body,
        "ext": ext,
        "contentType": "",
        "requestedUrl": "",
        "normalizedFromUrl": "",
    }


def _network_payload(
    url: str,
    *,
    supported_api: bool,
) -> dict[str, Any] | None:
    return fetch_public_image(
        url,
        supported_api=supported_api,
        min_bytes=_MIN_IMAGE_BYTES,
        max_bytes=_MAX_IMAGE_BYTES,
    )


def _frozen_supported_api_payload(
    item: Mapping[str, Any], *, output_root: Path,
) -> dict[str, Any]:
    """Read exact provider bytes already admitted by supported-API evidence."""
    relative = Path(str(item.get("apiEvidence") or ""))
    root = output_root.resolve()
    evidence_path = (root / relative).resolve()
    if (
        relative.is_absolute() or ".." in relative.parts
        or root not in evidence_path.parents
        or evidence_path.is_symlink() or not evidence_path.is_file()
    ):
        raise ValueError("supported_api evidence ref is unsafe or missing")
    evidence = read_json(evidence_path)
    if not isinstance(evidence, Mapping):
        raise TypeError("supported_api evidence must be an object")
    assert_valid(
        evidence, "source", "professional_image_supported_api_evidence",
        label="professional image supported API evidence",
    )
    asset_relative = Path(str(evidence.get("originalAssetRef") or ""))
    asset_roots = [root]
    relative_parts = relative.parts
    if "candidates" in relative_parts:
        candidates_index = relative_parts.index("candidates")
        if candidates_index:
            asset_roots.append(root.joinpath(*relative_parts[:candidates_index]))
    asset_path = next(
        (
            candidate
            for asset_root in asset_roots
            for candidate in ((asset_root / asset_relative).resolve(),)
            if (
                not asset_relative.is_absolute()
                and ".." not in asset_relative.parts
                and asset_root in candidate.parents
                and not candidate.is_symlink()
                and candidate.is_file()
            )
        ),
        root / "__missing_supported_api_asset__",
    )
    if (
        asset_relative.is_absolute() or ".." in asset_relative.parts
        or asset_path.is_symlink() or not asset_path.is_file()
    ):
        raise ValueError("supported_api original asset ref is unsafe or missing")
    descriptor = os.open(asset_path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        body = os.read(descriptor, _MAX_IMAGE_BYTES + 1)
    finally:
        os.close(descriptor)
    ext = sniff_image_ext(body, "")
    if (
        evidence.get("status") != "accepted"
        or evidence.get("candidateId") != item.get("assetId")
        or evidence.get("sourcePageUrl") != item.get("sourceUrl")
        or evidence.get("originalAssetUrl") != item.get("assetUrl")
        or evidence.get("contentSha256") != _content_digest(body)
        or len(body) < _MIN_IMAGE_BYTES or len(body) > _MAX_IMAGE_BYTES
        or ext is None
    ):
        raise ValueError("supported_api frozen physical input binding drift")
    return {
        "bytes": body, "ext": ext, "contentType": "",
        "requestedUrl": str(item["assetUrl"]),
        "normalizedFromUrl": str(item["assetUrl"]),
        "externalInputEvidenceSha256": file_sha256(evidence_path),
    }


def _put_cas(payload: bytes, ext: str, *, output_root: Path) -> Path:
    digest = hashlib.sha256(payload).hexdigest()
    destination = output_root / "cas" / "sha256" / digest[:2] / f"{digest}{ext}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file():
        if _content_digest(destination.read_bytes()) != f"sha256:{digest}":
            raise ValueError(f"image CAS collision: {destination}")
        return destination
    temporary = ""
    with tempfile.NamedTemporaryFile(
        "wb",
        dir=destination.parent,
        prefix=f".{digest}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temporary = handle.name
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, destination)
    return destination


def _portable_ref(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _write_create_once_receipt(path: Path, receipt: Mapping[str, Any]) -> None:
    body = json.dumps(receipt, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError:
        if read_json(path) != receipt:
            raise ValueError(
                f"professional image acquisition receipt collision: {path}"
            )
        return
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(body)
        handle.flush()
        os.fsync(handle.fileno())


def _portable_archived_ref(
    raw_ref: object,
    *,
    source: Mapping[str, Any],
    source_manifest_path: Path,
    target_root: Path,
    label: str,
) -> str:
    """Resolve one mixed historical ref into the target acquisition root."""
    relative = Path(str(raw_ref or "").strip())
    if not str(relative) or relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"professional image {label} is unsafe")
    source_root = source_manifest_path.expanduser().resolve().parent.parent
    manifest_id = str(source.get("manifestId") or "").strip()
    manifest_part = Path(manifest_id)
    if (
        not manifest_id
        or manifest_part.is_absolute()
        or len(manifest_part.parts) != 1
        or manifest_part.name in {".", ".."}
    ):
        raise ValueError("professional image manifestId is unsafe for archive ref")
    resolved_target = target_root.expanduser().resolve()
    candidates = (
        source_root / relative,
        source_root.parent / relative,
        resolved_target / relative,
        source_root / manifest_part / relative,
    )
    resolved = next(
        (
            candidate.resolve()
            for candidate in candidates
            if candidate.resolve() != resolved_target
            and resolved_target in candidate.resolve().parents
            and not candidate.is_symlink()
            and candidate.is_file()
        ),
        None,
    )
    if resolved is None:
        raise ValueError(f"professional image archived {label} is missing")
    return resolved.relative_to(resolved_target).as_posix()


def _portable_discovery_plan_ref(
    source: Mapping[str, Any],
    *,
    source_manifest_path: Path,
    target_root: Path,
) -> str:
    """Resolve one archived plan into the acquisition root's single ref form."""
    portable = _portable_archived_ref(
        source.get("discoveryPlanRef"),
        source=source,
        source_manifest_path=source_manifest_path,
        target_root=target_root,
        label="discoveryPlanRef",
    )
    load_discovery_candidates(
        {**dict(source), "discoveryPlanRef": portable},
        output_root=target_root,
    )
    return portable


def rebind_professional_image_acquisition_manifest(
    source_manifest_path: Path,
    *,
    handoff_ref: Path,
    destination: Path,
) -> tuple[dict[str, Any], Path]:
    """Rebind a verified frozen physical closure to one newer execution identity."""
    source = read_json(source_manifest_path)
    if not isinstance(source, dict):
        raise TypeError("source professional image acquisition manifest must be an object")
    assert_valid(
        source, "source", "professional_image_acquisition_manifest",
        label="source professional image acquisition manifest",
    )
    handoff = load_pre_acquisition_handoff(handoff_ref)
    frozen = source.get("frozenPhysicalInput")
    if not isinstance(frozen, Mapping):
        frozen = {
            "sourceRevision": source["sourceRevision"],
            "sourceDigest": source["sourceDigest"],
            "entityCatalogDigest": source["entityCatalogDigest"],
            "metadataCatalogDigest": source["discoveryPlanDigest"],
            "externalInputsDigest": _digest(source),
        }
    target_root = destination.expanduser().resolve().parent.parent
    discovery_plan_ref = _portable_discovery_plan_ref(
        source,
        source_manifest_path=source_manifest_path,
        target_root=target_root,
    )
    items: list[dict[str, Any]] = []
    for raw_item in source["items"]:
        item = dict(raw_item)
        if item.get("acquisitionPath") == "supported_api":
            item["apiEvidence"] = _portable_archived_ref(
                item.get("apiEvidence"),
                source=source,
                source_manifest_path=source_manifest_path,
                target_root=target_root,
                label=f"{item.get('assetId')}.apiEvidence",
            )
            safety = dict(item["safetyReview"])
            safety["evidenceRef"] = _portable_archived_ref(
                safety.get("evidenceRef"),
                source=source,
                source_manifest_path=source_manifest_path,
                target_root=target_root,
                label=f"{item.get('assetId')}.safetyReview.evidenceRef",
            )
            item["safetyReview"] = safety
        items.append(item)
    rebound = {
        **{
            key: value
            for key, value in source.items()
            if key not in {"reviewExecutionBindings", "reviewSourceBindings"}
        },
        "sourceRevision": handoff["sourceRevision"],
        "sourceDigest": handoff["sourceDigest"]["digest"],
        "entityCatalogDigest": handoff["entityCatalogDigest"],
        "executionBundle": handoff["executionBundle"],
        "frozenPhysicalInput": dict(frozen),
        "discoveryPlanRef": discovery_plan_ref,
        "items": items,
    }
    assert_valid(
        rebound, "source", "professional_image_acquisition_manifest",
        label="rebound professional image acquisition manifest",
    )
    body = json.dumps(rebound, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        if destination.is_symlink() or not destination.is_file() or destination.read_bytes() != body:
            raise ValueError(f"rebound acquisition manifest create-once collision: {destination}") from None
        return rebound, destination
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(body)
        handle.flush()
        os.fsync(handle.fileno())
    return rebound, destination


_validate_item = validate_professional_image_item


def acquire_professional_images(
    manifest_path: Path,
    *,
    handoff_ref: Path,
    repo_root: Path | None = None,
    manual_root: Path | None = None,
    output_root: Path = ACQUISITION_ROOT,
) -> tuple[dict[str, Any], Path]:
    """Acquire every manifest item and write a create-once auditable receipt."""
    manifest = read_json(manifest_path)
    if not isinstance(manifest, dict):
        raise TypeError("professional image acquisition manifest must be an object")
    assert_valid(
        manifest,
        "source",
        "professional_image_acquisition_manifest",
        label="professional image acquisition manifest",
    )
    guard_acquisition_source_identity(
        manifest,
        handoff_ref=handoff_ref,
        repo_root=repo_root,
    )
    asset_ids = [str(item["assetId"]) for item in manifest["items"]]
    if len(asset_ids) != len(set(asset_ids)):
        raise ValueError("professional image acquisition assetId values must be unique")
    discovery_candidates = load_discovery_candidates(
        manifest,
        output_root=output_root,
    )
    manifest_digest = _digest(manifest)
    rows: list[dict[str, Any]] = []
    seen_content: dict[str, str] = {}
    for raw in manifest["items"]:
        item = dict(raw)
        rows.append(
            acquire_professional_image_item(
                item,
                discovery_candidates=discovery_candidates,
                manual_root=manual_root,
                output_root=output_root,
                seen_content=seen_content,
                manual_loader=_manual_payload,
                network_loader=_network_payload,
                frozen_loader=_frozen_supported_api_payload,
                cas_writer=_put_cas,
                content_digest=_content_digest,
                portable_ref=_portable_ref,
                discovery_validator=validate_discovery_binding,
                safety_loader=load_bound_safety_evidence,
                safety_validator=validate_image_safety_payload,
            )
        )
    provider_counts = _provider_counts(rows)
    downloaded = sum(row["acquisitionStatus"] == "acquired" for row in rows)
    accepted = sum(
        row["distributionDecision"] in {"research_allowed", "commercial_allowed"}
        for row in rows
    )
    stable = {
        "schema": "quwoquan_data.professional_image_acquisition_receipt",
        "status": (
            "ready"
            if accepted == len(rows)
            else ("partial" if accepted else "blocked")
        ),
        "manifestId": str(manifest["manifestId"]),
        "manifestDigest": manifest_digest,
        "sourceRevision": str(manifest["sourceRevision"]),
        "sourceDigest": str(manifest["sourceDigest"]),
        "entityCatalogDigest": str(manifest["entityCatalogDigest"]),
        "discoveryPlanRef": str(manifest["discoveryPlanRef"]),
        "discoveryPlanDigest": str(manifest["discoveryPlanDigest"]),
        "plannedAssetCount": len(rows),
        "discoveredAssetCount": len(rows),
        "downloadedAssetCount": downloaded,
        "acceptedAssetCount": accepted,
        "rejectedAssetCount": len(rows) - accepted,
        "providerAssetCounts": provider_counts,
        "assets": rows,
    }
    receipt = {**stable, "receiptDigest": _digest(stable)}
    assert_valid(
        receipt,
        "source",
        "professional_image_acquisition_receipt",
        label="professional image acquisition receipt",
    )
    validate_image_receipt_inventory(
        receipt,
        resolved_root=output_root.resolve(),
        min_image_bytes=_MIN_IMAGE_BYTES,
        max_image_bytes=_MAX_IMAGE_BYTES,
        validate_item=_validate_item,
        pre_acquisition_block=pre_acquisition_block,
        provider_counts=_provider_counts,
    )
    receipt_path = (
        output_root / "receipts" / f"{manifest_digest.removeprefix('sha256:')}.json"
    )
    _write_create_once_receipt(receipt_path, receipt)
    if accepted == 0:
        failures = "; ".join(
            str(row["failure"])
            for row in rows
            if str(row.get("failure") or "")
        )
        raise ProfessionalImageAcquisitionError(
            "DATA.SOURCE.ACQUISITION_NO_SUCCESS",
            failures or "no image asset reached acquisition admission",
            receipt_ref=receipt_path.relative_to(output_root).as_posix(),
        )
    return receipt, receipt_path


def load_professional_image_acquisition_receipt(
    receipt_ref: str,
    *,
    root: Path | None = None,
    require_bodies: bool = True,
) -> dict[str, Any]:
    """Read a relative receipt and re-verify its digest plus every acquired CAS file.

    ``require_bodies=False`` admits a receipt whose bodies were all reclaimed
    after their object adopted them; the receipt itself is still verified in
    full. A partially reclaimed unit is refused either way.
    """
    relative = Path(str(receipt_ref or "").strip())
    if not str(relative) or relative.is_absolute():
        raise ValueError("professional image acquisition receiptRef must be relative")
    resolved_root = (root or ACQUISITION_ROOT).resolve()
    path = (resolved_root / relative).resolve()
    if path != resolved_root and resolved_root not in path.parents:
        raise ValueError(
            "professional image acquisition receiptRef escapes acquisition root"
        )
    receipt = read_json(path)
    if not isinstance(receipt, dict):
        raise TypeError("professional image acquisition receipt must be an object")
    assert_valid(
        receipt,
        "source",
        "professional_image_acquisition_receipt",
        label="professional image acquisition receipt",
    )
    stable = {key: value for key, value in receipt.items() if key != "receiptDigest"}
    if receipt.get("receiptDigest") != _digest(stable):
        raise ValueError("professional image acquisition receipt digest mismatch")
    expected_name = f"{str(receipt['manifestDigest']).removeprefix('sha256:')}.json"
    if path.name != expected_name or path.parent.name != "receipts":
        raise ValueError("professional image acquisition receipt path is not canonical")
    validate_image_receipt_inventory(
        receipt,
        resolved_root=resolved_root,
        min_image_bytes=_MIN_IMAGE_BYTES,
        max_image_bytes=_MAX_IMAGE_BYTES,
        validate_item=_validate_item,
        pre_acquisition_block=pre_acquisition_block,
        provider_counts=_provider_counts,
        require_bodies=require_bodies,
    )
    return receipt


def acquired_image_specs_for_entity(
    receipt_refs: list[str],
    *,
    entity_id: str,
    root: Path | None = None,
) -> list[dict[str, Any]]:
    """Project accepted receipt assets into the ordinary image-plan contract."""
    specs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for receipt_ref in receipt_refs:
        receipt = load_professional_image_acquisition_receipt(receipt_ref, root=root)
        for row in receipt["assets"]:
            if (
                not isinstance(row, Mapping)
                or str(row.get("entityId") or "") != entity_id
            ):
                continue
            if row.get("distributionDecision") not in {
                "research_allowed",
                "commercial_allowed",
            }:
                continue
            if row.get("acquisitionStatus") != "acquired":
                raise ValueError(
                    "professional image acquisition accepted asset was not acquired: "
                    f"{row.get('assetId')}"
                )
            plan_spec = row.get("planImageSpec")
            if not isinstance(plan_spec, Mapping):
                raise TypeError(
                    f"professional image acquisition accepted asset lacks planImageSpec: {row.get('assetId')}"
                )
            content_sha256 = str(row.get("contentSha256") or "")
            if content_sha256 in seen:
                raise ValueError(
                    f"professional image acquisition cross-receipt duplicate: {content_sha256}"
                )
            seen.add(content_sha256)
            specs.append(
                {
                    **dict(plan_spec),
                    "sourceCollectionId": (
                        f"acquisition:{receipt['manifestId']}:{row['assetId']}"
                    ),
                    "acquisitionReceiptRef": receipt_ref,
                    "professionalAssetId": str(row["assetId"]),
                    "professionalContentSha256": content_sha256,
                    "researchLane": "image",
                }
            )
    return specs


__all__ = [
    "ACQUISITION_ROOT",
    "ProfessionalImageAcquisitionError",
    "acquire_professional_images",
    "acquired_image_specs_for_entity",
    "load_professional_image_acquisition_receipt",
    "rebind_professional_image_acquisition_manifest",
]
