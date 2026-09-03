#!/usr/bin/env python3
"""Observe-only hosted authority integration smoke; performs no governed mutation."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

sys.dont_write_bytecode = True
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "quwoquan_ops/cli"))
sys.path.insert(0, str(REPO_ROOT))

from lib.agent_governance_contract import validate_feature_context_manifest  # noqa: E402
from lib.evidence_fingerprint import canonical_digest  # noqa: E402
from lib.feature_context_fingerprint import (  # noqa: E402
    validate_content_addressed_ref,
    validate_current_feature_context_fingerprint,
)
from lib.hosted_authority import (  # noqa: E402
    EnvironmentTokenProvider,
    HostedAuthorityError,
    HostedAuthorityHttpClient,
    runtime_from_env,
)
from lib.human_agent_delivery.contract import closed_values  # noqa: E402
from lib.objective_execution.hosted_provider import (  # noqa: E402
    HostedAuthorityProvider,
    HostedAuthorityVerifier,
    ObserveOnlyEffectAdapter,
)
from lib.readiness_case_result import (  # noqa: E402
    ReadinessCaseResultError,
    validate_readiness_result_bundle,
)

OWNER_MANIFEST_ROOT = Path(".qwq_output/env/repo/runs/feature-tree/by-fingerprint")
READINESS_BUNDLE_ROOT = Path(".qwq_output/env/repo/runs/readiness-result-bundle")
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_RAW_SHA256 = re.compile(r"^[0-9a-f]{64}$")

_SMOKE_RECOVERY = {
    "HOSTED_AUTHORITY.SMOKE_UNSAFE_PATH":
        "replace_with_regular_single_link_file_under_canonical_repo_root",
    "HOSTED_AUTHORITY.SMOKE_STALE_INPUT":
        "regenerate_current_owner_manifest_and_readiness_bundle",
    "HOSTED_AUTHORITY.SMOKE_SCHEMA_INVALID":
        "regenerate_inputs_from_canonical_owner_and_readiness_producers",
    "HOSTED_AUTHORITY.SMOKE_READINESS_NOT_QUALIFYING":
        "produce_nonempty_all_passed_readiness_for_the_expected_candidate",
    "HOSTED_AUTHORITY.SMOKE_AUTHORITY_UNAVAILABLE":
        "restore_authenticated_hosted_authority_provider_then_retry_readback",
    "HOSTED_AUTHORITY.SMOKE_READBACK_FAILED":
        "repair_exact_authority_readback_then_rerun_without_mutation",
    "HOSTED_AUTHORITY.SMOKE_AUTHORITY_INVALID":
        "obtain_new_available_authority_for_the_exact_expected_inputs",
}


class SmokeFailure(ValueError):
    """One fail-closed smoke terminal with exactly one recovery."""

    def __init__(self, code: str, detail: str) -> None:
        if code not in _SMOKE_RECOVERY:
            raise ValueError(f"unknown smoke terminal code: {code}")
        super().__init__(detail)
        self.code = code
        self.detail = detail

    def as_dict(self) -> dict[str, object]:
        return {
            "result": "typed_blocker",
            "code": self.code,
            "terminal": "blocked",
            "retry_allowed": False,
            "recovery": _SMOKE_RECOVERY[self.code],
            "detail": _safe_detail(self.detail),
        }


def _safe_detail(value: object) -> str:
    return " ".join(str(value).replace("\x00", "\\x00").split())


def _block(code: str, detail: object) -> SmokeFailure:
    return SmokeFailure(code, _safe_detail(detail))


def _sha256(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _normalize_canonical_input_path(
    raw_path: Path,
    *,
    allowed_root: Path,
    label: str,
    repo_root: Path | None = None,
) -> tuple[Path, str]:
    repository = Path(os.path.abspath(repo_root or REPO_ROOT))
    candidate = raw_path if raw_path.is_absolute() else repository / raw_path
    lexical_path = Path(os.path.abspath(candidate))
    try:
        relative = lexical_path.relative_to(repository)
        relative.relative_to(allowed_root)
    except ValueError as error:
        raise _block(
            "HOSTED_AUTHORITY.SMOKE_UNSAFE_PATH",
            f"{label} must stay under canonical repository root {allowed_root.as_posix()}",
        ) from error
    if relative == allowed_root:
        raise _block(
            "HOSTED_AUTHORITY.SMOKE_UNSAFE_PATH", f"{label} must name one file"
        )
    return lexical_path, relative.as_posix()


def _normalize_owner_manifest_path(
    raw_path: Path, *, repo_root: Path | None = None
) -> tuple[Path, str]:
    return _normalize_canonical_input_path(
        raw_path,
        allowed_root=OWNER_MANIFEST_ROOT,
        label="owner manifest",
        repo_root=repo_root,
    )


def _read_canonical_repo_ref(
    relative_ref: str,
    *,
    allowed_root: Path,
    label: str,
    repo_root: Path | None = None,
) -> bytes:
    repository = Path(os.path.abspath(repo_root or REPO_ROOT))
    relative = Path(relative_ref)
    if (
        relative.is_absolute()
        or relative.as_posix() != relative_ref
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise _block(
            "HOSTED_AUTHORITY.SMOKE_UNSAFE_PATH",
            f"{label} ref must be canonical repository-relative path",
        )
    try:
        inside = relative.relative_to(allowed_root)
    except ValueError as error:
        raise _block(
            "HOSTED_AUTHORITY.SMOKE_UNSAFE_PATH",
            f"{label} ref is outside canonical allowed root",
        ) from error
    if not inside.parts:
        raise _block(
            "HOSTED_AUTHORITY.SMOKE_UNSAFE_PATH", f"{label} ref must name one file"
        )
    directory_only = getattr(os, "O_DIRECTORY", None)
    nofollow = getattr(os, "O_NOFOLLOW", None)
    if directory_only is None or nofollow is None:
        raise _block(
            "HOSTED_AUTHORITY.SMOKE_UNSAFE_PATH",
            f"{label} verification requires O_DIRECTORY and O_NOFOLLOW",
        )
    close_on_exec = getattr(os, "O_CLOEXEC", 0)
    directory_flags = os.O_RDONLY | directory_only | nofollow | close_on_exec
    file_flags = os.O_RDONLY | nofollow | close_on_exec | getattr(os, "O_NONBLOCK", 0)
    descriptors: list[int] = []
    try:
        parent_fd = os.open(repository, directory_flags)
        descriptors.append(parent_fd)
        for component in (*allowed_root.parts, *inside.parts[:-1]):
            parent_fd = os.open(component, directory_flags, dir_fd=parent_fd)
            descriptors.append(parent_fd)
            if not stat.S_ISDIR(os.fstat(parent_fd).st_mode):
                raise OSError(f"{component} is not a directory")
        filename = inside.parts[-1]
        file_fd = os.open(filename, file_flags, dir_fd=parent_fd)
        descriptors.append(file_fd)
        before = os.fstat(file_fd)
        directory_identities = [
            (os.fstat(descriptor).st_dev, os.fstat(descriptor).st_ino)
            for descriptor in descriptors[:-1]
        ]
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise _block(
                "HOSTED_AUTHORITY.SMOKE_UNSAFE_PATH",
                f"{label} must be one regular single-link file",
            )
        chunks: list[bytes] = []
        while True:
            chunk = os.read(file_fd, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        payload = b"".join(chunks)
        after = os.fstat(file_fd)
        named = os.stat(filename, dir_fd=parent_fd, follow_symlinks=False)
        stable_fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        if (
            any(getattr(before, field) != getattr(after, field) for field in stable_fields)
            or any(getattr(after, field) != getattr(named, field) for field in ("st_dev", "st_ino"))
            or not stat.S_ISREG(named.st_mode)
            or after.st_nlink != 1
            or named.st_nlink != 1
            or len(payload) != after.st_size
        ):
            raise _block(
                "HOSTED_AUTHORITY.SMOKE_UNSAFE_PATH",
                f"{label} changed while exact bytes were read",
            )
        rebound: list[int] = []
        try:
            rebound_parent = os.open(repository, directory_flags)
            rebound.append(rebound_parent)
            rebound_metadata = os.fstat(rebound_parent)
            if (rebound_metadata.st_dev, rebound_metadata.st_ino) != directory_identities[0]:
                raise OSError("repository root identity changed")
            for index, component in enumerate(
                (*allowed_root.parts, *inside.parts[:-1]), start=1
            ):
                rebound_parent = os.open(
                    component, directory_flags, dir_fd=rebound_parent
                )
                rebound.append(rebound_parent)
                rebound_metadata = os.fstat(rebound_parent)
                if (
                    rebound_metadata.st_dev,
                    rebound_metadata.st_ino,
                ) != directory_identities[index]:
                    raise OSError(f"ancestor identity changed: {component}")
            rebound_file = os.open(filename, file_flags, dir_fd=rebound_parent)
            rebound.append(rebound_file)
            rebound_metadata = os.fstat(rebound_file)
            if (
                rebound_metadata.st_dev != after.st_dev
                or rebound_metadata.st_ino != after.st_ino
                or not stat.S_ISREG(rebound_metadata.st_mode)
                or rebound_metadata.st_nlink != 1
            ):
                raise OSError("final file identity changed")
        except OSError as error:
            raise _block(
                "HOSTED_AUTHORITY.SMOKE_UNSAFE_PATH",
                f"{label} canonical path identity changed during read: {error}",
            ) from error
        finally:
            for descriptor in reversed(rebound):
                try:
                    os.close(descriptor)
                except OSError:
                    pass
        return payload
    except SmokeFailure:
        raise
    except OSError as error:
        raise _block(
            "HOSTED_AUTHORITY.SMOKE_UNSAFE_PATH",
            f"{label} descriptor-relative no-follow read failed: {error}",
        ) from error
    finally:
        for descriptor in reversed(descriptors):
            try:
                os.close(descriptor)
            except OSError:
                pass


def _read_canonical_input(
    raw_path: Path, *, allowed_root: Path, label: str
) -> tuple[str, bytes]:
    _path, relative_ref = _normalize_canonical_input_path(
        raw_path, allowed_root=allowed_root, label=label
    )
    return relative_ref, _read_canonical_repo_ref(
        relative_ref, allowed_root=allowed_root, label=label
    )


def _json_bytes(raw: bytes, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise _block(
            "HOSTED_AUTHORITY.SMOKE_SCHEMA_INVALID",
            f"{label} must be valid UTF-8 JSON: {error}",
        ) from error
    if not isinstance(value, dict):
        raise _block(
            "HOSTED_AUTHORITY.SMOKE_SCHEMA_INVALID", f"{label} must be a JSON object"
        )
    return value


def _verify_owner_manifest_descriptor(
    *, filename: str, owner_manifest_bytes: bytes
) -> None:
    relative_ref = (OWNER_MANIFEST_ROOT / filename).as_posix()
    current = _read_canonical_repo_ref(
        relative_ref, allowed_root=OWNER_MANIFEST_ROOT, label="owner manifest"
    )
    if current != owner_manifest_bytes:
        raise _block(
            "HOSTED_AUTHORITY.SMOKE_STALE_INPUT",
            "owner manifest exact bytes changed after input binding",
        )


def _verify_owner_manifest(
    *, owner_manifest_ref: str, owner_manifest_bytes: bytes
) -> tuple[dict[str, Any], dict[str, Any], str]:
    exact_digest = _sha256(owner_manifest_bytes)
    expected_name = exact_digest.removeprefix("sha256:") + ".json"
    expected_ref = (OWNER_MANIFEST_ROOT / expected_name).as_posix()
    canonical_prefix = OWNER_MANIFEST_ROOT.as_posix() + "/"
    lexical_digest = owner_manifest_ref.removeprefix(canonical_prefix).removesuffix(".json")
    if (
        not owner_manifest_ref.startswith(canonical_prefix)
        or not owner_manifest_ref.endswith(".json")
        or _RAW_SHA256.fullmatch(lexical_digest) is None
    ):
        raise _block(
            "HOSTED_AUTHORITY.SMOKE_UNSAFE_PATH",
            "owner manifest ref must be one canonical repository-relative rawsha path",
        )
    if owner_manifest_ref != expected_ref:
        raise _block(
            "HOSTED_AUTHORITY.SMOKE_STALE_INPUT",
            "owner manifest ref filename does not match its exact raw bytes sha256",
        )
    try:
        validated_ref = validate_content_addressed_ref(
            owner_manifest_ref, raw_bytes=owner_manifest_bytes, repo_root=REPO_ROOT
        )
    except ValueError as error:
        raise _block(
            "HOSTED_AUTHORITY.SMOKE_SCHEMA_INVALID", error
        ) from error
    if validated_ref != owner_manifest_ref:
        raise _block(
            "HOSTED_AUTHORITY.SMOKE_UNSAFE_PATH",
            "owner manifest ref normalized away from its exact lexical identity",
        )
    _verify_owner_manifest_descriptor(
        filename=expected_name, owner_manifest_bytes=owner_manifest_bytes
    )
    manifest = _json_bytes(owner_manifest_bytes, label="owner manifest")
    try:
        validate_feature_context_manifest(manifest)
        fingerprint = validate_current_feature_context_fingerprint(
            manifest, repo_root=REPO_ROOT
        )
    except ValueError as error:
        code = (
            "HOSTED_AUTHORITY.SMOKE_STALE_INPUT"
            if "stale" in str(error).lower()
            else "HOSTED_AUTHORITY.SMOKE_SCHEMA_INVALID"
        )
        raise _block(code, error) from error
    return manifest, fingerprint, exact_digest


def _verify_readiness_descriptor(
    *, readiness_bundle_ref: str, readiness_bundle_bytes: bytes
) -> None:
    current = _read_canonical_repo_ref(
        readiness_bundle_ref,
        allowed_root=READINESS_BUNDLE_ROOT,
        label="readiness bundle",
    )
    if current != readiness_bundle_bytes:
        raise _block(
            "HOSTED_AUTHORITY.SMOKE_STALE_INPUT",
            "readiness bundle exact bytes changed after input binding",
        )


def _fresh_readiness(
    bundle: Mapping[str, Any], *, now: datetime, max_age_seconds: int
) -> dict[str, Any]:
    if now.tzinfo is None or now.utcoffset() is None:
        raise _block(
            "HOSTED_AUTHORITY.SMOKE_SCHEMA_INVALID",
            "readiness verification clock must be timezone-aware",
        )
    try:
        validated = validate_readiness_result_bundle(bundle)
        generated = datetime.fromisoformat(
            str(validated["generatedAt"]).replace("Z", "+00:00")
        )
    except (ReadinessCaseResultError, TypeError, ValueError) as error:
        raise _block("HOSTED_AUTHORITY.SMOKE_SCHEMA_INVALID", error) from error
    if generated.tzinfo is None or generated.astimezone(timezone.utc) > now:
        raise _block(
            "HOSTED_AUTHORITY.SMOKE_STALE_INPUT", "readiness generatedAt is invalid"
        )
    age = (now - generated.astimezone(timezone.utc)).total_seconds()
    if age > max_age_seconds:
        raise _block("HOSTED_AUTHORITY.SMOKE_STALE_INPUT", "readiness is stale")
    return validated


def _readiness_identity(
    readiness: Mapping[str, Any],
    *,
    expected_scope: Mapping[str, str],
    expected_environment: str,
    expected_manifest_sha256: str,
) -> dict[str, str]:
    results = readiness["results"]
    if not results or any(result.get("status") != "passed" for result in results):
        raise _block(
            "HOSTED_AUTHORITY.SMOKE_READINESS_NOT_QUALIFYING",
            "readiness must contain a nonempty all-passed qualifying result set",
        )
    tuples = {
        (
            result.get("candidateDigest"),
            result.get("environment"),
            result.get("candidateManifestSha256"),
        )
        for result in results
    }
    if len(tuples) != 1:
        raise _block(
            "HOSTED_AUTHORITY.SMOKE_READINESS_NOT_QUALIFYING",
            "qualifying readiness results do not share one candidate/environment/manifest",
        )
    candidate, environment, manifest_sha256 = next(iter(tuples))
    if not isinstance(candidate, str) or _DIGEST.fullmatch(candidate) is None:
        raise _block(
            "HOSTED_AUTHORITY.SMOKE_READINESS_NOT_QUALIFYING",
            "qualifying readiness candidateDigest is missing or invalid",
        )
    if (
        len(expected_scope) != 1
        or next(iter(expected_scope)) not in {"objective", "increment"}
        or next(iter(expected_scope.values())) != candidate
        or environment != expected_environment
        or manifest_sha256 != expected_manifest_sha256
    ):
        raise _block(
            "HOSTED_AUTHORITY.SMOKE_READINESS_NOT_QUALIFYING",
            "readiness candidate/environment/manifest does not equal the expected identity",
        )
    return {
        "candidate_digest": candidate,
        "environment": str(environment),
        "manifest_sha256": str(manifest_sha256),
    }


def _verify_authority_bindings(
    claims: Mapping[str, Any],
    *,
    expected_fingerprint: str,
    expected_scope: Mapping[str, str],
    expected_decision_kind: str,
    action: str,
    now: datetime,
) -> None:
    try:
        expires_at = datetime.fromisoformat(
            str(claims["expires_at"]).replace("Z", "+00:00")
        )
    except (KeyError, TypeError, ValueError) as error:
        raise _block(
            "HOSTED_AUTHORITY.SMOKE_AUTHORITY_INVALID",
            "authority expiry is missing or invalid",
        ) from error
    if expires_at.tzinfo is None or expires_at.astimezone(timezone.utc) <= now:
        raise _block(
            "HOSTED_AUTHORITY.SMOKE_AUTHORITY_INVALID", "authority receipt is expired"
        )
    if claims.get("evidence_fingerprint") != expected_fingerprint:
        raise _block(
            "HOSTED_AUTHORITY.SMOKE_AUTHORITY_INVALID",
            "authority evidence fingerprint does not match owner manifest",
        )
    if claims.get("scope") != dict(expected_scope):
        raise _block(
            "HOSTED_AUTHORITY.SMOKE_AUTHORITY_INVALID", "authority scope mismatch"
        )
    if (
        expected_decision_kind not in closed_values("decision_kind")
        or claims.get("decision_kind") != expected_decision_kind
    ):
        raise _block(
            "HOSTED_AUTHORITY.SMOKE_AUTHORITY_INVALID",
            "authority DecisionKind mismatch",
        )
    if claims.get("actions") != [action]:
        raise _block(
            "HOSTED_AUTHORITY.SMOKE_AUTHORITY_INVALID", "authority action mismatch"
        )
    if claims.get("receipt_state") != "available":
        raise _block(
            "HOSTED_AUTHORITY.SMOKE_AUTHORITY_INVALID",
            "authority receipt is consumed, revoked, or otherwise unavailable",
        )


def run_observe_only_smoke(
    *,
    owner_manifest_ref: str,
    owner_manifest_bytes: bytes,
    readiness_bundle_ref: str,
    readiness_bundle_bytes: bytes,
    receipt_ref: str,
    client: HostedAuthorityHttpClient,
    trusted_public_keys: Mapping[str, bytes],
    expected_scope: Mapping[str, str],
    expected_environment: str,
    expected_manifest_sha256: str,
    expected_decision_kind: str,
    action: str,
    now: datetime | None = None,
    readiness_max_age_seconds: int = 300,
) -> dict[str, Any]:
    """Verify exact owner/readiness/authority inputs without governed mutation."""
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None or current.utcoffset() is None:
        raise _block(
            "HOSTED_AUTHORITY.SMOKE_SCHEMA_INVALID", "smoke clock must be timezone-aware"
        )
    manifest, manifest_fingerprint, manifest_digest = _verify_owner_manifest(
        owner_manifest_ref=owner_manifest_ref,
        owner_manifest_bytes=owner_manifest_bytes,
    )
    _verify_readiness_descriptor(
        readiness_bundle_ref=readiness_bundle_ref,
        readiness_bundle_bytes=readiness_bundle_bytes,
    )
    readiness = _fresh_readiness(
        _json_bytes(readiness_bundle_bytes, label="readiness bundle"),
        now=current,
        max_age_seconds=readiness_max_age_seconds,
    )
    readiness_identity = _readiness_identity(
        readiness,
        expected_scope=expected_scope,
        expected_environment=expected_environment,
        expected_manifest_sha256=expected_manifest_sha256,
    )
    readiness_digest = _sha256(readiness_bundle_bytes)

    provider = HostedAuthorityProvider(client)
    readback = provider.readback(receipt_ref)
    if readback.status == "failed":
        raise _block(
            "HOSTED_AUTHORITY.SMOKE_AUTHORITY_UNAVAILABLE",
            readback.detail or "hosted authority query failed",
        )
    if (
        readback.status != "present"
        or readback.exact_bytes is None
        or readback.provider_receipt_ref is None
    ):
        raise _block(
            "HOSTED_AUTHORITY.SMOKE_READBACK_FAILED",
            readback.detail or f"authority readback status={readback.status}",
        )
    try:
        claims = HostedAuthorityVerifier(provider, trusted_public_keys).verify(
            readback.exact_bytes,
            readback.provider_receipt_ref,
        )
    except ValueError as error:
        raise _block("HOSTED_AUTHORITY.SMOKE_READBACK_FAILED", error) from error
    _verify_authority_bindings(
        claims,
        expected_fingerprint=str(manifest_fingerprint["digest"]),
        expected_scope=expected_scope,
        expected_decision_kind=expected_decision_kind,
        action=action,
        now=current.astimezone(timezone.utc),
    )
    authority_digest = _sha256(readback.exact_bytes)
    identity_inputs = {
        "schema_id": "hosted-authority-observe-only-smoke-input",
        "schema_version": 1,
        "owner_manifest": {
            "exact_ref": owner_manifest_ref,
            "exact_bytes_sha256": manifest_digest,
            "evidence_fingerprint": manifest_fingerprint["digest"],
        },
        "readiness": {
            "exact_ref": readiness_bundle_ref,
            "exact_bytes_sha256": readiness_digest,
            **readiness_identity,
        },
        "authority": {
            "exact_ref": readback.provider_receipt_ref,
            "exact_bytes_sha256": authority_digest,
        },
        "expected": {
            "scope": dict(expected_scope),
            "decision_kind": expected_decision_kind,
            "action": action,
        },
    }
    observation_identity = canonical_digest(identity_inputs)
    stable_id = observation_identity.removeprefix("sha256:")
    effect_id = "observe:smoke:" + stable_id
    idempotency_key = "smoke:" + stable_id
    effect = ObserveOnlyEffectAdapter()
    effect.invoke(
        action=action,
        effect_id=effect_id,
        idempotency_key=idempotency_key,
        payload={"environment": expected_environment, "mutation": False},
    )
    effect_readback = dict(
        effect.readback(effect_id=effect_id, idempotency_key=idempotency_key)
    )
    if (
        effect_readback["status"] != "applied"
        or effect_readback["exact_match"] is not True
    ):
        raise _block(
            "HOSTED_AUTHORITY.SMOKE_READBACK_FAILED",
            "observe effect readback is unknown",
        )
    return {
        "result": "observed",
        "owner_manifest_ref": owner_manifest_ref,
        "owner_manifest_digest": manifest_digest,
        "owner_manifest_fingerprint": manifest_fingerprint["digest"],
        "owner": manifest["resolved_owner"],
        "readiness_bundle_ref": readiness_bundle_ref,
        "readiness_bundle_digest": readiness_digest,
        "readiness_result_count": len(readiness["results"]),
        "readiness_candidate_digest": readiness_identity["candidate_digest"],
        "readiness_environment": readiness_identity["environment"],
        "readiness_manifest_sha256": readiness_identity["manifest_sha256"],
        "provider_kind": provider.provider_kind,
        "provider_receipt_ref": readback.provider_receipt_ref,
        "authority_readback_digest": authority_digest,
        "authority_receipt_id": claims.get("receipt_id"),
        "observation_identity": observation_identity,
        "signature_verified": True,
        "release_evidence_eligible": provider.release_evidence_eligible,
        "objective_effect": "observe-only-test",
        "mutation_performed": False,
        "review_consumer_available": (
            REPO_ROOT / "quwoquan_ops/cli/review_consolidator.py"
        ).is_file(),
        "handoff_consumer_available": (
            REPO_ROOT / "quwoquan_ops/cli/handoff_consumer.py"
        ).is_file(),
        "claim_limit": "does_not_prove_real_authority_or_governed_effect_completion",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner-manifest", required=True, type=Path)
    parser.add_argument("--readiness-bundle", required=True, type=Path)
    parser.add_argument("--authority-receipt-ref", required=True)
    parser.add_argument(
        "--expected-scope-kind", required=True, choices=("objective", "increment")
    )
    parser.add_argument("--expected-scope-id", required=True)
    parser.add_argument(
        "--expected-environment", required=True, choices=("alpha", "beta", "gamma", "prod")
    )
    parser.add_argument("--expected-manifest-sha256", required=True)
    parser.add_argument("--expected-decision-kind", required=True)
    parser.add_argument("--action", required=True)
    parser.add_argument("--readiness-max-age-seconds", type=int, default=300)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        owner_manifest_ref, owner_manifest_bytes = _read_canonical_input(
            args.owner_manifest,
            allowed_root=OWNER_MANIFEST_ROOT,
            label="owner manifest",
        )
        readiness_bundle_ref, readiness_bundle_bytes = _read_canonical_input(
            args.readiness_bundle,
            allowed_root=READINESS_BUNDLE_ROOT,
            label="readiness bundle",
        )
        if _RAW_SHA256.fullmatch(args.expected_manifest_sha256) is None:
            raise _block(
                "HOSTED_AUTHORITY.SMOKE_SCHEMA_INVALID",
                "expected manifest sha256 must be 64 lowercase hex",
            )
        runtime = runtime_from_env(
            REPO_ROOT, token_provider=EnvironmentTokenProvider()
        )
        result = run_observe_only_smoke(
            owner_manifest_ref=owner_manifest_ref,
            owner_manifest_bytes=owner_manifest_bytes,
            readiness_bundle_ref=readiness_bundle_ref,
            readiness_bundle_bytes=readiness_bundle_bytes,
            receipt_ref=args.authority_receipt_ref,
            client=HostedAuthorityHttpClient(
                runtime.config, token_provider=runtime.token_provider
            ),
            trusted_public_keys=runtime.trusted_public_keys,
            expected_scope={args.expected_scope_kind: args.expected_scope_id},
            expected_environment=args.expected_environment,
            expected_manifest_sha256=args.expected_manifest_sha256,
            expected_decision_kind=args.expected_decision_kind,
            action=args.action,
            readiness_max_age_seconds=args.readiness_max_age_seconds,
        )
    except SmokeFailure as error:
        result = error.as_dict()
    except HostedAuthorityError as error:
        result = SmokeFailure(
            "HOSTED_AUTHORITY.SMOKE_AUTHORITY_UNAVAILABLE", error.detail
        ).as_dict()
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as error:
        result = SmokeFailure(
            "HOSTED_AUTHORITY.SMOKE_SCHEMA_INVALID", str(error)
        ).as_dict()
    json.dump(
        result,
        sys.stdout,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    sys.stdout.write("\n")
    return 0 if result.get("result") == "observed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
