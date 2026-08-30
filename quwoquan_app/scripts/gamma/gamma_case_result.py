#!/usr/bin/env python3
"""Emit canonical, create-once Gamma App ``ReadinessCaseResult`` bundles."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_app.scripts.gamma import verify_local_gamma_mirror as gamma_verifier
from quwoquan_ops.cli.lib.deployment_candidate_manifest import load_candidate_manifest
from quwoquan_ops.cli.lib.output_paths import active_deployment_candidate, output_root
from quwoquan_ops.cli.lib.readiness_case_result import (
    ReadinessCaseResultError,
    build_readiness_result_bundle,
    validate_readiness_case_result,
    write_create_once_json,
)
from quwoquan_ops.cli.lib.startup_attempt_receipt import load_startup_attempt
from quwoquan_ops.cli.lib.target_uat_binding import (
    TargetUatBindingError,
    target_uat_binding_digest,
    validate_target_uat_binding,
)


ENVIRONMENT = "gamma"
TARGET = "gamma-local"
SPEC_REF = (
    "specs/feature-tree/discovery-content/object-homepage-coverage-scaling/"
    "multi-carrier-release/spec.md#gwt-001"
)
CASE_ID = "homepage_release_consumer_render_app_uat"
OBJECT_ID = "entity.homepage"
TARGET_VALUE = {"kind": "page", "id": "entity.detail"}
RUNNER_IDENTITY = "gamma-patrol-release-homepage"
RUNNER_SOURCE_PATH = (
    "quwoquan_app/test/user_acceptance/service/entity_service/entity_homepage/"
    "homepage/release_homepage__consumer_render__functional__user_acceptance_test.dart"
)
IDENTITY_SNAPSHOT_SCHEMA = "quwoquan.gamma-case-result-identity"
IDENTITY_FIELDS = (
    "environment",
    "target",
    "baselineId",
    "attemptId",
    "packageDigest",
    "configurationDigest",
    "runtimeConfigDigest",
    "providerRuntimeDigest",
    "observabilityLogSinkDigest",
    "imageDigest",
    "sourceRevision",
    "contractGraphSourceHash",
    "candidateManifestSha256",
)
IDENTITY_SNAPSHOT_FIELDS = frozenset({"schema", "phase", "preparedAt", "identity"})


class GammaCaseResultError(ValueError):
    """Gamma evidence cannot produce a trustworthy canonical raw result."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _timestamp(value: object, *, label: str) -> str:
    text = str(value or "").strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise GammaCaseResultError(f"{label} is invalid") from exc
    if parsed.tzinfo is None:
        raise GammaCaseResultError(f"{label} must include a timezone")
    return text


def resolve_gamma_evidence_path(raw_value: str, *, label: str) -> Path:
    """Keep every Gamma CaseResult artifact in the target evidence plane."""

    evidence_root_lexical = Path(
        os.path.abspath(output_root() / "env" / ENVIRONMENT / "runs")
    )
    evidence_root = evidence_root_lexical.resolve()
    candidate = Path(raw_value).expanduser()
    if not candidate.is_absolute():
        candidate = ROOT / candidate
    candidate = Path(os.path.abspath(candidate))
    try:
        relative = candidate.relative_to(evidence_root_lexical)
    except ValueError as exc:
        raise GammaCaseResultError(
            f"{label} must stay below QWQ_OUTPUT_ROOT/env/gamma/runs"
        ) from exc
    current = evidence_root_lexical
    for component in relative.parts:
        current /= component
        if current.is_symlink():
            raise GammaCaseResultError(f"{label} cannot traverse a symlink")
    try:
        candidate.resolve().relative_to(evidence_root)
    except ValueError as exc:
        raise GammaCaseResultError(
            f"{label} resolved outside QWQ_OUTPUT_ROOT/env/gamma/runs"
        ) from exc
    return candidate.resolve()


def _load_json(path: Path, *, label: str) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise GammaCaseResultError(f"{label} is missing or unsafe")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise GammaCaseResultError(f"{label} is unreadable: {exc}") from exc
    if not isinstance(payload, dict):
        raise GammaCaseResultError(f"{label} root must be an object")
    return payload


def _contract_graph_source_hash() -> str:
    graph = _load_json(
        ROOT / "quwoquan_service/generated/contract_graph.json",
        label="current ContractGraph",
    )
    sources = graph.get("sources")
    if not isinstance(sources, list) or not sources:
        raise GammaCaseResultError("current ContractGraph has no source identities")
    normalized: list[tuple[str, str]] = []
    for source in sources:
        if not isinstance(source, dict):
            raise GammaCaseResultError("current ContractGraph source identity is invalid")
        source_path = str(source.get("path") or "").strip()
        digest = str(source.get("sha256") or "").strip()
        if not source_path or len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
            raise GammaCaseResultError("current ContractGraph source identity is invalid")
        normalized.append((source_path, digest))
    normalized.sort()
    if len({source_path for source_path, _ in normalized}) != len(normalized):
        raise GammaCaseResultError("current ContractGraph has duplicate source paths")
    hasher = hashlib.sha256()
    for source_path, digest in normalized:
        hasher.update(source_path.encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(digest.encode("ascii"))
        hasher.update(b"\n")
    return hasher.hexdigest()


def _candidate_manifest_sha256(active: Mapping[str, Any]) -> str:
    candidate_dir = Path(str(active.get("candidateDir") or "")).resolve()
    manifest_path = candidate_dir / "manifest.json"
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise GammaCaseResultError("Gamma candidate manifest bytes are missing or unsafe")
    return hashlib.sha256(manifest_path.read_bytes()).hexdigest()


def _normalize_identity(value: object) -> dict[str, str]:
    if not isinstance(value, dict) or set(value) != set(IDENTITY_FIELDS):
        raise GammaCaseResultError("Gamma execution identity fields mismatch")
    identity = {field: str(value.get(field) or "") for field in IDENTITY_FIELDS}
    if identity["environment"] != ENVIRONMENT or identity["target"] != TARGET:
        raise GammaCaseResultError("Gamma execution identity target mismatch")
    return identity


def load_gamma_execution_identity() -> dict[str, str]:
    """Read one stable identity from the active candidate and running receipt."""

    try:
        startup = load_startup_attempt(TARGET)
        if startup is None:
            raise GammaCaseResultError("Gamma running startup receipt is missing")
        active = active_deployment_candidate(TARGET)
        if not isinstance(active, dict):
            raise GammaCaseResultError("Gamma active deployment candidate is missing")
        baseline_id = str(active.get("baselineId") or "")
        candidate = load_candidate_manifest(
            ENVIRONMENT,
            TARGET,
            baseline_id,
            require_full=True,
        )
        legacy_identity = gamma_verifier._candidate_identity(
            startup=startup,
            active=active,
            candidate=candidate,
            configuration_digest=str(startup.get("configurationDigest") or ""),
        )
        identity = {
            **legacy_identity,
            "runtimeConfigDigest": str(candidate.get("runtimeConfigDigest") or ""),
            "sourceRevision": str(candidate.get("sourceRevision") or ""),
            "contractGraphSourceHash": _contract_graph_source_hash(),
            "candidateManifestSha256": _candidate_manifest_sha256(active),
        }
        startup_after = load_startup_attempt(TARGET)
        active_after = active_deployment_candidate(TARGET)
    except GammaCaseResultError:
        raise
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise GammaCaseResultError(str(exc)) from exc
    if startup_after != startup or active_after != active:
        raise GammaCaseResultError(
            "Gamma startup or active candidate changed during identity validation"
        )
    return _normalize_identity(identity)


def require_unchanged_identity(expected: Mapping[str, str]) -> dict[str, str]:
    normalized = _normalize_identity(dict(expected))
    current = load_gamma_execution_identity()
    if current != normalized:
        raise GammaCaseResultError(
            "Gamma startup or active candidate changed during test execution"
        )
    return current


def load_target_uat_binding(path: Path) -> tuple[dict[str, Any], str]:
    try:
        encoded = path.read_bytes()
    except OSError as exc:
        raise GammaCaseResultError("TargetUatBinding is missing or unreadable") from exc
    try:
        binding = json.loads(encoded)
        validated = validate_target_uat_binding(
            binding,
            expected_bindings={"environment": ENVIRONMENT, "target": TARGET},
        )
        digest = target_uat_binding_digest(encoded)
    except (json.JSONDecodeError, TargetUatBindingError, TypeError, ValueError) as exc:
        raise GammaCaseResultError(f"TargetUatBinding is invalid: {exc}") from exc
    return validated, digest


def _slot_artifact_path(report_path: Path, slot_id: str) -> Path:
    safe = "".join(ch if ch.isalnum() or ch in "._-" else "-" for ch in slot_id)
    return report_path.with_name(f"{report_path.stem}.{safe}.json")


def _result(
    *,
    identity: Mapping[str, str],
    status: str,
    entry_surface: str,
    carrier: str,
    platform: str,
    device_class: str,
    runner_identity: str,
    started_at: str,
    completed_at: str,
    artifact_sha256: str,
    artifact_path: str,
    binding: Mapping[str, Any],
    binding_digest: str,
) -> dict[str, Any]:
    normalized = _normalize_identity(dict(identity))
    value: dict[str, Any] = {
        "objectId": OBJECT_ID,
        "specRef": SPEC_REF,
        "caseId": CASE_ID,
        "producer": "app",
        "layer": "user_acceptance",
        "status": status,
        "target": dict(TARGET_VALUE),
        "commitSha": normalized["sourceRevision"],
        "contractGraphSourceHash": normalized["contractGraphSourceHash"],
        "deploymentTarget": TARGET,
        "baselineId": normalized["baselineId"].removeprefix("sha256:"),
        "packageDigest": normalized["packageDigest"],
        "configurationDigest": normalized["configurationDigest"],
        "candidateManifestSha256": normalized["candidateManifestSha256"],
        "candidateDigest": normalized["baselineId"],
        "environment": ENVIRONMENT,
        "platform": platform,
        "deviceClass": device_class,
        "provider": str(binding["provider"]["identity"]),
        "startedAt": _timestamp(started_at, label="ReadinessCaseResult startedAt"),
        "completedAt": _timestamp(completed_at, label="ReadinessCaseResult completedAt"),
        "runnerIdentity": runner_identity,
        "artifactSha256": artifact_sha256,
        "artifactPath": artifact_path,
    }
    if status != "passed":
        value["reasonCode"] = (
            "APP.GAMMA_UAT.failed" if status == "failed" else "APP.GAMMA_UAT.blocked"
        )
    if not binding_digest:
        raise GammaCaseResultError("exact TargetUatBinding digest is missing")
    if (
            binding.get("candidateDigest") != normalized["baselineId"]
            or binding.get("packageDigest") != normalized["packageDigest"]
            or binding.get("configurationDigest") != normalized["configurationDigest"]
            or binding.get("runtimeConfigDigest") != normalized["runtimeConfigDigest"]
    ):
        raise GammaCaseResultError(
            "TargetUatBinding candidate identity differs from running Gamma"
        )
    value.update(
        {
                "releaseDigest": str(binding["releaseDigest"]),
                "releaseId": str(binding["releaseId"]),
                "targetUatBindingDigest": binding_digest,
                "entrySurface": entry_surface,
                "carrier": carrier,
                "deviceIdentity": str(binding["device"]["identity"]),
                "uatProfile": str(binding["profile"]),
                "nonPromotable": bool(binding["nonPromotable"]),
                "artifactClass": str(binding["artifact"]["class"]),
                "physicalDevice": binding["device"]["class"] == "physical",
        }
    )
    try:
        return validate_readiness_case_result(value, generated_at=completed_at)
    except ReadinessCaseResultError as exc:
        raise GammaCaseResultError(str(exc)) from exc


def _relative_artifact_path(path: Path) -> str:
    root = output_root().expanduser().resolve()
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError as exc:
        raise GammaCaseResultError("Gamma evidence artifact escapes QWQ_OUTPUT_ROOT") from exc


def write_blocker_artifact(
    *, report_path: Path, reason: str, slot_identity: Mapping[str, str]
) -> tuple[str, str]:
    payload = {
        "schema": "quwoquan.gamma-readiness-blocker.v1",
        "reason": " ".join(str(reason).split()).strip(),
        "slot": dict(slot_identity),
    }
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()
    blocker_path = report_path.with_name(f"{report_path.stem}.blocker.{digest}.json")
    try:
        write_create_once_json(blocker_path, payload)
    except ReadinessCaseResultError as exc:
        raise GammaCaseResultError(str(exc)) from exc
    return digest, _relative_artifact_path(blocker_path)


def write_result_bundle(*, report_path: Path, results: list[Mapping[str, Any]]) -> dict[str, Any]:
    if not results:
        raise GammaCaseResultError("Gamma execution produced no canonical raw results")
    generated_at = max(str(result["completedAt"]) for result in results)
    try:
        bundle = build_readiness_result_bundle(results, generated_at=generated_at)
        write_create_once_json(report_path, bundle)
    except ReadinessCaseResultError as exc:
        raise GammaCaseResultError(str(exc)) from exc
    return bundle


def write_identity_snapshot(
    *, path: Path, phase: str, identity: Mapping[str, str]
) -> dict[str, Any]:
    payload = {
        "schema": IDENTITY_SNAPSHOT_SCHEMA,
        "phase": phase,
        "preparedAt": utc_now(),
        "identity": _normalize_identity(dict(identity)),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return payload


def load_identity_snapshot(*, path: Path, phase: str) -> dict[str, str]:
    payload = _load_json(path, label=f"{phase} identity snapshot")
    if (
        set(payload) != IDENTITY_SNAPSHOT_FIELDS
        or payload.get("schema") != IDENTITY_SNAPSHOT_SCHEMA
        or payload.get("phase") != phase
    ):
        raise GammaCaseResultError(f"{phase} identity snapshot fields mismatch")
    _timestamp(payload.get("preparedAt"), label=f"{phase} identity preparedAt")
    return _normalize_identity(payload.get("identity"))


def prepare_device_uat(
    *,
    identity_snapshot_path: Path,
    patrol_report_path: Path,
) -> dict[str, str]:
    resolve_gamma_evidence_path(
        str(patrol_report_path), label="Gamma device-UAT Patrol report"
    )
    if identity_snapshot_path.exists() or identity_snapshot_path.is_symlink():
        raise GammaCaseResultError(
            "Gamma device-UAT identity snapshot already exists; use a new run path"
        )
    if patrol_report_path.exists() or patrol_report_path.is_symlink():
        raise GammaCaseResultError(
            "Gamma device-UAT Patrol report already exists; use a new run path"
        )
    identity = load_gamma_execution_identity()
    write_identity_snapshot(
        path=identity_snapshot_path, phase="device_uat", identity=identity
    )
    return identity


def _platform_for_device(device: Mapping[str, Any]) -> str:
    target_platform = str(device.get("targetPlatform") or "").strip().lower()
    if target_platform.startswith("android"):
        return "android"
    if target_platform == "ios":
        return "ios"
    raise GammaCaseResultError("Patrol cell platform is missing")


def _device_class(device: Mapping[str, Any]) -> str:
    emulator = device.get("emulator")
    if not isinstance(emulator, bool):
        raise GammaCaseResultError("Patrol cell deviceClass is missing")
    return "simulator" if emulator else "physical"


def _artifact_binding_for_device(
    payload: Mapping[str, Any], device_id: str
) -> Mapping[str, Any]:
    collection = payload.get("testedAppArtifactBinding")
    bindings = collection.get("bindings") if isinstance(collection, dict) else None
    if not isinstance(bindings, list):
        raise GammaCaseResultError("Patrol tested App artifact bindings are missing")
    matches = [
        item
        for item in bindings
        if isinstance(item, dict) and item.get("deviceId") == device_id
    ]
    if len(matches) != 1 or matches[0].get("status") != "passed":
        raise GammaCaseResultError("Patrol tested App artifact binding is not passed")
    return matches[0]


def _artifact_identity(binding: Mapping[str, Any]) -> tuple[str, str]:
    artifact = binding.get("buildArtifact")
    if not isinstance(artifact, dict):
        raise GammaCaseResultError("Patrol build artifact identity is missing")
    digest = str(artifact.get("artifactDigest") or "")
    if not digest.startswith("sha256:"):
        raise GammaCaseResultError("Patrol build artifact digest is missing")
    path = str(artifact.get("path") or "").strip().lstrip("/")
    if not path:
        raise GammaCaseResultError("Patrol build artifact path is missing")
    return digest.removeprefix("sha256:"), path


def _case_result_by_device(payload: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    cases = payload.get("caseResults")
    if not isinstance(cases, list):
        return {}
    result: dict[str, Mapping[str, Any]] = {}
    for case in cases:
        if not isinstance(case, dict):
            continue
        device_id = str(case.get("deviceId") or "").strip()
        if not device_id or device_id in result:
            raise GammaCaseResultError("Patrol caseResults device identity is duplicate")
        result[device_id] = case
    return result


def _run_by_device(payload: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    runs = payload.get("runs")
    if not isinstance(runs, list):
        return {}
    result: dict[str, Mapping[str, Any]] = {}
    for run in runs:
        if not isinstance(run, dict):
            continue
        device_id = str(run.get("deviceId") or "").strip()
        if not device_id:
            binding = run.get("testedAppArtifactBinding")
            device_id = (
                str(binding.get("deviceId") or "").strip()
                if isinstance(binding, dict)
                else ""
            )
        if not device_id:
            continue
        if device_id in result:
            raise GammaCaseResultError("Patrol runs device identity is duplicate")
        result[device_id] = run
    return result


def _blocked_cell_result(
    *,
    report_path: Path,
    identity: Mapping[str, str],
    binding: Mapping[str, Any],
    binding_digest: str,
    platform: str,
    device_class: str,
    runner_identity: str,
    reason: str,
    started_at: str,
    completed_at: str,
) -> dict[str, Any]:
    slot = {
        "platform": platform,
        "deviceClass": device_class,
        "entrySurface": "direct_or_object_route",
        "carrier": "homepage",
        "runnerIdentity": runner_identity,
    }
    artifact_sha256, artifact_path = write_blocker_artifact(
        report_path=report_path, reason=reason, slot_identity=slot
    )
    return _result(
        identity=identity,
        binding=binding,
        binding_digest=binding_digest,
        status="blocked",
        entry_surface="direct_or_object_route",
        carrier="homepage",
        platform=platform,
        device_class=device_class,
        runner_identity=runner_identity,
        started_at=started_at,
        completed_at=completed_at,
        artifact_sha256=artifact_sha256,
        artifact_path=artifact_path,
    )


def results_from_patrol(
    *,
    report_path: Path,
    payload: Mapping[str, Any],
    identity: Mapping[str, str],
    binding: Mapping[str, Any],
    binding_digest: str,
) -> list[dict[str, Any]]:
    started_at = _timestamp(payload.get("startedAt"), label="Patrol startedAt")
    completed_at = _timestamp(payload.get("endedAt"), label="Patrol endedAt")
    platform = str(binding["platform"])
    device_class = str(binding["device"]["class"])
    runner_identity = str(binding["runner"]["identity"])
    if (
        payload.get("composition") != "production_remote"
        or payload.get("evidenceClass") != "user_acceptance_remote"
        or payload.get("runtimeEnv") != ENVIRONMENT
        or payload.get("apiContractEnv") != ENVIRONMENT
        or payload.get("environmentAlias") not in {"local-gamma", TARGET}
    ):
        return [
            _blocked_cell_result(
                report_path=report_path,
                identity=identity,
                binding=binding,
                binding_digest=binding_digest,
                platform=platform,
                device_class=device_class,
                runner_identity=runner_identity,
                reason="Gamma device-UAT Patrol composition identity mismatch",
                started_at=started_at,
                completed_at=completed_at,
            )
        ]
    devices = payload.get("devices")
    if not isinstance(devices, list):
        devices = []
    devices_by_id = {
        str(device.get("id") or ""): device
        for device in devices
        if isinstance(device, dict) and str(device.get("id") or "")
    }
    device_id = str(binding["device"]["identity"])
    device = devices_by_id.get(device_id)
    if device is None:
        return [
            _blocked_cell_result(
                report_path=report_path,
                identity=identity,
                binding=binding,
                binding_digest=binding_digest,
                platform=platform,
                device_class=device_class,
                runner_identity=runner_identity,
                reason=f"Patrol evidence lacks exact TargetUatBinding device {device_id}",
                started_at=started_at,
                completed_at=completed_at,
            )
        ]
    reasons: list[str] = []
    try:
        if _platform_for_device(device) != platform:
            reasons.append("Patrol cell platform differs from TargetUatBinding")
        if _device_class(device) != device_class:
            reasons.append("Patrol cell deviceClass differs from TargetUatBinding")
    except GammaCaseResultError as exc:
        reasons.append(str(exc))
    case = _case_result_by_device(payload).get(device_id)
    run = _run_by_device(payload).get(device_id)
    if case is None or run is None:
        reasons.append("Patrol evidence lacks an independently identified run/case cell")
    summary = case.get("testExecution") if case is not None else None
    run_summary = run.get("testExecution") if run is not None else None
    if not isinstance(summary, dict) or summary != run_summary:
        reasons.append("Patrol cell testExecution identity is missing or drifted")
    elif (
        not isinstance(summary.get("executed"), int)
        or isinstance(summary.get("executed"), bool)
        or summary.get("executed", 0) <= 0
        or summary.get("skipped") != 0
        or summary.get("failed") != 0
    ):
        reasons.append("Patrol cell requires executed>0, skipped=0, failed=0")
    status = "passed"
    if (
        payload.get("status") != "passed"
        or case is None
        or case.get("status") != "passed"
        or run is None
        or run.get("exitCode") != 0
    ):
        status = "failed"
    try:
        artifact_binding = _artifact_binding_for_device(payload, device_id)
        artifact_sha256, artifact_path = _artifact_identity(artifact_binding)
    except GammaCaseResultError as exc:
        reasons.append(str(exc))
        artifact_sha256 = ""
        artifact_path = ""
    if reasons:
        return [
            _blocked_cell_result(
                report_path=report_path,
                identity=identity,
                binding=binding,
                binding_digest=binding_digest,
                platform=platform,
                device_class=device_class,
                runner_identity=runner_identity,
                reason="; ".join(reasons),
                started_at=started_at,
                completed_at=completed_at,
            )
        ]
    return [
        _result(
            identity=identity,
            binding=binding,
            binding_digest=binding_digest,
            status=status,
            entry_surface="direct_or_object_route",
            carrier="homepage",
            platform=platform,
            device_class=device_class,
            runner_identity=runner_identity,
            started_at=started_at,
            completed_at=completed_at,
            artifact_sha256=artifact_sha256,
            artifact_path=artifact_path,
        )
    ]


def finalize_device_uat(
    *,
    report_path: Path,
    identity_snapshot_path: Path,
    patrol_report_path: Path,
    target_uat_binding_path: Path,
    dry_run: bool,
    runner_exit_code: int = 0,
) -> dict[str, Any]:
    identity = load_identity_snapshot(
        path=identity_snapshot_path, phase="device_uat"
    )
    require_unchanged_identity(identity)
    binding, binding_digest = load_target_uat_binding(target_uat_binding_path)
    if dry_run:
        raise GammaCaseResultError("Gamma device-UAT dry-run has no raw CaseResult")
    if runner_exit_code != 0:
        raise GammaCaseResultError(
            f"Gamma device-UAT Patrol runner exited with {runner_exit_code}"
        )
    patrol_report = _load_json(
        patrol_report_path, label="Gamma device-UAT Patrol report"
    )
    results = results_from_patrol(
        report_path=report_path,
        payload=patrol_report,
        identity=identity,
        binding=binding,
        binding_digest=binding_digest,
    )
    return write_result_bundle(report_path=report_path, results=results)


def _paths(args: argparse.Namespace) -> tuple[Path, Path, Path, Path | None]:
    report = resolve_gamma_evidence_path(args.report, label="Gamma device-UAT ResultBundle")
    identity = resolve_gamma_evidence_path(
        args.identity_snapshot, label="Gamma device-UAT identity snapshot"
    )
    patrol = resolve_gamma_evidence_path(
        args.patrol_report, label="Gamma device-UAT Patrol report"
    )
    binding = None
    if getattr(args, "target_uat_binding", ""):
        binding = resolve_gamma_evidence_path(
            args.target_uat_binding, label="Gamma TargetUatBinding"
        )
    if len({report, identity, patrol}) != 3:
        raise GammaCaseResultError("Gamma device-UAT evidence paths must be distinct")
    return report, identity, patrol, binding


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare = subparsers.add_parser("prepare-device-uat")
    finalize = subparsers.add_parser("finalize-device-uat")
    for child in (prepare, finalize):
        child.add_argument("--report", required=True)
        child.add_argument("--identity-snapshot", required=True)
        child.add_argument("--patrol-report", required=True)
    finalize.add_argument("--target-uat-binding", required=True)
    finalize.add_argument("--dry-run", action="store_true")
    finalize.add_argument("--runner-exit-code", type=int, default=0)
    args = parser.parse_args()
    try:
        report_path, identity_path, patrol_path, binding_path = _paths(args)
        if args.command == "prepare-device-uat":
            prepare_device_uat(
                identity_snapshot_path=identity_path,
                patrol_report_path=patrol_path,
            )
            return 0
        assert binding_path is not None
        bundle = finalize_device_uat(
            report_path=report_path,
            identity_snapshot_path=identity_path,
            patrol_report_path=patrol_path,
            target_uat_binding_path=binding_path,
            dry_run=bool(args.dry_run),
            runner_exit_code=int(args.runner_exit_code),
        )
        return 0 if all(result["status"] == "passed" for result in bundle["results"]) else 1
    except GammaCaseResultError as exc:
        print(f"Gamma device-UAT GATE_BLOCK: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
