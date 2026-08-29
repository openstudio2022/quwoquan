"""Fail-closed runtime proof for one research release in one environment."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from content.release.canonical.release_header import validate_release_header
# 策略快照、契约可用性与由其派生的 blocker 归 research_isolation_policy；此处按
# 原有内部名 re-export，既保持调用点不变，也让错误类型对既有消费者仍从本模块可见。
from content.release.environment.research_isolation_policy import (
    IDENTITY_CONTRACT as _IDENTITY_CONTRACT,
    ResearchIsolationVerificationError,
    SIGNED_MEDIA_CONTRACT as _SIGNED_MEDIA_CONTRACT,
    blocker as _blocker,
    digest_bytes as _digest_bytes,
    identity_contract_available as _identity_contract_available,
    json_object as _object,
    policy_snapshot as _policy_snapshot,
    repository_ref as _repository_ref,
    safe_segment as _safe_segment,
    signed_media_contract_available as _signed_media_contract_available,
)
from content.release.environment.research_isolation_proof import (
    ResearchIsolationProofError,
    validate_research_isolation_pass_proof,
)
from core.paths import REPO_ROOT
from core.release_layout import payload_digest, payload_file
from core.schema import assert_valid

_ENVIRONMENTS = frozenset({"alpha", "beta", "gamma", "prod"})
_SECRET_KEY_PARTS = ("token", "authorization", "credential", "password", "secret")
# DEC-034：proof 复用的新鲜度上限。策略快照覆盖不了环境栈重建，
# 超过该时效的 PASS proof 不得复用，必须重新实测。
_PROOF_REUSE_MAX_AGE_SECONDS = 24 * 60 * 60


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
    verify_run_id: str | None,
    manifest_digest: str,
    require_pass: bool,
) -> dict[str, Any]:
    """Validate one isolation document.

    ``verify_run_id=None`` keeps the release/environment/digest binding strict
    while allowing a proof produced by a prior verify run of the same release
    to be revalidated for reuse.
    """

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
        "manifestDigest": manifest_digest,
        "releaseClass": "research",
        "productLifecycleState": "research",
    }
    if verify_run_id is not None:
        expected["verifyRunId"] = verify_run_id
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
    verify_run_id: str | None,
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


def _proof_is_stale(proof: Mapping[str, Any]) -> bool:
    """A PASS proof past the DEC-034 max-age must be re-observed, not reused."""
    try:
        verified_at = datetime.fromisoformat(str(proof.get("verifiedAt") or ""))
    except ValueError:
        return True
    if verified_at.tzinfo is None:
        verified_at = verified_at.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - verified_at).total_seconds()
    return age > _PROOF_REUSE_MAX_AGE_SECONDS


def _discover_prior_runtime_proof(
    *,
    release_runs_root: Path,
    current_run_dir: Path,
    environment: str,
    release_id: str,
    manifest_digest: str,
) -> tuple[dict[str, Any] | None, int, str]:
    """Find the newest reusable PASS proof from prior verify runs.

    Reuse binds release identity, manifest digest, policy snapshot and the
    DEC-034 max-age; only the verify-run binding is relaxed, so a verify retry
    does not force a full probe rerun while the release and its runtime policy
    are unchanged. Invalid, drifted or stale candidates are skipped, never
    repaired; the skip tally feeds blocker diagnostics.
    """

    if not release_runs_root.is_dir():
        return None, 0, ""
    skipped = 0
    first_skip_reason = ""
    candidates: list[tuple[str, dict[str, Any]]] = []
    for candidate in sorted(
        release_runs_root.glob("*/research-isolation-runtime-proof.json")
    ):
        if candidate.parent == current_run_dir:
            continue
        try:
            proof, _proof_bytes = _load_runtime_proof(
                candidate,
                environment=environment,
                release_id=release_id,
                verify_run_id=None,
                manifest_digest=manifest_digest,
            )
        except ResearchIsolationVerificationError as exc:
            skipped += 1
            if not first_skip_reason:
                first_skip_reason = f"drifted: {exc}"
            continue
        if _proof_is_stale(proof):
            skipped += 1
            if not first_skip_reason:
                first_skip_reason = (
                    "stale: proof verifiedAt exceeds the "
                    f"{_PROOF_REUSE_MAX_AGE_SECONDS}s reuse max-age"
                )
            continue
        candidates.append((str(proof.get("verifiedAt") or ""), proof))
    if not candidates:
        return None, skipped, first_skip_reason
    candidates.sort(key=lambda item: item[0])
    return candidates[-1][1], skipped, first_skip_reason


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

    PASS is accepted only from a create-once environment owner proof bound to
    the same release, manifest digest and runtime policy snapshot: either the
    proof of the current verify run, or a revalidated PASS proof from a prior
    verify run of the same release rebound to the current run id.  Static
    policy, environment variables and test fixtures are never used as
    positive evidence.
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
    skipped_priors = 0
    first_skip_reason = ""
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
        prior, skipped_priors, first_skip_reason = _discover_prior_runtime_proof(
            release_runs_root=expected_output.parent.parent,
            current_run_dir=expected_output.parent,
            environment=environment,
            release_id=release_id,
            manifest_digest=manifest_digest,
        )
        if prior is not None:
            rebound = dict(prior)
            rebound["verifyRunId"] = verify_run_id
            rebound["reusedFromVerifyRunId"] = str(prior.get("verifyRunId") or "")
            rebound.pop("verificationChecksum", None)
            rebound["verificationChecksum"] = _document_checksum(rebound)
            _assert_no_secret_keys(rebound)
            try:
                assert_valid(
                    rebound,
                    "release",
                    "research_isolation_verification",
                    label="research isolation verification",
                )
            except (FileNotFoundError, TypeError, ValueError) as exc:
                raise ResearchIsolationVerificationError(str(exc)) from exc
            print(
                "[research-isolation] reusing PASS runtime proof from verify run "
                f"{prior.get('verifyRunId')} for {verify_run_id} "
                f"(release={release_id})"
            )
            _write_create_once(output_path, _json_bytes(rebound))
            return output_path

    policy_path, policy_digest, policy_issues, _policy_ttl = _policy_snapshot(
        environment
    )
    code, message, evidence_refs = _blocker(policy_issues=policy_issues)
    if skipped_priors:
        message = (
            f"{message}; skipped {skipped_priors} prior proof candidate(s), "
            f"first: {first_skip_reason}"
        )
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
