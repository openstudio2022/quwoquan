"""Read-only fail-closed proof for the M1000 four-environment exit.

Callers select every exact-byte fact.  The evaluator performs no latest
selection, content production, environment action, plan write, or business
state mutation.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

from content.release.canonical.release_uat_sample_plan import canonical_digest
from core.schema import assert_valid
from governance.coverage.distribution import load_content_distribution_policy
from quwoquan_ops.cli.lib.environment_acceptance_fact import (
    EnvironmentAcceptanceFactError,
    validate_environment_acceptance_fact,
)

SCHEMA = "quwoquan_data.m1000_four_environment_proof_result"
REQUEST_SCHEMA = "quwoquan_data.m1000_four_environment_proof_request"
ENVIRONMENTS = ("alpha", "beta", "gamma", "prod")
PREDECESSOR = {"alpha": None, "beta": "alpha", "gamma": "beta", "prod": "gamma"}
CARRIERS = ("homepage", "article", "image", "video")
RESPONSIBILITY_ROLES = (
    "product_owner",
    "data_content_operations_owner",
    "quality_user_representative",
    "environment_reliability_owner",
    "release_owner",
)
_DIGEST_RE = re.compile(r"^sha256:[a-f0-9]{64}$")
_EXACT_REF_KEYS = frozenset({"ref", "digest"})
_REQUIRED_GATES = (
    "environment_acceptance",
    "capacity_timeliness",
    "fault_recovery",
    "rollback_replay",
    "responsibility_acceptance",
)


class M1000FourEnvironmentProofError(ValueError):
    """Selected evidence cannot establish this exit."""


def exact_byte_digest(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _text(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise M1000FourEnvironmentProofError(f"{label} must be a canonical non-empty string")
    return value


def _digest(value: object, *, label: str) -> str:
    result = _text(value, label=label)
    if _DIGEST_RE.fullmatch(result) is None:
        raise M1000FourEnvironmentProofError(f"{label} must be sha256:<64 lowercase hex>")
    return result


def _safe_root(root: Path) -> Path:
    candidate = Path(root).expanduser()
    try:
        if candidate.is_symlink():
            raise OSError("symlink root")
        result = candidate.resolve(strict=True)
        metadata = result.stat()
    except OSError as exc:
        raise M1000FourEnvironmentProofError("artifact root is unavailable or linked") from exc
    if not stat.S_ISDIR(metadata.st_mode):
        raise M1000FourEnvironmentProofError("artifact root must be a directory")
    return result


def _contained_path(root: Path, ref: str) -> Path:
    relative = PurePosixPath(_text(ref, label="ref"))
    if relative.is_absolute() or not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
        raise M1000FourEnvironmentProofError(f"ref must be relative and contained: {ref!r}")
    path = root.joinpath(*relative.parts)
    try:
        current = root
        for part in relative.parts:
            current /= part
            if current.is_symlink():
                raise OSError("symlink evidence")
        path.resolve(strict=True).relative_to(root)
    except (OSError, ValueError) as exc:
        raise M1000FourEnvironmentProofError(f"ref is unavailable or escapes containment: {ref}") from exc
    return path


def _read_regular_nofollow(path: Path) -> bytes:
    try:
        before = path.lstat()
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError as exc:
        raise M1000FourEnvironmentProofError(f"ref cannot be opened safely: {path}") from exc
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or not stat.S_ISREG(opened.st_mode)
            or (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino)
        ):
            raise M1000FourEnvironmentProofError("ref must be a stable regular file")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(descriptor)
        if (
            opened.st_dev,
            opened.st_ino,
            opened.st_size,
            opened.st_mtime_ns,
            opened.st_ctime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ):
            raise M1000FourEnvironmentProofError("ref changed while being read")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _decode_json(raw: bytes, *, label: str) -> dict[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise M1000FourEnvironmentProofError(
                    f"{label} contains duplicate JSON key {key!r}"
                )
            result[key] = value
        return result

    try:
        text = raw.decode("utf-8")
        decoder = json.JSONDecoder(
            object_pairs_hook=reject_duplicates,
            parse_constant=lambda value: (_ for _ in ()).throw(
                M1000FourEnvironmentProofError(
                    f"{label} contains invalid JSON constant {value}"
                )
            ),
        )
        value, end = decoder.raw_decode(text)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise M1000FourEnvironmentProofError(f"{label} is not UTF-8 JSON") from exc
    if text[end:].strip() or not isinstance(value, dict):
        raise M1000FourEnvironmentProofError(f"{label} must contain one JSON object")
    return value


def _load_exact(root: Path, value: object, *, label: str) -> tuple[dict[str, Any], dict[str, str]]:
    if not isinstance(value, Mapping) or set(value) != _EXACT_REF_KEYS:
        raise M1000FourEnvironmentProofError(f"{label} must contain only ref and digest")
    binding = {
        "ref": _text(value.get("ref"), label=f"{label}.ref"),
        "digest": _digest(value.get("digest"), label=f"{label}.digest"),
    }
    raw = _read_regular_nofollow(_contained_path(root, binding["ref"]))
    if exact_byte_digest(raw) != binding["digest"]:
        raise M1000FourEnvironmentProofError(f"{label} exact-byte digest drifted")
    return _decode_json(raw, label=label), binding


def _carrier_counts(rows: object, *, label: str, value_field: str) -> dict[str, int]:
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)) or len(rows) != 4:
        raise M1000FourEnvironmentProofError(f"{label} must contain exactly four carrier rows")
    result: dict[str, int] = {}
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise M1000FourEnvironmentProofError(f"{label}[{index}] is invalid")
        carrier = _text(row.get("carrier"), label=f"{label}[{index}].carrier")
        value = row.get(value_field)
        if carrier not in CARRIERS or carrier in result or isinstance(value, bool) or not isinstance(value, int):
            raise M1000FourEnvironmentProofError(f"{label} carrier/value drifted")
        result[carrier] = value
    if set(result) != set(CARRIERS):
        raise M1000FourEnvironmentProofError(f"{label} carrier coverage drifted")
    return {carrier: result[carrier] for carrier in CARRIERS}


def _validate_scale(
    *, release: Mapping[str, Any], sample_plan: Mapping[str, Any], promotion: Mapping[str, Any],
    predecessor: Mapping[str, Any], sample_binding: Mapping[str, str],
    predecessor_binding: Mapping[str, str],
) -> tuple[str, str, dict[str, int], dict[str, int], dict[str, int]]:
    milestone_targets = load_content_distribution_policy().milestone_targets()
    m100_counts = milestone_targets["M100"]
    m1000_counts = milestone_targets["M1000"]
    m1000_delta = {
        carrier: m1000_counts[carrier] - m100_counts[carrier]
        for carrier in CARRIERS
    }
    release_id = _text(release.get("releaseId"), label="M1000 releaseId")
    if (
        release.get("schema") != "quwoquan_data.release"
        or release.get("releaseKind") != "content"
        or release.get("releaseClass") != "research"
        or release.get("selectionScope") != "milestone"
        or release.get("milestone") != "M1000"
        or release.get("milestoneTargets") != m1000_counts
        or release.get("samplePlanRef") != sample_binding["ref"]
        or release.get("samplePlanDigest") != sample_binding["digest"]
    ):
        raise M1000FourEnvironmentProofError("M1000 immutable release identity/targets drifted")
    if sample_plan.get("schema") != "quwoquan_data.release_uat_sample_plan" or sample_plan.get("releaseId") != release_id:
        raise M1000FourEnvironmentProofError("M1000 sample plan release identity drifted")
    if sample_plan.get("milestone") != "M1000" or sample_plan.get("exactCohortCounts") != m1000_counts:
        raise M1000FourEnvironmentProofError("M1000 exact cohort differs from the distribution policy target")
    release_digest = _digest(sample_plan.get("releaseDigest"), label="samplePlan.releaseDigest")
    if promotion.get("schema") != "quwoquan_data.research_scale_promotion" or promotion.get("targetScale") != "M1000":
        raise M1000FourEnvironmentProofError("M1000 promotion schema/scale drifted")
    if promotion.get("releaseId") != release_id:
        raise M1000FourEnvironmentProofError("M1000 promotion release identity drifted")
    predecessor_ref = promotion.get("predecessorPromotion")
    if not isinstance(predecessor_ref, Mapping):
        raise M1000FourEnvironmentProofError("M1000 promotion lacks exact M100 predecessor")
    if predecessor_ref.get("receiptRef") != predecessor_binding["ref"] or predecessor_ref.get("receiptDigest") != predecessor_binding["digest"]:
        raise M1000FourEnvironmentProofError("M1000 promotion predecessor exact bytes drifted")
    if predecessor_ref.get("targetScale") != "M100":
        raise M1000FourEnvironmentProofError("M1000 promotion predecessor targetScale drifted")
    if predecessor.get("schema") != "quwoquan_data.research_scale_promotion" or predecessor.get("targetScale") != "M100":
        raise M1000FourEnvironmentProofError("predecessor promotion must be M100")
    if predecessor_ref.get("releaseId") != predecessor.get("releaseId") or predecessor_ref.get("promotionId") != predecessor.get("promotionId"):
        raise M1000FourEnvironmentProofError("M100 predecessor identity drifted")
    predecessor_counts = _carrier_counts(
        predecessor.get("carrierCounts"), label="M100 carrierCounts", value_field="totalUniqueFinalizedCount"
    )
    if predecessor_counts != m100_counts:
        raise M1000FourEnvironmentProofError("M100 predecessor differs from the distribution policy target")
    current_counts = _carrier_counts(
        promotion.get("carrierCounts"), label="M1000 carrierCounts", value_field="totalUniqueFinalizedCount"
    )
    carried_counts = _carrier_counts(
        promotion.get("carrierCounts"), label="M1000 carried counts", value_field="predecessorCarriedCount"
    )
    delta_counts = _carrier_counts(
        promotion.get("carrierCounts"), label="M1000 delta counts", value_field="newFinalizedCount"
    )
    if current_counts != m1000_counts or carried_counts != m100_counts or delta_counts != m1000_delta:
        raise M1000FourEnvironmentProofError("M1000 cumulative, carried, or policy-derived delta counts drifted")
    for row in promotion["carrierCounts"]:
        carrier = str(row["carrier"])
        if row.get("targetCount") != m1000_counts[carrier] or row.get("selectedCount") != m1000_counts[carrier] or row.get("shortfallCount") != 0:
            raise M1000FourEnvironmentProofError("M1000 promotion target/selection/shortfall drifted")
    return release_id, release_digest, m1000_counts, m100_counts, m1000_delta


def _validate_sampling(
    *, root: Path, release_id: str, release_digest: str, sample_plan: Mapping[str, Any],
    freeze_ref: object, approval_ref: object,
) -> tuple[str, dict[str, int]]:
    freeze, freeze_binding = _load_exact(root, freeze_ref, label="sampleStrategyFreeze")
    approval, approval_binding = _load_exact(root, approval_ref, label="sampleStrategyApproval")
    if freeze.get("schema") != "quwoquan_data.m1000_app_uat_sample_freeze" or freeze.get("milestone") != "M1000":
        raise M1000FourEnvironmentProofError("M1000 sample strategy freeze schema drifted")
    if freeze.get("releaseId") != release_id or freeze.get("releaseDigest") != release_digest:
        raise M1000FourEnvironmentProofError("M1000 sample strategy freeze release identity drifted")
    if freeze.get("approvalRef") != approval_binding["ref"] or freeze.get("approvalDigest") != approval_binding["digest"]:
        raise M1000FourEnvironmentProofError("sample strategy approval exact-byte binding drifted")
    strategy = freeze.get("strategy")
    if not isinstance(strategy, Mapping):
        raise M1000FourEnvironmentProofError("sample strategy freeze lacks strategy")
    strategy_digest = canonical_digest(dict(strategy))
    if freeze.get("strategyDigest") != strategy_digest:
        raise M1000FourEnvironmentProofError("sample strategy digest drifted")
    distribution = strategy.get("sampleDistribution")
    if not isinstance(distribution, Mapping) or set(distribution) != set(CARRIERS):
        raise M1000FourEnvironmentProofError("sample strategy must explicitly cover all carriers")
    normalized: dict[str, int] = {}
    for carrier in CARRIERS:
        value = distribution.get(carrier)
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise M1000FourEnvironmentProofError(f"sample strategy {carrier} count must be positive")
        normalized[carrier] = value
    if approval.get("schema") != "quwoquan_data.m1000_app_uat_sample_approval" or approval.get("strategyDigest") != strategy_digest:
        raise M1000FourEnvironmentProofError("sample strategy joint approval drifted")
    approvals = approval.get("approvals")
    if not isinstance(approvals, list) or len(approvals) != 2:
        raise M1000FourEnvironmentProofError("sample strategy requires exactly product and quality approvals")
    roles = [row.get("role") for row in approvals if isinstance(row, Mapping)]
    authorities = [row.get("authorityId") for row in approvals if isinstance(row, Mapping)]
    if roles != ["product_owner", "quality_owner"] or len(set(authorities)) != 2:
        raise M1000FourEnvironmentProofError("sample strategy approvals require distinct product and quality authorities")
    if any(row.get("decision") != "approved" for row in approvals if isinstance(row, Mapping)):
        raise M1000FourEnvironmentProofError("sample strategy approval is not approved")
    policy = sample_plan.get("sampleStrategy")
    if not isinstance(policy, Mapping) or policy.get("sampleDistribution") != normalized:
        raise M1000FourEnvironmentProofError("release sample plan differs from frozen strategy input")
    samples = sample_plan.get("samples")
    if not isinstance(samples, list) or Counter(str(row.get("carrier")) for row in samples if isinstance(row, Mapping)) != Counter(normalized):
        raise M1000FourEnvironmentProofError("release sample rows differ from frozen strategy input")
    if sample_plan.get("sampleCount") != sum(normalized.values()):
        raise M1000FourEnvironmentProofError("release sample count differs from frozen strategy input")
    return strategy_digest, normalized


def _identity(payload: Mapping[str, Any], *, environment: str, target: str, release_id: str, release_digest: str, fingerprint: str, label: str) -> None:
    expected = {
        "environment": environment,
        "target": target,
        "releaseId": release_id,
        "releaseDigest": release_digest,
        "sourceFingerprint": fingerprint,
    }
    for field, value in expected.items():
        if payload.get(field) != value:
            raise M1000FourEnvironmentProofError(f"{label} current candidate/environment drifted at {field}")


def _status(payload: Mapping[str, Any]) -> str:
    for field in ("status", "state", "verdict", "result"):
        value = payload.get(field)
        if isinstance(value, str) and value:
            return value.lower()
    if payload.get("passed") is True:
        return "passed"
    return ""


def _passing_current_fact(
    root: Path, binding: object, *, label: str, environment: str, target: str,
    release_id: str, release_digest: str, fingerprint: str, allowed: set[str],
) -> dict[str, Any]:
    payload, _ = _load_exact(root, binding, label=label)
    _identity(
        payload, environment=environment, target=target, release_id=release_id,
        release_digest=release_digest, fingerprint=fingerprint, label=label,
    )
    if _status(payload) not in allowed:
        raise M1000FourEnvironmentProofError(f"{label} is not passing")
    return payload


def _validate_environment(
    *, root: Path, gate: Mapping[str, Any], expected_environment: str,
    release_id: str, release_digest: str, fingerprint: str,
    previous: tuple[str, str, str] | None,
    expected_package_digest: str | None,
) -> tuple[dict[str, Any], tuple[str, str, str]]:
    environment = str(gate.get("environment") or "")
    target = _text(gate.get("target"), label=f"{expected_environment}.target")
    if environment != expected_environment:
        raise M1000FourEnvironmentProofError("environment gate order must be alpha/beta/gamma/prod")
    acceptance, acceptance_binding = _load_exact(
        root, gate.get("environmentAcceptanceFact"), label=f"{environment}.environmentAcceptanceFact"
    )
    profiles = [
        {"platform": item.get("platform"), "deviceProfile": item.get("deviceProfile")}
        for item in acceptance.get("targetBindingRefs", [])
        if isinstance(item, Mapping)
    ]
    try:
        validate_environment_acceptance_fact(
            acceptance,
            evidence_root=root,
            required_target_profiles=profiles,
            verify_references=True,
        )
    except EnvironmentAcceptanceFactError as exc:
        raise M1000FourEnvironmentProofError(
            f"{environment} EnvironmentAcceptanceFact is invalid: {exc}"
        ) from exc
    _identity(
        acceptance, environment=environment, target=target, release_id=release_id,
        release_digest=release_digest, fingerprint=fingerprint,
        label=f"{environment}.EnvironmentAcceptanceFact",
    )
    observed_profiles: set[tuple[str, str]] = set()
    package_digests: set[str] = set()
    candidate_digests: set[str] = set()
    device_identities: set[str] = set()
    for index, item in enumerate(acceptance.get("targetBindingRefs", [])):
        if not isinstance(item, Mapping):
            raise M1000FourEnvironmentProofError(f"{environment} target binding ref is invalid")
        binding, _ = _load_exact(
            root, {"ref": item.get("ref"), "digest": item.get("digest")},
            label=f"{environment}.targetBindingRefs[{index}]",
        )
        platform = str(item.get("platform") or "")
        profile = str(item.get("deviceProfile") or "")
        observed_profiles.add((platform, profile))
        if binding.get("device", {}).get("class") != "physical" or binding.get("device", {}).get("registered") is not True:
            raise M1000FourEnvironmentProofError(
                f"{environment} {platform} target is not a registered physical device"
            )
        device_identities.add(str(binding.get("device", {}).get("identity") or ""))
        package_digests.add(str(binding.get("packageDigest") or ""))
        candidate_digests.add(str(binding.get("candidateDigest") or ""))
    if not any(platform == "android" for platform, _profile in observed_profiles) or not any(platform == "ios" for platform, _profile in observed_profiles):
        raise M1000FourEnvironmentProofError(f"{environment} requires Android and iOS physical-device profiles")
    if len(device_identities) < 2 or "" in device_identities:
        raise M1000FourEnvironmentProofError(f"{environment} requires two distinct physical devices")
    if len(package_digests) != 1 or len(candidate_digests) != 1 or fingerprint not in candidate_digests:
        raise M1000FourEnvironmentProofError(
            f"{environment} target bindings must share the current candidate and immutable package"
        )
    observed_package_digest = next(iter(package_digests))
    if expected_package_digest is not None and observed_package_digest != expected_package_digest:
        raise M1000FourEnvironmentProofError(
            f"{environment} package differs from Alpha immutable package"
        )
    expected_predecessor = PREDECESSOR[environment]
    predecessor = acceptance.get("predecessorAcceptance")
    if expected_predecessor is None:
        if predecessor is not None or previous is not None:
            raise M1000FourEnvironmentProofError("alpha must have no predecessor acceptance")
    else:
        if not isinstance(predecessor, Mapping) or previous is None:
            raise M1000FourEnvironmentProofError(f"{environment} lacks predecessor acceptance")
        if predecessor.get("environment") != expected_predecessor or predecessor.get("factId") != previous[0] or predecessor.get("digest") != previous[1]:
            raise M1000FourEnvironmentProofError(f"{environment} predecessor does not bind exact {expected_predecessor}")
    lifecycle, _ = _load_exact(root, acceptance.get("lifecycleExit"), label=f"{environment}.lifecycleExit")
    if (
        lifecycle.get("schema") != "quwoquan_data.environment_release_lifecycle_exit"
        or lifecycle.get("environment") != environment
        or lifecycle.get("originalReleaseId") != release_id
        or lifecycle.get("replayManifestDigest") != acceptance.get("activeCas", {}).get("releaseDigest")
        or lifecycle.get("passed") is not True
    ):
        raise M1000FourEnvironmentProofError(f"{environment} rollback/replay lifecycle exit drifted")
    capacity = _passing_current_fact(
        root, gate.get("capacityTimeliness"), label=f"{environment}.capacityTimeliness",
        environment=environment, target=target, release_id=release_id,
        release_digest=release_digest, fingerprint=fingerprint, allowed={"passed", "ready"},
    )
    if capacity.get("withinCapacityBudget") is not True or capacity.get("withinTimelinessBudget") is not True:
        raise M1000FourEnvironmentProofError(f"{environment} capacity/timeliness budget did not pass")
    fault = _passing_current_fact(
        root, gate.get("faultRecovery"), label=f"{environment}.faultRecovery",
        environment=environment, target=target, release_id=release_id,
        release_digest=release_digest, fingerprint=fingerprint, allowed={"passed"},
    )
    if fault.get("automaticRecoveryStatus") != "MEASURED" or fault.get("rollbackVerified") is not True or fault.get("replayVerified") is not True:
        raise M1000FourEnvironmentProofError(f"{environment} fault recovery/rollback/replay is incomplete")
    raw_roles = gate.get("responsibilityAcceptances")
    if not isinstance(raw_roles, list) or len(raw_roles) != len(RESPONSIBILITY_ROLES):
        raise M1000FourEnvironmentProofError(f"{environment} responsibility acceptance set is incomplete")
    for expected_role, binding in zip(RESPONSIBILITY_ROLES, raw_roles, strict=True):
        if not isinstance(binding, Mapping) or binding.get("role") != expected_role:
            raise M1000FourEnvironmentProofError(f"{environment} responsibility acceptance role order drifted")
        payload = _passing_current_fact(
            root, {"ref": binding.get("ref"), "digest": binding.get("digest")},
            label=f"{environment}.responsibility.{expected_role}", environment=environment,
            target=target, release_id=release_id, release_digest=release_digest,
            fingerprint=fingerprint, allowed={"accepted", "approved", "passed"},
        )
        if payload.get("role") != expected_role or payload.get("decision") not in {"accepted", "approved"}:
            raise M1000FourEnvironmentProofError(f"{environment} {expected_role} acceptance did not pass")
    return (
        {
            "environment": environment,
            "target": target,
            "acceptanceFactId": str(acceptance["factId"]),
            "requiredGates": list(_REQUIRED_GATES),
            "responsibilityRoles": list(RESPONSIBILITY_ROLES),
        },
        (
            str(acceptance["factId"]),
            acceptance_binding["digest"],
            observed_package_digest,
        ),
    )


__all__ = [
    "CARRIERS", "ENVIRONMENTS",
    "M1000FourEnvironmentProofError", "REQUEST_SCHEMA", "RESPONSIBILITY_ROLES",
    "SCHEMA", "_digest", "_load_exact", "_safe_root", "_text",
    "_validate_environment", "_validate_sampling", "_validate_scale",
    "exact_byte_digest",
]
