"""Content-addressed external inputs for immutable campaign capsules."""
from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from core.io import read_json
from core.schema import assert_valid
from core.source_digest import content_source_revision

from content.source.professional_image_acquisition import (
    load_professional_image_acquisition_receipt,
)
from content.source.professional_video_receipt import (
    load_professional_video_acquisition_receipt,
)

PROFESSIONAL_IMAGE_ACQUISITION_KIND = "professional_image_acquisition"
PROFESSIONAL_VIDEO_ACQUISITION_KIND = "professional_video_acquisition"
EXTERNAL_INPUT_KINDS = frozenset(
    {
        PROFESSIONAL_IMAGE_ACQUISITION_KIND,
        PROFESSIONAL_VIDEO_ACQUISITION_KIND,
    }
)
EXTERNAL_INPUT_REF_SCHEMA = "quwoquan_data.campaign_external_input_ref"
CAMPAIGN_CARRIERS = ("homepage", "article", "image", "video")
_KIND_MANIFEST_SCHEMAS = {
    PROFESSIONAL_IMAGE_ACQUISITION_KIND: (
        "professional_image_acquisition_manifest"
    ),
    PROFESSIONAL_VIDEO_ACQUISITION_KIND: (
        "professional_video_acquisition_manifest"
    ),
}
_KIND_CARRIERS = {
    PROFESSIONAL_IMAGE_ACQUISITION_KIND: frozenset(
        {"homepage", "image"}
    ),
    PROFESSIONAL_VIDEO_ACQUISITION_KIND: frozenset({"video"}),
}


class CampaignExternalInputError(ValueError):
    """A typed, fail-closed external input admission error."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"GATE_BLOCK {code}: {detail}")
        self.code = code


def payload_digest(value: object) -> str:
    encoded = json.dumps(
        value,
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


def external_inputs_digest(refs: Iterable[Mapping[str, Any]]) -> str:
    rows = [dict(row) for row in refs]
    return payload_digest(
        {
            "schema": "quwoquan_data.campaign_external_input_set",
            "refs": rows,
        }
    )


def _typed(code: str, detail: str) -> CampaignExternalInputError:
    return CampaignExternalInputError(f"DATA.CAMPAIGN.EXTERNAL_INPUT_{code}", detail)


def _safe_ref(root: Path, raw: object, *, label: str) -> tuple[str, Path]:
    text = str(raw or "").strip()
    candidate = Path(text)
    if not text or candidate.is_absolute() or ".." in candidate.parts:
        raise _typed("PATH_ESCAPE", f"{label} must be a contained relative path")
    resolved_root = root.resolve()
    resolved = (resolved_root / candidate).resolve()
    if resolved == resolved_root or resolved_root not in resolved.parents:
        raise _typed("PATH_ESCAPE", f"{label} escapes acquisition root: {text}")
    if not resolved.is_file():
        raise _typed("MISSING", f"{label} is missing: {text}")
    return candidate.as_posix(), resolved


def _safe_root_ref(root: Path, raw: object, *, kind: str) -> tuple[str, Path]:
    text = str(raw if raw is not None else ".").strip()
    candidate = Path(text)
    if (
        not text
        or candidate.is_absolute()
        or ".." in candidate.parts
        or candidate.as_posix() not in {".", "video"}
    ):
        raise _typed(
            "PATH_ESCAPE",
            "acquisitionRootRef must be one of the governed relative roots: ., video",
        )
    if kind == PROFESSIONAL_IMAGE_ACQUISITION_KIND and candidate.as_posix() != ".":
        raise _typed("INVALID", "professional image acquisitionRootRef must be .")
    if kind == PROFESSIONAL_VIDEO_ACQUISITION_KIND and candidate.as_posix() != "video":
        raise _typed("INVALID", "professional video acquisitionRootRef must be video")
    resolved_root = root.resolve()
    resolved = (resolved_root / candidate).resolve()
    if resolved != resolved_root and resolved_root not in resolved.parents:
        raise _typed("PATH_ESCAPE", "acquisitionRootRef escapes acquisition root")
    if not resolved.is_dir():
        raise _typed("MISSING", f"acquisitionRootRef is missing: {candidate.as_posix()}")
    return candidate.as_posix(), resolved


def _load_manifest(path: Path, *, kind: str) -> dict[str, Any]:
    payload = read_json(path)
    if not isinstance(payload, dict):
        raise _typed("INVALID", "acquisition manifest must be an object")
    try:
        assert_valid(
            payload,
            "source",
            _KIND_MANIFEST_SCHEMAS[kind],
            label="campaign external acquisition manifest",
        )
    except ValueError as exc:
        raise _typed("INVALID", str(exc)) from exc
    return payload


def _load_receipt(
    kind: str,
    receipt_ref: str,
    *,
    acquisition_root: Path,
) -> dict[str, Any]:
    loader = (
        load_professional_image_acquisition_receipt
        if kind == PROFESSIONAL_IMAGE_ACQUISITION_KIND
        else load_professional_video_acquisition_receipt
    )
    try:
        return loader(receipt_ref, root=acquisition_root)
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        raise _typed("INVALID", str(exc)) from exc


def _identity_check(
    document: Mapping[str, Any],
    *,
    source_revision: str,
    source_digest: str,
    entity_catalog_digest: str,
    label: str,
) -> None:
    expected = {
        "sourceRevision": source_revision,
        "sourceDigest": source_digest,
        "entityCatalogDigest": entity_catalog_digest,
    }
    drift = [key for key, value in expected.items() if document.get(key) != value]
    if drift:
        raise _typed("IDENTITY_DRIFT", f"{label} drift: {', '.join(drift)}")


def _blob_rows(
    receipt: Mapping[str, Any],
    *,
    acquisition_root: Path,
) -> list[dict[str, Any]]:
    blobs: dict[str, dict[str, Any]] = {}
    for row in receipt.get("assets") or []:
        if not isinstance(row, Mapping) or row.get("acquisitionStatus") != "acquired":
            continue
        blob_ref, blob_path = _safe_ref(
            acquisition_root,
            row.get("assetRef"),
            label="blobRef",
        )
        content_sha = str(row.get("contentSha256") or "").strip()
        observed = file_digest(blob_path)
        if not content_sha or observed != content_sha:
            raise _typed("DIGEST_DRIFT", f"blob digest drift: {blob_ref}")
        current = {
            "blobRef": blob_ref,
            "contentSha256": content_sha,
            "sizeBytes": blob_path.stat().st_size,
        }
        if blob_ref in blobs and blobs[blob_ref] != current:
            raise _typed("DIGEST_DRIFT", f"conflicting blob declaration: {blob_ref}")
        blobs[blob_ref] = current
    return [blobs[key] for key in sorted(blobs)]


def bind_external_input_refs(
    carrier: str,
    declarations: Iterable[Mapping[str, Any]],
    *,
    acquisition_root: Path,
    source_revision: str,
    source_digest: str,
    entity_catalog_digest: str,
) -> list[dict[str, Any]]:
    """Resolve raw manifest/receipt refs into immutable content descriptors."""
    if carrier not in CAMPAIGN_CARRIERS:
        raise _typed("INVALID", f"unsupported carrier: {carrier}")
    refs: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for declaration in declarations:
        if not isinstance(declaration, Mapping):
            raise _typed("INVALID", "external input declaration must be an object")
        kind = str(declaration.get("kind") or "").strip()
        if kind not in EXTERNAL_INPUT_KINDS:
            raise _typed("INVALID", f"unsupported external input kind: {kind}")
        if carrier not in _KIND_CARRIERS[kind]:
            raise _typed(
                "INVALID",
                f"external input kind {kind} is not admitted for {carrier}",
            )
        acquisition_root_ref, kind_root = _safe_root_ref(
            acquisition_root,
            declaration.get("acquisitionRootRef"),
            kind=kind,
        )
        manifest_ref, manifest_path = _safe_ref(
            kind_root,
            declaration.get("manifestRef"),
            label="manifestRef",
        )
        receipt_ref, receipt_path = _safe_ref(
            kind_root,
            declaration.get("receiptRef"),
            label="receiptRef",
        )
        identity = (kind, acquisition_root_ref, manifest_ref, receipt_ref)
        if identity in seen:
            raise _typed("DUPLICATE", f"duplicate external input: {receipt_ref}")
        seen.add(identity)
        manifest = _load_manifest(manifest_path, kind=kind)
        receipt = _load_receipt(kind, receipt_ref, acquisition_root=kind_root)
        _identity_check(
            manifest,
            source_revision=source_revision,
            source_digest=source_digest,
            entity_catalog_digest=entity_catalog_digest,
            label="manifest",
        )
        _identity_check(
            receipt,
            source_revision=source_revision,
            source_digest=source_digest,
            entity_catalog_digest=entity_catalog_digest,
            label="receipt",
        )
        manifest_digest = payload_digest(manifest)
        if receipt.get("manifestDigest") != manifest_digest:
            raise _typed("DIGEST_DRIFT", "receipt manifestDigest drift")
        if receipt.get("manifestId") != manifest.get("manifestId"):
            raise _typed("IDENTITY_DRIFT", "manifest/receipt manifestId drift")
        stable = {
            "schema": EXTERNAL_INPUT_REF_SCHEMA,
            "kind": kind,
            "carrier": carrier,
            "acquisitionRootRef": acquisition_root_ref,
            "manifestId": str(receipt.get("manifestId") or ""),
            "manifestRef": manifest_ref,
            "manifestDigest": manifest_digest,
            "manifestFileDigest": file_digest(manifest_path),
            "receiptRef": receipt_ref,
            "receiptDigest": str(receipt.get("receiptDigest") or ""),
            "receiptFileDigest": file_digest(receipt_path),
            "sourceRevision": source_revision,
            "sourceDigest": source_digest,
            "entityCatalogDigest": entity_catalog_digest,
            "blobRefs": _blob_rows(receipt, acquisition_root=kind_root),
        }
        ref = {**stable, "refDigest": payload_digest(stable)}
        try:
            assert_valid(
                ref,
                "execution",
                "campaign_external_input_ref",
                label=f"campaign external input:{kind}",
            )
        except ValueError as exc:
            raise _typed("INVALID", str(exc)) from exc
        refs.append(ref)
    return sorted(refs, key=lambda row: (row["kind"], row["receiptRef"]))


def verify_external_input_refs(
    carrier: str,
    refs: Iterable[Mapping[str, Any]],
    *,
    acquisition_root: Path,
    source_revision: str,
    source_digest: str,
    entity_catalog_digest: str,
) -> list[dict[str, Any]]:
    """Re-resolve every descriptor and reject any runtime replacement."""
    expected = [dict(row) for row in refs]
    declarations = [
        {
            "kind": row.get("kind"),
            "acquisitionRootRef": row.get("acquisitionRootRef"),
            "manifestRef": row.get("manifestRef"),
            "receiptRef": row.get("receiptRef"),
        }
        for row in expected
    ]
    observed = bind_external_input_refs(
        carrier,
        declarations,
        acquisition_root=acquisition_root,
        source_revision=source_revision,
        source_digest=source_digest,
        entity_catalog_digest=entity_catalog_digest,
    )
    if observed != expected:
        raise _typed("DIGEST_DRIFT", "frozen external input descriptor drift")
    return observed


def _copy_verified(source: Path, destination: Path, *, expected_digest: str) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if not destination.is_file() or file_digest(destination) != expected_digest:
            raise _typed("BUNDLE_COLLISION", f"bundle collision: {destination}")
        return
    shutil.copyfile(source, destination)
    if file_digest(destination) != expected_digest:
        raise _typed("DIGEST_DRIFT", f"bundle copy drift: {destination}")


def materialize_external_input_bundle(
    destination: Path,
    refs: Iterable[Mapping[str, Any]],
    *,
    acquisition_root: Path,
    carrier: str,
    source_revision: str,
    source_digest: str,
    entity_catalog_digest: str,
) -> list[dict[str, Any]]:
    """Copy one lane's declared inputs into a self-contained capsule subtree."""
    frozen = verify_external_input_refs(
        carrier,
        refs,
        acquisition_root=acquisition_root,
        source_revision=source_revision,
        source_digest=source_digest,
        entity_catalog_digest=entity_catalog_digest,
    )
    destination.mkdir(parents=True, exist_ok=True)
    for row in frozen:
        acquisition_root_ref, source_kind_root = _safe_root_ref(
            acquisition_root,
            row["acquisitionRootRef"],
            kind=str(row["kind"]),
        )
        destination_kind_root = destination / acquisition_root_ref
        manifest_ref, manifest = _safe_ref(
            source_kind_root, row["manifestRef"], label="manifestRef"
        )
        receipt_ref, receipt = _safe_ref(
            source_kind_root, row["receiptRef"], label="receiptRef"
        )
        _copy_verified(
            manifest,
            destination_kind_root / manifest_ref,
            expected_digest=str(row["manifestFileDigest"]),
        )
        _copy_verified(
            receipt,
            destination_kind_root / receipt_ref,
            expected_digest=str(row["receiptFileDigest"]),
        )
        for blob in row["blobRefs"]:
            blob_ref, blob_path = _safe_ref(
                source_kind_root, blob["blobRef"], label="blobRef"
            )
            _copy_verified(
                blob_path,
                destination_kind_root / blob_ref,
                expected_digest=str(blob["contentSha256"]),
            )
    verify_external_input_refs(
        carrier,
        frozen,
        acquisition_root=destination,
        source_revision=source_revision,
        source_digest=source_digest,
        entity_catalog_digest=entity_catalog_digest,
    )
    return frozen


__all__ = [
    "EXTERNAL_INPUT_KINDS",
    "PROFESSIONAL_IMAGE_ACQUISITION_KIND",
    "PROFESSIONAL_VIDEO_ACQUISITION_KIND",
    "CampaignExternalInputError",
    "bind_external_input_refs",
    "content_source_revision",
    "external_inputs_digest",
    "file_digest",
    "materialize_external_input_bundle",
    "payload_digest",
    "verify_external_input_refs",
]
