"""Exact environment acceptance validation for stable production proof."""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from quwoquan_ops.cli.lib.target_uat_binding import (
    TargetUatBindingError,
    validate_target_uat_binding,
)

CARRIERS = ("homepage", "article", "image", "video")
_ACCEPTANCE_SCHEMA = "quwoquan_ops.environment_acceptance_fact.v1"


def _proof_module():
    from content.execution import stable_production_proof

    return stable_production_proof

def _status(payload: Mapping[str, Any]) -> str:
    for key in ("status", "state", "phase", "lifecycle", "lifecycleState"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value.lower()
    if payload.get("passed") is True:
        return "passed"
    return ""
def _require_status(payload: Mapping[str, Any], label: str, allowed: set[str]) -> None:
    observed = _status(payload)
    if observed not in {value.lower() for value in allowed}:
        raise _proof_module().StableProductionProofError(
            f"{label} is not passing/terminal: got {observed!r}"
        )
def _fact_binding(value: object, label: str) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != {"ref", "digest"}:
        raise _proof_module().StableProductionProofError(f"{label} exact ref fields mismatch")
    return _proof_module()._exact_ref(
        {"ref": value.get("ref"), "exactByteDigest": value.get("digest")}, label
    )
def _load_common_release_fact(
    root: Path,
    value: object,
    *,
    label: str,
    release_id: str,
    allowed_statuses: set[str] | None = None,
) -> tuple[dict[str, Any], dict[str, str]]:
    binding = _fact_binding(value, label)
    payload, _ = _proof_module()._load_exact_json(root, binding, label)
    if payload.get("releaseId", payload.get("originalReleaseId")) != release_id:
        raise _proof_module().StableProductionProofError(f"{label} releaseId drifted")
    if allowed_statuses is not None:
        _require_status(payload, label, allowed_statuses)
    return payload, binding

def validate_acceptance(
    root: Path,
    acceptance: Mapping[str, Any],
    *,
    release_id: str,
    release_digest: str,
    expected_fingerprint: str,
    expected_environment: str,
) -> tuple[
    dict[str, str],
    dict[str, str],
    dict[str, str],
    dict[str, str],
    list[dict[str, str]],
    dict[str, str],
    set[str],
]:
    if acceptance.get("schema") != _ACCEPTANCE_SCHEMA:
        raise _proof_module().StableProductionProofError("EnvironmentAcceptanceFact schema mismatch")
    if acceptance.get("releaseId") != release_id:
        raise _proof_module().StableProductionProofError("EnvironmentAcceptanceFact releaseId drifted")
    if acceptance.get("releaseDigest") != release_digest:
        raise _proof_module().StableProductionProofError("EnvironmentAcceptanceFact releaseDigest drifted")
    if acceptance.get("sourceFingerprint") != expected_fingerprint:
        raise _proof_module().StableProductionProofError("EnvironmentAcceptanceFact fingerprint drifted")
    if acceptance.get("environment") != expected_environment:
        raise _proof_module().StableProductionProofError(
            f"EnvironmentAcceptanceFact environment must be {expected_environment}"
        )

    target_bindings = acceptance.get("targetBindingRefs")
    if not isinstance(target_bindings, list) or not target_bindings:
        raise _proof_module().StableProductionProofError("EnvironmentAcceptanceFact lacks target bindings")
    target_binding_providers: dict[str, str] = {}
    runtime_identities: set[str] = set()
    for index, value in enumerate(target_bindings):
        if not isinstance(value, Mapping):
            raise _proof_module().StableProductionProofError("target binding must be an object")
        binding = _fact_binding(
            {"ref": value.get("ref"), "digest": value.get("digest")},
            f"targetBindingRefs[{index}]",
        )
        target_payload, _ = _proof_module()._load_exact_json(
            root, binding, f"targetBindingRefs[{index}]"
        )
        try:
            target_payload = validate_target_uat_binding(target_payload)
        except TargetUatBindingError as exc:
            raise _proof_module().StableProductionProofError(
                f"target binding is not a strict TargetUatBinding: {exc}"
            ) from exc
        if (
            target_payload.get("releaseId") != release_id
            or target_payload.get("releaseDigest") != release_digest
            or target_payload.get("environment") != expected_environment
        ):
            raise _proof_module().StableProductionProofError("target binding release identity drifted")
        runtime_identities.update(
            str(target_payload[field])
            for field in (
                "candidateDigest",
                "packageDigest",
                "configurationDigest",
                "runtimeConfigDigest",
                "environmentRuntimeDigest",
            )
        )
        target_binding_providers[binding["exactByteDigest"]] = str(
            target_payload["provider"]["identity"]
        )

    data_readiness, _ = _load_common_release_fact(
        root,
        acceptance.get("dataReadiness"),
        label="dataReadiness",
        release_id=release_id,
        allowed_statuses={"ready", "passed"},
    )
    active = acceptance.get("activeCas")
    if not isinstance(active, Mapping) or set(active) != {
        "ref",
        "digest",
        "readbackRef",
        "readbackDigest",
        "releaseId",
        "releaseDigest",
    }:
        raise _proof_module().StableProductionProofError("EnvironmentAcceptanceFact activeCas fields mismatch")
    if active.get("releaseId") != release_id or active.get("releaseDigest") != release_digest:
        raise _proof_module().StableProductionProofError("activeCas release identity drifted")
    _, activation = _load_common_release_fact(
        root,
        {"ref": active.get("ref"), "digest": active.get("digest")},
        label="activation",
        release_id=release_id,
        allowed_statuses={"active", "ready"},
    )
    _, readback = _load_common_release_fact(
        root,
        {"ref": active.get("readbackRef"), "digest": active.get("readbackDigest")},
        label="readback",
        release_id=release_id,
        allowed_statuses={"active", "passed", "ready"},
    )
    lifecycle_payload, lifecycle = _load_common_release_fact(
        root,
        acceptance.get("lifecycleExit"),
        label="lifecycle",
        release_id=release_id,
        allowed_statuses={"exit", "passed"},
    )
    original_digest = lifecycle_payload.get(
        "originalManifestDigest", lifecycle_payload.get("releaseDigest")
    )
    replay_digest = lifecycle_payload.get(
        "replayManifestDigest", lifecycle_payload.get("releaseDigest")
    )
    if original_digest != release_digest or replay_digest != release_digest:
        raise _proof_module().StableProductionProofError(
            "lifecycle is not an original→rollback→same-digest replay Exit"
        )
    rollback_payload, rollback_ref = _load_common_release_fact(
        root,
        acceptance.get("rollbackReadiness"),
        label="rollbackReadiness",
        release_id=release_id,
        allowed_statuses={"ready", "passed"},
    )
    if rollback_payload.get("environment") != expected_environment:
        raise _proof_module().StableProductionProofError("rollbackReadiness environment drifted")
    envelope = data_readiness.get("activationEnvelope")
    if not isinstance(envelope, Mapping):
        raise _proof_module().StableProductionProofError("dataReadiness lacks real activation/import envelope")
    import_binding = _proof_module()._exact_ref(
        {
            "ref": envelope.get("importReportRef"),
            "exactByteDigest": envelope.get("importReportDigest"),
        },
        "import",
    )
    import_payload, _ = _proof_module()._load_exact_json(root, import_binding, "import")
    if import_payload.get("releaseId") != release_id:
        raise _proof_module().StableProductionProofError("import releaseId drifted")
    _require_status(import_payload, "import", {"imported", "completed", "passed"})
    raw_results = acceptance.get("requiredRawResults")
    if not isinstance(raw_results, list) or not raw_results:
        raise _proof_module().StableProductionProofError("EnvironmentAcceptanceFact lacks raw App UAT refs")
    projected_raw: list[dict[str, str]] = []
    raw_carriers: set[str] = set()
    for index, raw in enumerate(raw_results):
        if not isinstance(raw, Mapping) or set(raw) != {
            "ref", "digest", "slotId", "status"
        }:
            raise _proof_module().StableProductionProofError("raw App UAT binding fields mismatch")
        if raw.get("status") != "passed":
            raise _proof_module().StableProductionProofError("raw App UAT binding did not pass")
        binding = _fact_binding(
            {"ref": raw.get("ref"), "digest": raw.get("digest")},
            f"requiredRawResults[{index}]",
        )
        result, _ = _proof_module()._load_exact_json(root, binding, f"requiredRawResults[{index}]")
        carrier = _proof_module()._text(result.get("carrier"), f"requiredRawResults[{index}].carrier")
        entry_surface = _proof_module()._text(
            result.get("entrySurface"), f"requiredRawResults[{index}].entrySurface"
        )
        spec_ref = _proof_module()._text(result.get("specRef"), f"requiredRawResults[{index}].specRef")
        expected = {
            "producer": "app",
            "layer": "user_acceptance",
            "status": "passed",
            "releaseId": release_id,
            "carrier": carrier,
            "entrySurface": entry_surface,
            "specRef": spec_ref,
        }
        for key, expected_value in expected.items():
            if result.get(key) != expected_value:
                raise _proof_module().StableProductionProofError(
                    f"raw App UAT result does not bind {key}={expected_value!r}"
                )
        binding_digest = str(result.get("targetUatBindingDigest") or "")
        provider_identity = target_binding_providers.get(binding_digest)
        if provider_identity is None:
            raise _proof_module().StableProductionProofError(
                "raw App UAT result does not bind an accepted target binding"
            )
        if result.get("provider") != provider_identity:
            raise _proof_module().StableProductionProofError(
                "raw App UAT result provider differs from TargetUatBinding provider"
            )
        if carrier not in CARRIERS:
            raise _proof_module().StableProductionProofError("raw App UAT carrier is unknown")
        raw_carriers.add(carrier)
        projected_raw.append(
            {
                **binding,
                "entrySurface": entry_surface,
                "carrier": carrier,
                "specRef": spec_ref,
            }
        )
    if raw_carriers != set(CARRIERS):
        raise _proof_module().StableProductionProofError(
            "environment lacks complete homepage/article/image/video raw App consumer UAT"
        )
    return activation, import_binding, readback, lifecycle, sorted(
        projected_raw, key=lambda item: (item["carrier"], item["entrySurface"], item["ref"])
    ), rollback_ref, runtime_identities

__all__ = ["validate_acceptance"]
