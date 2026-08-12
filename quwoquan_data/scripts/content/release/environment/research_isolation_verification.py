"""Fail-closed runtime proof for one research release in one environment."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from content.release.canonical.release_header import validate_release_header
from content.release.environment.research_isolation_proof import (
    ResearchIsolationProofError,
    validate_research_isolation_pass_proof,
)
from core.io import read_json
from core.paths import REPO_ROOT
from core.release_layout import payload_digest, payload_file
from core.schema import assert_valid

_ENVIRONMENTS = frozenset({"alpha", "beta", "gamma", "prod"})
_IDENTITY_CONTRACT = (
    REPO_ROOT / "quwoquan_service/services/user-service/contracts/account/"
    "account_session/operations.yaml"
)
_SIGNED_MEDIA_CONTRACT = (
    REPO_ROOT / "quwoquan_service/services/content-service/contracts/media/"
    "original_access_quota/operations.yaml"
)
_SIGNED_MEDIA_POLICY = (
    REPO_ROOT / "quwoquan_service/services/content-service/contracts/media/"
    "original_access_quota/original_access_policy.yaml"
)
_REQUIRED_IDENTITY_OPERATION = "IssueWhitelistedResearchSession"
_REQUIRED_SIGNED_MEDIA_OPERATION = "ReserveOriginalImageAccessGrant"
_REQUIRED_TRUE = (
    "identityWhitelistRequired",
    "sharingDisabled",
    "exportDisabled",
    "internalAppSignatureRequired",
    "researchBadgeRequired",
    "shortLivedSignedMediaUrlsRequired",
    "mediaAccessAuditLogRequired",
)
_REQUIRED_FALSE = (
    "anonymousContentAccess",
    "anonymousMediaAccess",
    "publicContentDistribution",
    "searchIndexingDisabled",
)
_SECRET_KEY_PARTS = ("token", "authorization", "credential", "password", "secret")


class ResearchIsolationVerificationError(ValueError):
    """Research isolation evidence is unsafe, drifted, or not canonical."""


def _digest_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _document_checksum(value: Mapping[str, Any]) -> str:
    return _digest_bytes(
        json.dumps(
            dict(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(
            dict(value),
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
        + "\n"
    ).encode("utf-8")


def _write_create_once(path: Path, payload: bytes) -> None:
    """Atomically create ``path`` without permitting a concurrent overwrite."""

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
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path)
    except FileExistsError as exc:
        raise ResearchIsolationVerificationError(
            f"research isolation verification already exists: {path}"
        ) from exc
    finally:
        if temporary:
            Path(temporary).unlink(missing_ok=True)


def research_isolation_file_digest(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise ResearchIsolationVerificationError(
            f"research isolation receipt is missing: {path}"
        )
    return _digest_bytes(path.read_bytes())


def _safe_segment(value: str, *, label: str) -> str:
    text = str(value or "").strip()
    candidate = Path(text)
    if (
        not text
        or text in {".", ".."}
        or candidate.is_absolute()
        or len(candidate.parts) != 1
        or "/" in text
        or "\\" in text
    ):
        raise ResearchIsolationVerificationError(f"{label} must be one safe segment")
    return text


def _object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = read_json(path)
    except (OSError, TypeError, ValueError) as exc:
        raise ResearchIsolationVerificationError(
            f"{label} is unreadable: {path}"
        ) from exc
    if not isinstance(value, Mapping):
        raise ResearchIsolationVerificationError(f"{label} must be an object: {path}")
    return dict(value)


def _yaml_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ResearchIsolationVerificationError(
            f"{label} is unreadable: {path}"
        ) from exc
    if not isinstance(value, Mapping):
        raise ResearchIsolationVerificationError(f"{label} must be an object: {path}")
    return dict(value)


def _repository_ref(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError as exc:
        raise ResearchIsolationVerificationError(
            f"research isolation evidence must be repository-owned: {path}"
        ) from exc


def _policy_snapshot(
    environment: str,
) -> tuple[Path, str, list[str], int | None]:
    path = REPO_ROOT / "quwoquan_ops/environments" / environment / "runtime.yaml"
    payload = _yaml_object(path, label="research runtime policy")
    issues: list[str] = []
    if payload.get("productLifecycleState") != "research":
        issues.append("productLifecycleState must be research")
    isolation = payload.get("researchContentIsolation")
    if not isinstance(isolation, Mapping):
        issues.append("researchContentIsolation must be an object")
        isolation = {}
    issues.extend(
        f"researchContentIsolation.{field} must be true"
        for field in _REQUIRED_TRUE
        if isolation.get(field) is not True
    )
    issues.extend(
        f"researchContentIsolation.{field} must be false"
        for field in _REQUIRED_FALSE
        if isolation.get(field) is not False
    )
    ttl = isolation.get("signedMediaUrlMaxTtlSeconds")
    if not isinstance(ttl, int) or isinstance(ttl, bool) or not 1 <= ttl <= 900:
        issues.append(
            "researchContentIsolation.signedMediaUrlMaxTtlSeconds must be 1..900"
        )
        ttl = None
    return path, _digest_bytes(path.read_bytes()), issues, ttl


def _identity_contract_available() -> bool:
    payload = _yaml_object(_IDENTITY_CONTRACT, label="account session operations")
    routes = payload.get("api_routes")
    if not isinstance(routes, list):
        return False
    for raw in routes:
        if not isinstance(raw, Mapping):
            continue
        security = raw.get("security")
        response_fields = raw.get("response_fields")
        if (
            raw.get("operation") == _REQUIRED_IDENTITY_OPERATION
            and raw.get("method") == "POST"
            and isinstance(security, Mapping)
            and security.get("auth_mode") == "required"
            and security.get("anonymous_policy") == "deny"
            and isinstance(response_fields, list)
            and {"subjectHash", "attestationId"}.issubset(response_fields)
        ):
            return True
    return False


def _signed_media_contract_available() -> bool:
    payload = _yaml_object(_SIGNED_MEDIA_CONTRACT, label="signed media operations")
    policy = _yaml_object(_SIGNED_MEDIA_POLICY, label="signed media policy")
    routes = payload.get("api_routes")
    ttl = policy.get("grant_ttl_seconds")
    if not isinstance(routes, list) or not isinstance(ttl, int) or not 1 <= ttl <= 900:
        return False
    for raw in routes:
        if not isinstance(raw, Mapping):
            continue
        security = raw.get("security")
        fields = raw.get("response_fields")
        if (
            raw.get("operation") == _REQUIRED_SIGNED_MEDIA_OPERATION
            and isinstance(security, Mapping)
            and security.get("auth_mode") == "required"
            and security.get("anonymous_policy") == "deny"
            and isinstance(fields, list)
            and {"originalUrl", "ttlSeconds", "auditId"}.issubset(fields)
        ):
            return True
    return False


def _blocker(
    *,
    policy_issues: list[str],
) -> tuple[str, str, list[str]]:
    if policy_issues:
        return (
            "DATA.RESEARCH.ISOLATION_POLICY_INVALID",
            "; ".join(policy_issues),
            [],
        )
    if not _identity_contract_available():
        return (
            "DATA.RESEARCH.IDENTITY_ADAPTER_UNAVAILABLE",
            (
                "No canonical whitelisted research identity issuance/attestation "
                "operation is available"
            ),
            [_repository_ref(_IDENTITY_CONTRACT)],
        )
    if not _signed_media_contract_available():
        return (
            "DATA.RESEARCH.SIGNED_MEDIA_ADAPTER_UNAVAILABLE",
            (
                "No canonical authenticated short-lived signed-media operation "
                "with audit identity is available"
            ),
            [
                _repository_ref(_SIGNED_MEDIA_CONTRACT),
                _repository_ref(_SIGNED_MEDIA_POLICY),
            ],
        )
    return (
        "DATA.RESEARCH.RUNTIME_PROOF_INCOMPLETE",
        (
            "Runtime identity, internal App, anonymous denial, egress denial and "
            "exact release readback probes are not implemented"
        ),
        [
            _repository_ref(_IDENTITY_CONTRACT),
            _repository_ref(_SIGNED_MEDIA_CONTRACT),
        ],
    )


def _assert_no_secret_keys(value: object, *, path: str = "receipt") -> None:
    if isinstance(value, Mapping):
        for raw_key, child in value.items():
            key = str(raw_key)
            lowered = key.casefold()
            if any(part in lowered for part in _SECRET_KEY_PARTS):
                raise ResearchIsolationVerificationError(
                    "research isolation receipt contains forbidden secret field: "
                    f"{path}.{key}"
                )
            _assert_no_secret_keys(child, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _assert_no_secret_keys(child, path=f"{path}[{index}]")


def _validate_research_isolation_document(
    payload: dict[str, Any],
    *,
    environment: str,
    release_id: str,
    verify_run_id: str,
    manifest_digest: str,
    require_pass: bool,
) -> dict[str, Any]:
    _assert_no_secret_keys(payload)
    try:
        assert_valid(
            payload,
            "release",
            "research_isolation_verification",
            label="research isolation verification",
        )
    except (FileNotFoundError, TypeError, ValueError) as exc:
        raise ResearchIsolationVerificationError(str(exc)) from exc
    declared = str(payload.get("verificationChecksum") or "")
    unsigned = dict(payload)
    unsigned.pop("verificationChecksum", None)
    if declared != _document_checksum(unsigned):
        raise ResearchIsolationVerificationError(
            "research isolation verificationChecksum drift"
        )
    expected = {
        "environment": environment,
        "releaseId": release_id,
        "verifyRunId": verify_run_id,
        "manifestDigest": manifest_digest,
        "releaseClass": "research",
        "productLifecycleState": "research",
    }
    if any(payload.get(key) != value for key, value in expected.items()):
        raise ResearchIsolationVerificationError(
            "research isolation release/environment identity drift"
        )
    policy_path, policy_digest, policy_issues, policy_ttl = _policy_snapshot(
        environment
    )
    if (
        payload.get("policyRef") != _repository_ref(policy_path)
        or policy_path.is_symlink()
        or not policy_path.is_file()
        or policy_digest != payload.get("policySha256")
    ):
        raise ResearchIsolationVerificationError(
            "research isolation policy snapshot drift"
        )
    if payload.get("outcome") == "PASS":
        if policy_issues or policy_ttl is None:
            raise ResearchIsolationVerificationError(
                "DATA.RESEARCH.ISOLATION_POLICY_INVALID: " + "; ".join(policy_issues)
            )
        if not _identity_contract_available():
            raise ResearchIsolationVerificationError(
                "DATA.RESEARCH.IDENTITY_ADAPTER_UNAVAILABLE: canonical "
                "whitelisted research identity issuance/attestation operation "
                "is absent"
            )
        if not _signed_media_contract_available():
            raise ResearchIsolationVerificationError(
                "DATA.RESEARCH.SIGNED_MEDIA_ADAPTER_UNAVAILABLE: canonical "
                "authenticated signed-media operation is absent"
            )
        try:
            validate_research_isolation_pass_proof(
                payload,
                policy_ttl=policy_ttl,
                repository_root=REPO_ROOT,
                identity_contract=_IDENTITY_CONTRACT,
            )
        except ResearchIsolationProofError as exc:
            raise ResearchIsolationVerificationError(str(exc)) from exc
    if require_pass and payload.get("outcome") != "PASS":
        blocker = payload.get("blocker")
        code = blocker.get("code") if isinstance(blocker, Mapping) else "unknown"
        raise ResearchIsolationVerificationError(
            f"{code}: canonical research isolation runtime proof is GATE_BLOCK"
        )
    return payload


def load_research_isolation_verification(
    path: Path,
    *,
    environment: str,
    release_id: str,
    verify_run_id: str,
    manifest_digest: str,
    require_pass: bool,
) -> dict[str, Any]:
    payload = _object(path, label="research isolation verification")
    return _validate_research_isolation_document(
        payload,
        environment=environment,
        release_id=release_id,
        verify_run_id=verify_run_id,
        manifest_digest=manifest_digest,
        require_pass=require_pass,
    )


def _load_runtime_proof(
    path: Path,
    *,
    environment: str,
    release_id: str,
    verify_run_id: str,
    manifest_digest: str,
) -> tuple[dict[str, Any], bytes]:
    if path.is_symlink() or not path.is_file():
        raise ResearchIsolationVerificationError(
            f"research isolation runtime proof is missing: {path}"
        )
    try:
        proof_bytes = path.read_bytes()
        raw = json.loads(proof_bytes.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ResearchIsolationVerificationError(
            f"research isolation runtime proof is unreadable: {path}"
        ) from exc
    if not isinstance(raw, Mapping):
        raise ResearchIsolationVerificationError(
            "research isolation runtime proof must be an object"
        )
    proof = _validate_research_isolation_document(
        dict(raw),
        environment=environment,
        release_id=release_id,
        verify_run_id=verify_run_id,
        manifest_digest=manifest_digest,
        require_pass=True,
    )
    return proof, proof_bytes


def write_research_isolation_verification(
    *,
    environment: str,
    release_id: str,
    verify_run_id: str,
    release_root: Path,
    output_root: Path,
    output_path: Path,
    runtime_proof_path: Path | None = None,
) -> Path:
    """Freeze a validated runtime proof, or write the current typed blocker.

    PASS is accepted only from an explicitly supplied, create-once environment
    owner proof in the same canonical verify run.  Static policy, environment
    variables and test fixtures are never used as positive evidence.
    """

    environment = _safe_segment(environment, label="environment")
    release_id = _safe_segment(release_id, label="releaseId")
    verify_run_id = _safe_segment(verify_run_id, label="verifyRunId")
    if environment not in _ENVIRONMENTS:
        raise ResearchIsolationVerificationError("environment is not canonical")
    resolved_output_root = output_root.resolve()
    expected_release_root = output_root / "data" / "releases" / release_id
    if (
        release_root.is_symlink()
        or not release_root.is_dir()
        or release_root.resolve() != expected_release_root.resolve()
    ):
        raise ResearchIsolationVerificationError(
            "research isolation requires the canonical immutable release root"
        )
    expected_output = (
        output_root
        / "env"
        / environment
        / "runs/data-release"
        / release_id
        / verify_run_id
        / "research-isolation-verification.json"
    )
    try:
        expected_output.resolve().relative_to(resolved_output_root)
    except ValueError as exc:
        raise ResearchIsolationVerificationError(
            "research isolation output escapes QWQ_OUTPUT_ROOT"
        ) from exc
    if output_path.resolve() != expected_output.resolve():
        raise ResearchIsolationVerificationError(
            "research isolation output must use the canonical verify run path"
        )
    header = _object(payload_file(release_root, "release.json"), label="release header")
    try:
        validate_release_header(header, label="release header")
    except (FileNotFoundError, TypeError, ValueError) as exc:
        raise ResearchIsolationVerificationError(str(exc)) from exc
    if (
        header.get("releaseId") != release_id
        or header.get("releaseClass") != "research"
        or header.get("productLifecycleState") != "research"
    ):
        raise ResearchIsolationVerificationError(
            "research isolation requires the exact immutable research release"
        )
    manifest_digest = payload_digest(release_root)
    if runtime_proof_path is not None:
        expected_runtime_proof = expected_output.with_name(
            "research-isolation-runtime-proof.json"
        )
        if runtime_proof_path.resolve() != expected_runtime_proof.resolve():
            raise ResearchIsolationVerificationError(
                "research isolation runtime proof must use the canonical "
                "create-once verify run path"
            )
        if runtime_proof_path.exists() or runtime_proof_path.is_symlink():
            _proof, proof_bytes = _load_runtime_proof(
                runtime_proof_path,
                environment=environment,
                release_id=release_id,
                verify_run_id=verify_run_id,
                manifest_digest=manifest_digest,
            )
            _write_create_once(output_path, proof_bytes)
            return output_path

    policy_path, policy_digest, policy_issues, _policy_ttl = _policy_snapshot(
        environment
    )
    code, message, evidence_refs = _blocker(policy_issues=policy_issues)
    if not evidence_refs:
        evidence_refs = [_repository_ref(policy_path)]
    document: dict[str, Any] = {
        "schema": "quwoquan_data.research_isolation_verification",
        "environment": environment,
        "releaseId": release_id,
        "manifestDigest": manifest_digest,
        "releaseClass": "research",
        "productLifecycleState": "research",
        "verifyRunId": verify_run_id,
        "policyRef": _repository_ref(policy_path),
        "policySha256": policy_digest,
        "outcome": "GATE_BLOCK",
        "blocker": {
            "code": code,
            "message": message,
            "evidenceRefs": sorted(set(evidence_refs)),
        },
        "verifiedAt": datetime.now(timezone.utc).isoformat(),
    }
    document["verificationChecksum"] = _document_checksum(document)
    _assert_no_secret_keys(document)
    try:
        assert_valid(
            document,
            "release",
            "research_isolation_verification",
            label="research isolation verification",
        )
    except (FileNotFoundError, TypeError, ValueError) as exc:
        raise ResearchIsolationVerificationError(str(exc)) from exc
    _write_create_once(output_path, _json_bytes(document))
    return output_path


__all__ = [
    "ResearchIsolationVerificationError",
    "load_research_isolation_verification",
    "research_isolation_file_digest",
    "write_research_isolation_verification",
]
