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
import shlex
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib import external_provider_governance as governance
from quwoquan_ops.cli.lib.output_paths import output_root


EVIDENCE_SCHEMA = ROOT / "quwoquan_ops" / "environments" / "provider_conformance_evidence.schema.json"
# Alpha/Beta/Gamma exercise Port-equivalent substitutes. Prod owns the
# independent hosted real-Provider rollout receipt.
ENVIRONMENTS = ("alpha", "beta", "gamma")
RELEASE_ENVIRONMENT = "prod"
RELEASE_READINESS_ENVIRONMENTS = frozenset({RELEASE_ENVIRONMENT})
EVIDENCE_ENVIRONMENTS = (*ENVIRONMENTS, RELEASE_ENVIRONMENT)
READINESS_ENVIRONMENTS = EVIDENCE_ENVIRONMENTS
LAYERS = ("local_contract", "api_integration", "user_acceptance")
CELL_PROFILES = {
    ("alpha", "local_contract"): "baseline",
    ("beta", "local_contract"): "baseline",
    ("gamma", "local_contract"): "baseline",
    ("alpha", "api_integration"): "smoke",
    ("beta", "api_integration"): "integration",
    ("gamma", "api_integration"): "release",
    ("alpha", "user_acceptance"): "smoke",
    ("beta", "user_acceptance"): "integration",
    ("gamma", "user_acceptance"): "release",
}


def execution_profile_for(environment: str, layer: str) -> str | None:
    """Return the only permitted profile for a conformance evidence cell."""
    if environment == RELEASE_ENVIRONMENT:
        return "release" if layer == "user_acceptance" else None
    return CELL_PROFILES.get((environment, layer))


def requires_release_readiness(environment: str, layer: str) -> bool:
    return environment in RELEASE_READINESS_ENVIRONMENTS and layer == "user_acceptance"
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
        "testArtifactRef",
        "testArtifactDigest",
        "testSource",
        "testSourceDigest",
        "testCommand",
        "testTarget",
        "typedPort",
        "contractRef",
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
        "bindingPreflightReceiptRef",
        "adapterHealthReceiptRef",
        "switchCompatibilityReceiptRef",
        "callbackDrainReceiptRef",
        "lastGoodReceiptRef",
        "rollbackReceiptRef",
    }
)
EXECUTION_REPORT_SCHEMA = "provider-conformance-test-report"
EXECUTION_REPORT_VERSION = 2
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
        "testArtifactRef",
        "testArtifactDigest",
        "testSource",
        "testSourceDigest",
        "testCommand",
        "testTarget",
        "typedPort",
        "contractRef",
        "assertionIds",
        "networkBoundary",
        "dataDigest",
        "testSource",
        "testCommand",
        "exitCode",
    }
)
CASE_RESULT_SCHEMA = "provider-conformance-case-results"
CASE_RESULT_VERSION = 1
CASE_RESULT_REQUIRED_FIELDS = frozenset(
    {
        "schema",
        "version",
        "status",
        "adapterId",
        "capabilityId",
        "environment",
        "testLayer",
        "typedPort",
        "contractRef",
        "networkBoundary",
        "testTarget",
        "configDigest",
        "assertionIds",
        "caseResults",
        "dataDigest",
        "cleanupReceipt",
        "observabilityRefs",
    }
)
CASE_RESULT_RELEASE_FIELDS = frozenset({"releaseReadiness"})
B10_REMOTE_READBACK_SCHEMA = "b10-remote-uat-readback"
CASE_RESULT_B10_REMOTE_FIELDS = frozenset({"nativeReadback"})
NATIVE_READBACK_ARTIFACT_RE = re.compile(
    r"^[a-z0-9][a-z0-9._-]*\.native-device-readback\.json$"
)
SOURCE_METADATA_RE = re.compile(
    r"^\s*(?:#|//)\s*provider_conformance:\s*(\{.+\})\s*$"
)
SOURCE_STATIC_BLOCK_RE = re.compile(
    r"\b(?:should[\s_-]*block|gate[\s_-]*block|not[\s_-]*run|dry[\s_-]*run)\b",
    re.IGNORECASE,
)
SOURCE_DYNAMIC_EXECUTOR_RE = re.compile(
    r"(?:QWQ_PROVIDER_CONFORMANCE_EXECUTOR_COMMAND_JSON|"
    r"external_provider_executor)",
)
TEST_LAYER_ROOTS = {
    "local_contract": ROOT / "quwoquan_ops" / "tests" / "local_contract",
    "api_integration": ROOT
    / "quwoquan_ops"
    / "tests"
    / "acceptance"
    / "api_integration",
    "user_acceptance": ROOT
    / "quwoquan_ops"
    / "tests"
    / "acceptance"
    / "user_acceptance",
}
PUBLIC_ASSERTION_IDS = frozenset(
    {
        "provider.success",
        "provider.validation",
        "provider.auth",
        "provider.network_dns",
        "provider.timeout",
        "provider.throttle",
        "provider.retry",
        "provider.idempotency",
        "provider.callback_ordering",
        "provider.redaction",
        "provider.observability",
    }
)
RELEASE_ASSERTION_IDS = frozenset(
    {
        "provider.adapter_health",
        "provider.adapter_switch",
        "provider.adapter_rollback",
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
    for environment in EVIDENCE_ENVIRONMENTS:
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


def network_boundary_for_layer(layer: str) -> str:
    return {
        "local_contract": "offline_harness",
        "api_integration": "remote_protocol",
        "user_acceptance": "user_journey",
    }[layer]


def capability_assertion_id(capability: Mapping[str, Any]) -> str:
    profile = capability.get("conformance_profile")
    if not isinstance(profile, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", profile):
        raise ValueError("capability conformance_profile must be a stable identifier")
    return f"provider.{profile}"


def _digest_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def implementation_digest(path: Path) -> str | None:
    """Digest one Adapter source file or its deterministic source closure."""
    try:
        if path.is_file():
            return _digest_bytes(path.read_bytes())
        if not path.is_dir():
            return None
        source_suffixes = {
            ".c",
            ".cc",
            ".go",
            ".h",
            ".html",
            ".java",
            ".js",
            ".kt",
            ".mod",
            ".proto",
            ".py",
            ".rs",
            ".sh",
            ".sql",
            ".sum",
            ".swift",
            ".tmpl",
            ".ts",
        }
        files = sorted(
            candidate
            for candidate in path.rglob("*")
            if candidate.is_file()
            and candidate.suffix in source_suffixes
            and not candidate.name.endswith("_test.go")
            and not any(
                part in {"testdata", "tests", ".git", ".qwq_output"}
                for part in candidate.relative_to(path).parts
            )
        )
        if not files:
            return None
        digest = hashlib.sha256()
        for candidate in files:
            digest.update(candidate.relative_to(path).as_posix().encode("utf-8"))
            digest.update(b"\0")
            digest.update(candidate.read_bytes())
            digest.update(b"\0")
        return f"sha256:{digest.hexdigest()}"
    except OSError:
        return None


def binding_config_digest(
    binding: Mapping[str, Any],
    binding_roots: Iterable[Mapping[str, Any]],
) -> str:
    """Digest the compiled Binding selected for a concrete execution cell."""
    return _digest_bytes(
        json.dumps(
            {
                "binding": binding,
                "bindingRoots": list(binding_roots),
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    )


def _source_spec_refs(raw_source: str, *, location: str) -> list[str]:
    refs = [
        match.group(1)
        for line in raw_source.splitlines()
        if (
            match := re.match(r"^\s*(?://|#)\s*spec_ref:\s*(\S+)\s*$", line)
        )
        is not None
    ]
    if not refs:
        raise ValueError(f"{location} must declare at least one spec_ref")
    return list(dict.fromkeys(refs))


def _source_metadata(raw_source: str, *, location: str) -> Mapping[str, Any]:
    declarations = [
        match.group(1)
        for line in raw_source.splitlines()
        if (match := SOURCE_METADATA_RE.match(line)) is not None
    ]
    if len(declarations) != 1:
        raise ValueError(
            f"{location} must declare exactly one provider_conformance JSON header"
        )
    try:
        metadata = json.loads(declarations[0])
    except json.JSONDecodeError as exc:
        raise ValueError(f"{location} has invalid provider_conformance JSON: {exc}") from exc
    if not isinstance(metadata, Mapping):
        raise ValueError(f"{location} provider_conformance header must be an object")
    return metadata


def load_test_source(
    path: Path,
    *,
    capabilities: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Load a self-describing executable Provider Conformance source.

    The test source, instead of a registry/manifest, declares its identity,
    exact command and target. Its command must write a CaseResult document to
    ``QWQ_PROVIDER_CONFORMANCE_RESULT_PATH``.
    """
    try:
        resolved = path.resolve()
        relative = resolved.relative_to(ROOT.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError("Provider Conformance test source must be inside the repository") from exc
    if not resolved.is_file() or resolved.suffix not in {".py", ".go"}:
        raise ValueError(f"{relative} is not a supported Provider Conformance test source")
    raw = resolved.read_text(encoding="utf-8")
    metadata = _source_metadata(raw, location=relative)
    required = {
        "adapterId",
        "capabilityId",
        "testLayer",
        "typedPort",
        "contractRef",
        "assertionIds",
        "command",
        "target",
        "networkBoundary",
    }
    if set(metadata) != required:
        raise ValueError(
            f"{relative} provider_conformance header fields must be exactly {sorted(required)}"
        )
    layer = metadata.get("testLayer")
    if layer not in LAYERS:
        raise ValueError(f"{relative} declares an unsupported testLayer")
    layer_root = TEST_LAYER_ROOTS[str(layer)].resolve()
    if layer_root not in resolved.parents:
        raise ValueError(f"{relative} must live under the declared {layer} test root")
    adapter_id = metadata.get("adapterId")
    capability_id = metadata.get("capabilityId")
    typed_port = metadata.get("typedPort")
    contract_ref = metadata.get("contractRef")
    target = metadata.get("target")
    command = metadata.get("command")
    assertion_ids = metadata.get("assertionIds")
    if not isinstance(adapter_id, str) or not ADAPTER_PATTERN.fullmatch(adapter_id):
        raise ValueError(f"{relative} declares an invalid adapterId")
    if not isinstance(capability_id, str) or not CAPABILITY_PATTERN.fullmatch(capability_id):
        raise ValueError(f"{relative} declares an invalid capabilityId")
    if not all(_is_non_empty_string(value) for value in (typed_port, contract_ref, target)):
        raise ValueError(f"{relative} must declare typedPort, contractRef and target")
    if (
        not isinstance(command, list)
        or not command
        or not all(_is_non_empty_string(item) and "\n" not in item for item in command)
    ):
        raise ValueError(f"{relative} must declare a concrete argv command")
    if any(
        re.search(r"(?:--dry-run|\bdry[\s_-]*run\b)", item, re.IGNORECASE)
        for item in command
    ):
        raise ValueError(f"{relative} command must not declare a dry-run")
    if (
        not isinstance(assertion_ids, list)
        or not assertion_ids
        or len(assertion_ids) != len(set(assertion_ids))
        or not all(
            isinstance(assertion_id, str)
            and ASSERTION_ID_PATTERN.fullmatch(assertion_id)
            for assertion_id in assertion_ids
        )
    ):
        raise ValueError(f"{relative} must declare unique stable assertionIds")
    missing_public = PUBLIC_ASSERTION_IDS - set(assertion_ids)
    if missing_public:
        raise ValueError(
            f"{relative} omits mandatory public assertions {sorted(missing_public)}"
        )
    if capabilities is None:
        capabilities = {
            str(capability["capability_id"]): capability
            for capability in governance.load_registry().get("capabilities", [])
            if isinstance(capability, Mapping) and capability.get("capability_id")
        }
    capability = capabilities.get(str(capability_id))
    if capability is None:
        raise ValueError(f"{relative} declares an unknown capabilityId")
    expected_capability_assertion = capability_assertion_id(capability)
    if expected_capability_assertion not in assertion_ids:
        raise ValueError(
            f"{relative} omits capability assertion {expected_capability_assertion}"
        )
    if typed_port != capability.get("canonical_port"):
        raise ValueError(f"{relative} typedPort does not match the canonical capability Port")
    if contract_ref != capability.get("source"):
        raise ValueError(f"{relative} contractRef does not match the capability source")
    if metadata.get("networkBoundary") != network_boundary_for_layer(str(layer)):
        raise ValueError(f"{relative} networkBoundary conflicts with its testLayer")
    if "QWQ_PROVIDER_CONFORMANCE_RESULT_PATH" not in raw:
        raise ValueError(
            f"{relative} must write command results to QWQ_PROVIDER_CONFORMANCE_RESULT_PATH"
        )
    if layer in {"api_integration", "user_acceptance"} and SOURCE_STATIC_BLOCK_RE.search(raw):
        raise ValueError(
            f"{relative} is a static should-block/GATE_BLOCK test and cannot prove remote evidence"
        )
    if SOURCE_DYNAMIC_EXECUTOR_RE.search(raw):
        raise ValueError(
            f"{relative} delegates to a runtime-selected executor and cannot prove "
            "the declared Adapter/target"
        )
    return {
        **dict(metadata),
        "testSource": relative,
        "testSourceDigest": _digest_bytes(raw.encode("utf-8")),
        "acceptanceRefs": _source_spec_refs(raw, location=relative),
    }


def discover_test_sources() -> tuple[dict[tuple[str, str, str], dict[str, Any]], list[str]]:
    """Discover source-declared harnesses without a path or assertion registry."""
    sources: dict[tuple[str, str, str], dict[str, Any]] = {}
    issues: list[str] = []
    capabilities = {
        str(capability["capability_id"]): capability
        for capability in governance.load_registry().get("capabilities", [])
        if isinstance(capability, Mapping) and capability.get("capability_id")
    }
    for root in TEST_LAYER_ROOTS.values():
        if not root.is_dir():
            continue
        paths = [
            *root.rglob("*provider_conformance*.py"),
            *root.rglob("*provider_conformance*.go"),
        ]
        for path in sorted(paths):
            raw = path.read_text(encoding="utf-8")
            if not any(
                SOURCE_METADATA_RE.match(line) for line in raw.splitlines()
            ):
                continue
            try:
                source = load_test_source(path, capabilities=capabilities)
            except (OSError, ValueError) as exc:
                issues.append(str(exc))
                continue
            key = (
                str(source["capabilityId"]),
                str(source["adapterId"]),
                str(source["testLayer"]),
            )
            if key in sources:
                issues.append(
                    f"{source['testSource']} duplicates Provider Conformance source "
                    f"for capability/adapter/layer {key}"
                )
                continue
            sources[key] = source
    return sources, issues


def source_for_cell(
    *,
    capability_id: str,
    adapter_id: str,
    layer: str,
    sources: Mapping[tuple[str, str, str], Mapping[str, Any]] | None = None,
) -> Mapping[str, Any] | None:
    catalog, _ = discover_test_sources() if sources is None else (sources, [])
    return catalog.get((capability_id, adapter_id, layer))


def source_coverage_issues(
    *,
    compiled: Mapping[str, Any],
    sources: Mapping[tuple[str, str, str], Mapping[str, Any]] | None = None,
) -> list[str]:
    """Return release-blocking gaps in the selected-Binding source catalog.

    One self-describing source may serve the same Adapter in more than one
    environment, so coverage is evaluated by the unique
    Capability/Adapter/layer key consumed by ``source_for_cell`` rather than
    by blindly counting all nine environment cells.
    """

    catalog, discovery_issues = (
        discover_test_sources() if sources is None else (dict(sources), [])
    )
    issues = list(discovery_issues)
    required: dict[str, set[tuple[str, str]]] = defaultdict(set)
    selected_bindings = compiled.get("selectedBindings")
    if not isinstance(selected_bindings, Mapping):
        return [*issues, _issue("source_coverage", "compiled selected Bindings are unavailable")]
    for environment in ENVIRONMENTS:
        environment_bindings = selected_bindings.get(environment)
        if not isinstance(environment_bindings, Mapping):
            issues.append(
                _issue(
                    f"source_coverage.{environment}",
                    "compiled selected Bindings are unavailable",
                )
            )
            continue
        for capability_id, binding in environment_bindings.items():
            if not isinstance(capability_id, str) or not isinstance(binding, Mapping):
                continue
            adapter_id = binding.get("adapter_id")
            if not isinstance(adapter_id, str):
                issues.append(
                    _issue(
                        f"source_coverage.{environment}.{capability_id}",
                        "selected Binding has no Adapter ID",
                    )
                )
                continue
            required[capability_id].update((adapter_id, layer) for layer in LAYERS)
    release_bindings = selected_bindings.get(RELEASE_ENVIRONMENT)
    if not isinstance(release_bindings, Mapping):
        issues.append(
            _issue(
                f"source_coverage.{RELEASE_ENVIRONMENT}",
                "compiled selected Bindings are unavailable",
            )
        )
    else:
        for capability_id, binding in release_bindings.items():
            if not isinstance(capability_id, str) or not isinstance(binding, Mapping):
                continue
            adapter_id = binding.get("adapter_id")
            if not isinstance(adapter_id, str):
                issues.append(
                    _issue(
                        f"source_coverage.{RELEASE_ENVIRONMENT}.{capability_id}",
                        "selected Binding has no Adapter ID",
                    )
                )
                continue
            required[capability_id].add((adapter_id, "user_acceptance"))
    for capability_id, cells in sorted(required.items()):
        missing = [
            f"{adapter_id}/{layer}"
            for adapter_id, layer in sorted(cells)
            if (capability_id, adapter_id, layer) not in catalog
        ]
        if missing:
            issues.append(
                _issue(
                    f"source_coverage.{capability_id}",
                    "missing self-describing executable sources for " + ", ".join(missing),
                )
            )
    return issues


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


def _observability_refs_valid(value: object) -> bool:
    return (
        isinstance(value, Mapping)
        and set(value) == {"logs", "traces", "metrics"}
        and all(
            isinstance(value[facet], list)
            and value[facet]
            and all(_is_non_empty_string(ref) for ref in value[facet])
            for facet in ("logs", "traces", "metrics")
        )
    )


def _b10_native_readback_valid(
    value: object,
    *,
    case_result_path: Path,
) -> bool:
    """Verify the B10 device readback sidecar is present and content-bound."""
    if not isinstance(value, Mapping) or set(value) != {
        "schema",
        "artifactName",
        "artifactDigest",
    }:
        return False
    if value.get("schema") != B10_REMOTE_READBACK_SCHEMA:
        return False
    artifact_name = value.get("artifactName")
    artifact_digest = value.get("artifactDigest")
    if (
        not isinstance(artifact_name, str)
        or not NATIVE_READBACK_ARTIFACT_RE.fullmatch(artifact_name)
        or not isinstance(artifact_digest, str)
        or not SHA256_PATTERN.fullmatch(artifact_digest)
    ):
        return False
    artifact_path = case_result_path.parent / artifact_name
    try:
        actual_digest = f"sha256:{hashlib.sha256(artifact_path.read_bytes()).hexdigest()}"
    except OSError:
        return False
    return hmac.compare_digest(artifact_digest, actual_digest)


def load_case_results(
    artifact_path: Path,
    *,
    source: Mapping[str, Any],
    environment: str,
    config_digest: str,
) -> tuple[dict[str, Any] | None, list[str]]:
    """Validate the real test-owned CaseResult artifact for one execution cell."""
    issues: list[str] = []
    try:
        result = json.loads(artifact_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, [_issue(str(artifact_path), f"invalid CaseResult artifact: {exc}")]
    if not isinstance(result, dict):
        return None, [_issue(str(artifact_path), "CaseResult artifact root must be an object")]
    is_release_case = requires_release_readiness(
        environment,
        str(source.get("testLayer") or ""),
    )
    is_b10_remote_case = is_release_case and str(source.get("target") or "").startswith(
        "b10-remote-"
    )
    expected_fields = (
        CASE_RESULT_REQUIRED_FIELDS
        | CASE_RESULT_RELEASE_FIELDS
        | (CASE_RESULT_B10_REMOTE_FIELDS if is_b10_remote_case else frozenset())
        if is_release_case
        else CASE_RESULT_REQUIRED_FIELDS
    )
    missing = expected_fields - set(result)
    unknown = set(result) - expected_fields
    if missing or unknown:
        if missing:
            issues.append(
                _issue(str(artifact_path), f"CaseResult missing fields {sorted(missing)}")
            )
        if unknown:
            issues.append(
                _issue(str(artifact_path), f"CaseResult contains unknown fields {sorted(unknown)}")
            )
        return None, issues
    if (
        result.get("schema") != CASE_RESULT_SCHEMA
        or result.get("version") != CASE_RESULT_VERSION
    ):
        issues.append(_issue(str(artifact_path), "CaseResult has unsupported schema/version"))
    expected = {
        "adapterId": source.get("adapterId"),
        "capabilityId": source.get("capabilityId"),
        "environment": environment,
        "testLayer": source.get("testLayer"),
        "typedPort": source.get("typedPort"),
        "contractRef": source.get("contractRef"),
        "networkBoundary": source.get("networkBoundary"),
        "testTarget": source.get("target"),
        "configDigest": config_digest,
    }
    for field, value in expected.items():
        if result.get(field) != value:
            issues.append(
                _issue(
                    str(artifact_path),
                    f"CaseResult {field} does not match the executed source/binding",
                )
            )
    if result.get("status") != "passed":
        issues.append(_issue(str(artifact_path), "CaseResult status must be passed"))
    assertion_ids = result.get("assertionIds")
    expected_assertion_ids = source.get("assertionIds")
    if (
        not isinstance(assertion_ids, list)
        or not assertion_ids
        or len(assertion_ids) != len(set(assertion_ids))
        or tuple(sorted(assertion_ids)) != tuple(sorted(expected_assertion_ids or []))
    ):
        issues.append(
            _issue(
                str(artifact_path),
                "CaseResult assertionIds must exactly match its source-declared assertion set",
            )
        )
    cases = result.get("caseResults")
    if not isinstance(cases, list) or len(cases) != len(assertion_ids or []):
        issues.append(
            _issue(
                str(artifact_path),
                "CaseResult must contain exactly one result for every assertionId",
            )
        )
    else:
        case_ids: list[str] = []
        for case in cases:
            if (
                not isinstance(case, Mapping)
                or set(case) != {"assertionId", "status", "logRef", "traceRef", "metricRefs"}
                or not _is_non_empty_string(case.get("assertionId"))
                or case.get("status") != "passed"
                or not _is_non_empty_string(case.get("logRef"))
                or not _is_non_empty_string(case.get("traceRef"))
                or not isinstance(case.get("metricRefs"), list)
                or not case["metricRefs"]
                or not all(_is_non_empty_string(ref) for ref in case["metricRefs"])
            ):
                issues.append(
                    _issue(
                        str(artifact_path),
                        "every CaseResult must be a passed assertion with log/trace/metric references",
                    )
                )
                break
            case_ids.append(str(case["assertionId"]))
        if sorted(case_ids) != sorted(assertion_ids or []):
            issues.append(
                _issue(
                    str(artifact_path),
                    "CaseResult assertion records must exactly cover assertionIds",
                )
            )
    if not isinstance(result.get("configDigest"), str) or not SHA256_PATTERN.fullmatch(
        str(result.get("configDigest"))
    ):
        issues.append(_issue(str(artifact_path), "CaseResult configDigest must be sha256"))
    if not isinstance(result.get("dataDigest"), str) or not SHA256_PATTERN.fullmatch(
        str(result.get("dataDigest"))
    ):
        issues.append(_issue(str(artifact_path), "CaseResult dataDigest must be sha256"))
    if not _valid_receipt_ref(result.get("cleanupReceipt")):
        issues.append(
            _issue(
                str(artifact_path),
                "CaseResult cleanupReceipt must be a non-sensitive receipt reference",
            )
        )
    if not _observability_refs_valid(result.get("observabilityRefs")):
        issues.append(
            _issue(
                str(artifact_path),
                "CaseResult observabilityRefs must contain logs/traces/metrics",
            )
        )
    elif isinstance(cases, list):
        observability_refs = result["observabilityRefs"]
        for case in cases:
            if not isinstance(case, Mapping):
                continue
            if (
                case.get("logRef") not in observability_refs["logs"]
                or case.get("traceRef") not in observability_refs["traces"]
                or not set(case.get("metricRefs", [])).issubset(
                    set(observability_refs["metrics"])
                )
            ):
                issues.append(
                    _issue(
                        str(artifact_path),
                        "CaseResult observabilityRefs must include each assertion's log/trace/metric references",
                    )
                )
                break
    if is_release_case and not _release_readiness_valid(result):
        issues.append(
            _issue(
                str(artifact_path),
                "release Provider CaseResult must contain test-owned release "
                "readiness receipts",
            )
        )
    if is_b10_remote_case and not _b10_native_readback_valid(
        result.get("nativeReadback"),
        case_result_path=artifact_path,
    ):
        issues.append(
            _issue(
                str(artifact_path),
                "B10 Remote CaseResult must bind an existing native-device readback "
                "sidecar with a matching digest",
            )
        )
    if re.search(
        r"(?:endpoint|secret|credential|token|password|https?://)",
        json.dumps(result, sort_keys=True),
        re.IGNORECASE,
    ):
        issues.append(
            _issue(
                str(artifact_path),
                "CaseResult must not contain endpoint, credential, token or URL values",
            )
        )
    return result, issues


def _validate_execution_report(
    *,
    artifact_path: Path,
    evidence: Mapping[str, Any],
    expected_source: Mapping[str, Any] | None,
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
        "testArtifactRef",
        "testArtifactDigest",
        "testSourceDigest",
        "testTarget",
        "typedPort",
        "contractRef",
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
    if report.get("testSource") != (
        expected_source.get("testSource") if expected_source is not None else None
    ):
        issues.append(
            _issue(
                str(artifact_path),
                "execution report testSource does not match the discovered source contract",
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


def _current_contract_graph_digest() -> str | None:
    path = ROOT / "quwoquan_service" / "generated" / "contract_graph.json"
    try:
        return _digest_bytes(path.read_bytes()) if path.is_file() else None
    except OSError:
        return None


def _current_adapter_digest(adapter: Mapping[str, Any]) -> str | None:
    implementation_path = adapter.get("implementation_path")
    if not isinstance(implementation_path, str):
        return None
    path = ROOT / implementation_path
    return implementation_digest(path)


def validate_evidence(
    evidence: Iterable[Mapping[str, Any]],
    *,
    registry: Mapping[str, Any],
    root: Path | None = None,
    current_commit: str | None = None,
    compiled: Mapping[str, Any] | None = None,
    source_catalog: Mapping[tuple[str, str, str], Mapping[str, Any]] | None = None,
    expected_image_digest: str | None = None,
) -> list[str]:
    issues: list[str] = []
    compiled_governance = compiled
    if compiled_governance is None:
        compiled_governance, _ = governance.compile_governance(
            registry,
            governance.load_bindings(),
            governance.load_conformance_manifest(),
        )
    discovered_sources, source_issues = (
        discover_test_sources() if source_catalog is None else (dict(source_catalog), [])
    )
    issues.extend(source_issues)
    expected_image = (
        expected_image_digest
        if expected_image_digest is not None
        else os.environ.get("QWQ_PROVIDER_CONFORMANCE_EXPECTED_IMAGE_DIGEST", "")
    )
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
        if item.get("schema") != "provider-conformance-evidence" or item.get("version") != 4:
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
        elif item.get("typedPort") != capability.get("canonical_port"):
            issues.append(
                _issue(location, "typedPort does not match the capability canonical typed Port")
            )
        elif item.get("contractRef") != capability.get("source"):
            issues.append(
                _issue(location, "contractRef does not match the capability contract source")
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
        expected_source: Mapping[str, Any] | None = None
        selected_binding: Mapping[str, Any] | None = None
        compiled_roots: list[dict[str, Any]] | None = None
        expected_profile = (
            execution_profile_for(environment, layer)
            if isinstance(environment, str) and isinstance(layer, str)
            else None
        )
        if expected_profile is None:
            issues.append(_issue(location, "environment/testLayer is not a required conformance cell"))
        elif item.get("executionProfile") != expected_profile:
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
            expected_source = source_for_cell(
                capability_id=str(capability_id),
                adapter_id=adapter_id,
                layer=layer,
                sources=discovered_sources,
            )
            if expected_source is None:
                issues.append(
                    _issue(
                        location,
                        "no self-describing executable Provider Conformance source exists "
                        "for the selected capability/adapter/layer",
                    )
                )
            else:
                if item.get("testSource") != expected_source.get("testSource"):
                    issues.append(
                        _issue(location, "testSource does not match the discovered source contract")
                    )
                if item.get("testSourceDigest") != expected_source.get("testSourceDigest"):
                    issues.append(
                        _issue(location, "testSourceDigest does not match current source bytes")
                    )
                if item.get("testTarget") != expected_source.get("target"):
                    issues.append(
                        _issue(location, "testTarget does not match the discovered source contract")
                    )
                if item.get("typedPort") != expected_source.get("typedPort"):
                    issues.append(
                        _issue(location, "typedPort does not match the discovered source contract")
                    )
                if item.get("contractRef") != expected_source.get("contractRef"):
                    issues.append(
                        _issue(location, "contractRef does not match the discovered source contract")
                    )
                if item.get("networkBoundary") != expected_source.get("networkBoundary"):
                    issues.append(
                        _issue(location, "networkBoundary does not match the discovered source contract")
                    )
                if item.get("acceptanceRefs") != expected_source.get("acceptanceRefs"):
                    issues.append(
                        _issue(location, "acceptanceRefs must exactly match source spec_ref values")
                    )
            if isinstance(selected_binding, Mapping):
                try:
                    compiled_roots = compiled_capability_binding_roots(
                        compiled_governance,
                        capability_id=str(capability_id),
                    )
                except ValueError:
                    compiled_roots = None
            implementation_status = adapter.get("implementation_status")
            accepted_statuses = (
                governance.READY_IMPLEMENTATION_STATUSES
                if environment in governance.RELEASE_ADAPTER_ENVIRONMENTS
                else {
                    *governance.READY_IMPLEMENTATION_STATUSES,
                    "mock",
                    "test_fixture_only",
                    "sandbox",
                }
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
        if item.get("status") != "passed":
            issues.append(
                _issue(
                    location,
                    "blocked/failed/dry-run reports are not Provider Conformance evidence",
                )
            )
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
        test_artifact_path: Path | None = None
        for field, destination in (
            ("artifactRef", "execution"),
            ("testArtifactRef", "test"),
        ):
            reference = item.get(field)
            if not isinstance(reference, str) or not reference.startswith(
                f".qwq_output/env/{environment}/runs/"
            ):
                issues.append(
                    _issue(location, f"{field} must remain inside its environment run root")
                )
                continue
            path = _output_path(reference, root=configured_root)
            if path is None or not path.exists():
                issues.append(_issue(location, f"{field} must resolve to an existing output artifact"))
            elif configured_root.resolve() not in path.parents and path != configured_root:
                issues.append(_issue(location, f"{field} escapes configured output root"))
            elif reference in artifact_refs:
                issues.append(_issue(location, f"{field} must identify one conformance cell only"))
            artifact_refs.add(reference)
            if destination == "execution":
                artifact_path = path
            else:
                test_artifact_path = path
        for field in (
            "artifactDigest",
            "testArtifactDigest",
            "testSourceDigest",
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
                    expected_source=expected_source,
                )
            )
        if test_artifact_path is not None and test_artifact_path.exists():
            expected_test_artifact_digest = _digest_bytes(test_artifact_path.read_bytes())
            if item.get("testArtifactDigest") != expected_test_artifact_digest:
                issues.append(
                    _issue(
                        location,
                        "testArtifactDigest does not match the test-owned CaseResult artifact",
                    )
                )
            if expected_source is not None and isinstance(environment, str):
                _, case_result_issues = load_case_results(
                    test_artifact_path,
                    source=expected_source,
                    environment=environment,
                    config_digest=str(item.get("configDigest") or ""),
                )
                issues.extend(case_result_issues)
        if not isinstance(item.get("commit"), str) or not COMMIT_PATTERN.fullmatch(str(item["commit"])):
            issues.append(_issue(location, "commit must be a git commit digest"))
        elif current_commit is not None and item["commit"] != current_commit:
            issues.append(_issue(location, "commit does not match the current source revision"))
        if not isinstance(expected_image, str) or not SHA256_PATTERN.fullmatch(expected_image):
            issues.append(
                _issue(
                    location,
                    "QWQ_PROVIDER_CONFORMANCE_EXPECTED_IMAGE_DIGEST must identify the active immutable image",
                )
            )
        elif item.get("imageDigest") != expected_image:
            issues.append(_issue(location, "imageDigest does not match the active immutable image"))
        if isinstance(selected_binding, Mapping) and compiled_roots is not None:
            current_config_digest = binding_config_digest(selected_binding, compiled_roots)
            if item.get("configDigest") != current_config_digest:
                issues.append(
                    _issue(location, "configDigest does not match the current selected Binding")
                )
        current_contract_graph_digest = _current_contract_graph_digest()
        if current_contract_graph_digest is None:
            issues.append(_issue(location, "current ContractGraph digest is unavailable"))
        elif item.get("contractGraphDigest") != current_contract_graph_digest:
            issues.append(_issue(location, "contractGraphDigest is stale"))
        current_adapter_digest = _current_adapter_digest(adapter)
        if current_adapter_digest is None:
            issues.append(_issue(location, "current Adapter digest is unavailable"))
        elif item.get("adapterDigest") != current_adapter_digest:
            issues.append(_issue(location, "adapterDigest is stale"))
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
            if not PUBLIC_ASSERTION_IDS.issubset(set(assertion_ids)):
                issues.append(
                    _issue(
                        location,
                        "assertionIds omit mandatory public Provider scenarios",
                    )
                )
            if expected_source is not None and tuple(sorted(assertion_ids)) != tuple(
                sorted(expected_source.get("assertionIds", []))
            ):
                issues.append(
                    _issue(
                        location,
                        "assertionIds must exactly match the discovered source assertion set",
                    )
                )
            if item.get("assertionCount") != len(assertion_ids):
                issues.append(_issue(location, "assertionCount must equal assertionIds length"))
        if item.get("networkBoundary") not in {
            "offline_harness",
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
        if not _valid_receipt_ref(item.get("cleanupReceipt")):
            issues.append(
                _issue(location, "cleanupReceipt must be a non-sensitive receipt reference")
            )
        acceptance_refs = item.get("acceptanceRefs")
        if not isinstance(acceptance_refs, list) or not acceptance_refs or not all(
            isinstance(ref, str) and ref.startswith("specs/feature-tree/") for ref in acceptance_refs
        ):
            issues.append(
                _issue(location, "acceptanceRefs must be non-empty feature-tree references")
            )
        if (
            expected_source is not None
            and acceptance_refs != expected_source.get("acceptanceRefs")
        ):
            issues.append(
                _issue(location, "acceptanceRefs must exactly match source spec_ref values")
            )
        observability_refs = item.get("observabilityRefs")
        if not _observability_refs_valid(observability_refs):
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
        if expected_source is not None and item.get("testCommand") != shlex.join(
            list(expected_source["command"])
        ):
            issues.append(
                _issue(location, "testCommand does not match the source-declared executable argv")
            )
        is_release_cell = requires_release_readiness(str(environment), str(layer))
        if is_release_cell and not _release_readiness_valid(item):
            issues.append(
                _issue(
                    location,
                    "release Provider user_acceptance requires adapter-health, "
                    "switch and rollback receipt references",
                )
            )
        if is_release_cell and not RELEASE_ASSERTION_IDS.issubset(
            set(assertion_ids) if isinstance(assertion_ids, list) else set()
        ):
            issues.append(
                _issue(
                    location,
                    "release Provider user_acceptance must execute "
                    "adapter health/switch/rollback assertions",
                )
            )
        elif not is_release_cell and "releaseReadiness" in item:
            issues.append(
                _issue(
                    location,
                    "releaseReadiness is reserved for Gamma/Prod release "
                    "user_acceptance cells",
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
    return tuple(
        sorted(
            assertion_id
            for assertion_id in assertion_ids
            if assertion_id not in RELEASE_ASSERTION_IDS
        )
    )


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
    if (
        len({cell.get("typedPort") for cell in concrete_cells}) != 1
        or len({cell.get("contractRef") for cell in concrete_cells}) != 1
    ):
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
                and execution_profile_for(environment, layer) is not None
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
            prod_remote_release_cell = by_cell.get(
                (capability_id, RELEASE_ENVIRONMENT, "user_acceptance")
            )
            prod_remote_release_ready = (
                prod_remote_release_cell is not None
                and prod_remote_release_cell.get("status") == "passed"
                and _release_readiness_valid(prod_remote_release_cell)
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
            item["matrix_selected_adapters_ready"] = matrix_selected_adapters_ready
            if environment == RELEASE_ENVIRONMENT:
                item["prod_remote_release_ready"] = prod_remote_release_ready
                item["capability_ready"] = (
                    item.get("state") == "enabled"
                    and bool(item.get("adapter_preflight_ready"))
                    and capability_matrix_ready
                    and matrix_selected_adapters_ready
                    and prod_remote_release_ready
                )
            else:
                item["capability_ready"] = (
                    item.get("state") == "enabled"
                    and bool(item.get("adapter_preflight_ready"))
                    and selected_adapter_ready
                    and capability_matrix_ready
                    and matrix_selected_adapters_ready
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
    executable_sources, source_discovery_issues = discover_test_sources()
    evidence_issues = validate_evidence(
        evidence,
        registry=governance.load_registry(),
        root=root,
        current_commit=current_commit,
        compiled=compiled,
        source_catalog=executable_sources,
    )
    readiness = derive_readiness(compiled=compiled, evidence=evidence)
    coverage_issues = source_coverage_issues(
        compiled=compiled,
        sources=executable_sources,
    )
    report = {
        "schema": "provider-conformance-readiness",
        "version": 1,
        "evidenceCount": len(evidence),
        "executableSourceCount": len(executable_sources),
        "sourceCoverageIssues": coverage_issues,
        "readiness": readiness,
        "issues": [
            *(issue.render() for issue in governance_issues),
            *evidence_load_issues,
            *current_commit_issues,
            *source_discovery_issues,
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
    issues: list[str] = []
    source_coverage = report.get("sourceCoverageIssues")
    if isinstance(source_coverage, list):
        issues.extend(str(issue) for issue in source_coverage)
    evidence_count = report.get("evidenceCount")
    if not isinstance(evidence_count, int) or evidence_count <= 0:
        return [
            *issues,
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
