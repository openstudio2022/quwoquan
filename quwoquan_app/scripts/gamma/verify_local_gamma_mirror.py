#!/usr/bin/env python3
"""Aggregate local-gamma gate evidence into one commit gate report."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.deployment_candidate_manifest import (  # noqa: E402
    load_candidate_manifest,
)
from quwoquan_ops.cli.lib.output_paths import (  # noqa: E402
    active_deployment_candidate,
    env_run_dir,
)
from quwoquan_ops.cli.lib.startup_attempt_receipt import (  # noqa: E402
    image_composition_from_candidate_oci,
    startup_attempt_path,
    validate_startup_attempt,
)


GAMMA_RUN_ROOT = Path(
    os.environ.get("QWQ_RUN_ROOT")
    or env_run_dir("gamma", "verify-local-gamma", target="gamma-local")
)
DEFAULT_REPORT = GAMMA_RUN_ROOT / "report.json"
DEFAULT_STARTUP_RECEIPT = startup_attempt_path("gamma-local")
START_SCRIPT = ROOT / "quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh"
README = ROOT / "quwoquan_ops/environments/gamma/local/README.md"
CASE_RESULT_SCHEMA = "quwoquan.test.case-result"
CASE_SPEC_REFS = [
    "specs/feature-tree/runtime/deliver-deploy-prod-pipeline/"
    "local-gamma-mirror/spec.md#gwt-003"
]
CASE_IDS = {
    "release_consumer": "local-gamma.release-consumer.remote-api",
    "device_uat": "local-gamma.device-uat",
}
CASE_RESULT_FIELDS = frozenset(
    {
        "schema",
        "caseId",
        "status",
        "environment",
        "target",
        "baselineId",
        "attemptId",
        "packageDigest",
        "configurationDigest",
        "providerRuntimeDigest",
        "observabilityLogSinkDigest",
        "imageDigest",
        "executed",
        "skipped",
        "failed",
        "executedAt",
        "specRefs",
    }
)
DIGEST_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"missing or unsafe report: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"unreadable report {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"report root must be an object: {path}")
    return payload


def git_sha() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def _timestamp(value: object, *, label: str) -> str:
    text = str(value or "").strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} is invalid") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{label} must include a timezone")
    return text


def _candidate_identity(
    *,
    startup: dict[str, Any],
    active: dict[str, Any],
    candidate: dict[str, Any],
    configuration_digest: str,
) -> dict[str, str]:
    baseline_id = str(active.get("baselineId") or "")
    if DIGEST_PATTERN.fullmatch(baseline_id) is None:
        raise ValueError("active Gamma candidate baselineId is invalid")
    if candidate.get("baselineId") != baseline_id:
        raise ValueError("active Gamma candidate manifest baseline drifted")
    if startup.get("status") != "running":
        raise ValueError("Gamma startup attempt is not running")
    if startup.get("workload") != "full":
        raise ValueError("Gamma Green requires workload=full")

    package_digest = str(candidate.get("packageDigest") or "")
    configuration_digest_candidate = str(candidate.get("configurationDigest") or "")
    runtime_config_digest = str(candidate.get("runtimeConfigDigest") or "")
    image_digest = str(candidate.get("imageDigest") or "")
    build_input_digest = str(candidate.get("buildInputDigest") or "")
    for label, digest in (
        ("packageDigest", package_digest),
        ("configurationDigest", configuration_digest_candidate),
        ("runtimeConfigDigest", runtime_config_digest),
        ("imageDigest", image_digest),
        ("buildInputDigest", build_input_digest),
    ):
        if DIGEST_PATTERN.fullmatch(digest) is None:
            raise ValueError(f"active Gamma candidate {label} is invalid")

    provider_runtime = candidate.get("providerRuntime")
    provider_composition = (
        provider_runtime.get("composition")
        if isinstance(provider_runtime, dict)
        else None
    )
    provider_digest = (
        str(provider_composition.get("runtimeCompositionDigest") or "")
        if isinstance(provider_composition, dict)
        else ""
    )
    log_sink = candidate.get("observabilityLogSink")
    log_sink_digest = (
        str(log_sink.get("composeDigest") or "")
        if isinstance(log_sink, dict)
        else ""
    )
    if DIGEST_PATTERN.fullmatch(provider_digest) is None:
        raise ValueError("active Gamma Provider runtime digest is invalid")
    if DIGEST_PATTERN.fullmatch(log_sink_digest) is None:
        raise ValueError("active Gamma observability log-sink digest is invalid")

    if startup.get("candidateDigest") != baseline_id:
        raise ValueError("startup candidate differs from active candidate")
    if (
        startup.get("configurationDigest") != configuration_digest_candidate
        or configuration_digest != configuration_digest_candidate
    ):
        raise ValueError("startup configuration differs from active candidate")
    if startup.get("providerRuntimeDigest") != provider_digest:
        raise ValueError("startup Provider runtime differs from active candidate")
    if startup.get("observabilityLogSinkDigest") != log_sink_digest:
        raise ValueError("startup observability log sink differs from active candidate")

    candidate_dir = Path(str(active.get("candidateDir") or "")).resolve()
    oci_path = (
        candidate_dir / "packages" / "runtime-shared" / "oci-images.json"
    )
    oci = load_json(oci_path)
    if (
        oci.get("configurationDigest") != configuration_digest_candidate
        or oci.get("buildInputDigest") != build_input_digest
        or oci.get("imageDigest") != image_digest
    ):
        raise ValueError("active Gamma OCI manifest identity drifted")
    expected_image_composition = image_composition_from_candidate_oci(
        oci,
        expected_environment="gamma",
        expected_target="gamma-local",
    )
    if (
        startup.get("imageComposition") != expected_image_composition
        or startup.get("imageTransportTag")
        != expected_image_composition["imageVersion"]
    ):
        raise ValueError("startup image composition differs from active candidate")

    return {
        "environment": "gamma",
        "target": "gamma-local",
        "baselineId": baseline_id,
        "attemptId": str(startup["attemptId"]),
        "packageDigest": package_digest,
        "configurationDigest": configuration_digest_candidate,
        "providerRuntimeDigest": provider_digest,
        "observabilityLogSinkDigest": log_sink_digest,
        "imageDigest": image_digest,
    }


def validate_gamma_case_result(
    value: object,
    *,
    phase: str,
    identity: dict[str, str],
) -> dict[str, Any]:
    if phase not in CASE_IDS:
        raise ValueError(f"unsupported Gamma CaseResult phase: {phase}")
    if not isinstance(value, dict) or set(value) != CASE_RESULT_FIELDS:
        raise ValueError(f"{phase} CaseResult fields mismatch")
    if (
        value.get("schema") != CASE_RESULT_SCHEMA
        or value.get("caseId") != CASE_IDS[phase]
        or value.get("status") != "passed"
        or value.get("specRefs") != CASE_SPEC_REFS
    ):
        raise ValueError(f"{phase} CaseResult schema/identity mismatch")
    for field, expected in identity.items():
        if value.get(field) != expected:
            raise ValueError(f"{phase} CaseResult {field} mismatch")
    for field in ("executed", "skipped", "failed"):
        count = value.get(field)
        if not isinstance(count, int) or isinstance(count, bool):
            raise ValueError(f"{phase} CaseResult {field} is invalid")
    if value["executed"] <= 0 or value["skipped"] != 0 or value["failed"] != 0:
        raise ValueError(
            f"{phase} CaseResult requires executed>0, skipped=0, failed=0"
        )
    _timestamp(value.get("executedAt"), label=f"{phase} CaseResult executedAt")
    return dict(value)


def _blocked_case(phase: str, reason: str, *, failed: bool = False) -> dict[str, Any]:
    return {
        "schema": CASE_RESULT_SCHEMA,
        "caseId": CASE_IDS[phase],
        "status": "failed" if failed else "gate_block",
        "reason": reason,
    }


def static_contract_issues() -> list[str]:
    """Guard local-gamma against falling back to retired taxonomy projections."""
    retired_tags_path = "/".join(("publish", "v1", "tags"))
    issues: list[str] = []
    for path in (START_SCRIPT, README):
        text = path.read_text(encoding="utf-8")
        if retired_tags_path in text:
            issues.append(f"{path.relative_to(ROOT)} still references {retired_tags_path}")
    script = START_SCRIPT.read_text(encoding="utf-8")
    expected = "$ROOT/quwoquan_data/control_plane/governance/taxonomy"
    if expected not in script:
        issues.append(
            "start_local_gamma_mirror.sh must default LOCAL_GAMMA_TAGS_DIR "
            "to quwoquan_data/control_plane/governance/taxonomy"
        )
    if "bootstrap_local_gamma_tag_taxonomy" in script:
        issues.append("local-gamma must not materialize a runtime taxonomy copy")
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument(
        "--startup-receipt",
        default=str(DEFAULT_STARTUP_RECEIPT),
    )
    parser.add_argument("--release-consumer-report", default=str(GAMMA_RUN_ROOT / "release_consumer_report.json"))
    parser.add_argument("--device-uat-report", default=str(GAMMA_RUN_ROOT / "device_uat_report.json"))
    parser.add_argument(
        "--configuration-digest",
        default=os.environ.get("LOCAL_GAMMA_CONFIG_VERSION", ""),
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if re.fullmatch(r"sha256:[0-9a-f]{64}", args.configuration_digest) is None:
        print(
            "[local-gamma] GATE_BLOCK: --configuration-digest must be the "
            "canonical sha256 runtime configuration digest"
        )
        return 2
    static_issues = static_contract_issues()
    if static_issues:
        for issue in static_issues:
            print(f"[local-gamma] FAIL: {issue}")
        return 1

    if args.dry_run:
        report = {
            "status": "gate_block",
            "dryRun": True,
            "contractOnly": True,
            "commitSha": git_sha(),
            "configurationDigest": args.configuration_digest,
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "gammaValidationSuiteRegistry": "quwoquan_ops/environments/gamma/validation_suites.json",
            "serviceMode": "single-stack",
            "restartedFromPrevious": False,
            "tests": {
                "release_consumer": _blocked_case("release_consumer", "dry-run has no executed CaseResult"),
                "device_uat": _blocked_case("device_uat", "dry-run has no executed CaseResult"),
            },
        }
    else:
        startup_issue = ""
        startup: dict[str, Any] = {}
        release_consumer: dict[str, Any] = _blocked_case(
            "release_consumer",
            "startup identity is unavailable",
        )
        device_uat: dict[str, Any] = _blocked_case(
            "device_uat",
            "startup identity is unavailable",
        )
        image_transport_tag = ""
        identity: dict[str, str] = {}
        try:
            startup = load_json(Path(args.startup_receipt))
            image_transport_tag = str(startup.get("imageTransportTag") or "")
            validate_startup_attempt(
                startup,
                expected_env="gamma",
                expected_target="gamma-local",
            )
            active = active_deployment_candidate("gamma-local")
            if not isinstance(active, dict):
                raise ValueError("gamma-local active candidate is missing")
            baseline_id = str(active.get("baselineId") or "")
            candidate = load_candidate_manifest(
                "gamma",
                "gamma-local",
                baseline_id,
                require_full=True,
            )
            identity = _candidate_identity(
                startup=startup,
                active=active,
                candidate=candidate,
                configuration_digest=args.configuration_digest,
            )
            startup_ready = True
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            startup_ready = False
            startup_issue = str(exc)
        if startup_ready:
            raw_cases = {
                "release_consumer": Path(args.release_consumer_report),
                "device_uat": Path(args.device_uat_report),
            }
            normalized_cases: dict[str, dict[str, Any]] = {}
            for phase, case_path in raw_cases.items():
                raw_case: dict[str, Any] = {}
                try:
                    raw_case = load_json(case_path)
                    normalized_cases[phase] = validate_gamma_case_result(
                        raw_case,
                        phase=phase,
                        identity=identity,
                    )
                except (TypeError, ValueError) as exc:
                    normalized_cases[phase] = _blocked_case(
                        phase,
                        str(exc),
                        failed=raw_case.get("status") == "failed",
                    )
            release_consumer = normalized_cases["release_consumer"]
            device_uat = normalized_cases["device_uat"]
        statuses = {
            "startup": "passed" if startup_ready else "gate_block",
            "release_consumer": str(
                release_consumer.get("status") or "gate_block"
            ),
            "device_uat": str(device_uat.get("status") or "gate_block"),
        }
        if any(value == "failed" for value in statuses.values()):
            overall = "failed"
        elif any(value != "passed" for value in statuses.values()):
            overall = "gate_block"
        else:
            overall = "passed"
        report = {
            "status": overall,
            "dryRun": False,
            "commitSha": git_sha(),
            "configurationDigest": args.configuration_digest,
            "imageVersion": image_transport_tag,
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "gammaValidationSuiteRegistry": "quwoquan_ops/environments/gamma/validation_suites.json",
            "serviceMode": "single-stack",
            "startupAttempt": startup,
            "startupIssue": startup_issue,
            "tests": {
                "release_consumer": release_consumer,
                "device_uat": device_uat,
            },
            "prodGateReminder": (
                "Local gamma mirror does not replace prod-hosted validation, prod SLO, "
                "rollback drill, or prod observability gates."
            ),
        }

    report_path = Path(args.report)
    if not report_path.is_absolute():
        report_path = ROOT / report_path
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"[local-gamma] report: {report_path}")
    print(f"[local-gamma] status: {report['status']}")
    return 0 if report["status"] == "passed" else 2 if report["status"] == "gate_block" else 1


if __name__ == "__main__":
    raise SystemExit(main())
