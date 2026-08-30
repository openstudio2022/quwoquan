"""Validate canonical app launch attempt, seal, terminal, and process identity."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from quwoquan_app.scripts.device.startup_terminal_receipt import (
    canonical_document_digest as startup_terminal_digest,
)
from quwoquan_app.scripts.device.startup_terminal_receipt import (
    read_startup_terminal_receipt,
)
from quwoquan_ops.cli.commands.app_preflight_uat_process import (
    observe_canonical_app_process_id,
)
from quwoquan_ops.cli.commands.app_preflight_uat_projection_path import (
    canonical_source_projection_root,
    load_canonical_projection_evidence,
)
from quwoquan_ops.cli.lib.app_launch_attempt import read_app_launch_attempt
from quwoquan_ops.cli.lib.package_reuse.dependency_bundle_projection_verify import (
    load_dependency_projection_cas_evidence_bytes,
    load_dependency_projection_cas_readback_bytes,
)

from .app_preflight_uat_binding_contract import (
    _BUILD_PROJECTION_SEAL_FIELDS,
    _DIGEST_RE,
)

_DEPENDENCY_PROJECTION_EVIDENCE_FIELDS = (
    "dependencyProjectionExpectationRef",
    "dependencyProjectionExpectationDigest",
    "dependencyProjectionPrebuildReadbackRef",
    "dependencyProjectionPrebuildReadbackDigest",
    "dependencyProjectionPostbuildReadbackRef",
    "dependencyProjectionPostbuildReadbackDigest",
)
_DEPENDENCY_COMPONENT_IDENTITY_FIELDS = {
    "pub": (
        "manifestDigest",
        "treeDigest",
        "entryCount",
        "directoryCount",
        "lockDigest",
    ),
    "iosPods": ("treeDigest", "entryCount", "lockDigest"),
    "androidGradle": ("manifestDigest", "treeDigest", "entryCount"),
}
_DEPENDENCY_COMPONENT_KINDS = {
    "productionPub": "pub",
    "patrolPub": "pub",
    "productionIosPods": "iosPods",
    "patrolIosPods": "iosPods",
    "androidGradle": "androidGradle",
}
_PLATFORM_REQUIRED_DEPENDENCY_COMPONENTS = {
    "android": frozenset({"productionPub", "patrolPub", "androidGradle"}),
    "ios-simulator": frozenset(
        {
            "productionPub",
            "patrolPub",
            "productionIosPods",
            "patrolIosPods",
        }
    ),
}
_CONTRACT_GRAPH_LOGICAL_PATH = "quwoquan_service/generated/contract_graph.json"


def _exact_receipt_string(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"APP.LAUNCH.receipt_invalid: {label} is invalid")
    return value


def _canonical_absolute_posix_ref(value: Any, *, label: str) -> str:
    """Validate signed path bytes before constructing any ``Path`` object."""

    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"APP.LAUNCH.receipt_invalid: {label} is invalid")
    segments = value.split("/")
    if (
        not value.startswith("/")
        or PurePosixPath(value).as_posix() != value
        or segments[0] != ""
        or any(segment in {"", ".", ".."} for segment in segments[1:])
    ):
        raise ValueError(
            f"APP.LAUNCH.receipt_invalid: {label} is not a canonical absolute POSIX path"
        )
    return value


def _load_stable_absolute_file(
    raw_ref: str,
    *,
    label: str,
    loader: Callable[[Path, bytes, int], Any],
) -> Any:
    """Read one exact absolute file with stable ancestor and name identity."""

    path = Path(raw_ref)
    parent = canonical_source_projection_root(str(path.parent))
    return load_canonical_projection_evidence(
        raw_ref,
        projection_root=parent,
        output_root=parent,
        label=label,
        loader=loader,
    )


def _exact_source_capsule_manifest_ref(
    expectation_ref: Any,
    launch_ref: Any,
) -> str:
    expectation = _canonical_absolute_posix_ref(
        expectation_ref,
        label="dependency expectation source capsule manifest reference",
    )
    launch = _canonical_absolute_posix_ref(
        launch_ref,
        label="launch source capsule manifest reference",
    )
    if expectation != launch:
        raise ValueError("dependency expectation source identity drifted")
    return expectation


def _contract_graph_operation_failures(encoded: bytes) -> dict[str, frozenset[str]]:
    try:
        graph = json.loads(encoded)
        operations = graph["operations"]
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("candidate ContractGraph is invalid") from exc
    if not isinstance(operations, list):
        raise TypeError("candidate ContractGraph operations are invalid")
    registry: dict[str, frozenset[str]] = {}
    for item in operations:
        if not isinstance(item, Mapping):
            raise TypeError("candidate ContractGraph operation is invalid")
        operation_id = item.get("id")
        error_codes = item.get("errorCodes")
        if (
            not isinstance(operation_id, str)
            or not operation_id
            or operation_id != operation_id.strip()
            or not isinstance(error_codes, list)
            or any(
                not isinstance(code, str) or not code or code != code.strip()
                for code in error_codes
            )
            or operation_id in registry
        ):
            raise ValueError("candidate ContractGraph operation registry is invalid")
        registry[operation_id] = frozenset(error_codes)
    return registry


def _launch_evidence_path(value: str | Path, *, label: str) -> Path:
    """Resolve one immutable launch evidence file inside QWQ_OUTPUT_ROOT."""
    import quwoquan_ops.cli.stackctl as _stackctl

    evidence_root = _stackctl.output_root().expanduser().resolve()
    candidate = Path(value).expanduser()
    candidate = candidate if candidate.is_absolute() else evidence_root / candidate
    absolute = Path(candidate.absolute())
    if absolute.is_symlink() or not absolute.is_file():
        raise ValueError(f"App content UAT {label} is missing")
    resolved = absolute.resolve()
    try:
        resolved.relative_to(evidence_root)
    except ValueError as exc:
        raise ValueError(f"App content UAT {label} escapes QWQ_OUTPUT_ROOT") from exc
    return resolved


def _load_dependency_projection_evidence(
    value: Any,
    *,
    label: str,
    output_root: Path,
    projection_root: Path,
    loader: Callable[[Path, bytes, int], Any],
) -> Any:
    """Validate and read dependency evidence through its exact projection fd."""

    try:
        return load_canonical_projection_evidence(
            value,
            projection_root=projection_root,
            output_root=output_root,
            label=label,
            loader=loader,
        )
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise ValueError(
            f"APP.LAUNCH.receipt_invalid: {label} is unavailable or invalid"
        ) from exc


def _expected_dependency_component_identities(
    components: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    expected: dict[str, dict[str, Any]] = {}
    for name, raw in components.items():
        if not isinstance(raw, Mapping):
            raise TypeError(f"dependency component {name} is invalid")
        component = str(name)
        kind = str(raw.get("kind") or "")
        fields = _DEPENDENCY_COMPONENT_IDENTITY_FIELDS.get(kind)
        if fields is None or _DEPENDENCY_COMPONENT_KINDS.get(component) != kind:
            raise ValueError(f"dependency component {name} kind is invalid")
        identity = {field: raw.get(field) for field in fields}
        for field, value in identity.items():
            if field.endswith("Digest"):
                if _DIGEST_RE.fullmatch(str(value or "")) is None:
                    raise ValueError(f"dependency component {name} {field} is invalid")
            elif not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"dependency component {name} {field} is invalid")
        expected[component] = identity
    return expected


def _verified_dependency_projection_binding(
    *,
    report: Mapping[str, Any],
    launch_projection: Mapping[str, Any],
    platform: str,
) -> dict[str, str]:
    """Bind strict UAT to pre/post CAS readbacks from its fresh projection."""

    import quwoquan_ops.cli.stackctl as _stackctl

    values: dict[str, str] = {}
    for field in _DEPENDENCY_PROJECTION_EVIDENCE_FIELDS:
        raw = report.get(field)
        if not isinstance(raw, str) or not raw or raw != raw.strip():
            raise ValueError(
                "APP.LAUNCH.receipt_invalid: dependency projection binding is "
                f"missing or invalid: {field}"
            )
        values[field] = raw
    invalid = [
        field
        for field, value in values.items()
        if not value
        or (field.endswith("Digest") and _DIGEST_RE.fullmatch(value) is None)
    ]
    if invalid:
        raise ValueError(
            "APP.LAUNCH.receipt_invalid: dependency projection binding is "
            f"missing or invalid: {','.join(invalid)}"
        )
    output_root = _stackctl.output_root().expanduser().resolve()
    try:
        projection_root = canonical_source_projection_root(
            launch_projection.get("sourceProjectionRoot")
        )
        projection_root.relative_to(output_root)
    except (OSError, ValueError) as exc:
        raise ValueError(
            "APP.LAUNCH.receipt_invalid: current dependency projection root is invalid"
        ) from exc
    try:
        expectation = _load_dependency_projection_evidence(
            values["dependencyProjectionExpectationRef"],
            label="dependencyProjectionExpectationRef",
            output_root=output_root,
            projection_root=projection_root,
            loader=lambda path, encoded, mode: (
                load_dependency_projection_cas_evidence_bytes(
                    projection_root=projection_root,
                    evidence_path=path,
                    encoded=encoded,
                    evidence_mode=mode,
                    expected_digest=values["dependencyProjectionExpectationDigest"],
                )
            ),
        )
        prebuild = _load_dependency_projection_evidence(
            values["dependencyProjectionPrebuildReadbackRef"],
            label="dependencyProjectionPrebuildReadbackRef",
            output_root=output_root,
            projection_root=projection_root,
            loader=lambda path, encoded, mode: (
                load_dependency_projection_cas_readback_bytes(
                    evidence_path=path,
                    encoded=encoded,
                    evidence_mode=mode,
                    expected_digest=values[
                        "dependencyProjectionPrebuildReadbackDigest"
                    ],
                    expected_expectation_digest=expectation.evidence_digest,
                )
            ),
        )
        postbuild = _load_dependency_projection_evidence(
            values["dependencyProjectionPostbuildReadbackRef"],
            label="dependencyProjectionPostbuildReadbackRef",
            output_root=output_root,
            projection_root=projection_root,
            loader=lambda path, encoded, mode: (
                load_dependency_projection_cas_readback_bytes(
                    evidence_path=path,
                    encoded=encoded,
                    evidence_mode=mode,
                    expected_digest=values[
                        "dependencyProjectionPostbuildReadbackDigest"
                    ],
                    expected_expectation_digest=expectation.evidence_digest,
                )
            ),
        )
        paths = {
            "dependencyProjectionExpectationRef": expectation.evidence_path,
            "dependencyProjectionPrebuildReadbackRef": prebuild.evidence_path,
            "dependencyProjectionPostbuildReadbackRef": postbuild.evidence_path,
        }
        if len(set(paths.values())) != len(paths):
            raise ValueError("dependency projection evidence references overlap")
        source = expectation.manifest.get("source")
        components = expectation.manifest.get("components")
        if not isinstance(source, Mapping) or not isinstance(components, Mapping):
            raise TypeError("dependency expectation identity is invalid")
        raw_source_manifest_digest = source.get("manifestDigest")
        if (
            not isinstance(raw_source_manifest_digest, str)
            or _DIGEST_RE.fullmatch(raw_source_manifest_digest) is None
        ):
            raise ValueError("dependency expectation source identity is invalid")
        raw_source_manifest_ref = _exact_source_capsule_manifest_ref(
            source.get("manifestPath"),
            launch_projection.get("sourceCapsuleManifestRef"),
        )
        source_manifest_digest = raw_source_manifest_digest
        source_manifest_path, encoded_source_manifest = _load_stable_absolute_file(
            raw_source_manifest_ref,
            label="strict UAT source capsule manifest",
            loader=lambda path, encoded, _mode: (path, encoded),
        )
        source_manifest = json.loads(encoded_source_manifest)
        observed_source_manifest_digest = (
            "sha256:" + hashlib.sha256(encoded_source_manifest).hexdigest()
        )
        if (
            expectation.projection_root != projection_root
            or str(source_manifest_path) != raw_source_manifest_ref
            or observed_source_manifest_digest != source_manifest_digest
            or not isinstance(source_manifest, Mapping)
            or _stackctl._canonical_document_checksum(source_manifest)
            != launch_projection.get("sourceCapsuleManifestDigest")
        ):
            raise ValueError("dependency expectation source identity drifted")
        expected_components = _expected_dependency_component_identities(components)
        required = _PLATFORM_REQUIRED_DEPENDENCY_COMPONENTS.get(platform)
        if required is None or set(expected_components) != set(required):
            raise ValueError(
                f"dependency expectation has an invalid {platform} component set"
            )
        for phase, readback in (("prebuild", prebuild), ("postbuild", postbuild)):
            manifest = readback.manifest
            if (
                manifest.get("projectionRoot") != str(projection_root)
                or manifest.get("sourceManifestDigest") != source_manifest_digest
                or manifest.get("components") != expected_components
            ):
                raise ValueError(f"dependency {phase} readback identity drifted")
        if prebuild.manifest["components"] != postbuild.manifest["components"]:
            raise ValueError("dependency pre/post component identity drifted")
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        detail = str(exc) or type(exc).__name__
        if detail.startswith("APP.LAUNCH.receipt_invalid:"):
            raise
        raise ValueError(f"APP.LAUNCH.receipt_invalid: {detail}") from exc
    return {
        **values,
        "dependencyProjectionExpectationRef": str(expectation.evidence_path),
        "dependencyProjectionPrebuildReadbackRef": str(prebuild.evidence_path),
        "dependencyProjectionPostbuildReadbackRef": str(postbuild.evidence_path),
    }


def _verified_candidate_contract_graph_binding(
    *,
    runtime_binding: Mapping[str, Any],
    launch_projection: Mapping[str, Any],
) -> dict[str, Any]:
    """Bind candidate manifest, capsule entry, and projected Graph bytes."""

    expected_digest = _exact_receipt_string(
        runtime_binding.get("contractGraphDigest"),
        label="candidate ContractGraph digest",
    )
    if _DIGEST_RE.fullmatch(expected_digest) is None:
        raise ValueError(
            "APP.LAUNCH.receipt_invalid: candidate ContractGraph digest is invalid"
        )
    raw_manifest_ref = _canonical_absolute_posix_ref(
        launch_projection.get("sourceCapsuleManifestRef"),
        label="launch source capsule manifest reference",
    )
    _manifest_path, encoded_manifest = _load_stable_absolute_file(
        raw_manifest_ref,
        label="candidate source capsule manifest",
        loader=lambda path, encoded, _mode: (path, encoded),
    )
    try:
        manifest = json.loads(encoded_manifest)
        entries = manifest["entries"]
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError(
            "APP.LAUNCH.receipt_invalid: source capsule manifest is invalid"
        ) from exc
    if not isinstance(entries, list):
        raise TypeError(
            "APP.LAUNCH.receipt_invalid: source capsule entries are invalid"
        )
    matching = [
        entry
        for entry in entries
        if isinstance(entry, Mapping)
        and entry.get("logicalPath") == _CONTRACT_GRAPH_LOGICAL_PATH
    ]
    if len(matching) != 1:
        raise ValueError(
            "APP.LAUNCH.receipt_invalid: candidate ContractGraph entry is ambiguous"
        )
    entry = matching[0]
    if (
        entry.get("capsulePath") != f"repo/{_CONTRACT_GRAPH_LOGICAL_PATH}"
        or entry.get("kind") != "file"
        or entry.get("digest") != expected_digest
        or entry.get("mode") not in {0o444, 0o555}
        or not isinstance(entry.get("size"), int)
        or isinstance(entry.get("size"), bool)
        or entry.get("size") < 0
    ):
        raise ValueError(
            "APP.LAUNCH.receipt_invalid: candidate ContractGraph entry drifted"
        )

    projection_root = canonical_source_projection_root(
        launch_projection.get("sourceProjectionRoot")
    )
    raw_graph_ref = f"{projection_root}/{_CONTRACT_GRAPH_LOGICAL_PATH}"
    graph_ref, encoded_graph = load_canonical_projection_evidence(
        raw_graph_ref,
        projection_root=projection_root,
        output_root=projection_root,
        label="candidate ContractGraph projection",
        loader=lambda path, encoded, _mode: (path, encoded),
    )
    observed_digest = "sha256:" + hashlib.sha256(encoded_graph).hexdigest()
    if observed_digest != expected_digest or len(encoded_graph) != entry.get("size"):
        raise ValueError(
            "APP.LAUNCH.receipt_invalid: candidate ContractGraph projection drifted"
        )
    registry = _contract_graph_operation_failures(encoded_graph)
    return {
        "contractGraphDigest": expected_digest,
        "contractGraphRef": str(graph_ref),
        "contractGraphOperationCount": len(registry),
        "sourceProjectionRoot": str(projection_root),
    }


def _verified_app_content_projection_build_seal(
    *,
    launch_projection: Mapping[str, Any],
    launch_control: Mapping[str, Any],
    report: Mapping[str, Any],
    attempt_ref: str | Path,
) -> dict[str, Any]:
    """Bind a launch report to one fresh full-tree seal and current bytes."""
    import quwoquan_ops.cli.stackctl as _stackctl
    from quwoquan_ops.cli.commands.app_preflight_uat_launch import (
        verify_app_content_projection_build_seal,
    )

    seal_ref = _exact_receipt_string(
        launch_control.get("buildProjectionSealRef"),
        label="build projection seal reference",
    )
    seal_digest = _exact_receipt_string(
        report.get("buildProjectionSealDigest"),
        label="build projection seal digest",
    )
    policy_id = _exact_receipt_string(
        launch_control.get("buildProjectionPolicyId"),
        label="build projection policy",
    )
    if (
        not seal_ref
        or report.get("launchAttemptRef") != str(attempt_ref)
        or report.get("buildProjectionSealRef") != seal_ref
        or _DIGEST_RE.fullmatch(seal_digest) is None
        or not policy_id
    ):
        raise ValueError(
            "APP.LAUNCH.receipt_invalid: build projection seal binding is incomplete"
        )
    issued_control_ref = launch_control.get("controlRef")
    issued_control_digest = launch_control.get("controlDigest")
    if issued_control_ref is not None:
        issued_control_ref = _exact_receipt_string(
            issued_control_ref,
            label="issued launch control reference",
        )
        issued_control_digest = _exact_receipt_string(
            issued_control_digest,
            label="issued launch control digest",
        )
    if issued_control_ref and (
        report.get("canonicalLaunchControlRef") != issued_control_ref
        or report.get("canonicalLaunchControlDigest") != issued_control_digest
    ):
        raise ValueError(
            "APP.LAUNCH.receipt_invalid: retry launch control identity drifted"
        )
    try:
        verified = verify_app_content_projection_build_seal(
            manifest_path=Path(
                str(launch_projection.get("sourceCapsuleManifestRef") or "")
            ),
            projection_root=Path(
                str(launch_projection.get("sourceProjectionRoot") or "")
            ),
            output_root=_stackctl.output_root().expanduser().resolve(),
            seal_path=Path(seal_ref),
            expected_seal_digest=seal_digest,
            expected_policy_id=policy_id,
        )
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise ValueError(f"APP.LAUNCH.receipt_invalid: {exc}") from exc
    seal_payload = {
        field: value
        for field, value in verified.items()
        if field not in {"buildProjectionSealDigest", "buildProjectionSealRef"}
    }
    if (
        set(seal_payload) != _BUILD_PROJECTION_SEAL_FIELDS
        or report.get("buildProjectionSeal") != seal_payload
        or verified.get("sourceProjectionDigest")
        != launch_projection.get("sourceProjectionDigest")
        or verified.get("sourceEntryCount")
        != launch_projection.get("sourceProjectionFileCount")
    ):
        raise ValueError(
            "APP.LAUNCH.receipt_invalid: build projection seal differs from source projection"
        )
    attempt_name = Path(attempt_ref).parent.name
    expected_digest = launch_control.get("expectedBuildProjectionDigest")
    prebuild_digest = _exact_receipt_string(
        report.get("prebuildProjectionDigest"),
        label="pre-build projection digest",
    )
    if _DIGEST_RE.fullmatch(prebuild_digest) is None:
        raise ValueError(
            "APP.LAUNCH.receipt_invalid: pre-build projection digest is invalid"
        )
    if attempt_name == "attempt-1":
        if expected_digest is not None:
            raise ValueError(
                "APP.LAUNCH.receipt_invalid: first attempt cannot preclaim a build projection digest"
            )
    elif attempt_name == "attempt-2":
        if expected_digest != prebuild_digest:
            raise ValueError(
                "APP.LAUNCH.receipt_invalid: retry build projection digest drifted"
            )
    else:
        raise ValueError(
            "APP.LAUNCH.receipt_invalid: canonical launch attempt path is invalid"
        )
    return verified


def _app_content_launch_binding(
    *,
    runtime_binding: Mapping[str, Any],
    report_ref: str | Path,
    attempt_ref: str | Path,
    platform: str,
    device_id: str,
    launch_provenance: str,
    launch_projection: Mapping[str, Any],
    process_observer: Callable[..., int] | None = None,
) -> dict[str, Any]:
    """Bind one page-UAT target to the exact adjacent canonical App launch.

    The test-live report is only a projection.  This validator always rereads
    and validates the canonical app-launch-attempt, recomputes both document
    digests, then binds its source/package/trust/AppArtifact identity to the
    immutable candidate selected by app-debug-preflight.
    """
    import quwoquan_ops.cli.stackctl as _stackctl

    report_path = _launch_evidence_path(report_ref, label="launch report")
    attempt_path = _launch_evidence_path(attempt_ref, label="launch attempt")
    report = _stackctl._read_json_object(str(report_path))
    attempt = read_app_launch_attempt(attempt_path)
    attempt_digest = _stackctl._canonical_document_checksum(attempt)
    report_attempt_ref = _exact_receipt_string(
        report.get("launchAttemptRef"),
        label="launch attempt reference",
    )
    report_attempt_path = _launch_evidence_path(
        report_attempt_ref,
        label="report launch attempt",
    )
    if report_attempt_path != attempt_path:
        raise ValueError("App content UAT launch attempt reference drifted")

    expected_platform = "ios" if platform.startswith("ios-") else "android"
    expected_identity = {
        "environment": str(runtime_binding.get("environment") or ""),
        "target": str(runtime_binding.get("target") or ""),
        "platform": expected_platform,
        "deviceId": device_id,
        "launchProvenance": launch_provenance,
        "runtimeConfigSupplyMode": "external_runtime_package",
        "sourceGitSha": str(runtime_binding.get("sourceRevision") or ""),
        "sourceTreeDigest": str(runtime_binding.get("sourceCapsuleDigest") or ""),
    }
    for field, expected in expected_identity.items():
        if not expected or report.get(field) != expected:
            subject = (
                "source" if field in {"sourceGitSha", "sourceTreeDigest"} else field
            )
            raise ValueError(f"App content UAT launch {subject} identity drifted")
    attempt_expected = {
        "environment": expected_identity["environment"],
        "target": expected_identity["target"],
        "platform": expected_platform,
        "deviceId": device_id,
        "launchProvenance": launch_provenance,
        "runtimeConfigSupplyMode": "external_runtime_package",
        "runMode": "content-live",
        "buildProfile": "nonprod",
        "buildMode": "debug",
    }
    for field, expected in attempt_expected.items():
        if attempt.get(field) != expected:
            subject = "device" if field == "deviceId" else field
            raise ValueError(f"App content UAT launch {subject} identity drifted")

    transitions = [
        str(item.get("status") or "")
        for item in attempt.get("transitions") or []
        if isinstance(item, Mapping)
    ]
    required_transitions = (
        "compiled",
        "installed",
        "configured",
        "launched",
    )
    if any(status not in transitions for status in required_transitions):
        raise ValueError("App content UAT launch lifecycle is incomplete")
    if (
        attempt.get("status") != "stopped"
        or attempt.get("firstBlocker") not in {None, ""}
        or attempt.get("configurationState") != "complete"
        or attempt.get("runtimeHealthStatus") != "healthy"
        or bool(attempt.get("warnings"))
    ):
        raise ValueError("App content UAT launch lifecycle is not healthy")
    if report.get("runtimeWarnings") not in ([], None):
        raise ValueError("App content UAT launch warnings are forbidden")

    report_expected = {
        "schema": "quwoquan_app.test_live_launch",
        "runMode": "content-live",
        "nonPromotable": platform in {"ios-simulator", "android"},
        "launchPolicy": "test_live",
        "compileStatus": "compiled",
        "installStatus": "installed",
        "launchStatus": "launched",
        "runtimeStatus": "healthy",
        "lifecycleStatus": attempt["status"],
        "firstBlocker": "",
        "launchAttemptId": attempt["attemptId"],
        "launchAttemptDigest": attempt_digest,
        "artifactDigest": attempt["artifactDigest"],
        "runtimeConfigTrustEnvelopeDigest": attempt["runtimeConfigTrustEnvelopeDigest"],
        "runtimeConfigPackageDigest": attempt["runtimeConfigPackageDigest"],
        "effectiveLaunchManifestDigest": attempt["launchDigest"],
        "applicationId": attempt["applicationId"],
        "startupTerminalAttemptId": attempt["startupTerminalAttemptId"],
        "startupTerminalEvidenceDigest": attempt["startupTerminalEvidenceDigest"],
        "startupTerminalEvidenceRef": attempt["startupTerminalEvidenceRef"],
        "candidateDigest": runtime_binding.get("candidateDigest"),
        "candidatePackageDigest": runtime_binding.get("packageDigest"),
        "sourceCapsuleManifestDigest": launch_projection.get(
            "sourceCapsuleManifestDigest"
        ),
        "sourceProjectionEvidenceDigest": launch_projection.get(
            "sourceProjectionEvidenceDigest"
        ),
        "sourceProjectionEvidenceRef": launch_projection.get(
            "sourceProjectionEvidenceRef"
        ),
        "sourceProjectionDigest": launch_projection.get("sourceProjectionDigest"),
        "sourceProjectionFileCount": launch_projection.get("sourceProjectionFileCount"),
    }
    for field, expected in report_expected.items():
        if report.get(field) != expected:
            if field == "artifactDigest":
                subject = "artifact"
            elif field == "runtimeConfigTrustEnvelopeDigest":
                subject = "trust"
            elif field == "runtimeConfigPackageDigest":
                subject = "package"
            elif field == "launchAttemptDigest":
                subject = "attempt digest"
            else:
                subject = field
            raise ValueError(f"App content UAT launch {subject} identity drifted")
    for field in (
        "artifactDigest",
        "runtimeConfigTrustEnvelopeDigest",
        "runtimeConfigPackageDigest",
        "effectiveLaunchManifestDigest",
        "launchAttemptDigest",
        "startupTerminalEvidenceDigest",
        "candidateDigest",
        "candidatePackageDigest",
        "sourceCapsuleManifestDigest",
        "sourceProjectionEvidenceDigest",
        "sourceProjectionDigest",
    ):
        raw_digest = _exact_receipt_string(
            report.get(field),
            label=f"launch {field}",
        )
        if _DIGEST_RE.fullmatch(raw_digest) is None:
            raise ValueError(f"App content UAT launch {field} is invalid")
    if re.fullmatch(r"[0-9a-f]{40}", expected_identity["sourceGitSha"]) is None:
        raise ValueError("App content UAT launch source identity is invalid")

    dependency_projection_binding = _verified_dependency_projection_binding(
        report=report,
        launch_projection=launch_projection,
        platform=platform,
    )
    contract_graph_binding = _verified_candidate_contract_graph_binding(
        runtime_binding=runtime_binding,
        launch_projection=launch_projection,
    )

    terminal_path = _launch_evidence_path(
        str(attempt["startupTerminalEvidenceRef"]),
        label="safe-terminal receipt",
    )
    terminal = read_startup_terminal_receipt(
        terminal_path,
        launch_attempt=attempt,
    )
    if terminal.get("startupAttemptId") != attempt.get(
        "startupTerminalAttemptId"
    ) or startup_terminal_digest(terminal) != attempt.get(
        "startupTerminalEvidenceDigest"
    ):
        raise ValueError("App content UAT safe-terminal evidence drifted")
    projection_evidence_path = _launch_evidence_path(
        _exact_receipt_string(
            launch_projection.get("sourceProjectionEvidenceRef"),
            label="source projection evidence reference",
        ),
        label="source projection evidence",
    )
    projection_evidence = _stackctl._read_json_object(str(projection_evidence_path))
    if (
        _stackctl._canonical_document_checksum(projection_evidence)
        != launch_projection.get("sourceProjectionEvidenceDigest")
        or projection_evidence.get("candidateDigest")
        != runtime_binding.get("candidateDigest")
        or projection_evidence.get("packageDigest")
        != runtime_binding.get("packageDigest")
        or projection_evidence.get("sourceCapsuleDigest")
        != runtime_binding.get("sourceCapsuleDigest")
        or projection_evidence.get("sourceProjectionDigest")
        != launch_projection.get("sourceProjectionDigest")
        or projection_evidence.get("sourceProjectionFileCount")
        != launch_projection.get("sourceProjectionFileCount")
    ):
        raise ValueError("App content UAT source projection evidence drifted")
    control_path = _launch_evidence_path(
        _exact_receipt_string(
            report.get("canonicalLaunchControlRef"),
            label="canonical launch control reference",
        ),
        label="canonical launch control",
    )
    control = _stackctl._read_json_object(str(control_path))
    control_digest = _stackctl._canonical_document_checksum(control)
    build_projection_seal = _verified_app_content_projection_build_seal(
        launch_projection=launch_projection,
        launch_control=control,
        report=report,
        attempt_ref=attempt_path,
    )
    control_expected = {
        "schema": "quwoquan_ops.app_content_uat_launch_control.v1",
        "actor": "app-content-uat",
        "environment": expected_identity["environment"],
        "target": expected_identity["target"],
        "platform": platform,
        "deviceId": device_id,
        "candidateDigest": runtime_binding.get("candidateDigest"),
        "packageDigest": runtime_binding.get("packageDigest"),
        "sourceRevision": runtime_binding.get("sourceRevision"),
        "sourceCapsuleDigest": runtime_binding.get("sourceCapsuleDigest"),
        "sourceCapsuleManifestDigest": launch_projection.get(
            "sourceCapsuleManifestDigest"
        ),
        "sourceCapsuleManifestRef": launch_projection.get("sourceCapsuleManifestRef"),
        "sourceProjectionRoot": launch_projection.get("sourceProjectionRoot"),
        "sourceProjectionEvidenceDigest": launch_projection.get(
            "sourceProjectionEvidenceDigest"
        ),
        "sourceProjectionEvidenceRef": launch_projection.get(
            "sourceProjectionEvidenceRef"
        ),
        "buildProjectionPolicyId": build_projection_seal.get("policyId"),
        "buildProjectionSealRef": build_projection_seal.get("buildProjectionSealRef"),
        "expectedBuildProjectionDigest": (
            None
            if attempt_path.parent.name == "attempt-1"
            else report.get("prebuildProjectionDigest")
        ),
        "launchAttemptRef": str(attempt_path),
        "launchReportRef": str(report_path),
        "startupTerminalReceiptRef": str(terminal_path),
    }
    if (
        report.get("canonicalLaunchControlDigest") != control_digest
        or set(control) != set(control_expected)
        or any(control.get(field) != value for field, value in control_expected.items())
    ):
        raise ValueError("App content UAT canonical launch control drifted")
    teardown_path = _launch_evidence_path(
        str(attempt_path.with_name("teardown.json")),
        label="launch teardown receipt",
    )
    teardown = _stackctl._read_json_object(str(teardown_path))
    if set(teardown) != {
        "schema",
        "launchAttemptRef",
        "exitCode",
        "status",
        "warnings",
        "completedAt",
    }:
        raise ValueError("App content UAT launch teardown receipt is invalid")
    if (
        teardown.get("schema") != "quwoquan_app.launch_teardown.v1"
        or teardown.get("launchAttemptRef") != str(attempt_path)
        or teardown.get("exitCode") != 0
        or teardown.get("status") != "passed"
        or teardown.get("warnings") != []
        or not str(teardown.get("completedAt") or "").strip()
    ):
        raise ValueError("App content UAT launch teardown is not clean")
    teardown_digest = _stackctl._canonical_document_checksum(teardown)
    observer = process_observer or observe_canonical_app_process_id
    canonical_process_id = observer(
        platform=platform,
        device_id=device_id,
        application_id=str(attempt["applicationId"]),
    )
    if (
        not isinstance(canonical_process_id, int)
        or isinstance(canonical_process_id, bool)
        or canonical_process_id <= 0
    ):
        raise ValueError("canonical device-observed App processId is invalid")

    return {
        **expected_identity,
        "applicationId": str(attempt["applicationId"]),
        "canonicalProcessId": canonical_process_id,
        "launchAttemptId": str(attempt["attemptId"]),
        "artifactDigest": str(attempt["artifactDigest"]),
        "runtimeConfigTrustEnvelopeDigest": str(
            attempt["runtimeConfigTrustEnvelopeDigest"]
        ),
        "runtimeConfigPackageDigest": str(attempt["runtimeConfigPackageDigest"]),
        "effectiveLaunchManifestDigest": str(attempt["launchDigest"]),
        "launchAttemptDigest": attempt_digest,
        "launchAttemptRef": str(attempt_path),
        "startupTerminalAttemptId": str(attempt["startupTerminalAttemptId"]),
        "startupTerminalEvidenceDigest": str(attempt["startupTerminalEvidenceDigest"]),
        "startupTerminalEvidenceRef": str(terminal_path),
        "candidateDigest": str(runtime_binding["candidateDigest"]),
        "candidatePackageDigest": str(runtime_binding["packageDigest"]),
        "sourceCapsuleManifestDigest": str(
            launch_projection["sourceCapsuleManifestDigest"]
        ),
        "sourceCapsuleManifestRef": str(launch_projection["sourceCapsuleManifestRef"]),
        "sourceProjectionEvidenceDigest": str(
            launch_projection["sourceProjectionEvidenceDigest"]
        ),
        "sourceProjectionEvidenceRef": str(projection_evidence_path),
        "sourceProjectionDigest": str(launch_projection["sourceProjectionDigest"]),
        "sourceProjectionFileCount": int(
            launch_projection["sourceProjectionFileCount"]
        ),
        **contract_graph_binding,
        **dependency_projection_binding,
        "buildProjectionSeal": {
            field: value
            for field, value in build_projection_seal.items()
            if field not in {"buildProjectionSealDigest", "buildProjectionSealRef"}
        },
        "buildProjectionSealDigest": str(
            build_projection_seal["buildProjectionSealDigest"]
        ),
        "buildProjectionSealRef": str(build_projection_seal["buildProjectionSealRef"]),
        "canonicalLaunchControlDigest": control_digest,
        "canonicalLaunchControlRef": str(control_path),
        "teardownReceiptDigest": teardown_digest,
        "teardownReceiptRef": str(teardown_path),
        "launchReportDigest": _stackctl._canonical_document_checksum(report),
        "launchReportRef": str(report_path),
    }
