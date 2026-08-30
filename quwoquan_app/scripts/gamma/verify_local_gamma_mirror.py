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
from quwoquan_ops.cli.lib.target_uat_binding import (  # noqa: E402
    TargetUatBindingError,
    read_target_uat_binding,
    target_uat_binding_digest,
)


GAMMA_RUN_ROOT = Path(
    os.environ.get("QWQ_RUN_ROOT")
    or env_run_dir("gamma", "verify-local-gamma", target="gamma-local")
)
DEFAULT_REPORT = GAMMA_RUN_ROOT / "report.json"
DEFAULT_STARTUP_RECEIPT = startup_attempt_path("gamma-local")
START_SCRIPT = ROOT / "quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh"
README = ROOT / "quwoquan_ops/environments/gamma/local/README.md"
RAW_STATUSES = frozenset({"passed", "failed", "blocked", "skipped"})
CANONICAL_RESULT_FIELDS = frozenset(
    {
        "objectId",
        "specRef",
        "caseId",
        "producer",
        "layer",
        "status",
        "target",
        "commitSha",
        "contractGraphSourceHash",
        "deploymentTarget",
        "baselineId",
        "packageDigest",
        "configurationDigest",
        "candidateManifestSha256",
        "candidateDigest",
        "releaseDigest",
        "releaseId",
        "targetUatBindingDigest",
        "entrySurface",
        "carrier",
        "environment",
        "platform",
        "deviceClass",
        "provider",
        "startedAt",
        "completedAt",
        "runnerIdentity",
        "artifactSha256",
        "artifactPath",
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


def _sha256_bytes(path: Path) -> str:
    return "sha256:" + __import__("hashlib").sha256(path.read_bytes()).hexdigest()


def validate_gamma_result_bundle(
    value: object,
    *,
    identity: dict[str, str],
    target_binding: dict[str, Any],
    target_binding_digest: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    if not isinstance(value, dict) or set(value) != {"generatedAt", "results"}:
        raise ValueError("Gamma raw ResultBundle fields mismatch")
    _timestamp(value.get("generatedAt"), label="Gamma raw ResultBundle generatedAt")
    rows = value.get("results")
    if not isinstance(rows, list) or not rows:
        raise ValueError("Gamma raw ResultBundle has no results")
    normalized: list[dict[str, Any]] = []
    issues: list[str] = []
    slots: set[tuple[str, str, str, str]] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"Gamma raw result[{index}] is not an object")
        if not CANONICAL_RESULT_FIELDS.issubset(row):
            raise ValueError(f"Gamma raw result[{index}] fields mismatch")
        if (
            row.get("producer") != "app"
            or row.get("layer") != "user_acceptance"
            or row.get("environment") != "gamma"
            or row.get("deploymentTarget") != "gamma-local"
            or row.get("status") not in RAW_STATUSES
        ):
            raise ValueError(f"Gamma raw result[{index}] canonical identity mismatch")
        if row.get("commitSha") != identity.get("sourceRevision"):
            raise ValueError(f"Gamma raw result[{index}] commitSha mismatch")
        if row.get("packageDigest") != identity.get("packageDigest"):
            raise ValueError(f"Gamma raw result[{index}] packageDigest mismatch")
        if row.get("targetUatBindingDigest") != target_binding_digest:
            raise ValueError(f"Gamma raw result[{index}] TargetUatBinding digest mismatch")
        if row.get("provider") != target_binding["provider"]["identity"]:
            raise ValueError(f"Gamma raw result[{index}] provider identity mismatch")
        slot = (
            str(row.get("platform") or ""),
            str(row.get("deviceClass") or ""),
            str(row.get("entrySurface") or ""),
            str(row.get("carrier") or ""),
        )
        if "" in slot or slot in slots:
            raise ValueError("Gamma raw ResultBundle contains duplicate/incomplete slots")
        slots.add(slot)
        if row["status"] != "passed":
            issues.append(f"{slot} status={row['status']}")
        normalized.append(dict(row))
    return normalized, issues


def _blocked_ref(label: str, reason: str) -> dict[str, str]:
    return {"label": label, "missing": reason}


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
    parser.add_argument("--startup-receipt", default=str(DEFAULT_STARTUP_RECEIPT))
    parser.add_argument("--release-consumer-report", default=str(GAMMA_RUN_ROOT / "release_consumer_report.json"))
    parser.add_argument("--device-uat-report", default=str(GAMMA_RUN_ROOT / "device_uat_report.json"))
    parser.add_argument("--target-uat-binding", required=True)
    parser.add_argument(
        "--configuration-digest",
        default=os.environ.get("LOCAL_GAMMA_CONFIG_VERSION", ""),
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if re.fullmatch(r"sha256:[0-9a-f]{64}", args.configuration_digest) is None:
        print("[local-gamma] GATE_BLOCK: --configuration-digest is invalid")
        return 2
    static_issues = static_contract_issues()
    if static_issues:
        for issue in static_issues:
            print(f"[local-gamma] FAIL: {issue}")
        return 1

    report: dict[str, Any] = {
        "schema": "quwoquan.gamma-mirror-completeness.v1",
        "dryRun": bool(args.dry_run),
        "commitSha": git_sha(),
        "configurationDigest": args.configuration_digest,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "rawRefs": [],
        "coverage": {"observed": 0},
        "missing": [],
        "nonPassed": [],
        "diagnosticRefs": [],
        "promotionAuthority": False,
    }
    exit_code = 0
    if args.dry_run:
        report["missing"].append(_blocked_ref("device_uat", "dry-run has no raw results"))
        exit_code = 2
    else:
        try:
            startup = load_json(Path(args.startup_receipt))
            validate_startup_attempt(
                startup, expected_env="gamma", expected_target="gamma-local"
            )
            active = active_deployment_candidate("gamma-local")
            if not isinstance(active, dict):
                raise ValueError("gamma-local active candidate is missing")
            candidate = load_candidate_manifest(
                "gamma", "gamma-local", str(active.get("baselineId") or ""), require_full=True
            )
            identity = _candidate_identity(
                startup=startup,
                active=active,
                candidate=candidate,
                configuration_digest=args.configuration_digest,
            )
            identity.update(
                {
                    "sourceRevision": str(candidate.get("sourceRevision") or ""),
                }
            )
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            report["missing"].append(_blocked_ref("startup", str(exc)))
            identity = {}
            exit_code = 2

        release_path = Path(args.release_consumer_report)
        if release_path.is_file() and not release_path.is_symlink():
            report["diagnosticRefs"].append(
                {"label": "release_consumer", "ref": str(release_path), "digest": _sha256_bytes(release_path)}
            )
        else:
            report["missing"].append(
                _blocked_ref("release_consumer", "diagnostic report is missing")
            )
            exit_code = 2

        device_path = Path(args.device_uat_report)
        try:
            binding_path = Path(args.target_uat_binding)
            target_binding = read_target_uat_binding(binding_path)
            binding_digest = target_uat_binding_digest(binding_path.read_bytes())
            raw = load_json(device_path)
            results, issues = validate_gamma_result_bundle(
                raw,
                identity=identity,
                target_binding=target_binding,
                target_binding_digest=binding_digest,
            )
            report["rawRefs"].append(
                {"ref": str(device_path), "digest": _sha256_bytes(device_path), "resultCount": len(results)}
            )
            report["coverage"]["observed"] = len(results)
            report["nonPassed"].extend(issues)
            if issues:
                exit_code = 1
        except (OSError, TargetUatBindingError, TypeError, ValueError) as exc:
            report["missing"].append(_blocked_ref("device_uat", str(exc)))
            exit_code = 2

    report_path = Path(args.report)
    if not report_path.is_absolute():
        report_path = ROOT / report_path
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[local-gamma] completeness report: {report_path}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
