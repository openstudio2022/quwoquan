"""Create handoff-bound evidence from explicit local professional-image bytes."""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from core.image_decode import probe_image_bytes
from core.io import read_json
from core.schema import assert_valid
from core.source_attribution import canonical_source_attribution

from content.execution.controller.execute.pre_acquisition_handoff import (
    guard_acquisition_source_identity,
    load_pre_acquisition_handoff,
)
from content.source.image_payload import sniff_image_ext
from content.source.professional_image_source_attribution import (
    bound_image_source_attribution,
)

MANUAL_EVIDENCE_INVALID = "DATA.SOURCE.IMAGE_MANUAL_EVIDENCE_INVALID"
MANUAL_EVIDENCE_SHA_DRIFT = "DATA.SOURCE.IMAGE_MANUAL_EVIDENCE_SHA_DRIFT"
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_PROVIDER_HOSTS = {
    "pinterest": ("pinterest.com",),
    "tuchong": ("tuchong.com",),
    "wikimedia_commons": ("commons.wikimedia.org",),
    "openverse": ("openverse.org",),
}
_PLATFORMS = {
    "pinterest": "Pinterest",
    "tuchong": "图虫",
    "wikimedia_commons": "Wikimedia Commons",
    "openverse": "Openverse",
}


class ProfessionalImageManualEvidenceError(ValueError):
    """Typed rejection for unsafe bytes or unsupported provenance claims."""

    def __init__(self, code: str, issue: str) -> None:
        self.code = code
        self.issue = str(issue).strip()
        super().__init__(f"{code}: {self.issue}")


def _fail(issue: str, *, code: str = MANUAL_EVIDENCE_INVALID) -> None:
    raise ProfessionalImageManualEvidenceError(code, issue)


def _digest(value: Mapping[str, Any]) -> str:
    body = json.dumps(
        dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(body).hexdigest()


def _sha256(body: bytes) -> str:
    return "sha256:" + hashlib.sha256(body).hexdigest()


def _text(value: object, *, label: str) -> str:
    rendered = " ".join(str(value or "").split())
    if not rendered or "\x00" in rendered:
        _fail(f"{label} must be non-empty")
    return rendered


def _timestamp(value: object) -> str:
    rendered = _text(value, label="observedAt")
    try:
        parsed = datetime.fromisoformat(rendered.replace("Z", "+00:00"))
    except ValueError:
        _fail("observedAt must be an ISO-8601 timestamp")
    if parsed.tzinfo is None:
        _fail("observedAt must include a timezone")
    return rendered


def _safe_relative(value: object, *, label: str) -> Path:
    rendered = str(value or "").strip()
    relative = Path(rendered)
    if (
        not rendered
        or relative.is_absolute()
        or ".." in relative.parts
        or "\x00" in rendered
    ):
        _fail(f"{label} must be a safe relative reference")
    return relative


def _root(path: Path, *, label: str, must_exist: bool) -> Path:
    expanded = path.expanduser()
    if not expanded.is_absolute():
        _fail(f"{label} must be absolute")
    if expanded.is_symlink():
        _fail(f"{label} must not be a symlink")
    if must_exist and (not expanded.exists() or not expanded.is_dir()):
        _fail(f"{label} must be an existing directory")
    if not must_exist and not expanded.exists():
        expanded.mkdir(parents=True, mode=0o700)
        if expanded.is_symlink():
            _fail(f"{label} must not be a symlink")
    if expanded.exists() and not expanded.is_dir():
        _fail(f"{label} must be a directory")
    return expanded.resolve()


def _read_regular(root: Path, ref: object, *, label: str) -> tuple[bytes, Path]:
    relative = _safe_relative(ref, label=label)
    current = root
    for part in relative.parts[:-1]:
        current = current / part
        try:
            mode = current.lstat().st_mode
        except FileNotFoundError:
            _fail(f"{label} is missing")
        if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
            _fail(f"{label} must not traverse a symlink or non-directory")
    path = current / relative.name
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        _fail(f"{label} cannot be opened safely: {exc}")
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            _fail(f"{label} must be a regular file")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(descriptor)
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns
        ):
            _fail(f"{label} changed while being read")
        return b"".join(chunks), path
    finally:
        os.close(descriptor)


def _write_once(
    root: Path, ref: object, body: bytes, *, mode: int = 0o600
) -> Path:
    relative = _safe_relative(ref, label="outputRef")
    current = root
    for part in relative.parts[:-1]:
        current = current / part
        try:
            current.mkdir(mode=0o700)
        except FileExistsError:
            pass
        mode_bits = current.lstat().st_mode
        if stat.S_ISLNK(mode_bits) or not stat.S_ISDIR(mode_bits):
            _fail("outputRef must not traverse a symlink or non-directory")
    path = current / relative.name
    try:
        descriptor = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            mode,
        )
    except FileExistsError:
        existing, _path = _read_regular(root, relative, label="outputRef")
        if existing != body:
            _fail(f"create-once collision: {path}")
        return path
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(body)
        handle.flush()
        os.fsync(handle.fileno())
    return path


def _provider_url(provider: str, value: object) -> str:
    source_page = _text(value, label="sourcePageUrl")
    parsed = urlsplit(source_page)
    host = str(parsed.hostname or "").casefold()
    allowed = _PROVIDER_HOSTS.get(provider)
    if (
        allowed is None
        or parsed.scheme != "https"
        or not host
        or parsed.username is not None
        or parsed.password is not None
        or not any(host == root or host.endswith("." + root) for root in allowed)
    ):
        _fail("sourcePageUrl must be provider-owned HTTPS")
    return source_page


def _https_url(value: object, *, label: str) -> str:
    rendered = _text(value, label=label)
    parsed = urlsplit(rendered)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        _fail(f"{label} must be HTTPS without embedded credentials")
    return rendered


def _attribution(
    body: bytes,
    *,
    expected_sha256: str,
    item: Mapping[str, Any],
    platform: str,
) -> dict[str, Any]:
    if _sha256(body) != expected_sha256:
        _fail(
            "sourceAttribution input SHA-256 differs from --source-attribution-sha256",
            code=MANUAL_EVIDENCE_SHA_DRIFT,
        )
    try:
        value = json.loads(body.decode("utf-8"))
        attribution = canonical_source_attribution(value)
    except (UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        _fail(f"sourceAttribution input is invalid: {exc}")
    admission = str(attribution["publicationAdmission"])
    if admission == "commercial_release":
        decision = "commercial_allowed"
    elif admission == "research_release":
        decision = "research_allowed"
    else:
        _fail("risk-accepted attribution is not admitted by manual evidence writer")
    try:
        bound_image_source_attribution(
            {**dict(item), "sourceAttribution": attribution},
            platform=platform,
            distribution_decision=decision,
        )
    except (TypeError, ValueError) as exc:
        _fail(f"sourceAttribution binding is invalid: {exc}")
    return attribution


def prepare_professional_image_manual_evidence(
    *,
    source_root: Path,
    source_ref: str,
    source_sha256: str,
    source_attribution_root: Path,
    source_attribution_ref: str,
    source_attribution_sha256: str,
    handoff_ref: Path,
    output_root: Path,
    provider: str,
    discovery_candidate_id: str,
    source_page_url: str,
    creator: str,
    title: str,
    observed_at: str,
    rights_status: str,
    license_name: str,
    license_snapshot: str,
    usage_scope: str,
    model_release_status: str,
    terms_url: str,
    authorization_proof: str,
    rights_issues: Sequence[str] = (),
) -> tuple[dict[str, Any], Path]:
    """Copy exact bytes and write one immutable, handoff-bound evidence object."""

    if not _SHA256.fullmatch(source_sha256):
        _fail("sourceSha256 must be sha256")
    if not _SHA256.fullmatch(source_attribution_sha256):
        _fail("sourceAttributionSha256 must be sha256")
    source_base = _root(source_root, label="sourceRoot", must_exist=True)
    attribution_base = _root(
        source_attribution_root, label="sourceAttributionRoot", must_exist=True
    )
    destination_root = _root(output_root, label="outputRoot", must_exist=False)
    body, _ = _read_regular(source_base, source_ref, label="sourceRef")
    content_sha256 = _sha256(body)
    if content_sha256 != source_sha256:
        _fail(
            "source bytes differ from --source-sha256",
            code=MANUAL_EVIDENCE_SHA_DRIFT,
        )
    if not 3000 <= len(body) <= 64 * 1024 * 1024:
        _fail("source image bytes must be within 3000..67108864")
    extension = sniff_image_ext(body, "")
    probe = probe_image_bytes(body)
    if extension is None or not probe.succeeded:
        _fail("sourceRef is not a decodable supported image")

    handoff_path = handoff_ref.expanduser().resolve()
    handoff = load_pre_acquisition_handoff(handoff_path)
    source_document = handoff.get("sourceDigest")
    source_digest = str(
        source_document.get("digest") if isinstance(source_document, Mapping) else ""
    )
    identity = {
        "sourceRevision": str(handoff["sourceRevision"]),
        "sourceDigest": source_digest,
        "executionBundle": dict(handoff["executionBundle"]),
        "entityCatalogDigest": str(handoff["entityCatalogDigest"]),
    }
    guard_acquisition_source_identity(identity, handoff_ref=handoff_path)

    provider_value = _text(provider, label="provider").casefold()
    source_page = _provider_url(provider_value, source_page_url)
    candidate_id = _text(discovery_candidate_id, label="discoveryCandidateId")
    if not re.fullmatch(
        rf"{re.escape(provider_value)}:(?:[a-z0-9_-]+:)?[0-9a-f]{{16}}",
        candidate_id,
    ):
        _fail("discoveryCandidateId must be scoped to provider")
    observed = _timestamp(observed_at)
    issues = sorted({_text(issue, label="rightsIssue") for issue in rights_issues})
    if rights_status not in {"verified", "unverified", "restricted", "unknown"}:
        _fail("rightsStatus is invalid")
    if rights_status != "verified" and not issues:
        _fail("non-verified rightsStatus requires at least one rightsIssue")
    item = {
        "sourceUrl": source_page,
        "assetUrl": "",
        "creator": _text(creator, label="creator"),
        "capturedAt": observed,
        "license": _text(license_name, label="license"),
        "modelReleaseStatus": _text(
            model_release_status, label="modelReleaseStatus"
        ),
        "termsUrl": _https_url(terms_url, label="termsUrl"),
        "authorizationProof": _https_url(
            authorization_proof, label="authorizationProof"
        ),
        "safetyReview": {"watermarkStatus": "absent"},
    }
    attribution_body, _ = _read_regular(
        attribution_base,
        source_attribution_ref,
        label="sourceAttributionRef",
    )
    attribution_file_sha256 = _sha256(attribution_body)
    attribution = _attribution(
        attribution_body,
        expected_sha256=source_attribution_sha256,
        item=item,
        platform=_PLATFORMS[provider_value],
    )
    stable_id = {
        "handoffDigest": handoff["handoffDigest"],
        "provider": provider_value,
        "discoveryCandidateId": candidate_id,
        "sourcePageUrl": source_page,
        "contentSha256": content_sha256,
        "sourceAttribution": attribution,
    }
    evidence_id = "professional-image-manual-" + _digest(stable_id)[7:23]
    asset_ref = f"manual-image-inputs/{evidence_id}/asset{extension}"
    attribution_ref = (
        f"manual-image-inputs/{evidence_id}/source-attribution.json"
    )
    _write_once(destination_root, asset_ref, body)
    _write_once(destination_root, attribution_ref, attribution_body)
    stable = {
        "schema": "quwoquan_data.professional_image_manual_file_evidence",
        "evidenceId": evidence_id,
        **identity,
        "handoffId": str(handoff["handoffId"]),
        "handoffRevision": int(handoff["handoffRevision"]),
        "handoffDigest": str(handoff["handoffDigest"]),
        "provider": provider_value,
        "acquisitionPath": "manual_file",
        "discoveryCandidateId": candidate_id,
        "sourcePageUrl": source_page,
        "assetUrl": "",
        "manualFile": asset_ref,
        "apiEvidence": "",
        "creator": item["creator"],
        "title": _text(title, label="title"),
        "observedAt": observed,
        "contentSha256": content_sha256,
        "assetBytes": len(body),
        "dimensions": {"width": probe.width, "height": probe.height},
        "originalAssetCandidate": True,
        "generated": False,
        "rightsStatus": rights_status,
        "license": item["license"],
        "licenseSnapshot": _text(license_snapshot, label="licenseSnapshot"),
        "usageScope": _text(usage_scope, label="usageScope"),
        "modelReleaseStatus": item["modelReleaseStatus"],
        "termsUrl": item["termsUrl"],
        "authorizationProof": item["authorizationProof"],
        "rightsIssues": issues,
        "sourceAttributionFile": attribution_ref,
        "sourceAttributionFileSha256": attribution_file_sha256,
        "sourceAttribution": attribution,
    }
    evidence = {**stable, "evidenceDigest": _digest(stable)}
    assert_valid(
        evidence,
        "source",
        "professional_image_manual_file_evidence",
        label=f"professional image manual evidence:{evidence_id}",
    )
    evidence_path = destination_root / "manual-image-evidence" / f"{evidence_id}.json"
    payload = json.dumps(evidence, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    _write_once(
        destination_root,
        evidence_path.relative_to(destination_root),
        payload,
    )
    return evidence, evidence_path


__all__ = [
    "MANUAL_EVIDENCE_INVALID",
    "MANUAL_EVIDENCE_SHA_DRIFT",
    "ProfessionalImageManualEvidenceError",
    "prepare_professional_image_manual_evidence",
]
