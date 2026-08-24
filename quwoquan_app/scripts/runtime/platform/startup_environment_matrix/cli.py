"""启动环境矩阵门禁主流程（原 ``main``，逐字搬移）。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .context import (
    DEVICE_PROFILES,
    ENVIRONMENTS,
    RUNTIME_CASES,
    RUNTIME_TARGETS,
    SHA256_PATTERN,
    SPEC_REFS,
)
from .evidence_validation import (
    _validate_observability_evidence,
    _validate_readback_evidence,
    _validate_runtime_evidence,
)
from .package_probe import (
    _ios_compile_defines,
    _launcher_handoff,
    _runtime_package,
    _validate_compile_defines,
    _validate_runtime_package,
)
from .reporting import _case, _case_counts, _report_status, _write_report


_PROD_TEST_LIVE_REJECTION = "test_live target/environment selection is invalid"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-root", default="")
    parser.add_argument("--require-runtime-evidence", action="store_true")
    parser.add_argument("--require-readback", action="store_true")
    parser.add_argument("--require-observability", action="store_true")
    parser.add_argument(
        "--require-physical-release",
        action="store_true",
        help="Require prod-hosted Android and iOS samples from physical devices.",
    )
    parser.add_argument(
        "--minimum-runtime-runs",
        type=int,
        default=1,
        help="Minimum independently validated cold-start samples per target/platform.",
    )
    parser.add_argument("--baseline-id", default="")
    parser.add_argument("--release-id", default="")
    parser.add_argument("--release-digest", default="")
    parser.add_argument("--report", default="")
    parser.add_argument(
        "--component-environment",
        action="append",
        choices=ENVIRONMENTS,
        dest="component_environments",
        help=(
            "Limit component-readiness probes to explicit environments. "
            "Release-bound evidence still uses the complete canonical matrix."
        ),
    )
    args = parser.parse_args()

    issues: list[str] = []
    packages: dict[str, Any] = {}
    runtime_evidence: dict[str, Any] = {}
    readback_evidence: dict[str, Any] = {}
    observability_evidence: dict[str, Any] = {}
    cases: list[dict[str, Any]] = []
    root = Path(args.evidence_root) if args.evidence_root else None
    release_requirements = {
        "runtime-evidence": args.require_runtime_evidence,
        "app-core-readback": args.require_readback,
        "observability-readback": args.require_observability,
    }
    release_gate = any(release_requirements.values())

    if release_gate:
        for evidence_kind, enabled in release_requirements.items():
            if not enabled:
                cases.append(
                    _case(
                        f"matrix-policy:{evidence_kind}",
                        kind="matrix_policy",
                        status="gate_block",
                        required=True,
                        reason=(
                            "release-bound startup verification requires "
                            f"{evidence_kind}"
                        ),
                    )
                )
        if not args.require_physical_release:
            cases.append(
                _case(
                    "matrix-policy:physical-release",
                    kind="matrix_policy",
                    status="gate_block",
                    required=True,
                    reason=(
                        "release-bound startup evidence must explicitly require "
                        "the physical-device matrix"
                    ),
                )
            )
        for name, value in (
            ("baselineId", args.baseline_id),
            ("releaseId", args.release_id),
            ("releaseDigest", args.release_digest),
        ):
            if str(value).strip() in {"", "unknown"}:
                cases.append(
                    _case(
                        f"candidate-identity:{name}",
                        kind="candidate_identity",
                        status="gate_block",
                        required=True,
                        reason=f"{name} is required for release-bound evidence",
                    )
                )
        if args.release_digest and not SHA256_PATTERN.fullmatch(
            args.release_digest
        ):
            issues.append("releaseDigest must use sha256:<64 lowercase hex>")
            cases.append(
                _case(
                    "candidate-identity:releaseDigest-format",
                    kind="candidate_identity",
                    status="failed",
                    required=True,
                    reason=issues[-1],
                )
            )
        if root is None:
            cases.append(
                _case(
                    "evidence-root",
                    kind="evidence_root",
                    status="gate_block",
                    required=True,
                    reason="evidence root is required for release-bound verification",
                )
            )

    component_environments = tuple(args.component_environments or ENVIRONMENTS)
    for environment in component_environments:
        if environment == "prod":
            prod_issues: list[str] = []
            rejection_reason = ""
            try:
                _runtime_package(environment)
            except RuntimeError as exc:
                rejection_reason = str(exc).strip()
                if rejection_reason != _PROD_TEST_LIVE_REJECTION:
                    prod_issues.append(
                        "prod: test_live rejection reason mismatch: "
                        f"{rejection_reason or '<empty>'}"
                    )
            except (KeyError, json.JSONDecodeError) as exc:
                prod_issues.append(f"prod: test_live boundary probe invalid: {exc}")
            else:
                prod_issues.append("prod: test_live was unexpectedly accepted")

            boundary_status = (
                "expected_fail_closed" if not prod_issues else "failed"
            )
            issues.extend(prod_issues)
            packages[environment] = {
                "runtimeDefineKeys": [],
                "iosDefineKeys": [],
                "runtimeTarget": RUNTIME_TARGETS[environment],
                "entrypoint": "",
                "dartDefinesDigest": "",
                "runtimeConfigDigest": "",
                "effectiveLaunchManifestDigest": "",
                "status": boundary_status,
                "componentEligible": False,
                "promotionEligible": False,
                "reason": rejection_reason,
            }
            cases.append(
                _case(
                    "component:prod",
                    kind="component_readiness",
                    status=boundary_status,
                    required=bool(prod_issues),
                    environment=environment,
                    target=RUNTIME_TARGETS[environment],
                    launchPolicy="test_live",
                    componentEligible=False,
                    promotionEligible=False,
                    effectiveLaunchManifestDigest="",
                    reason=rejection_reason,
                    issues=prod_issues,
                )
            )
            continue

        package_issues: list[str] = []
        runtime: dict[str, str] = {}
        ios: dict[str, str] = {}
        handoff: dict[str, Any] = {}
        try:
            runtime = _runtime_package(environment)
            ios = _ios_compile_defines(environment)
            handoff = _launcher_handoff(environment)
            package_issues.extend(_validate_runtime_package(environment, runtime))
            package_issues.extend(_validate_compile_defines(environment, ios))
            manifest_digest = str(
                handoff.get("effectiveLaunchManifestDigest") or ""
            )
            if not SHA256_PATTERN.fullmatch(manifest_digest):
                package_issues.append(
                    f"{environment}: effective launch manifest digest invalid"
                )
        except (RuntimeError, KeyError, json.JSONDecodeError) as exc:
            package_issues.append(f"{environment}: {exc}")
        issues.extend(package_issues)
        packages[environment] = {
            "runtimeDefineKeys": sorted(runtime),
            "iosDefineKeys": sorted(ios),
            "runtimeTarget": handoff.get("target", ""),
            "entrypoint": handoff.get("entrypoint", ""),
            "runtimeConfigPackageDigest": handoff.get(
                "runtimeConfigPackageDigest", ""
            ),
            "effectiveLaunchManifestDigest": handoff.get(
                "effectiveLaunchManifestDigest",
                "",
            ),
            "status": "component_ready" if not package_issues else "failed",
        }
        cases.append(
            _case(
                f"component:{environment}",
                kind="component_readiness",
                status=packages[environment]["status"],
                required=True,
                environment=environment,
                target=handoff.get("target", ""),
                effectiveLaunchManifestDigest=handoff.get(
                    "effectiveLaunchManifestDigest",
                    "",
                ),
                issues=package_issues,
            )
        )

    if root is not None:
        for environment, target in RUNTIME_CASES:
            try:
                handoff = _launcher_handoff(environment, target)
            except (RuntimeError, KeyError, json.JSONDecodeError) as exc:
                handoff = {}
                issues.append(f"{target}: {exc}")
            for platform, device_kind, evidence_stem in DEVICE_PROFILES[target]:
                evidence_path = root / target / f"{evidence_stem}.json"
                key = f"{target}/{evidence_stem}"
                if not evidence_path.is_file():
                    runtime_evidence[key] = {"status": "gate_block"}
                    if args.require_runtime_evidence:
                        cases.append(
                            _case(
                                f"startup:{key}",
                                kind="startup_runtime",
                                status="gate_block",
                                required=True,
                                environment=environment,
                                target=target,
                                platform=platform,
                                deviceKind=device_kind,
                                evidenceRef=str(evidence_path),
                                reason="runtime evidence missing",
                            )
                        )
                else:
                    try:
                        evidence_issues, payload = _validate_runtime_evidence(
                            evidence_path,
                            expected_environment=environment,
                            expected_target=target,
                            expected_platform=platform,
                            expected_effective_manifest_digest=str(
                                handoff.get(
                                    "effectiveLaunchManifestDigest",
                                    "",
                                )
                            ),
                            expected_device_kind=device_kind,
                            expected_baseline_id=args.baseline_id,
                            expected_release_id=args.release_id,
                            expected_release_digest=args.release_digest,
                            require_device_identity=args.require_runtime_evidence,
                            minimum_runs=max(args.minimum_runtime_runs, 1),
                        )
                    except (OSError, json.JSONDecodeError) as exc:
                        payload = {}
                        evidence_issues = [f"{evidence_path}: {exc}"]
                    issues.extend(evidence_issues)
                    runtime_status = (
                        "passed" if not evidence_issues else "failed"
                    )
                    runtime_evidence[key] = {
                        "status": runtime_status,
                        "evidence": payload,
                    }
                    if args.require_runtime_evidence:
                        cases.append(
                            _case(
                                f"startup:{key}",
                                kind="startup_runtime",
                                status=runtime_status,
                                required=True,
                                environment=environment,
                                target=target,
                                platform=platform,
                                deviceKind=device_kind,
                                effectiveLaunchManifestDigest=handoff.get(
                                    "effectiveLaunchManifestDigest",
                                    "",
                                ),
                                evidenceRef=str(evidence_path),
                                issues=evidence_issues,
                            )
                        )

                readback_path = root / target / f"{evidence_stem}.readback.json"
                if args.require_readback:
                    if not readback_path.is_file():
                        readback_evidence[key] = {"status": "gate_block"}
                        cases.append(
                            _case(
                                f"readback:{key}",
                                kind="app_core_readback",
                                status="gate_block",
                                required=True,
                                environment=environment,
                                target=target,
                                platform=platform,
                                deviceKind=device_kind,
                                evidenceRef=str(readback_path),
                                reason="app core readback evidence missing",
                            )
                        )
                    else:
                        try:
                            readback_issues, readback_payload = (
                                _validate_readback_evidence(
                                    readback_path,
                                    expected_environment=environment,
                                    expected_target=target,
                                    expected_platform=platform,
                                    expected_effective_manifest_digest=str(
                                        handoff.get(
                                            "effectiveLaunchManifestDigest",
                                            "",
                                        )
                                    ),
                                    expected_baseline_id=args.baseline_id,
                                    expected_release_id=args.release_id,
                                    expected_release_digest=args.release_digest,
                                    expected_device_kind=(
                                        "physical"
                                        if device_kind in {
                                            "physical",
                                            "true_device",
                                        }
                                        else "simulator"
                                    ),
                                )
                            )
                        except (OSError, json.JSONDecodeError) as exc:
                            readback_payload = {}
                            readback_issues = [f"{readback_path}: {exc}"]
                        issues.extend(readback_issues)
                        readback_status = (
                            "passed"
                            if not readback_issues
                            else (
                                "gate_block"
                                if readback_payload.get("status")
                                == "gate_block"
                                else "failed"
                            )
                        )
                        readback_evidence[key] = {
                            "status": readback_status,
                            "evidence": readback_payload,
                        }
                        cases.append(
                            _case(
                                f"readback:{key}",
                                kind="app_core_readback",
                                status=readback_status,
                                required=True,
                                environment=environment,
                                target=target,
                                platform=platform,
                                deviceKind=device_kind,
                                effectiveLaunchManifestDigest=handoff.get(
                                    "effectiveLaunchManifestDigest",
                                    "",
                                ),
                                evidenceRef=str(readback_path),
                                issues=readback_issues,
                            )
                        )

            observability_path = root / target / "observability.json"
            observability: dict[str, Any] = {}
            observability_issues: list[str] = []
            if observability_path.is_file():
                try:
                    expected_attempt_values = [
                        str(sample.get("attemptId") or "")
                        for platform_payload in (
                            runtime_evidence.get(
                                f"{target}/{evidence_stem}",
                                {},
                            ).get(
                                "evidence",
                                {},
                            )
                            for _, _, evidence_stem in DEVICE_PROFILES[target]
                        )
                        for sample in platform_payload.get("samples", [])
                        if isinstance(sample, dict)
                    ]
                    expected_device_values = [
                        str(sample.get("deviceId") or "")
                        for platform_payload in (
                            runtime_evidence.get(
                                f"{target}/{evidence_stem}",
                                {},
                            ).get(
                                "evidence",
                                {},
                            )
                            for _, _, evidence_stem in DEVICE_PROFILES[target]
                        )
                        for sample in platform_payload.get("samples", [])
                        if isinstance(sample, dict)
                    ]
                    observability_issues, observability = (
                        _validate_observability_evidence(
                            observability_path,
                            expected_environment=environment,
                            expected_target=target,
                            expected_effective_manifest_digest=str(
                                handoff.get(
                                    "effectiveLaunchManifestDigest",
                                    "",
                                )
                            ),
                            expected_baseline_id=args.baseline_id,
                            expected_release_id=args.release_id,
                            expected_release_digest=args.release_digest,
                            expected_attempt_ids=expected_attempt_values,
                            expected_device_ids=expected_device_values,
                        )
                    )
                except (OSError, json.JSONDecodeError) as exc:
                    observability_issues = [f"{observability_path}: {exc}"]
                    observability = {}
                issues.extend(observability_issues)
            observability_ready = (
                observability_path.is_file() and not observability_issues
            )
            observability_evidence[target] = {
                "status": (
                    "passed"
                    if observability_ready
                    else "gate_block"
                    if not observability_path.is_file()
                    else "failed"
                ),
                "evidence": observability,
                "issues": observability_issues,
            }
            if args.require_observability:
                cases.append(
                    _case(
                        f"observability:{target}",
                        kind="startup_observability",
                        status=(
                            "passed"
                            if observability_ready
                            else "gate_block"
                            if not observability_path.is_file()
                            else "failed"
                        ),
                        required=True,
                        environment=environment,
                        target=target,
                        effectiveLaunchManifestDigest=handoff.get(
                            "effectiveLaunchManifestDigest",
                            "",
                        ),
                        evidenceRef=str(observability_path),
                        reason=(
                            ""
                            if observability_ready
                            else (
                                "telemetry readback is missing attempt IDs or "
                                "candidate launch identity"
                            )
                        ),
                    )
                )

    counts = _case_counts(cases)
    status = _report_status(cases, release_gate=release_gate)
    report = {
        "schema": "qwq.startup-environment-case-result",
        "status": status,
        **counts,
        "baselineId": args.baseline_id,
        "releaseId": args.release_id,
        "releaseDigest": args.release_digest,
        "specRefs": list(SPEC_REFS),
        "packages": packages,
        "runtimeEvidence": runtime_evidence,
        "readbackEvidence": readback_evidence,
        "observabilityEvidence": observability_evidence,
        "cases": cases,
        "issues": issues,
    }
    _write_report(args.report, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if status in {"passed", "component_ready"}:
        return 0
    return 2 if status == "gate_block" else 1
