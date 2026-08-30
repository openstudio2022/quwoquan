"""Stable storage, identity, and projection support for API image inputs."""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from core.paths import SOURCE_ACQUISITION_ROOT
from core.schema import assert_valid
from content.source.professional_image_supported_api_contract import (
    load_document,
    source_attribution,
)
from content.source.professional_safety_evidence import file_sha256

PREPARATION_ROOT = (
    SOURCE_ACQUISITION_ROOT / "professional-image-supported-api-preparations"
)
SOURCE_POOL_SHORTFALL = "DATA.SOURCE.POOL_SHORTFALL"
PREPARATION_INVALID = "DATA.SOURCE.SUPPORTED_API_INPUT_INVALID"
_MIN_IMAGE_BYTES = 3_000
_MAX_IMAGE_BYTES = 64 * 1024 * 1024
_LICENSE_DENY = ("noncommercial", "non-commercial", "no derivatives", "fair use")


class ProfessionalImageSupportedApiInputError(RuntimeError):
    def __init__(self, code: str, detail: str, *, receipt_ref: str = "") -> None:
        self.code = code
        self.receipt_ref = receipt_ref
        super().__init__(f"{code}: {detail}")


def _digest(value: object) -> str:
    body = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(body).hexdigest()


def _bytes_digest(body: bytes) -> str:
    return "sha256:" + hashlib.sha256(body).hexdigest()


def _external_inputs_digest(
    *, plan: Mapping[str, Any], catalog: Mapping[str, Any], root: Path,
) -> str:
    """Bind immutable provider metadata, transport, pixels and review prompts."""
    rows: list[dict[str, str]] = []
    for candidate in catalog["candidates"]:
        token = _safe_token(candidate["candidateId"])
        candidate_root = root / "candidates" / token
        refs = [
            candidate_root / "api-response.json",
            candidate_root / "api-https-transport.json",
            candidate_root / "original-https-transport.json",
            candidate_root / "machine-assessment.json",
            candidate_root / "review-request.json",
        ]
        asset_root = candidate_root / "original"
        assets = sorted(asset_root.glob("asset.*")) if asset_root.is_dir() else []
        refs.extend(assets)
        for path in refs:
            if not path.exists():
                continue
            if path.is_symlink() or not path.is_file():
                raise ProfessionalImageSupportedApiInputError(
                    PREPARATION_INVALID, f"frozen physical input is unsafe: {path}"
                )
            rows.append({"ref": _safe_ref(path, root), "sha256": file_sha256(path)})
    return _digest({
        "discoveryPlanDigest": plan["planDigest"],
        "metadataCatalogDigest": catalog["catalogDigest"],
        "inputs": sorted(rows, key=lambda row: row["ref"]),
    })


def _safe_token(value: object) -> str:
    token = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(value or "")).strip("-.")
    if not token:
        raise ProfessionalImageSupportedApiInputError(
            PREPARATION_INVALID, "candidate identity is empty"
        )
    return token


def _write_once(path: Path, body: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        if path.is_symlink() or not path.is_file() or path.read_bytes() != body:
            raise ProfessionalImageSupportedApiInputError(
                PREPARATION_INVALID, f"create-once collision: {path}"
            ) from None
        return path
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(body)
        handle.flush()
        os.fsync(handle.fileno())
    return path


def _write_json(path: Path, payload: Mapping[str, Any]) -> Path:
    return _write_once(
        path,
        json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8") + b"\n",
    )


def _safe_ref(path: Path, root: Path) -> str:
    resolved = path.resolve()
    if resolved == root.resolve() or root.resolve() not in resolved.parents:
        raise ProfessionalImageSupportedApiInputError(
            PREPARATION_INVALID, f"evidence path escapes preparation root: {path}"
        )
    return resolved.relative_to(root.resolve()).as_posix()


def _prior_physical_identities(
    *, output_root: Path, current_root: Path,
) -> list[tuple[str, str, str, str]]:
    """Load validated physical identities from older create-once preparations."""
    identities: list[tuple[str, str, str, str]] = []
    resolved_current = current_root.resolve()
    roots = {SOURCE_ACQUISITION_ROOT.resolve(), output_root.resolve()}
    paths = {
        path
        for root in roots
        if root.is_dir() and not root.is_symlink()
        for path in root.rglob(
            "professional-image-supported-api-*/candidates/*/evidence/*.json"
        )
    }
    for path in sorted(paths):
        resolved = path.resolve()
        if resolved_current in resolved.parents or path.is_symlink():
            continue
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
            assert_valid(
                document,
                "source",
                "professional_image_supported_api_evidence",
                label=f"prior supported API evidence:{path}",
            )
        except (FileNotFoundError, OSError, TypeError, ValueError, json.JSONDecodeError):
            continue
        content_sha = str(document.get("contentSha256") or "")
        phash = str(document.get("perceptualHash") or "")
        candidate_id = str(document.get("candidateId") or "")
        provider_asset_id = str(document.get("providerAssetId") or "")
        if content_sha and phash and candidate_id and provider_asset_id:
            identities.append(
                (content_sha, phash, candidate_id, provider_asset_id)
            )
    return identities


def _prior_rebindable_physical_inputs(
    *, output_root: Path, current_root: Path,
) -> dict[str, tuple[Path, Mapping[str, Any], Mapping[str, Any]]]:
    """Load immutable raw bytes that may be rebound only to matching provenance."""
    resolved_current = current_root.resolve()
    roots = {SOURCE_ACQUISITION_ROOT.resolve(), output_root.resolve()}
    records: dict[str, tuple[Path, Mapping[str, Any], Mapping[str, Any]]] = {}
    for root in roots:
        if not root.is_dir() or root.is_symlink():
            continue
        for evidence_path in sorted(
            root.rglob(
                "professional-image-supported-api-*/candidates/*/evidence/*.json"
            )
        ):
            if evidence_path.is_symlink() or resolved_current in evidence_path.resolve().parents:
                continue
            try:
                evidence = load_document(
                    evidence_path,
                    group="source",
                    name="professional_image_supported_api_evidence",
                )
                preparation_root = evidence_path.parents[3]
                asset_path = preparation_root / str(evidence["originalAssetRef"])
                request_path = preparation_root / str(evidence["reviewRequestRef"])
                if (
                    asset_path.is_symlink()
                    or request_path.is_symlink()
                    or not asset_path.is_file()
                    or not request_path.is_file()
                    or file_sha256(asset_path) != evidence["contentSha256"]
                ):
                    continue
                request = load_document(
                    request_path,
                    group="source",
                    name="professional_image_supported_api_review_request",
                )
                if (
                    request["contentSha256"] != evidence["contentSha256"]
                    or request["originalAssetSha256"] != file_sha256(asset_path)
                ):
                    continue
                provider_asset_id = str(evidence["providerAssetId"])
                previous = records.get(provider_asset_id)
                if previous is not None and file_sha256(previous[0]) != file_sha256(asset_path):
                    continue
                records[provider_asset_id] = (asset_path, evidence, request)
            except (FileNotFoundError, OSError, TypeError, ValueError):
                continue
    return records


def _assert_rebindable_provenance(
    *,
    candidate: Mapping[str, Any],
    meta: Mapping[str, Any],
    evidence: Mapping[str, Any],
    request: Mapping[str, Any],
) -> None:
    """Fail closed when a matching provider asset changed source, rights, or entity."""
    checks = {
        "provider": (candidate["provider"], evidence["provider"]),
        "providerAssetId": (candidate["providerAssetId"], evidence["providerAssetId"]),
        "entityId": (candidate["entityId"], request["entityId"]),
        "observedEntityId": (candidate["observedEntityId"], request["observedEntityId"]),
        "sourcePageUrl": (meta["sourcePageUrl"], evidence["sourcePageUrl"]),
        "originalAssetUrl": (meta["originalAssetUrl"], evidence["originalAssetUrl"]),
        "creator": (meta["creator"], evidence["creator"]),
        "license": (meta["license"], evidence["license"]),
        "licenseVersion": (meta["licenseVersion"], evidence["licenseVersion"]),
        "attributionText": (meta["attributionText"], evidence["attributionText"]),
        "termsUrl": (meta["termsUrl"], evidence["termsUrl"]),
    }
    drifted = [
        field for field, (current, prior) in checks.items() if str(current) != str(prior)
    ]
    if drifted:
        raise ProfessionalImageSupportedApiInputError(
            "DATA.SOURCE.REBIND_IDENTITY_DRIFT",
            "source rebind requires matching source, rights, entity, and asset identity: "
            + ", ".join(sorted(drifted)),
        )


def _validated_transport(
    fetched: Mapping[str, Any], *, body: bytes,
) -> dict[str, Any]:
    evidence = fetched.get("transportEvidence")
    if not isinstance(evidence, dict):
        raise ProfessionalImageSupportedApiInputError(
            PREPARATION_INVALID, "supported API fetch lacks HTTPS transport evidence"
        )
    assert_valid(
        evidence,
        "source",
        "professional_image_https_transport_evidence",
        label="professional image supported API HTTPS transport evidence",
    )
    if evidence["responseSha256"] != _bytes_digest(body):
        raise ProfessionalImageSupportedApiInputError(
            PREPARATION_INVALID, "supported API HTTPS transport bytes drift"
        )
    return evidence


def _manifest_item(
    candidate: Mapping[str, Any], planned: Mapping[str, Any], meta: Mapping[str, Any],
    safety_ref: str, safety_sha: str,
    api_evidence_ref: str, judgment: Mapping[str, Any], observed_at: str,
) -> dict[str, Any]:
    return {
        "assetId": str(candidate["candidateId"]),
        "entityId": str(candidate["entityId"]),
        "observedEntityId": str(candidate["observedEntityId"]),
        "entityAliases": list(candidate["entityAliases"]),
        "sourceId": str(candidate["provider"]),
        "displayName": (
            "Openverse" if candidate["provider"] == "openverse" else "Wikimedia Commons"
        ),
        "discoveryCandidateId": str(candidate["discoveryCandidateId"]),
        "discoveryUrl": str(planned["discoveryUrl"]),
        "acquisitionPath": "supported_api",
        "sourceUrl": str(meta["sourcePageUrl"]),
        "assetUrl": str(meta["originalAssetUrl"]), "manualFile": "",
        "apiEvidence": api_evidence_ref,
        "accessEvidence": {
            "anonymousAssetAccess": True, "loginRequired": False,
            "captchaRequired": False, "paywallRequired": False,
            "drmProtected": False, "accessControlBypass": False,
        },
        "creator": str(meta["creator"]), "capturedAt": observed_at,
        "rightsStatus": "unverified", "license": str(meta["license"]),
        "licenseSnapshot": (
            f"{meta['license']} indexed by Openverse and bound to original landing page"
            if candidate["provider"] == "openverse"
            else f"{meta['license']} recorded on Wikimedia Commons file page"
        ),
        "usageScope": "app_publish", "modelReleaseStatus": "not_required",
        "termsUrl": str(meta["termsUrl"]), "authorizationProof": str(meta["sourcePageUrl"]),
        "rightsIssues": ["commercial authorization not established; research-only"],
        "caption": str(candidate["caption"]), "relevance": str(candidate["relevance"]),
        "safetyReview": {
            "status": "passed", "entityMatch": "matched",
            "privacyRisk": "none", "minorRisk": "none", "maliciousMediaRisk": "none",
            "watermarkStatus": "absent",
            "reviewedAt": str(judgment.get("reviewerReviewedAt") or ""),
            "reviewer": "semantic:" + str(judgment.get("reviewerRunId") or "bound-result"),
            "evidenceRef": safety_ref, "safetyEvidenceFileSha256": safety_sha,
        },
        "sourceAttribution": source_attribution(
            meta,
            observed_at=observed_at,
            platform=(
                "Openverse"
                if candidate["provider"] == "openverse"
                else "Wikimedia Commons"
            ),
        ),
    }


def _review_bindings(
    reviewers: Mapping[str, Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    execution_bindings: list[dict[str, Any]] = []
    for binding in sorted(
        {
            (
                str(row["executionId"]),
                str(row["executionManifestRef"]),
                str(row["executionManifestSha256"]),
                json.dumps(row["executionBundle"], sort_keys=True),
            )
            for row in reviewers.values()
            if row.get("executionId")
        }
    ):
        execution_id, manifest_ref, manifest_sha, bundle_json = binding
        execution_bindings.append(
            {
                "executionId": execution_id,
                "executionBundle": json.loads(bundle_json),
                "executionManifestRef": manifest_ref,
                "executionManifestSha256": manifest_sha,
            }
        )
    source_bindings = [
        {
            "sourceReview": dict(row["sourceIdentity"]),
            "reviewerResultRef": str(row["evidenceRef"]),
            "reviewerResultSha256": file_sha256(row["evidencePath"]),
        }
        for row in reviewers.values()
        if row.get("sourceIdentity") and not row.get("executionId")
    ]
    return execution_bindings, source_bindings

