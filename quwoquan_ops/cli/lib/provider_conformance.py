"""Validate Provider Conformance evidence and derive evidence-backed readiness."""
from __future__ import annotations

import argparse
from collections import defaultdict
from collections.abc import Iterable, Mapping
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib import external_provider_governance as governance
from quwoquan_ops.cli.lib.output_paths import output_root


EVIDENCE_SCHEMA = ROOT / "quwoquan_ops" / "environments" / "provider_conformance_evidence.schema.json"
# Conformance evidence has exactly three executable environments.  Production
# consumes Gamma's release evidence; it must never contribute a fourth matrix
# row or overwrite Gamma's result with a smoke run.
ENVIRONMENTS = ("alpha", "beta", "gamma")
READINESS_ENVIRONMENTS = (*ENVIRONMENTS, "prod")
LAYERS = ("local_contract", "api_integration", "user_acceptance")
CELL_PROFILES = {
    ("alpha", "local_contract"): "baseline",
    ("beta", "local_contract"): "baseline",
    ("gamma", "local_contract"): "baseline",
    ("alpha", "api_integration"): "smoke",
    ("beta", "api_integration"): "integration",
    ("gamma", "api_integration"): "integration",
    ("alpha", "user_acceptance"): "smoke",
    ("beta", "user_acceptance"): "integration",
    ("gamma", "user_acceptance"): "release",
}
MESSAGE_TRANSPORT_CAPABILITY_ID = "runtime.message.transport"
MESSAGE_TRANSPORT_METRIC_NAMES = (
    "pending_lag",
    "dead_letter",
    "publish_p95",
    "consume_p95",
)
REQUIRED_FIELDS = frozenset(
    {
        "schema",
        "version",
        "adapterId",
        "capabilityId",
        "bindingRoots",
        "environment",
        "testLayer",
        "executionProfile",
        "status",
        "executedAt",
        "artifactRef",
        "artifactDigest",
        "artifactAttestation",
        "commit",
        "imageDigest",
        "configDigest",
        "contractGraphDigest",
        "adapterDigest",
        "assertionCount",
        "assertionIds",
        "networkBoundary",
        "dataDigest",
        "cleanupReceipt",
        "acceptanceRefs",
        "observabilityRefs",
    }
)
RELEASE_READINESS_FIELDS = frozenset(
    {
        "switchCompatibilityReceiptRef",
        "callbackDrainReceiptRef",
        "lastGoodReceiptRef",
        "rollbackReceiptRef",
        "prodBindingPreflightReceiptRef",
    }
)
EXECUTION_REPORT_SCHEMA = "provider-conformance-test-report"
EXECUTION_REPORT_VERSION = 1
EXECUTION_REPORT_REQUIRED_FIELDS = frozenset(
    {
        "schema",
        "version",
        "adapterId",
        "capabilityId",
        "bindingRoots",
        "environment",
        "testLayer",
        "executionProfile",
        "status",
        "executedAt",
        "commit",
        "imageDigest",
        "configDigest",
        "contractGraphDigest",
        "adapterDigest",
        "assertionIds",
        "networkBoundary",
        "dataDigest",
        "testSource",
        "testCommand",
        "exitCode",
    }
)
ALLOWED_FIELDS = REQUIRED_FIELDS | {"failure", "releaseReadiness"}
ADAPTER_PATTERN = re.compile(r"^(?:ext|infra|data|dev|cap)\.[a-z0-9_]+(?:\.[a-z0-9_]+)*$")
CAPABILITY_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+$")
SHA256_PATTERN = re.compile(r"^sha256:[a-f0-9]{64}$")
ARTIFACT_ATTESTATION_PATTERN = re.compile(r"^hmac-sha256:[a-f0-9]{64}$")
COMMIT_PATTERN = re.compile(r"^[a-f0-9]{7,64}$")
ASSERTION_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
RECEIPT_REF_PATTERN = re.compile(r"^receipt:[a-z0-9][a-z0-9._:-]{2,255}$")
SENSITIVE_RECEIPT_REF_PATTERN = re.compile(
    r"(?:endpoint|secret|credential|token|password|https?|://)", re.IGNORECASE
)
MAX_EVIDENCE_AGE = timedelta(hours=24)


def _issue(location: str, message: str) -> str:
    return f"{location}: {message}"


def _output_path(reference: str, *, root: Path) -> Path | None:
    parts = Path(reference).parts
    if not parts or parts[0] != ".qwq_output":
        return None
    candidate = root / Path(*parts[1:])
    try:
        resolved = candidate.resolve()
        resolved.relative_to(root.resolve())
    except ValueError:
        return None
    return resolved


def evidence_files(root: Path | None = None) -> list[Path]:
    base = Path(root) if root is not None else output_root()
    files: list[Path] = []
    for environment in ENVIRONMENTS:
        run_root = base / "env" / environment / "runs"
        if run_root.is_dir():
            files.extend(sorted(run_root.rglob("provider-conformance-*.evidence.json")))
    return files


def load_evidence(root: Path | None = None) -> tuple[list[dict[str, Any]], list[str]]:
    evidence: list[dict[str, Any]] = []
    issues: list[str] = []
    for path in evidence_files(root):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            issues.append(_issue(path.as_posix(), f"invalid evidence JSON: {exc}"))
            continue
        if not isinstance(payload, dict):
            issues.append(_issue(path.as_posix(), "evidence root must be an object"))
            continue
        payload["_source"] = path
        evidence.append(payload)
    return evidence, issues


def _is_non_empty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _root_id_list(root_ids: object) -> list[str] | None:
    if not isinstance(root_ids, list) or not root_ids:
        return None
    if not all(_is_non_empty_string(root_id) for root_id in root_ids):
        return None
    if len(root_ids) != len(set(root_ids)):
        return None
    return list(root_ids)


def _binding_root_ids(roots: object) -> list[str] | None:
    if not isinstance(roots, list) or not roots:
        return None
    if not all(isinstance(root, Mapping) for root in roots):
        return None
    return _root_id_list([root.get("root_id") for root in roots])


def compiled_capability_binding_roots(
    compiled: Mapping[str, Any],
    *,
    capability_id: str,
) -> list[dict[str, Any]]:
    """读取 BindingCompiler 唯一输出的 Capability 根组合。"""
    roots_by_capability = compiled.get("capabilityBindingRoots")
    if not isinstance(roots_by_capability, Mapping):
        raise ValueError("compiled provider binding receipt is missing capabilityBindingRoots")
    roots = roots_by_capability.get(capability_id)
    root_ids = _binding_root_ids(roots)
    if root_ids is None:
        raise ValueError(
            f"compiled provider binding receipt has invalid binding roots for {capability_id}"
        )
    return [dict(root) for root in roots]


def required_metric_refs(capability_id: str) -> tuple[str, ...]:
    if capability_id != MESSAGE_TRANSPORT_CAPABILITY_ID:
        return ()
    return tuple(
        f"provider-conformance://{capability_id}/metrics/{metric_name}"
        for metric_name in MESSAGE_TRANSPORT_METRIC_NAMES
    )


def _selected_binding(
    compiled: Mapping[str, Any],
    *,
    capability_id: str,
    environment: str,
) -> Mapping[str, Any] | None:
    selected_bindings = compiled.get("selectedBindings")
    if not isinstance(selected_bindings, Mapping):
        return None
    environment_bindings = selected_bindings.get(environment)
    if not isinstance(environment_bindings, Mapping):
        return None
    binding = environment_bindings.get(capability_id)
    return binding if isinstance(binding, Mapping) else None


def _selected_adapter_id(
    compiled: Mapping[str, Any],
    *,
    capability_id: str,
    environment: str,
) -> str | None:
    binding = _selected_binding(
        compiled,
        capability_id=capability_id,
        environment=environment,
    )
    adapter_id = binding.get("adapter_id") if binding is not None else None
    return adapter_id if isinstance(adapter_id, str) else None


def _binding_preflight_ready(
    compiled: Mapping[str, Any],
    *,
    capability_id: str,
    environment: str,
) -> bool:
    readiness = compiled.get("readiness")
    if not isinstance(readiness, Mapping):
        return False
    environment_readiness = readiness.get(environment)
    if not isinstance(environment_readiness, Mapping):
        return False
    binding_readiness = environment_readiness.get(capability_id)
    return isinstance(binding_readiness, Mapping) and bool(
        binding_readiness.get("adapter_preflight_ready")
    )


def _valid_receipt_ref(value: object) -> bool:
    return (
        isinstance(value, str)
        and RECEIPT_REF_PATTERN.fullmatch(value) is not None
        and SENSITIVE_RECEIPT_REF_PATTERN.search(value) is None
    )


def _expected_test_source(
    manifest: Mapping[str, Any],
    *,
    adapter: Mapping[str, Any],
    layer: object,
) -> str | None:
    if not isinstance(layer, str):
        return None
    profiles = manifest.get("profiles")
    profile_id = adapter.get("conformance_profile")
    if not isinstance(profiles, Mapping) or not isinstance(profile_id, str):
        return None
    profile = profiles.get(profile_id)
    if not isinstance(profile, Mapping):
        return None
    source = profile.get(layer)
    return source if _is_non_empty_string(source) else None


def sign_execution_report(raw: bytes, *, key: str | None = None) -> str:
    """为不可变执行报告生成仅 CI 持有密钥可复核的证明。"""
    signing_key = key or os.environ.get("QWQ_PROVIDER_CONFORMANCE_ATTESTATION_KEY", "")
    if not signing_key:
        raise ValueError("QWQ_PROVIDER_CONFORMANCE_ATTESTATION_KEY is required")
    return "hmac-sha256:" + hmac.new(
        signing_key.encode("utf-8"),
        raw,
        hashlib.sha256,
    ).hexdigest()


def _validate_execution_report(
    *,
    artifact_path: Path,
    evidence: Mapping[str, Any],
    expected_test_source: str | None,
) -> list[str]:
    issues: list[str] = []
    try:
        raw = artifact_path.read_bytes()
        report = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        return [_issue(str(artifact_path), f"invalid execution report: {exc}")]
    if not isinstance(report, Mapping):
        return [_issue(str(artifact_path), "execution report root must be an object")]
    missing = EXECUTION_REPORT_REQUIRED_FIELDS - set(report)
    if missing:
        issues.append(
            _issue(
                str(artifact_path),
                f"execution report missing fields {sorted(missing)}",
            )
        )
        return issues
    if (
        report.get("schema") != EXECUTION_REPORT_SCHEMA
        or report.get("version") != EXECUTION_REPORT_VERSION
    ):
        issues.append(
            _issue(
                str(artifact_path),
                "execution report has unsupported schema/version",
            )
        )
    expected_digest = evidence.get("artifactDigest")
    actual_digest = f"sha256:{hashlib.sha256(raw).hexdigest()}"
    if expected_digest != actual_digest:
        issues.append(
            _issue(
                str(artifact_path),
                "artifactDigest does not match the immutable execution report bytes",
            )
        )
    supplied_attestation = evidence.get("artifactAttestation")
    if (
        not isinstance(supplied_attestation, str)
        or not ARTIFACT_ATTESTATION_PATTERN.fullmatch(supplied_attestation)
    ):
        issues.append(
            _issue(
                str(artifact_path),
                "artifactAttestation must be an HMAC-SHA256 value",
            )
        )
    else:
        try:
            expected_attestation = sign_execution_report(raw)
        except ValueError as exc:
            issues.append(_issue(str(artifact_path), str(exc)))
        else:
            if not hmac.compare_digest(supplied_attestation, expected_attestation):
                issues.append(
                    _issue(
                        str(artifact_path),
                        "artifactAttestation is not trusted for the immutable execution report",
                    )
                )
    for field in (
        "adapterId",
        "capabilityId",
        "environment",
        "testLayer",
        "executionProfile",
        "status",
        "executedAt",
        "commit",
        "imageDigest",
        "configDigest",
        "contractGraphDigest",
        "adapterDigest",
        "bindingRoots",
        "assertionIds",
        "networkBoundary",
        "dataDigest",
    ):
        if report.get(field) != evidence.get(field):
            issues.append(
                _issue(
                    str(artifact_path),
                    f"execution report {field} does not match evidence",
                )
            )
    if report.get("testSource") != expected_test_source:
        issues.append(
            _issue(
                str(artifact_path),
                "execution report testSource does not match the Adapter profile/layer contract",
            )
        )
    if not _is_non_empty_string(report.get("testCommand")):
        issues.append(_issue(str(artifact_path), "execution report testCommand is required"))
    if report.get("exitCode") != 0:
        issues.append(_issue(str(artifact_path), "execution report exitCode must be zero"))
    return issues


def _release_readiness_valid(item: Mapping[str, Any]) -> bool:
    release_readiness = item.get("releaseReadiness")
    return (
        isinstance(release_readiness, Mapping)
        and set(release_readiness) == RELEASE_READINESS_FIELDS
        and all(_valid_receipt_ref(release_readiness[field]) for field in RELEASE_READINESS_FIELDS)
    )


def _current_commit() -> str | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    commit = completed.stdout.strip()
    return commit if COMMIT_PATTERN.fullmatch(commit) else None


def validate_evidence(
    evidence: Iterable[Mapping[str, Any]],
    *,
    registry: Mapping[str, Any],
    root: Path | None = None,
    current_commit: str | None = None,
    conformance_manifest: Mapping[str, Any] | None = None,
    compiled: Mapping[str, Any] | None = None,
) -> list[str]:
    issues: list[str] = []
    manifest = (
        conformance_manifest
        if conformance_manifest is not None
        else governance.load_conformance_manifest()
    )
    compiled_governance = compiled
    if compiled_governance is None:
        compiled_governance, _ = governance.compile_governance(
            registry,
            governance.load_bindings(),
            manifest,
        )
    common_assertion_ids = manifest.get("common_assertion_ids", [])
    profile_assertion_ids = manifest.get("profile_assertion_ids", {})
    adapter_by_id = {
        str(adapter.get("adapter_id")): adapter
        for adapter in registry.get("adapters", [])
        if isinstance(adapter, Mapping)
    }
    capability_by_id = {
        str(capability.get("capability_id")): capability
        for capability in registry.get("capabilities", [])
        if isinstance(capability, Mapping)
    }
    configured_root = Path(root) if root is not None else output_root()
    duplicate_cells: set[tuple[str, str, str]] = set()
    artifact_refs: set[str] = set()
    for index, item in enumerate(evidence):
        location = str(item.get("_source") or f"evidence[{index}]")
        fields = set(item) - {"_source"}
        missing = REQUIRED_FIELDS - fields
        unknown = fields - ALLOWED_FIELDS
        if missing:
            issues.append(_issue(location, f"missing required fields {sorted(missing)}"))
            continue
        if unknown:
            issues.append(_issue(location, f"contains unknown fields {sorted(unknown)}"))
            continue
        if item.get("schema") != "provider-conformance-evidence" or item.get("version") != 1:
            issues.append(_issue(location, "has unsupported evidence schema/version"))
        adapter_id = item.get("adapterId")
        capability_id = item.get("capabilityId")
        if not isinstance(adapter_id, str) or not ADAPTER_PATTERN.fullmatch(adapter_id):
            issues.append(_issue(location, "adapterId must be a stable Adapter ID"))
            continue
        adapter = adapter_by_id.get(adapter_id)
        if adapter is None:
            issues.append(_issue(location, "adapterId is not registered"))
            continue
        capability = (
            capability_by_id.get(capability_id)
            if isinstance(capability_id, str)
            else None
        )
        if not isinstance(capability_id, str) or not CAPABILITY_PATTERN.fullmatch(capability_id):
            issues.append(_issue(location, "capabilityId must be a stable Capability ID"))
        elif adapter.get("capability_id") != capability_id:
            issues.append(_issue(location, "capabilityId does not match adapterId"))
        elif not _is_non_empty_string(
            (capability_by_id.get(capability_id) or {}).get("canonical_port")
        ):
            issues.append(
                _issue(
                    location,
                    "capabilityId does not resolve to a registered canonical typed Port",
                )
            )
        evidence_root_ids = _root_id_list(item.get("bindingRoots"))
        if evidence_root_ids is None:
            issues.append(
                _issue(location, "bindingRoots must be a non-empty unique ordered root_id list")
            )
        elif not isinstance(capability, Mapping):
            issues.append(
                _issue(location, "bindingRoots cannot resolve an evidence capability")
            )
        else:
            registry_root_ids = _binding_root_ids(capability.get("binding_roots"))
            try:
                compiled_roots = compiled_capability_binding_roots(
                    compiled_governance,
                    capability_id=capability_id,
                )
            except ValueError as exc:
                issues.append(_issue(location, str(exc)))
            else:
                compiled_root_ids = _binding_root_ids(compiled_roots)
                if registry_root_ids is None or compiled_root_ids is None:
                    issues.append(
                        _issue(
                            location,
                            "registry/compiled capability binding roots must be non-empty and unique",
                        )
                    )
                elif registry_root_ids != compiled_root_ids:
                    issues.append(
                        _issue(
                            location,
                            "registry and compiled capability binding roots diverge",
                        )
                    )
                elif evidence_root_ids != compiled_root_ids:
                    issues.append(
                        _issue(
                            location,
                            "bindingRoots must strictly match registry/compiled capability roots",
                        )
                    )
        environment = item.get("environment")
        layer = item.get("testLayer")
        if environment not in ENVIRONMENTS or layer not in LAYERS:
            issues.append(_issue(location, "environment/testLayer is not a required conformance cell"))
        elif item.get("executionProfile") != CELL_PROFILES[(environment, layer)]:
            issues.append(_issue(location, "executionProfile does not match the nine-cell contract"))
        else:
            selected_binding = _selected_binding(
                compiled_governance,
                capability_id=capability_id,
                environment=environment,
            )
            selected_adapter_id = (
                selected_binding.get("adapter_id")
                if isinstance(selected_binding, Mapping)
                else None
            )
            if not isinstance(selected_adapter_id, str):
                issues.append(
                    _issue(
                        location,
                        "capability has no selected Binding adapter in this evidence environment",
                    )
                )
            elif adapter_id != selected_adapter_id:
                issues.append(
                    _issue(
                        location,
                        "adapterId does not match the environment-selected Binding adapter",
                    )
                )
            if environment not in adapter.get("allowed_environments", []):
                issues.append(_issue(location, "adapterId is not allowed in this environment"))
            implementation_status = adapter.get("implementation_status")
            accepted_statuses = (
                {
                    *governance.READY_IMPLEMENTATION_STATUSES,
                    "mock",
                    "test_fixture_only",
                    "sandbox",
                }
                if environment == "alpha"
                else governance.READY_IMPLEMENTATION_STATUSES
            )
            if implementation_status not in accepted_statuses:
                issues.append(
                    _issue(
                        location,
                        "adapterId implementation is not eligible for this environment evidence",
                    )
                )
        cell = (str(capability_id), str(environment), str(layer))
        if cell in duplicate_cells:
            issues.append(_issue(location, "duplicates a Capability/environment/layer cell"))
        duplicate_cells.add(cell)
        if item.get("status") not in {"passed", "blocked", "failed"}:
            issues.append(_issue(location, "status must be passed, blocked or failed"))
        parsed_time: datetime | None = None
        try:
            parsed_time = datetime.fromisoformat(str(item["executedAt"]).replace("Z", "+00:00"))
            if parsed_time.tzinfo is None:
                raise ValueError("missing timezone")
            if parsed_time > datetime.now(timezone.utc):
                issues.append(_issue(location, "executedAt cannot be in the future"))
            elif current_commit is not None and datetime.now(timezone.utc) - parsed_time > MAX_EVIDENCE_AGE:
                issues.append(_issue(location, "executedAt exceeds the 24-hour readiness window"))
        except (TypeError, ValueError):
            issues.append(_issue(location, "executedAt must be an ISO-8601 timestamp with timezone"))
        artifact_path: Path | None = None
        artifact_ref = item.get("artifactRef")
        if not isinstance(artifact_ref, str) or not artifact_ref.startswith(
            f".qwq_output/env/{environment}/runs/"
        ):
            issues.append(_issue(location, "artifactRef must remain inside its environment run root"))
        else:
            artifact_path = _output_path(artifact_ref, root=configured_root)
            if artifact_path is None or not artifact_path.exists():
                issues.append(_issue(location, "artifactRef must resolve to an existing output artifact"))
            elif configured_root.resolve() not in artifact_path.parents and artifact_path != configured_root:
                issues.append(_issue(location, "artifactRef escapes configured output root"))
            elif artifact_ref in artifact_refs:
                issues.append(_issue(location, "artifactRef must identify one conformance cell only"))
            artifact_refs.add(artifact_ref)
        for field in (
            "artifactDigest",
            "imageDigest",
            "configDigest",
            "contractGraphDigest",
            "adapterDigest",
        ):
            if not isinstance(item.get(field), str) or not SHA256_PATTERN.fullmatch(str(item[field])):
                issues.append(_issue(location, f"{field} must be a sha256 digest"))
        if artifact_path is not None and artifact_path.exists():
            issues.extend(
                _validate_execution_report(
                    artifact_path=artifact_path,
                    evidence=item,
                    expected_test_source=_expected_test_source(
                        manifest,
                        adapter=adapter,
                        layer=layer,
                    ),
                )
            )
        if not isinstance(item.get("commit"), str) or not COMMIT_PATTERN.fullmatch(str(item["commit"])):
            issues.append(_issue(location, "commit must be a git commit digest"))
        elif current_commit is not None and item["commit"] != current_commit:
            issues.append(_issue(location, "commit does not match the current source revision"))
        if not isinstance(item.get("dataDigest"), str) or not SHA256_PATTERN.fullmatch(str(item["dataDigest"])):
            issues.append(_issue(location, "dataDigest must be a sha256 digest"))
        if not isinstance(item.get("assertionCount"), int) or item["assertionCount"] <= 0:
            issues.append(_issue(location, "assertionCount must be greater than zero"))
        assertion_ids = item.get("assertionIds")
        if (
            not isinstance(assertion_ids, list)
            or not assertion_ids
            or not all(
                isinstance(assertion_id, str) and ASSERTION_ID_PATTERN.fullmatch(assertion_id)
                for assertion_id in assertion_ids
            )
            or len(assertion_ids) != len(set(assertion_ids))
        ):
            issues.append(_issue(location, "assertionIds must be a non-empty unique stable list"))
        else:
            profile = adapter.get("conformance_profile")
            profile_ids = (
                profile_assertion_ids.get(profile, [])
                if isinstance(profile_assertion_ids, Mapping)
                else []
            )
            required_assertion_ids = {
                *(common_assertion_ids if isinstance(common_assertion_ids, list) else []),
                *(profile_ids if isinstance(profile_ids, list) else []),
            }
            missing_assertions = required_assertion_ids - set(assertion_ids)
            if missing_assertions:
                issues.append(
                    _issue(
                        location,
                        f"assertionIds omit required scenarios {sorted(missing_assertions)}",
                    )
                )
            if item.get("assertionCount") != len(assertion_ids):
                issues.append(_issue(location, "assertionCount must equal assertionIds length"))
        if item.get("networkBoundary") not in {
            "offline_harness",
            "local_protocol",
            "remote_protocol",
            "user_journey",
        }:
            issues.append(_issue(location, "networkBoundary is invalid"))
        elif layer == "local_contract" and item["networkBoundary"] != "offline_harness":
            issues.append(_issue(location, "local_contract must use offline_harness"))
        elif layer == "api_integration" and item["networkBoundary"] != "remote_protocol":
            issues.append(_issue(location, "api_integration must use remote_protocol"))
        elif layer == "user_acceptance" and item["networkBoundary"] != "user_journey":
            issues.append(_issue(location, "user_acceptance must use user_journey"))
        if not _is_non_empty_string(item.get("cleanupReceipt")):
            issues.append(_issue(location, "cleanupReceipt must be non-empty"))
        acceptance_refs = item.get("acceptanceRefs")
        if not isinstance(acceptance_refs, list) or not acceptance_refs or not all(
            isinstance(ref, str) and ref.startswith("specs/feature-tree/") for ref in acceptance_refs
        ):
            issues.append(
                _issue(location, "acceptanceRefs must be non-empty feature-tree references")
            )
        observability_refs = item.get("observabilityRefs")
        if (
            not isinstance(observability_refs, Mapping)
            or set(observability_refs) != {"logs", "traces", "metrics"}
            or not all(
                isinstance(observability_refs[facet], list)
                and observability_refs[facet]
                and all(_is_non_empty_string(ref) for ref in observability_refs[facet])
                for facet in ("logs", "traces", "metrics")
            )
        ):
            issues.append(
                _issue(location, "observabilityRefs must contain non-empty logs/traces/metrics lists")
            )
        else:
            required_metric_refs_for_capability = required_metric_refs(
                capability_id if isinstance(capability_id, str) else ""
            )
            if not set(required_metric_refs_for_capability).issubset(
                set(observability_refs["metrics"])
            ):
                issues.append(
                    _issue(
                        location,
                        "runtime.message.transport metrics must include fixed non-sensitive "
                        "pending_lag/dead_letter/publish_p95/consume_p95 references",
                    )
                )
        if item["status"] == "passed" and "failure" in item:
            issues.append(_issue(location, "passed evidence must not contain failure"))
        if item["status"] != "passed":
            failure = item.get("failure")
            if not isinstance(failure, Mapping) or not _is_non_empty_string(failure.get("code")):
                issues.append(_issue(location, "blocked/failed evidence requires failure.code"))
        is_gamma_release_cell = environment == "gamma" and layer == "user_acceptance"
        if is_gamma_release_cell and not _release_readiness_valid(item):
            issues.append(
                _issue(
                    location,
                    "Gamma release user_acceptance requires complete non-sensitive releaseReadiness receipts",
                )
            )
        elif not is_gamma_release_cell and "releaseReadiness" in item:
            issues.append(
                _issue(
                    location,
                    "releaseReadiness is reserved for the Gamma release user_acceptance cell",
                )
            )
    return issues


def _digest(value: object) -> str | None:
    return value if isinstance(value, str) and SHA256_PATTERN.fullmatch(value) else None


def _commit_digest(value: object) -> str | None:
    return value if isinstance(value, str) and COMMIT_PATTERN.fullmatch(value) else None


def _assertion_semantics(cell: Mapping[str, Any]) -> tuple[str, ...] | None:
    assertion_ids = cell.get("assertionIds")
    if (
        not isinstance(assertion_ids, list)
        or not assertion_ids
        or not all(
            isinstance(assertion_id, str) and ASSERTION_ID_PATTERN.fullmatch(assertion_id)
            for assertion_id in assertion_ids
        )
    ):
        return None
    return tuple(sorted(assertion_ids))


def _cells_share_release(
    cells: Iterable[Mapping[str, Any] | None],
    *,
    expected_environments: Iterable[str],
    require_adapter_digest: bool,
) -> bool:
    evidence_cells = list(cells)
    if not evidence_cells or any(
        cell is None or cell.get("status") != "passed" for cell in evidence_cells
    ):
        return False
    concrete_cells = [cell for cell in evidence_cells if cell is not None]
    release_digests = {
        (
            _commit_digest(cell.get("commit")),
            _digest(cell.get("imageDigest")),
            _digest(cell.get("contractGraphDigest")),
        )
        for cell in concrete_cells
    }
    if len(release_digests) != 1 or any(None in digest for digest in release_digests):
        return False
    if len({_assertion_semantics(cell) for cell in concrete_cells}) != 1:
        return False
    if any(_assertion_semantics(cell) is None for cell in concrete_cells):
        return False
    for environment in expected_environments:
        environment_cells = [
            cell for cell in concrete_cells if cell.get("environment") == environment
        ]
        if not environment_cells or len(
            {_digest(cell.get("configDigest")) for cell in environment_cells}
        ) != 1:
            return False
        if _digest(environment_cells[0].get("configDigest")) is None:
            return False
    if require_adapter_digest:
        adapter_digests = {_digest(cell.get("adapterDigest")) for cell in concrete_cells}
        if len(adapter_digests) != 1 or None in adapter_digests:
            return False
    return True


def derive_readiness(
    *,
    compiled: Mapping[str, Any],
    evidence: Iterable[Mapping[str, Any]],
) -> dict[str, dict[str, dict[str, Any]]]:
    by_cell: dict[tuple[str, str, str], Mapping[str, Any]] = {}
    for item in evidence:
        adapter_id = item.get("adapterId")
        capability_id = item.get("capabilityId")
        environment = item.get("environment")
        layer = item.get("testLayer")
        if all(isinstance(value, str) for value in (adapter_id, capability_id, environment, layer)):
            if (
                _selected_adapter_id(
                    compiled,
                    capability_id=capability_id,
                    environment=environment,
                )
                == adapter_id
                and environment in ENVIRONMENTS
                and layer in LAYERS
            ):
                by_cell[(capability_id, environment, layer)] = item

    selected_adapter_environments: dict[tuple[str, str], set[str]] = defaultdict(set)
    for environment in ENVIRONMENTS:
        selected_bindings = compiled.get("selectedBindings", {})
        environment_bindings = (
            selected_bindings.get(environment)
            if isinstance(selected_bindings, Mapping)
            else None
        )
        if not isinstance(environment_bindings, Mapping):
            continue
        for capability_id, binding in environment_bindings.items():
            if not isinstance(capability_id, str) or not isinstance(binding, Mapping):
                continue
            adapter_id = binding.get("adapter_id")
            if isinstance(adapter_id, str):
                selected_adapter_environments[(capability_id, adapter_id)].add(environment)

    adapter_ready: dict[tuple[str, str], bool] = {}
    for (capability_id, adapter_id), selected_environments in selected_adapter_environments.items():
        expected_cells = [
            by_cell.get((capability_id, environment, layer))
            for environment in sorted(selected_environments)
            for layer in LAYERS
        ]
        adapter_evidence_ready = _cells_share_release(
            expected_cells,
            expected_environments=selected_environments,
            require_adapter_digest=True,
        )
        preflight_ready = all(
            _binding_preflight_ready(
                compiled,
                capability_id=capability_id,
                environment=environment,
            )
            for environment in selected_environments
        )
        adapter_ready[(capability_id, adapter_id)] = (
            adapter_evidence_ready and preflight_ready
        )

    result: dict[str, dict[str, dict[str, Any]]] = {}
    for environment, capabilities in compiled.get("readiness", {}).items():
        environment_result: dict[str, dict[str, Any]] = {}
        for capability_id, baseline in capabilities.items():
            item = dict(baseline)
            adapter_id = item.get("adapter_id")
            expected_cells = [
                by_cell.get((capability_id, evidence_environment, layer))
                for evidence_environment in ENVIRONMENTS
                for layer in LAYERS
            ]
            capability_matrix_ready = _cells_share_release(
                expected_cells,
                expected_environments=ENVIRONMENTS,
                require_adapter_digest=False,
            )
            gamma_release_cell = by_cell.get(
                (capability_id, "gamma", "user_acceptance")
            )
            gamma_release_ready = (
                gamma_release_cell is not None
                and gamma_release_cell.get("status") == "passed"
                and _release_readiness_valid(gamma_release_cell)
            )
            matrix_selected_adapters_ready = all(
                adapter_ready.get(
                    (
                        capability_id,
                        _selected_adapter_id(
                            compiled,
                            capability_id=capability_id,
                            environment=evidence_environment,
                        ),
                    ),
                    False,
                )
                for evidence_environment in ENVIRONMENTS
            )
            selected_adapter_ready = (
                adapter_ready.get((capability_id, adapter_id), False)
                if isinstance(adapter_id, str)
                else False
            )
            item["evidence_ready"] = capability_matrix_ready
            item["adapter_ready"] = selected_adapter_ready
            item["gamma_release_ready"] = gamma_release_ready
            item["matrix_selected_adapters_ready"] = matrix_selected_adapters_ready
            item["capability_ready"] = (
                item.get("state") == "enabled"
                and bool(item.get("adapter_preflight_ready"))
                and selected_adapter_ready
                and capability_matrix_ready
                and matrix_selected_adapters_ready
                and gamma_release_ready
            )
            environment_result[capability_id] = item
        result[environment] = environment_result
    return result


def load_validate_and_derive(
    *, root: Path | None = None
) -> tuple[dict[str, Any], list[str]]:
    compiled, governance_issues = governance.load_and_compile()
    evidence, evidence_load_issues = load_evidence(root)
    current_commit = _current_commit()
    current_commit_issues = (
        ["cannot determine the current git revision for evidence validation"]
        if evidence and current_commit is None
        else []
    )
    evidence_issues = validate_evidence(
        evidence,
        registry=governance.load_registry(),
        root=root,
        current_commit=current_commit,
        conformance_manifest=governance.load_conformance_manifest(),
    )
    readiness = derive_readiness(compiled=compiled, evidence=evidence)
    report = {
        "schema": "provider-conformance-readiness",
        "version": 1,
        "evidenceCount": len(evidence),
        "readiness": readiness,
        "issues": [
            *(issue.render() for issue in governance_issues),
            *evidence_load_issues,
            *current_commit_issues,
            *evidence_issues,
        ],
    }
    return report, report["issues"]


def readiness_issues(
    report: Mapping[str, Any],
    *,
    environment: str,
) -> list[str]:
    if environment not in READINESS_ENVIRONMENTS:
        return [_issue("readiness", f"unsupported readiness environment {environment}")]
    evidence_count = report.get("evidenceCount")
    if not isinstance(evidence_count, int) or evidence_count <= 0:
        return [
            _issue(
                f"readiness.{environment}",
                "zero Provider Conformance evidence artifacts cannot satisfy release readiness",
            )
        ]
    readiness_by_environment = report.get("readiness")
    readiness = (
        readiness_by_environment.get(environment)
        if isinstance(readiness_by_environment, Mapping)
        else None
    )
    if not isinstance(readiness, Mapping):
        return [_issue(f"readiness.{environment}", "is unavailable")]
    issues: list[str] = []
    for capability_id, capability_readiness in readiness.items():
        if not isinstance(capability_readiness, Mapping):
            continue
        if capability_readiness.get("required") and not capability_readiness.get(
            "capability_ready"
        ):
            issues.append(
                _issue(
                    f"readiness.{environment}.{capability_id}",
                    "required capability lacks current selected-Binding release evidence",
                )
            )
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate Provider Conformance evidence and calculate readiness."
    )
    parser.add_argument("--require-ready", choices=READINESS_ENVIRONMENTS)
    args = parser.parse_args()
    report, issues = load_validate_and_derive()
    if args.require_ready:
        issues.extend(readiness_issues(report, environment=args.require_ready))
        report["issues"] = issues
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
