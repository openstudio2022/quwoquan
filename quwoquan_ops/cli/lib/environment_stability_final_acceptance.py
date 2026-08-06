"""Authority-backed final environment-stability receipt aggregation.

The aggregator calculates a verdict only.  Authority comes from the canonical
ReleaseEvidenceManifest artifact closure, GitHub artifact-attestation
verification, and canonical hosted-ledger readbacks.  Fields inside an input
JSON document never establish their own authority.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from quwoquan_ops.ci import render_release_lifecycle_receipts as lifecycle
from quwoquan_ops.cli.lib import external_provider_governance, provider_conformance
from quwoquan_ops.cli.lib.deployment_candidate_manifest import (
    validate_release_attestations,
)
from quwoquan_ops.cli.prod import oci_supply_chain
from quwoquan_ops.cli.prod.finalize_mainline_release_artifact import (
    DIGEST_PATTERN,
    canonical_candidate_digest,
    canonical_manifest_digest,
    sha256_file,
    validate_manifest,
    validate_manifest_files,
)

SCHEMA = "qwq.environment_stability_final_acceptance"
SCHEMA_PATH = (
    Path(__file__).resolve().parents[2]
    / "gate"
    / "environment_stability_final_acceptance.schema.json"
)
PROMOTABLE_VERDICT = "PROMOTABLE"
BLOCKED_VERDICT = "GATE_BLOCK"
MAX_FUTURE_SKEW_SECONDS = 300
ENVIRONMENTS = ("alpha", "beta", "gamma")
PROVIDER_NONPROD_ENVIRONMENTS = ("alpha", "beta", "gamma")
REQUIRED_SOAK_CLAIMS = frozenset(
    {"soak", "fresh", "credentials", "approval"}
)
DEVICE_WORKFLOW = ".github/workflows/app-env-device-matrix-self-hosted.yml"
GITHUB_ATTESTED_WORKFLOW_BY_KIND = {
    "recovery.ios": DEVICE_WORKFLOW,
    "recovery.android": DEVICE_WORKFLOW,
    "nightly": DEVICE_WORKFLOW,
    "prod_sim": ".github/workflows/prod-sim-manual-admission.yml",
}

_GIT_SHA = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
_RECEIPT_ID = re.compile(r"^[0-9a-f]{64}$")
_FORBIDDEN_INPUT_NAMES = frozenset({"verdict.json", "todo.json", "todos.json"})
_SELF_AUTHORITY_FIELDS = frozenset(
    {
        "sourceauthority",
        "authorityverification",
        "credentialreceiptreff",
        "credentialreceiptrefs",
        "approvalreceiptref",
        "realreceipt",
    }
)

BLOCKER_CODES = frozenset(
    {
        "MISSING_INPUT",
        "UNREADABLE_INPUT",
        "UNSUPPORTED_INPUT",
        "SCHEMA_MISMATCH",
        "STATUS_NOT_PASSED",
        "STALE_EVIDENCE",
        "IDENTITY_MISMATCH",
        "DIGEST_MISMATCH",
        "NON_PROMOTABLE",
        "LOCAL_ATTESTATION",
        "EXPECTED_SKIP",
        "ARTIFACT_CLOSURE_INVALID",
        "UNVERIFIABLE_AUTHORITY",
        "HOSTED_READBACK_INVALID",
    }
)


@dataclass(frozen=True)
class FinalAcceptanceInputs:
    artifact_root: Path | None = None
    candidate_manifest: Path | None = None
    pilot_release_attestation: Path | None = None
    pilot_rollback_attestation: Path | None = None
    content_lifecycle_alpha: Path | None = None
    content_lifecycle_beta: Path | None = None
    content_lifecycle_gamma: Path | None = None
    local_env_green_matrix: Path | None = None
    ios_recovery_uat: Path | None = None
    android_recovery_uat: Path | None = None
    nightly_artifact: Path | None = None
    prod_sim_receipt: Path | None = None
    prod_rollout_readback: Path | None = None
    prod_rollback_readback: Path | None = None
    prod_soak_readback: Path | None = None

    def receipt_paths(self) -> dict[str, Path | None]:
        return {
            "candidate": self.candidate_manifest,
            "pilot.release": self.pilot_release_attestation,
            "pilot.rollback": self.pilot_rollback_attestation,
            "content.alpha": self.content_lifecycle_alpha,
            "content.beta": self.content_lifecycle_beta,
            "content.gamma": self.content_lifecycle_gamma,
            "local_env.green_matrix": self.local_env_green_matrix,
            "recovery.ios": self.ios_recovery_uat,
            "recovery.android": self.android_recovery_uat,
            "nightly": self.nightly_artifact,
            "prod_sim": self.prod_sim_receipt,
            "prod.rollout_readback": self.prod_rollout_readback,
            "prod.rollback_readback": self.prod_rollback_readback,
            "prod.soak_readback": self.prod_soak_readback,
        }


@dataclass(frozen=True)
class LoadedReceipt:
    label: str
    path: Path
    payload: dict[str, Any]
    digest: str


@dataclass(frozen=True)
class VerifiedAuthority:
    """Result returned only by a trusted external verifier."""

    authority: str
    subject_digest: str
    verification_digest: str
    claims: frozenset[str] = frozenset()


AttestationVerifier = Callable[
    [Path, str, Mapping[str, Any]],
    VerifiedAuthority,
]
ProviderReadinessVerifier = Callable[
    [Path, Mapping[str, Any], list[Mapping[str, Any]], Mapping[str, Any]],
    VerifiedAuthority,
]
SoakAuthorityVerifier = Callable[
    [Path, Mapping[str, Any], Mapping[str, Any]],
    VerifiedAuthority,
]
ArtifactClosureVerifier = Callable[[Path, dict[str, Any]], None]
CommandRunner = Callable[..., subprocess.CompletedProcess[str]]


class _Evaluation:
    def __init__(self) -> None:
        self.blockers: list[dict[str, str]] = []
        self.observed_at: dict[str, str] = {}
        self.authority: dict[str, VerifiedAuthority] = {}

    def block(self, code: str, label: str, message: str) -> None:
        if code not in BLOCKER_CODES:
            raise ValueError(f"unknown final-acceptance blocker code: {code}")
        blocker = {"code": code, "input": label, "message": message}
        if blocker not in self.blockers:
            self.blockers.append(blocker)


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _canonical_digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _sha256(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _load_receipt(
    evaluation: _Evaluation,
    *,
    label: str,
    path: Path | None,
) -> LoadedReceipt | None:
    if path is None or not str(path).strip():
        evaluation.block("MISSING_INPUT", label, "required typed JSON receipt is missing")
        return None
    candidate = Path(path).expanduser()
    if (
        candidate.suffix.lower() != ".json"
        or candidate.name.lower() in _FORBIDDEN_INPUT_NAMES
        or "todo" in candidate.name.lower()
    ):
        evaluation.block(
            "UNSUPPORTED_INPUT",
            label,
            "Markdown, Todo and legacy VERDICT inputs are not accepted",
        )
        return None
    try:
        if candidate.is_symlink():
            raise OSError("symbolic links are not accepted")
        resolved = candidate.resolve(strict=True)
        if not resolved.is_file():
            raise OSError("not a regular file")
        raw = resolved.read_bytes()
        payload = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        evaluation.block("UNREADABLE_INPUT", label, f"typed JSON is unreadable: {exc}")
        return None
    if not isinstance(payload, dict):
        evaluation.block("SCHEMA_MISMATCH", label, "typed receipt root must be an object")
        return None
    return LoadedReceipt(label, resolved, payload, _sha256(raw))


def _walk(value: Any) -> Iterable[tuple[str, Any]]:
    if isinstance(value, Mapping):
        for key, child in value.items():
            yield str(key), child
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _reject_self_asserted_authority(
    evaluation: _Evaluation,
    receipt: LoadedReceipt,
    *,
    allow_prod_sim_non_promotable: bool = False,
) -> None:
    for key, value in _walk(receipt.payload):
        normalized = key.replace("_", "").lower()
        text = str(value or "").strip().lower() if isinstance(value, str) else ""
        if normalized in _SELF_AUTHORITY_FIELDS:
            evaluation.block(
                "UNVERIFIABLE_AUTHORITY",
                receipt.label,
                f"self-described authority field {key!r} is not trusted",
            )
        if (
            text.startswith(("hmac-sha256:", "local-sha256:"))
            or normalized in {"attestationauthority", "authority"}
            and text in {"local", "local-hmac", "developer", "workstation"}
        ):
            evaluation.block(
                "LOCAL_ATTESTATION",
                receipt.label,
                "local or self-calculated attestation cannot establish authority",
            )
        if normalized == "expectedskip" and value is True:
            evaluation.block(
                "EXPECTED_SKIP",
                receipt.label,
                "expected skip cannot qualify final acceptance",
            )
        non_promotable = (
            normalized == "promotable" and value is False
        ) or (
            normalized == "nonpromotable" and value is True
        ) or (
            normalized in {"status", "verdict"} and text == "gate_block"
        )
        if non_promotable and not allow_prod_sim_non_promotable:
            evaluation.block(
                "NON_PROMOTABLE",
                receipt.label,
                "non-promotable evidence cannot qualify final acceptance",
            )


def _timestamp(
    evaluation: _Evaluation,
    receipt: LoadedReceipt,
    fields: Sequence[str],
    *,
    now: datetime,
    max_age_seconds: int,
) -> str:
    raw = next(
        (
            receipt.payload.get(field)
            for field in fields
            if isinstance(receipt.payload.get(field), str)
            and str(receipt.payload[field]).strip()
        ),
        "",
    )
    try:
        parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("timezone is required")
        parsed = parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        evaluation.block(
            "STALE_EVIDENCE",
            receipt.label,
            "authoritative timestamp is missing or invalid",
        )
        return ""
    age = (now - parsed).total_seconds()
    if age < -MAX_FUTURE_SKEW_SECONDS or age > max_age_seconds:
        evaluation.block(
            "STALE_EVIDENCE",
            receipt.label,
            f"receipt is outside the {max_age_seconds}-second freshness window",
        )
    normalized = parsed.isoformat().replace("+00:00", "Z")
    evaluation.observed_at[receipt.label] = normalized
    return normalized


def _schema(
    evaluation: _Evaluation,
    receipt: LoadedReceipt,
    expected: str,
) -> bool:
    if receipt.payload.get("schema") != expected:
        evaluation.block(
            "SCHEMA_MISMATCH",
            receipt.label,
            f"expected schema {expected!r}",
        )
        return False
    return True


def _passed(evaluation: _Evaluation, receipt: LoadedReceipt) -> bool:
    if receipt.payload.get("status") != "passed":
        evaluation.block(
            "STATUS_NOT_PASSED",
            receipt.label,
            "receipt status must be exactly 'passed'",
        )
        return False
    return True


def _resolve_artifact_root(
    evaluation: _Evaluation,
    configured: Path | None,
) -> Path | None:
    if configured is None or not str(configured).strip():
        evaluation.block(
            "MISSING_INPUT",
            "artifact_root",
            "canonical ReleaseEvidenceManifest artifact root is required",
        )
        return None
    try:
        candidate = Path(configured).expanduser()
        if candidate.is_symlink():
            raise OSError("symbolic links are not accepted")
        resolved = candidate.resolve(strict=True)
        if not resolved.is_dir():
            raise OSError("artifact root is not a directory")
        return resolved
    except OSError as exc:
        evaluation.block(
            "ARTIFACT_CLOSURE_INVALID",
            "artifact_root",
            f"artifact root is unavailable: {exc}",
        )
        return None


def verify_canonical_provider_readiness(
    artifact_root: Path,
    payload: Mapping[str, Any],
    evidence: list[Mapping[str, Any]],
    manifest: Mapping[str, Any],
) -> VerifiedAuthority:
    """Re-derive manifest-bound Provider readiness from canonical governance."""

    compiled, governance_issues = external_provider_governance.load_and_compile()
    if governance_issues:
        raise ValueError(
            "Provider governance is invalid: "
            + "; ".join(issue.render() for issue in governance_issues)
        )
    source_catalog, source_issues = provider_conformance.discover_test_sources()
    if source_issues:
        raise ValueError("Provider source discovery is invalid: " + "; ".join(source_issues))
    validation_issues = provider_conformance.validate_evidence(
        evidence,
        registry=external_provider_governance.load_registry(),
        root=artifact_root / "evidence/raw/provider",
        current_commit=str(manifest["source"]["gitSha"]),
        compiled=compiled,
        source_catalog=source_catalog,
    )
    if validation_issues:
        raise ValueError(
            "Provider raw evidence is invalid: " + "; ".join(validation_issues)
        )
    coverage_issues = provider_conformance.source_coverage_issues(
        compiled=compiled,
        sources=source_catalog,
    )
    if coverage_issues:
        raise ValueError(
            "Provider source coverage is incomplete: " + "; ".join(coverage_issues)
        )
    derived = provider_conformance.derive_readiness(
        compiled=compiled,
        evidence=evidence,
    )
    derived_report = {
        "schema": "provider-conformance-readiness",
        "evidenceCount": len(evidence),
        "sourceCoverageIssues": coverage_issues,
        "readiness": derived,
        "issues": [],
    }
    readiness_errors = [
        issue
        for environment in (*PROVIDER_NONPROD_ENVIRONMENTS, "prod")
        for issue in provider_conformance.readiness_issues(
            derived_report,
            environment=environment,
        )
    ]
    if readiness_errors:
        raise ValueError(
            "Provider derived readiness is not promotable: "
            + "; ".join(readiness_errors)
        )
    declared = payload.get("readiness")
    if not isinstance(declared, Mapping):
        raise TypeError("Provider readiness payload is missing")
    for environment in (*PROVIDER_NONPROD_ENVIRONMENTS, "prod"):
        expected = derived.get(environment)
        actual = declared.get(environment)
        if not isinstance(expected, Mapping) or not isinstance(actual, Mapping):
            raise TypeError(f"Provider readiness.{environment} is missing")
        for capability_id, expected_item in expected.items():
            if not expected_item.get("required"):
                continue
            actual_item = actual.get(capability_id)
            if (
                not isinstance(actual_item, Mapping)
                or actual_item.get("required") is not True
                or actual_item.get("capability_ready")
                != expected_item.get("capability_ready")
                or actual_item.get("capability_ready") is not True
            ):
                raise ValueError(
                    f"Provider readiness.{environment}.{capability_id} drifted"
                )
    provider_path = artifact_root / str(manifest["providerEvidence"]["path"])
    return VerifiedAuthority(
        authority="canonical-provider-conformance",
        subject_digest=sha256_file(provider_path),
        verification_digest=_canonical_digest(
            {
                "compiled": compiled,
                "readiness": derived,
                "evidenceDigests": sorted(
                    sha256_file(Path(str(item["_source"]))) for item in evidence
                ),
            }
        ),
        claims=frozenset({"provider_readiness", "140_required_cells"}),
    )


def _provider_layers(
    evaluation: _Evaluation,
    *,
    artifact_root: Path,
    manifest: Mapping[str, Any],
    now: datetime,
    max_age_seconds: int,
    verifier: ProviderReadinessVerifier,
) -> None:
    provider = manifest.get("providerEvidence")
    if not isinstance(provider, Mapping):
        evaluation.block(
            "ARTIFACT_CLOSURE_INVALID",
            "artifact.provider",
            "manifest provider evidence descriptor is missing",
        )
        return
    try:
        provider_path = artifact_root / str(provider["path"])
        payload = json.loads(provider_path.read_text(encoding="utf-8"))
        files = payload["sourceEvidence"]["files"]
    except (KeyError, OSError, TypeError, json.JSONDecodeError) as exc:
        evaluation.block(
            "ARTIFACT_CLOSURE_INVALID",
            "artifact.provider",
            f"provider evidence closure is unreadable: {exc}",
        )
        return
    if not isinstance(payload, dict) or not isinstance(files, Mapping):
        evaluation.block(
            "SCHEMA_MISMATCH",
            "artifact.provider",
            "Provider readiness payload or sourceEvidence.files is not canonical",
        )
        return
    compiled, governance_issues = external_provider_governance.load_and_compile()
    capability_ids = frozenset(
        provider_conformance.provider_conformance_capability_ids(compiled)
    )
    if governance_issues or len(capability_ids) != 14:
        evaluation.block(
            "STATUS_NOT_PASSED",
            "artifact.provider",
            "canonical Provider governance must define exactly 14 required capabilities",
        )
        return
    expected_cells = set(
        provider_conformance.expected_required_cell_keys(compiled)
    )
    evidence: list[Mapping[str, Any]] = []
    observed_cells: list[tuple[str, str, str]] = []
    for relative in files:
        try:
            raw_path = artifact_root / str(relative)
            raw = json.loads(raw_path.read_text(encoding="utf-8"))
        except (OSError, TypeError, json.JSONDecodeError) as exc:
            evaluation.block(
                "ARTIFACT_CLOSURE_INVALID",
                "artifact.provider",
                f"provider raw evidence is unreadable: {exc}",
            )
            continue
        if not isinstance(raw, dict):
            evaluation.block(
                "SCHEMA_MISMATCH",
                "artifact.provider",
                "provider raw evidence root must be an object",
            )
            continue
        layer = str(raw.get("testLayer") or "")
        environment = str(raw.get("environment") or "")
        capability_id = str(raw.get("capabilityId") or "")
        cell = (capability_id, environment, layer)
        if (
            raw.get("schema") != "provider-conformance-evidence"
            or raw.get("status") != "passed"
            or raw.get("nonPromotable") is not False
            or raw.get("sourceTreeState") != "clean"
            or raw.get("commitReview") != "reviewed"
            or raw.get("candidateStatus") != "active_immutable"
            or raw.get("attestationAuthority") != "ci"
            or raw.get("commit") != manifest["source"]["gitSha"]
            or raw.get("contractGraphDigest") != manifest["contractGraphDigest"]
            or cell not in expected_cells
        ):
            evaluation.block(
                "STATUS_NOT_PASSED",
                "artifact.provider",
                f"provider raw evidence is not promotable: {relative}",
            )
            continue
        raw["_source"] = raw_path
        evidence.append(raw)
        observed_cells.append(cell)
        raw_receipt = LoadedReceipt(
            "artifact.provider",
            raw_path,
            raw,
            sha256_file(raw_path),
        )
        _timestamp(
            evaluation,
            raw_receipt,
            ("executedAt",),
            now=now,
            max_age_seconds=max_age_seconds,
        )
    duplicate_cells = len(observed_cells) != len(set(observed_cells))
    if duplicate_cells or set(observed_cells) != expected_cells:
        evaluation.block(
            "STATUS_NOT_PASSED",
            "artifact.provider",
            "manifest-bound Provider evidence must contain exactly 140 unique required cells",
        )
    readiness = payload.get("readiness")
    readiness_valid = (
        payload.get("issues") == []
        and payload.get("sourceCoverageIssues") == []
        and payload.get("evidenceCount") == 140
        and len(files) == 140
        and isinstance(readiness, Mapping)
        and set(readiness) == {"alpha", "beta", "gamma", "prod"}
    )
    if readiness_valid:
        for environment in (*PROVIDER_NONPROD_ENVIRONMENTS, "prod"):
            environment_readiness = readiness.get(environment)
            if (
                not isinstance(environment_readiness, Mapping)
                or set(environment_readiness) != capability_ids
                or any(
                    not isinstance(item, Mapping)
                    or item.get("required") is not True
                    or item.get("capability_ready") is not True
                    for item in environment_readiness.values()
                )
            ):
                readiness_valid = False
                break
    if not readiness_valid:
        evaluation.block(
            "STATUS_NOT_PASSED",
            "artifact.provider",
            "manifest-bound Provider readiness is incomplete or reports issues",
        )
    if duplicate_cells or set(observed_cells) != expected_cells or not readiness_valid:
        return
    try:
        verified = verifier(artifact_root, payload, evidence, manifest)
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        evaluation.block(
            "UNVERIFIABLE_AUTHORITY",
            "artifact.provider",
            f"canonical Provider readiness verification failed: {exc}",
        )
        return
    provider_digest = sha256_file(provider_path)
    if (
        verified.authority != "canonical-provider-conformance"
        or verified.subject_digest != provider_digest
        or DIGEST_PATTERN.fullmatch(verified.verification_digest) is None
        or not {"provider_readiness", "140_required_cells"}.issubset(
            verified.claims
        )
    ):
        evaluation.block(
            "UNVERIFIABLE_AUTHORITY",
            "artifact.provider",
            "Provider verifier did not bind canonical readiness and all 140 cells",
        )
        return
    evaluation.authority["artifact.provider"] = verified


def _artifact_closure(
    evaluation: _Evaluation,
    *,
    artifact_root: Path | None,
    manifest_receipt: LoadedReceipt | None,
    verifier: ArtifactClosureVerifier,
    provider_verifier: ProviderReadinessVerifier,
    now: datetime,
    max_age_seconds: int,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if artifact_root is None or manifest_receipt is None:
        return None, None
    if manifest_receipt.path != artifact_root / "manifest.json":
        evaluation.block(
            "ARTIFACT_CLOSURE_INVALID",
            "candidate",
            "candidate manifest must be artifact_root/manifest.json",
        )
        return None, None
    try:
        manifest = validate_manifest(
            manifest_receipt.payload,
            allowed_statuses={"released"},
        )
        verifier(artifact_root, manifest)
    except (OSError, RuntimeError, ValueError) as exc:
        evaluation.block(
            "ARTIFACT_CLOSURE_INVALID",
            "candidate",
            f"ReleaseEvidenceManifest artifact closure is invalid: {exc}",
        )
        return None, None
    if (
        manifest.get("candidateId") != canonical_candidate_digest(manifest)
        or manifest.get("artifactDigest") != canonical_manifest_digest(manifest)
    ):
        evaluation.block(
            "DIGEST_MISMATCH",
            "candidate",
            "manifest canonical candidate or artifact digest drifted",
        )
        return None, None
    if set(manifest["environmentReceipts"]) != {"alpha", "beta", "gamma", "prod"}:
        evaluation.block(
            "ARTIFACT_CLOSURE_INVALID",
            "candidate",
            "released artifact lacks the four canonical environment receipts",
        )
    if manifest.get("rolloutReceipt") is None or manifest.get("rollbackReceipt") is None:
        evaluation.block(
            "ARTIFACT_CLOSURE_INVALID",
            "candidate",
            "released artifact lacks rollout or rollback receipt closure",
        )
    _timestamp(
        evaluation,
        manifest_receipt,
        ("generatedAt",),
        now=now,
        max_age_seconds=max_age_seconds,
    )
    _provider_layers(
        evaluation,
        artifact_root=artifact_root,
        manifest=manifest,
        now=now,
        max_age_seconds=max_age_seconds,
        verifier=provider_verifier,
    )
    closure = {
        "root": artifact_root.as_posix(),
        "manifest": {
            "path": manifest_receipt.path.as_posix(),
            "digest": manifest_receipt.digest,
        },
        "candidateId": manifest["candidateId"],
        "artifactDigest": manifest["artifactDigest"],
        "providerEvidence": _bound_descriptor(artifact_root, manifest["providerEvidence"]),
        "testEvidence": _bound_descriptor(artifact_root, manifest["testEvidence"]),
        "environmentReceipts": {
            environment: _bound_descriptor(artifact_root, descriptor)
            for environment, descriptor in sorted(
                manifest["environmentReceipts"].items()
            )
        },
        "rolloutReceipt": _bound_descriptor(artifact_root, manifest["rolloutReceipt"]),
        "rollbackReceipt": _bound_descriptor(
            artifact_root,
            manifest["rollbackReceipt"],
        ),
    }
    return manifest, closure


def _bound_descriptor(
    artifact_root: Path,
    descriptor: Mapping[str, Any],
) -> dict[str, str]:
    return {
        "path": (artifact_root / str(descriptor["path"])).as_posix(),
        "digest": str(descriptor["digest"]),
    }


def _artifact_binding_matches(
    *,
    artifact_root: Path,
    receipt: LoadedReceipt,
    evidence: Any,
) -> bool:
    try:
        receipt.path.relative_to(artifact_root)
    except ValueError:
        return False
    for _, value in _walk(evidence):
        if not isinstance(value, Mapping):
            continue
        relative = value.get("path")
        digest = value.get("digest")
        if not isinstance(relative, str) or not isinstance(digest, str):
            continue
        path = artifact_root / relative
        try:
            resolved = path.resolve(strict=True)
            resolved.relative_to(artifact_root)
        except (OSError, ValueError):
            continue
        if (
            not path.is_symlink()
            and resolved == receipt.path
            and digest == receipt.digest
            and sha256_file(resolved) == digest
        ):
            return True
    return False


def _validate_manifest_bound_acceptance_inputs(
    evaluation: _Evaluation,
    *,
    artifact_root: Path | None,
    manifest: Mapping[str, Any] | None,
    loaded: Mapping[str, LoadedReceipt | None],
) -> None:
    if artifact_root is None or manifest is None:
        return
    environment_receipts = manifest["environmentReceipts"]
    for environment in ENVIRONMENTS:
        receipt = loaded[f"content.{environment}"]
        descriptor = environment_receipts.get(environment)
        if receipt is not None and (
            not isinstance(descriptor, Mapping)
            or not _artifact_binding_matches(
                artifact_root=artifact_root,
                receipt=receipt,
                evidence=descriptor.get("evidence"),
            )
        ):
            evaluation.block(
                "UNVERIFIABLE_AUTHORITY",
                receipt.label,
                "content lifecycle bytes are not bound by the matching environment receipt",
            )
    for label in ("pilot.release", "pilot.rollback"):
        receipt = loaded[label]
        if receipt is None:
            continue
        bound_environments = {
            environment
            for environment in ENVIRONMENTS
            if _artifact_binding_matches(
                artifact_root=artifact_root,
                receipt=receipt,
                evidence=environment_receipts[environment].get("evidence"),
            )
        }
        if bound_environments != set(ENVIRONMENTS):
            evaluation.block(
                "UNVERIFIABLE_AUTHORITY",
                label,
                "pilot attestation bytes are not bound by all preprod environment receipts",
            )
    matrix = loaded["local_env.green_matrix"]
    if matrix is not None:
        try:
            test_path = artifact_root / str(manifest["testEvidence"]["path"])
            test_payload = json.loads(test_path.read_text(encoding="utf-8"))
        except (KeyError, OSError, TypeError, json.JSONDecodeError) as exc:
            evaluation.block(
                "ARTIFACT_CLOSURE_INVALID",
                matrix.label,
                f"manifest test evidence is unreadable: {exc}",
            )
        else:
            if not _artifact_binding_matches(
                artifact_root=artifact_root,
                receipt=matrix,
                evidence=test_payload,
            ):
                evaluation.block(
                    "UNVERIFIABLE_AUTHORITY",
                    matrix.label,
                    "Green Matrix bytes are not bound by manifest test evidence",
                )


def _pilot_identity(
    evaluation: _Evaluation,
    release: LoadedReceipt | None,
    rollback: LoadedReceipt | None,
    *,
    now: datetime,
    max_age_seconds: int,
) -> dict[str, str] | None:
    if release is None or rollback is None:
        return None
    if not _schema(evaluation, release, "quwoquan_data.release_attestation"):
        return None
    if not _schema(evaluation, rollback, "quwoquan_data.release_attestation"):
        return None
    try:
        bindings = validate_release_attestations(str(release.path), str(rollback.path))
    except ValueError as exc:
        evaluation.block("SCHEMA_MISMATCH", "pilot", str(exc))
        return None
    candidate = bindings["candidate"]
    previous = bindings["rollback"]
    release_id = candidate["releaseId"]
    if release_id != "pilot-003" and not release_id.endswith("--pilot-003"):
        evaluation.block(
            "IDENTITY_MISMATCH",
            release.label,
            "candidate content release must be pilot-003",
        )
    if (
        release.payload.get("releaseClass") != "commercial"
        or release.payload.get("productLifecycleState") != "commercial"
        or release.payload.get("containsUnverifiedAssets") is not False
        or release.payload.get("authorizationRequiredAssetIds") != []
    ):
        evaluation.block(
            "STATUS_NOT_PASSED",
            release.label,
            "pilot-003 is not a commercially admissible release attestation",
        )
    if release_id == previous["releaseId"] or candidate["releaseDigest"] == previous["releaseDigest"]:
        evaluation.block(
            "DIGEST_MISMATCH",
            "pilot",
            "candidate and rollback content releases must be distinct",
        )
    for receipt in (release, rollback):
        _timestamp(
            evaluation,
            receipt,
            ("recordedAt",),
            now=now,
            max_age_seconds=max_age_seconds,
        )
    return {
        "releaseId": release_id,
        "releaseDigest": candidate["releaseDigest"],
        "rollbackReleaseId": previous["releaseId"],
        "rollbackDigest": previous["releaseDigest"],
    }


def _verify_checksum(evaluation: _Evaluation, receipt: LoadedReceipt) -> None:
    unsigned = dict(receipt.payload)
    declared = unsigned.pop("verificationChecksum", None)
    if declared != _canonical_digest(unsigned):
        evaluation.block(
            "DIGEST_MISMATCH",
            receipt.label,
            "verificationChecksum does not bind the receipt payload",
        )


def _validate_content_lifecycle(
    evaluation: _Evaluation,
    receipt: LoadedReceipt | None,
    *,
    environment: str,
    pilot: Mapping[str, str] | None,
    now: datetime,
    max_age_seconds: int,
) -> None:
    if receipt is None:
        return
    if not _schema(
        evaluation,
        receipt,
        "quwoquan_data.environment_release_lifecycle_exit",
    ):
        return
    payload = receipt.payload
    if payload.get("passed") is not True or payload.get("sourceOwner") != "qwq_data":
        evaluation.block(
            "STATUS_NOT_PASSED",
            receipt.label,
            "content lifecycle Exit receipt is not passed",
        )
    if payload.get("environment") != environment:
        evaluation.block(
            "IDENTITY_MISMATCH",
            receipt.label,
            f"content lifecycle environment must be {environment}",
        )
    _verify_checksum(evaluation, receipt)
    if pilot is not None:
        expected = {
            "originalReleaseId": pilot["releaseId"],
            "originalManifestDigest": pilot["releaseDigest"],
            "replayManifestDigest": pilot["releaseDigest"],
            "rollbackToReleaseId": pilot["rollbackReleaseId"],
            "rollbackToManifestDigest": pilot["rollbackDigest"],
        }
        for field, value in expected.items():
            if payload.get(field) != value:
                evaluation.block(
                    "DIGEST_MISMATCH",
                    receipt.label,
                    f"{field} differs from pilot-003 release binding",
                )
    _timestamp(
        evaluation,
        receipt,
        ("recordedAt",),
        now=now,
        max_age_seconds=max_age_seconds,
    )


def _validate_green_matrix(
    evaluation: _Evaluation,
    receipt: LoadedReceipt | None,
    *,
    pilot: Mapping[str, str] | None,
    now: datetime,
    max_age_seconds: int,
) -> None:
    if receipt is None:
        return
    if not _schema(evaluation, receipt, "quwoquan.test.case-result"):
        return
    payload = receipt.payload
    if not (
        payload.get("caseId") == "stackctl.local-env-gate.alpha-beta-gamma"
        and payload.get("status") == "passed"
        and payload.get("claim") == "ALPHA_BETA_GAMMA_LOCAL_GREEN"
        and payload.get("executionClass") == "live"
        and payload.get("targets") == ["alpha-local", "beta-local", "gamma-local"]
        and isinstance(payload.get("executed"), int)
        and payload["executed"] > 0
        and payload.get("skipped") == 0
        and payload.get("failureCategory") in {"", None}
        and DIGEST_PATTERN.fullmatch(str(payload.get("baselineId") or "")) is not None
    ):
        evaluation.block(
            "STATUS_NOT_PASSED",
            receipt.label,
            "local-env receipt is not the live Alpha/Beta/Gamma Green Matrix",
        )
    if pilot is not None and (
        payload.get("releaseId") != pilot["releaseId"]
        or payload.get("releaseDigest") != pilot["releaseDigest"]
    ):
        evaluation.block(
            "DIGEST_MISMATCH",
            receipt.label,
            "Green Matrix content release differs from pilot-003",
        )
    phases = payload.get("phases")
    if not isinstance(phases, list) or not phases or any(
        not isinstance(item, dict) or item.get("status") != "passed" for item in phases
    ):
        evaluation.block(
            "STATUS_NOT_PASSED",
            receipt.label,
            "Green Matrix contains a missing or non-passed phase",
        )
    _timestamp(
        evaluation,
        receipt,
        ("generatedAt",),
        now=now,
        max_age_seconds=max_age_seconds,
    )


def verify_github_actions_receipt(
    path: Path,
    kind: str,
    manifest: Mapping[str, Any],
    *,
    runner: CommandRunner = subprocess.run,
) -> VerifiedAuthority:
    """Verify exact receipt bytes with GitHub's trusted OIDC attestation chain."""

    repository = str(manifest["source"]["repository"])
    if oci_supply_chain.REPOSITORY_PATTERN.fullmatch(repository) is None:
        raise ValueError("manifest repository is not canonical owner/repository")
    if kind not in GITHUB_ATTESTED_WORKFLOW_BY_KIND:
        raise ValueError(f"unsupported GitHub-attested evidence kind: {kind}")
    workflow = f"{repository}/{GITHUB_ATTESTED_WORKFLOW_BY_KIND[kind]}"
    receipt_payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(receipt_payload, Mapping):
        raise TypeError("GitHub-attested receipt root must be an object")
    receipt_candidate = (
        (receipt_payload.get("releaseEvidence") or {}).get("candidateId")
        if kind == "prod_sim"
        else receipt_payload.get("candidateId")
    )
    if receipt_candidate != manifest["candidateId"]:
        raise ValueError("GitHub-attested receipt candidate differs from manifest")
    result = runner(
        [
            "gh",
            "attestation",
            "verify",
            str(path),
            "--repo",
            repository,
            "--signer-workflow",
            workflow,
            "--cert-oidc-issuer",
            oci_supply_chain.OIDC_ISSUER,
            "--format",
            "json",
        ],
        text=True,
        capture_output=True,
        check=False,
        timeout=120,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "no command output"
        raise RuntimeError(f"gh attestation verify failed: {detail[-1200:]}")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("gh attestation verify returned invalid JSON") from exc
    expected_hex = sha256_file(path).removeprefix("sha256:")
    if not _attestation_has_subject_digest(payload, expected_hex):
        raise RuntimeError("GitHub attestation does not bind the exact receipt bytes")
    return VerifiedAuthority(
        authority="github-actions-oidc",
        subject_digest=f"sha256:{expected_hex}",
        verification_digest=_canonical_digest(payload),
        claims=frozenset(
            {
                "receipt_bytes",
                kind,
                f"repository:{repository}",
                f"workflow:{workflow}",
                f"issuer:{oci_supply_chain.OIDC_ISSUER}",
                f"candidate:{manifest['candidateId']}",
            }
        ),
    )


def _attestation_has_subject_digest(value: Any, expected_hex: str) -> bool:
    if not isinstance(value, list) or not value:
        return False
    for item in value:
        try:
            subjects = item["verificationResult"]["statement"]["subject"]
        except (KeyError, TypeError):
            continue
        if isinstance(subjects, list) and any(
            isinstance(subject, Mapping)
            and isinstance(subject.get("digest"), Mapping)
            and subject["digest"].get("sha256") == expected_hex
            for subject in subjects
        ):
            return True
    return False


def _verify_authority(
    evaluation: _Evaluation,
    receipt: LoadedReceipt | None,
    *,
    manifest: Mapping[str, Any] | None,
    verifier: AttestationVerifier,
) -> None:
    if receipt is None or manifest is None:
        return
    try:
        verified = verifier(receipt.path, receipt.label, manifest)
    except (
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
        subprocess.SubprocessError,
    ) as exc:
        evaluation.block(
            "UNVERIFIABLE_AUTHORITY",
            receipt.label,
            f"cryptographic receipt verification failed: {exc}",
        )
        return
    repository = str(manifest["source"]["repository"])
    workflow_path = GITHUB_ATTESTED_WORKFLOW_BY_KIND[receipt.label]
    required_claims = {
        "receipt_bytes",
        receipt.label,
        f"repository:{repository}",
        f"workflow:{repository}/{workflow_path}",
        f"issuer:{oci_supply_chain.OIDC_ISSUER}",
        f"candidate:{manifest['candidateId']}",
    }
    if (
        verified.authority != "github-actions-oidc"
        or verified.subject_digest != receipt.digest
        or DIGEST_PATTERN.fullmatch(verified.verification_digest) is None
        or not required_claims.issubset(verified.claims)
    ):
        evaluation.block(
            "UNVERIFIABLE_AUTHORITY",
            receipt.label,
            "trusted verifier result does not bind exact receipt bytes and evidence kind",
        )
        return
    evaluation.authority[receipt.label] = verified


def _validate_ci_evidence(
    evaluation: _Evaluation,
    receipt: LoadedReceipt | None,
    *,
    kind: str,
    manifest: Mapping[str, Any] | None,
    pilot: Mapping[str, str] | None,
    now: datetime,
    max_age_seconds: int,
) -> None:
    if receipt is None:
        return
    if not _schema(evaluation, receipt, "quwoquan.test.case-result"):
        return
    payload = receipt.payload
    _passed(evaluation, receipt)
    expected_case = {
        "recovery.ios": "environment-stability.recovery.ios",
        "recovery.android": "environment-stability.recovery.android",
        "nightly": "environment-stability.nightly_full",
    }[kind]
    if (
        payload.get("caseId") != expected_case
        or not isinstance(payload.get("executed"), int)
        or payload["executed"] <= 0
        or payload.get("skipped") != 0
        or DIGEST_PATTERN.fullmatch(str(payload.get("artifactDigest") or "")) is None
    ):
        evaluation.block(
            "STATUS_NOT_PASSED",
            receipt.label,
            "CI case result is not a complete executed canonical case",
        )
    if manifest is not None and (
        payload.get("candidateId") != manifest["candidateId"]
        or payload.get("commit") != manifest["source"]["gitSha"]
    ):
        evaluation.block(
            "IDENTITY_MISMATCH",
            receipt.label,
            "CI case result differs from ReleaseEvidenceManifest",
        )
    if pilot is not None and (
        payload.get("releaseId") != pilot["releaseId"]
        or payload.get("releaseDigest") != pilot["releaseDigest"]
    ):
        evaluation.block(
            "DIGEST_MISMATCH",
            receipt.label,
            "CI case result content release differs from pilot-003",
        )
    _timestamp(
        evaluation,
        receipt,
        ("executedAt", "generatedAt"),
        now=now,
        max_age_seconds=max_age_seconds,
    )


def _validate_prod_sim(
    evaluation: _Evaluation,
    receipt: LoadedReceipt | None,
    *,
    manifest: Mapping[str, Any] | None,
    pilot: Mapping[str, str] | None,
    now: datetime,
    max_age_seconds: int,
) -> None:
    if receipt is None:
        return
    if not _schema(
        evaluation,
        receipt,
        "prod-hosted-first-party-prevalidation-report",
    ):
        return
    payload = receipt.payload
    eligibility = payload.get("releaseEligibility")
    release = payload.get("releaseEvidence")
    if not (
        payload.get("target") == "prod-hosted"
        and payload.get("mode") == "prevalidate"
        and payload.get("dataMode") == "isolated"
        and payload.get("scope") == "first-party"
        and payload.get("dryRun") is False
        and (payload.get("containerDeployment") or {}).get("status") == "passed"
        and isinstance(eligibility, Mapping)
        and eligibility.get("status") == "GATE_BLOCK"
        and eligibility.get("promotable") is False
        and eligibility.get("ledgerWritten") is False
        and eligibility.get("receiptWritten") is False
        and payload.get("issues") == []
    ):
        evaluation.block(
            "STATUS_NOT_PASSED",
            receipt.label,
            "prod-sim is not the canonical non-promotable isolated rehearsal",
        )
    if manifest is not None and (
        not isinstance(release, Mapping)
        or release.get("candidateId") != manifest["candidateId"]
        or (release.get("source") or {}).get("gitSha")
        != manifest["source"]["gitSha"]
    ):
        evaluation.block(
            "IDENTITY_MISMATCH",
            receipt.label,
            "prod-sim rehearsal differs from ReleaseEvidenceManifest",
        )
    if pilot is not None and (
        payload.get("releaseId") != pilot["releaseId"]
        or payload.get("releaseDigest") != pilot["releaseDigest"]
    ):
        evaluation.block(
            "DIGEST_MISMATCH",
            receipt.label,
            "prod-sim content release differs from pilot-003",
        )
    _timestamp(
        evaluation,
        receipt,
        ("endedAt",),
        now=now,
        max_age_seconds=max_age_seconds,
    )


def _service_from_readback(payload: Mapping[str, Any]) -> str:
    receipt = payload.get("receipt")
    if not isinstance(receipt, Mapping):
        return ""
    return str(receipt.get("service") or "")


def _manifest_contains_receipt_id(
    descriptor: Mapping[str, Any] | None,
    receipt_id: str,
) -> bool:
    if not isinstance(descriptor, Mapping):
        return False
    return any(
        key == "receiptId" and value == receipt_id
        for key, value in _walk(descriptor.get("evidence"))
    )


def _bound_stage_readback(
    artifact_root: Path,
    descriptor: Mapping[str, Any],
    receipt_id: str,
) -> tuple[Path, str] | None:
    for _, value in _walk(descriptor.get("evidence")):
        if not isinstance(value, Mapping) or value.get("receiptId") != receipt_id:
            continue
        readback = value.get("readback")
        if (
            isinstance(readback, Mapping)
            and isinstance(readback.get("path"), str)
            and isinstance(readback.get("digest"), str)
        ):
            return artifact_root / readback["path"], str(readback["digest"])
    return None


def _validate_hosted_readbacks(
    evaluation: _Evaluation,
    *,
    rollout: LoadedReceipt | None,
    rollback: LoadedReceipt | None,
    artifact_root: Path | None,
    manifest: Mapping[str, Any] | None,
    now: datetime,
    max_age_seconds: int,
) -> Mapping[str, Any] | None:
    if rollout is None or rollback is None or artifact_root is None or manifest is None:
        return None
    rollout_service = _service_from_readback(rollout.payload)
    rollback_service = _service_from_readback(rollback.payload)
    if not rollout_service or rollback_service != rollout_service:
        evaluation.block(
            "HOSTED_READBACK_INVALID",
            "prod.hosted",
            "hosted readbacks lack one consistent service identity",
        )
        return None
    try:
        rollout_receipt = lifecycle._validate_receipt_readback(
            rollout.payload,
            service=rollout_service,
        )
        ledger_receipt = lifecycle._validate_ledger_readback(
            rollback.payload,
            service=rollout_service,
        )
    except ValueError as exc:
        evaluation.block(
            "HOSTED_READBACK_INVALID",
            "prod.hosted",
            f"canonical hosted ledger validation failed: {exc}",
        )
        return None
    receipt_id = str(rollout_receipt["receiptId"])
    if (
        ledger_receipt["receiptId"] != receipt_id
        or rollout_receipt.get("stage") != "full"
        or rollout_receipt.get("triggerStage") != "full"
        or rollout_receipt.get("decision") != "continue"
        or rollout_receipt.get("rollbackOutcome") != "not_triggered"
        or rollout_receipt.get("toCandidateDigest") != manifest["candidateId"]
        or rollout_receipt.get("lastGoodCandidateDigest") != manifest["candidateId"]
        or not _manifest_contains_receipt_id(manifest["rolloutReceipt"], receipt_id)
        or not _manifest_contains_receipt_id(manifest["rollbackReceipt"], receipt_id)
    ):
        evaluation.block(
            "HOSTED_READBACK_INVALID",
            "prod.hosted",
            "hosted readbacks do not match the released manifest outcome",
        )
        return None
    bound = _bound_stage_readback(
        artifact_root,
        manifest["rolloutReceipt"],
        receipt_id,
    )
    if (
        bound is None
        or rollout.path != bound[0]
        or rollout.digest != bound[1]
    ):
        evaluation.block(
            "HOSTED_READBACK_INVALID",
            rollout.label,
            "rollout readback bytes are not the manifest-bound full-stage readback",
        )
        return None
    for receipt, hosted in (
        (rollout, rollout_receipt),
        (rollback, ledger_receipt),
    ):
        timestamp_receipt = LoadedReceipt(
            receipt.label,
            receipt.path,
            dict(hosted),
            receipt.digest,
        )
        _timestamp(
            evaluation,
            timestamp_receipt,
            ("verifiedAt",),
            now=now,
            max_age_seconds=max_age_seconds,
        )
        evaluation.authority[receipt.label] = VerifiedAuthority(
            authority=lifecycle.HOSTED_AUTHORITY,
            subject_digest=receipt.digest,
            verification_digest=_canonical_digest(receipt.payload),
            claims=frozenset({"hosted_readback", receipt_id}),
        )
    return rollout_receipt


def verify_canonical_hosted_prod_soak(
    path: Path,
    rollout_receipt: Mapping[str, Any],
    manifest: Mapping[str, Any],
) -> VerifiedAuthority:
    """Verify exact hosted soak bytes and derive all final soak claims."""

    raw = path.read_bytes()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ValueError("hosted prod soak readback is invalid JSON") from error
    if not isinstance(payload, dict):
        raise TypeError("hosted prod soak readback must be an object")
    service = str(rollout_receipt.get("service") or "")
    receipt = lifecycle._validate_soak_readback(payload, service=service)
    receipt_id = str(receipt["receiptId"])

    root = Path(__file__).resolve().parents[3]
    sync_script = root / "quwoquan_ops/cli/prod/sync_prod_plane_stack.sh"
    with tempfile.TemporaryDirectory(prefix="qwq-prod-soak-readback-") as temporary:
        remote_path = Path(temporary) / "soak-readback.json"
        result = subprocess.run(
            [
                "bash",
                str(sync_script),
                "--plane",
                "service",
                "--operation",
                "release-ledger-soak-receipt",
                "--service",
                service,
                "--receipt-id",
                receipt_id,
                "--output-path",
                str(remote_path),
            ],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0 or not remote_path.is_file():
            raise RuntimeError(
                result.stderr.strip()
                or result.stdout.strip()
                or "canonical hosted prod soak readback failed"
            )
        remote_raw = remote_path.read_bytes()
    if remote_raw != raw:
        raise ValueError("supplied prod soak bytes differ from canonical remote readback")
    remote_payload = json.loads(remote_raw)
    remote_receipt = lifecycle._validate_soak_readback(
        remote_payload, service=service
    )
    if remote_receipt != receipt:
        raise ValueError("canonical remote prod soak receipt identity drifted")

    source = manifest.get("source")
    if not isinstance(source, Mapping):
        raise TypeError("released manifest source is missing")
    configuration_packages = manifest.get("configurationPackages")
    config_graph_digest = _canonical_digest(configuration_packages)
    expected_bindings = {
        "fullRolloutReceiptId": rollout_receipt.get("receiptId"),
        "candidateId": manifest.get("candidateId"),
        "rolloutArtifactDigest": rollout_receipt.get("artifactDigest"),
        "artifactDigest": manifest.get("artifactDigest"),
        "sourceGitSha": source.get("gitSha"),
        "sourceTreeDigest": source.get("treeDigest"),
        "rolloutConfigDigest": rollout_receipt.get("configDigest"),
        "configGraphDigest": config_graph_digest,
        "contractGraphDigest": manifest.get("contractGraphDigest"),
    }
    for field, expected in expected_bindings.items():
        if receipt.get(field) != expected:
            raise ValueError(f"hosted prod soak {field} binding drifted")

    policy_path = (
        root / "quwoquan_ops/policies/config-release/slo_thresholds.yaml"
    )
    credential_policy_path = (
        root / "quwoquan_ops/environments/prod/access-isolation.yaml"
    )
    if (
        receipt.get("soakPolicyDigest") != sha256_file(policy_path)
        or receipt.get("credentialPolicyDigest")
        != sha256_file(credential_policy_path)
    ):
        raise ValueError("hosted prod soak policy digest drifted")
    policy = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    credential_policy = yaml.safe_load(
        credential_policy_path.read_text(encoding="utf-8")
    )
    if not isinstance(policy, dict) or not isinstance(policy.get("readback"), dict):
        raise TypeError("canonical prod soak policy is invalid")
    readback_policy = policy["readback"]
    required_seconds = lifecycle._window_seconds(readback_policy.get("window"))
    maximum_age = int(readback_policy.get("authority_max_age_seconds") or 0)
    minimum_samples = int(readback_policy.get("minimum_samples") or 0)
    if (
        receipt.get("requiredSoakSeconds") != required_seconds
        or receipt.get("soakDurationSeconds", 0) < required_seconds
        or maximum_age <= 0
        or minimum_samples <= 0
    ):
        raise ValueError("hosted prod soak duration policy is not satisfied")

    started_at = datetime.fromisoformat(
        str(receipt["soakStartedAt"]).replace("Z", "+00:00")
    )
    ended_at = datetime.fromisoformat(
        str(receipt["soakEndedAt"]).replace("Z", "+00:00")
    )
    now = datetime.now(timezone.utc)
    age = (now - ended_at).total_seconds()
    if age < -MAX_FUTURE_SKEW_SECONDS or age > maximum_age:
        raise ValueError("hosted prod soak receipt is stale")
    for name in ("slo", "alerts", "health"):
        observed_at = datetime.fromisoformat(
            str(receipt[name]["observedAt"]).replace("Z", "+00:00")
        )
        if observed_at < started_at or observed_at > ended_at:
            raise ValueError(f"hosted prod soak {name} observation is out of window")

    slo = receipt["slo"]
    thresholds = policy.get("thresholds")
    if not isinstance(thresholds, Mapping):
        raise TypeError("canonical prod soak thresholds are invalid")
    threshold_bindings = {
        "errorRate": "error_rate",
        "p95Ms": "p95_ms",
        "redisErrorRate": "redis_error_rate",
    }
    if (
        slo.get("minimumSamples") != minimum_samples
        or slo.get("sampleCount", 0) < minimum_samples
        or slo.get("windowSeconds") != required_seconds
    ):
        raise ValueError("hosted prod soak SLO sample policy is not satisfied")
    for field, policy_field in threshold_bindings.items():
        policy_threshold = thresholds.get(policy_field)
        if not isinstance(policy_threshold, Mapping) or not isinstance(
            policy_threshold.get("warn"), (int, float)
        ):
            raise TypeError(f"canonical prod soak {policy_field} policy is invalid")
        if float(slo["values"][field]) >= float(policy_threshold["warn"]):
            raise ValueError(f"hosted prod soak SLO breached {policy_field}")

    if not isinstance(credential_policy, dict):
        raise TypeError("canonical prod credential policy is invalid")
    expected_credentials: set[tuple[str, str]] = set()
    for plane in credential_policy.get("planes") or []:
        if (
            not isinstance(plane, dict)
            or plane.get("access") != "read-write"
            or "full" not in (plane.get("appliesToStages") or [])
        ):
            continue
        governed = plane.get("rootlessGovernedComposeServices") or []
        support = plane.get("rootlessSupportComposeServices") or []
        if (
            "rootlessGovernedComposeServices" in plane
            or "rootlessSupportComposeServices" in plane
        ) and not (governed or support):
            continue
        expected_credentials.add(
            (str(plane.get("plane") or ""), str(plane.get("account") or ""))
        )
    actual_credentials = {
        (str(item["plane"]), str(item["account"]))
        for item in receipt["credentials"]
    }
    if actual_credentials != expected_credentials:
        raise ValueError("hosted prod soak credentials do not cover canonical planes")
    for credential in receipt["credentials"]:
        expires_at = datetime.fromisoformat(
            str(credential["expiresAt"]).replace("Z", "+00:00")
        )
        verified_at = datetime.fromisoformat(
            str(credential["verifiedAt"]).replace("Z", "+00:00")
        )
        if expires_at <= now or verified_at < started_at or verified_at > ended_at:
            raise ValueError("hosted prod credential is expired or out of soak window")

    approval = receipt["approval"]
    if (
        approval.get("kind") != "github-reviewed-mainline"
        or approval.get("sourceGitSha") != source.get("gitSha")
        or approval.get("artifactDigest") != manifest.get("artifactDigest")
        or int(approval.get("distinctPrincipals") or 0) < 2
        or not approval.get("approvers")
    ):
        raise ValueError("hosted prod approval is not canonical or candidate-bound")
    return VerifiedAuthority(
        authority=lifecycle.HOSTED_AUTHORITY,
        subject_digest=_sha256(raw),
        verification_digest=_canonical_digest(
            {
                "receiptId": receipt_id,
                "remoteBytesDigest": _sha256(remote_raw),
                "bindings": expected_bindings,
                "soakStartedAt": receipt["soakStartedAt"],
                "soakEndedAt": receipt["soakEndedAt"],
            }
        ),
        claims=REQUIRED_SOAK_CLAIMS,
    )


def _validate_soak_authority(
    evaluation: _Evaluation,
    *,
    soak: LoadedReceipt | None,
    rollout_receipt: Mapping[str, Any] | None,
    manifest: Mapping[str, Any] | None,
    verifier: SoakAuthorityVerifier,
) -> None:
    if soak is None or rollout_receipt is None or manifest is None:
        return
    try:
        verified = verifier(soak.path, rollout_receipt, manifest)
    except (
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
        subprocess.SubprocessError,
    ) as exc:
        evaluation.block(
            "UNVERIFIABLE_AUTHORITY",
            soak.label,
            f"hosted soak authority verification failed: {exc}",
        )
        return
    if (
        verified.authority != lifecycle.HOSTED_AUTHORITY
        or verified.subject_digest != soak.digest
        or DIGEST_PATTERN.fullmatch(verified.verification_digest) is None
        or not REQUIRED_SOAK_CLAIMS.issubset(verified.claims)
    ):
        evaluation.block(
            "UNVERIFIABLE_AUTHORITY",
            soak.label,
            "soak verifier lacks exact bytes, freshness, credentials, approval, or soak claims",
        )
        return
    evaluation.authority[soak.label] = verified


def _descriptor(
    receipt: LoadedReceipt | None,
    evaluation: _Evaluation,
    *,
    role: str = "promotion",
) -> dict[str, Any] | None:
    if receipt is None:
        return None
    authority = evaluation.authority.get(receipt.label)
    return {
        "schema": str(receipt.payload.get("schema") or ""),
        "path": receipt.path.as_posix(),
        "digest": receipt.digest,
        "observedAt": evaluation.observed_at.get(receipt.label, ""),
        "role": role,
        "authority": (
            {
                "kind": authority.authority,
                "verificationDigest": authority.verification_digest,
                "claims": sorted(authority.claims),
            }
            if authority is not None
            else None
        ),
    }


def _input_projection(
    loaded: Mapping[str, LoadedReceipt | None],
    evaluation: _Evaluation,
) -> dict[str, Any]:
    return {
        "pilot": {
            "release": _descriptor(loaded["pilot.release"], evaluation),
            "rollback": _descriptor(loaded["pilot.rollback"], evaluation),
        },
        "contentLifecycle": {
            environment: _descriptor(loaded[f"content.{environment}"], evaluation)
            for environment in ENVIRONMENTS
        },
        "localEnvGreenMatrix": _descriptor(
            loaded["local_env.green_matrix"],
            evaluation,
            role="supporting",
        ),
        "recoveryUat": {
            platform: _descriptor(loaded[f"recovery.{platform}"], evaluation)
            for platform in ("ios", "android")
        },
        "nightlyArtifact": _descriptor(loaded["nightly"], evaluation),
        "prodSim": _descriptor(
            loaded["prod_sim"],
            evaluation,
            role="diagnostic_only",
        ),
        "prodHosted": {
            "rolloutReadback": _descriptor(
                loaded["prod.rollout_readback"],
                evaluation,
            ),
            "rollbackReadback": _descriptor(
                loaded["prod.rollback_readback"],
                evaluation,
            ),
            "soakReadback": _descriptor(
                loaded["prod.soak_readback"],
                evaluation,
            ),
        },
    }


def evaluate_final_acceptance(
    inputs: FinalAcceptanceInputs,
    *,
    max_age_seconds: int = 86_400,
    now: datetime | None = None,
    artifact_closure_verifier: ArtifactClosureVerifier = validate_manifest_files,
    provider_readiness_verifier: ProviderReadinessVerifier = (
        verify_canonical_provider_readiness
    ),
    attestation_verifier: AttestationVerifier = verify_github_actions_receipt,
    soak_authority_verifier: SoakAuthorityVerifier = verify_canonical_hosted_prod_soak,
) -> dict[str, Any]:
    """Validate authority-backed receipts and calculate one terminal verdict."""

    if max_age_seconds <= 0:
        raise ValueError("max_age_seconds must be positive")
    current_time = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    evaluation = _Evaluation()
    artifact_root = _resolve_artifact_root(evaluation, inputs.artifact_root)
    loaded = {
        label: _load_receipt(evaluation, label=label, path=path)
        for label, path in inputs.receipt_paths().items()
    }

    seen_paths: dict[Path, str] = {}
    for label, receipt in loaded.items():
        if receipt is None:
            continue
        previous = seen_paths.get(receipt.path)
        if previous is not None and {
            previous,
            label,
        } != {"prod.rollout_readback", "prod.rollback_readback"}:
            evaluation.block(
                "DIGEST_MISMATCH",
                label,
                f"one file cannot satisfy both {previous} and {label}",
            )
        seen_paths[receipt.path] = label
        if label != "candidate":
            _reject_self_asserted_authority(
                evaluation,
                receipt,
                allow_prod_sim_non_promotable=label == "prod_sim",
            )

    manifest, closure = _artifact_closure(
        evaluation,
        artifact_root=artifact_root,
        manifest_receipt=loaded["candidate"],
        verifier=artifact_closure_verifier,
        provider_verifier=provider_readiness_verifier,
        now=current_time,
        max_age_seconds=max_age_seconds,
    )
    pilot = _pilot_identity(
        evaluation,
        loaded["pilot.release"],
        loaded["pilot.rollback"],
        now=current_time,
        max_age_seconds=max_age_seconds,
    )
    for environment in ENVIRONMENTS:
        _validate_content_lifecycle(
            evaluation,
            loaded[f"content.{environment}"],
            environment=environment,
            pilot=pilot,
            now=current_time,
            max_age_seconds=max_age_seconds,
        )
    _validate_green_matrix(
        evaluation,
        loaded["local_env.green_matrix"],
        pilot=pilot,
        now=current_time,
        max_age_seconds=max_age_seconds,
    )
    _validate_manifest_bound_acceptance_inputs(
        evaluation,
        artifact_root=artifact_root,
        manifest=manifest,
        loaded=loaded,
    )
    for kind in ("recovery.ios", "recovery.android", "nightly"):
        _validate_ci_evidence(
            evaluation,
            loaded[kind],
            kind=kind,
            manifest=manifest,
            pilot=pilot,
            now=current_time,
            max_age_seconds=max_age_seconds,
        )
        _verify_authority(
            evaluation,
            loaded[kind],
            manifest=manifest,
            verifier=attestation_verifier,
        )
    _validate_prod_sim(
        evaluation,
        loaded["prod_sim"],
        manifest=manifest,
        pilot=pilot,
        now=current_time,
        max_age_seconds=max_age_seconds,
    )
    _verify_authority(
        evaluation,
        loaded["prod_sim"],
        manifest=manifest,
        verifier=attestation_verifier,
    )
    hosted_receipt = _validate_hosted_readbacks(
        evaluation,
        rollout=loaded["prod.rollout_readback"],
        rollback=loaded["prod.rollback_readback"],
        artifact_root=artifact_root,
        manifest=manifest,
        now=current_time,
        max_age_seconds=max_age_seconds,
    )
    if hosted_receipt is not None:
        deployment_artifact = hosted_receipt["artifactDigest"]
        for kind in ("recovery.ios", "recovery.android", "nightly"):
            receipt = loaded[kind]
            if (
                receipt is not None
                and receipt.payload.get("artifactDigest") != deployment_artifact
            ):
                evaluation.block(
                    "DIGEST_MISMATCH",
                    kind,
                    "signed CI evidence differs from the hosted deployment artifact",
                )
        prod_sim = loaded["prod_sim"]
        prod_sim_release = (
            prod_sim.payload.get("releaseEvidence")
            if prod_sim is not None
            else None
        )
        if prod_sim is not None and (
            not isinstance(prod_sim_release, Mapping)
            or prod_sim_release.get("artifactDigest") != deployment_artifact
        ):
            evaluation.block(
                "DIGEST_MISMATCH",
                "prod_sim",
                "signed prod-sim evidence differs from the hosted deployment artifact",
            )
    _validate_soak_authority(
        evaluation,
        soak=loaded["prod.soak_readback"],
        rollout_receipt=hosted_receipt,
        manifest=manifest,
        verifier=soak_authority_verifier,
    )

    blockers = sorted(
        evaluation.blockers,
        key=lambda item: (item["input"], item["code"], item["message"]),
    )
    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "generatedAt": current_time.isoformat().replace("+00:00", "Z"),
        "verdict": BLOCKED_VERDICT if blockers else PROMOTABLE_VERDICT,
        "artifactClosure": closure,
        "pilot": pilot,
        "inputs": _input_projection(loaded, evaluation),
        "blockers": blockers,
    }
    payload["receiptDigest"] = _canonical_digest(payload)
    return payload


def write_final_acceptance(path: Path, payload: dict[str, Any]) -> None:
    """Atomically write the final typed receipt without following symlinks."""

    output = path.expanduser()
    if output.is_symlink():
        raise ValueError("final acceptance output must not be a symlink")
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary_name = ""
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=output.parent,
            prefix=f".{output.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_name = temporary.name
            json.dump(payload, temporary, ensure_ascii=False, indent=2, sort_keys=True)
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, output)
    finally:
        if temporary_name:
            Path(temporary_name).unlink(missing_ok=True)
