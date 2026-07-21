#!/usr/bin/env python3
"""执行声明的 Provider Conformance 测试并生成受 CI 证明保护的证据。"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import sys
from typing import Any, Mapping

import yaml


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib import external_provider_governance as governance
from quwoquan_ops.cli.lib import provider_conformance
from quwoquan_ops.cli.lib.output_paths import env_run_dir, output_root


def _digest_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _digest_json(value: object) -> str:
    return _digest_bytes(
        json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    )


def _source_command(source: str) -> tuple[list[str], Path]:
    source_path = ROOT / source
    if not source_path.is_file():
        raise ValueError(f"declared conformance test source is missing: {source}")
    if source_path.suffix == ".py":
        return [sys.executable, source], ROOT
    if source_path.suffix == ".go":
        try:
            package = source_path.parent.relative_to(ROOT / "quwoquan_service")
        except ValueError as exc:
            raise ValueError(f"Go conformance source must be under quwoquan_service: {source}") from exc
        return ["go", "test", f"./{package.as_posix()}"], ROOT / "quwoquan_service"
    raise ValueError(f"unsupported conformance test source type: {source}")


def _blocked_user_acceptance_prerequisite(source: str) -> Mapping[str, str] | None:
    """读取尚未注册真实 Remote journey 的受控 fail-closed 前置条件。"""

    source_path = ROOT / source
    if source_path.suffix not in {".yaml", ".yml"}:
        return None
    try:
        payload = yaml.safe_load(source_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"cannot read user_acceptance prerequisite {source}: {exc}") from exc
    if not isinstance(payload, Mapping):
        return None
    if (
        payload.get("schema")
        != governance.MESSAGE_TRANSPORT_REMOTE_UAT_PREREQUISITE_SCHEMA
    ):
        return None
    expected_fields = {
        "schema",
        "status",
        "prerequisite_id",
        "reason_code",
        "recovery_action",
        "required_harness",
        "required_assertions",
        "forbidden_substitutes",
    }
    if set(payload) != expected_fields:
        raise ValueError(
            f"user_acceptance prerequisite {source} has an invalid controlled contract"
        )
    prerequisite_id = payload.get("prerequisite_id")
    reason_code = payload.get("reason_code")
    recovery_action = payload.get("recovery_action")
    if (
        payload.get("status") != "blocked"
        or not all(
            isinstance(value, str) and value.strip()
            for value in (prerequisite_id, reason_code, recovery_action)
        )
    ):
        raise ValueError(
            f"user_acceptance prerequisite {source} must declare a blocked recovery contract"
        )
    return {
        "prerequisite_id": prerequisite_id,
        "reason_code": reason_code,
        "recovery_action": recovery_action,
    }


def _selected_binding(
    compiled: Mapping[str, Any],
    *,
    capability_id: str,
    environment: str,
) -> Mapping[str, Any]:
    selected = compiled.get("selectedBindings")
    if not isinstance(selected, Mapping):
        raise ValueError("compiled provider binding receipt is missing")
    environment_bindings = selected.get(environment)
    if not isinstance(environment_bindings, Mapping):
        raise ValueError(f"compiled provider binding receipt has no {environment} environment")
    binding = environment_bindings.get(capability_id)
    if not isinstance(binding, Mapping):
        raise ValueError(f"{environment} has no selected Binding for {capability_id}")
    return binding


def _profile_assertion_ids(
    manifest: Mapping[str, Any],
    *,
    profile_id: str,
) -> list[str]:
    common = manifest.get("common_assertion_ids")
    profile_assertions = manifest.get("profile_assertion_ids")
    if not isinstance(common, list) or not isinstance(profile_assertions, Mapping):
        raise ValueError("provider conformance manifest has invalid assertion declarations")
    specific = profile_assertions.get(profile_id)
    if not isinstance(specific, list):
        raise ValueError(f"provider conformance profile {profile_id!r} has no assertion set")
    assertion_ids = [*common, *specific]
    if not all(isinstance(item, str) for item in assertion_ids):
        raise ValueError(f"provider conformance profile {profile_id!r} has non-string assertions")
    return assertion_ids


def _network_boundary(layer: str) -> str:
    return {
        "local_contract": "offline_harness",
        "api_integration": "remote_protocol",
        "user_acceptance": "user_journey",
    }[layer]


def _current_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        check=True,
        text=True,
    )
    return result.stdout.strip()


def _contract_graph_digest() -> str:
    contract_graph = ROOT / "quwoquan_service" / "generated" / "contract_graph.json"
    if not contract_graph.is_file():
        raise ValueError("generated/contract_graph.json is required before conformance execution")
    return _digest_bytes(contract_graph.read_bytes())


def _write_json(path: Path, value: Mapping[str, Any]) -> bytes:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ).encode("utf-8") + b"\n"
    path.write_bytes(raw)
    return raw


def _evidence_ref(path: Path) -> str:
    try:
        relative = path.relative_to(output_root())
    except ValueError as exc:
        raise ValueError("conformance artifacts must be under QWQ_OUTPUT_ROOT") from exc
    return f".qwq_output/{relative.as_posix()}"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Execute one Provider Conformance cell and emit attested evidence.",
    )
    parser.add_argument("--adapter-id", required=True)
    parser.add_argument("--environment", required=True, choices=provider_conformance.ENVIRONMENTS)
    parser.add_argument("--layer", required=True, choices=provider_conformance.LAYERS)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="run the declared test command; without this flag the evidence remains blocked",
    )
    parser.add_argument(
        "--image-digest",
        default="",
        help="immutable deployment image digest; required for a passed cell",
    )
    parser.add_argument(
        "--data-digest",
        default="",
        help="immutable fixture/seed digest; defaults only for a blocked dry run",
    )
    parser.add_argument("--switch-compatibility-receipt-ref", default="")
    parser.add_argument("--callback-drain-receipt-ref", default="")
    parser.add_argument("--last-good-receipt-ref", default="")
    parser.add_argument("--rollback-receipt-ref", default="")
    parser.add_argument("--prod-binding-preflight-receipt-ref", default="")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        registry = governance.load_registry()
        manifest = governance.load_conformance_manifest()
        compiled, issues = governance.load_and_compile()
        if issues:
            raise ValueError("; ".join(issue.render() for issue in issues))
        adapters = {
            item.get("adapter_id"): item
            for item in registry.get("adapters", [])
            if isinstance(item, Mapping)
        }
        adapter = adapters.get(args.adapter_id)
        if not isinstance(adapter, Mapping):
            raise ValueError(f"unregistered adapter: {args.adapter_id}")
        capability_id = adapter.get("capability_id")
        profile_id = adapter.get("conformance_profile")
        if not isinstance(capability_id, str) or not isinstance(profile_id, str):
            raise ValueError(f"adapter {args.adapter_id} is missing capability/profile metadata")
        capabilities = {
            item.get("capability_id"): item
            for item in registry.get("capabilities", [])
            if isinstance(item, Mapping)
        }
        capability = capabilities.get(capability_id)
        if not isinstance(capability, Mapping):
            raise ValueError(f"unregistered capability for adapter {args.adapter_id}: {capability_id}")
        binding = _selected_binding(
            compiled,
            capability_id=capability_id,
            environment=args.environment,
        )
        if binding.get("adapter_id") != args.adapter_id:
            raise ValueError(
                f"{args.adapter_id} is not selected for {capability_id} in {args.environment}"
            )
        binding_root_records = provider_conformance.compiled_capability_binding_roots(
            compiled,
            capability_id=capability_id,
        )
        binding_roots = [root["root_id"] for root in binding_root_records]
        profiles = manifest.get("profiles")
        profile = profiles.get(profile_id) if isinstance(profiles, Mapping) else None
        source = profile.get(args.layer) if isinstance(profile, Mapping) else None
        if not isinstance(source, str):
            raise ValueError(f"profile {profile_id} has no {args.layer} test source")
        user_acceptance_prerequisite = _blocked_user_acceptance_prerequisite(source)
        if user_acceptance_prerequisite is None:
            command, command_cwd = _source_command(source)
        else:
            command = [
                "provider-conformance-prerequisite",
                user_acceptance_prerequisite["prerequisite_id"],
            ]
            command_cwd = ROOT
        assertion_ids = _profile_assertion_ids(manifest, profile_id=profile_id)
        execution_gate_blocked = False
        if not args.execute:
            status = "blocked"
            exit_code = 0
            failure: Mapping[str, str] | None = {
                "code": "PROVIDER.CONFORMANCE.EXECUTION_REQUIRED"
            }
        elif user_acceptance_prerequisite is not None:
            status = "blocked"
            exit_code = 0
            failure = {
                "code": user_acceptance_prerequisite["reason_code"],
                "recoveryAction": user_acceptance_prerequisite["recovery_action"],
            }
            execution_gate_blocked = True
        else:
            result = subprocess.run(command, cwd=command_cwd, capture_output=True, text=True)
            exit_code = result.returncode
            status = "passed" if exit_code == 0 else "failed"
            failure = (
                None
                if exit_code == 0
                else {"code": "PROVIDER.CONFORMANCE.TEST_COMMAND_FAILED"}
            )
        image_digest = args.image_digest or _digest_json({"commit": _current_commit()})
        if status == "passed" and not args.image_digest:
            raise ValueError("--image-digest is required for passed conformance evidence")
        data_digest = args.data_digest or _digest_json(
            {
                "source": source,
                "mode": (
                    "remote_uat_prerequisite"
                    if user_acceptance_prerequisite is not None
                    else ("dry_run" if not args.execute else "test_harness")
                ),
            }
        )
        executed_at = datetime.now(timezone.utc).isoformat()
        adapter_path = ROOT / str(adapter.get("implementation_path"))
        if not adapter_path.is_file():
            raise ValueError(f"adapter implementation path is missing: {adapter_path}")
        report: dict[str, Any] = {
            "schema": provider_conformance.EXECUTION_REPORT_SCHEMA,
            "version": provider_conformance.EXECUTION_REPORT_VERSION,
            "adapterId": args.adapter_id,
            "capabilityId": capability_id,
            "bindingRoots": binding_roots,
            "environment": args.environment,
            "testLayer": args.layer,
            "executionProfile": provider_conformance.CELL_PROFILES[
                (args.environment, args.layer)
            ],
            "status": status,
            "executedAt": executed_at,
            "commit": _current_commit(),
            "imageDigest": image_digest,
            "configDigest": _digest_json(
                {
                    "binding": binding,
                    "bindingRoots": binding_root_records,
                }
            ),
            "contractGraphDigest": _contract_graph_digest(),
            "adapterDigest": _digest_bytes(adapter_path.read_bytes()),
            "assertionIds": assertion_ids,
            "networkBoundary": _network_boundary(args.layer),
            "dataDigest": data_digest,
            "testSource": source,
            "testCommand": shlex.join(command),
            "exitCode": exit_code,
        }
        run_dir = env_run_dir(
            args.environment,
            "provider-conformance",
            target=f"{args.adapter_id}-{args.layer}",
        )
        run_dir.mkdir(parents=True, exist_ok=True)
        stem = f"provider-conformance-{args.adapter_id.replace('.', '-')}-{args.layer}"
        report_path = run_dir / f"{stem}.report.json"
        report_bytes = _write_json(report_path, report)
        evidence: dict[str, Any] = {
            "schema": "provider-conformance-evidence",
            "version": 1,
            "adapterId": args.adapter_id,
            "capabilityId": capability_id,
            "bindingRoots": binding_roots,
            "environment": args.environment,
            "testLayer": args.layer,
            "executionProfile": report["executionProfile"],
            "status": status,
            "executedAt": executed_at,
            "artifactRef": _evidence_ref(report_path),
            "artifactDigest": _digest_bytes(report_bytes),
            "artifactAttestation": provider_conformance.sign_execution_report(report_bytes),
            "commit": report["commit"],
            "imageDigest": image_digest,
            "configDigest": report["configDigest"],
            "contractGraphDigest": report["contractGraphDigest"],
            "adapterDigest": report["adapterDigest"],
            "assertionCount": len(assertion_ids),
            "assertionIds": assertion_ids,
            "networkBoundary": report["networkBoundary"],
            "dataDigest": data_digest,
            "cleanupReceipt": f"cleanup:provider-conformance:{run_dir.name}",
            "acceptanceRefs": capability.get("acceptance_refs", []),
            "observabilityRefs": {
                "logs": [f"provider-conformance://{args.adapter_id}/logs"],
                "traces": [f"provider-conformance://{args.adapter_id}/traces"],
                "metrics": [
                    f"provider-conformance://{args.adapter_id}/metrics",
                    *provider_conformance.required_metric_refs(capability_id),
                ],
            },
        }
        if failure is not None:
            evidence["failure"] = failure
        if args.environment == "gamma" and args.layer == "user_acceptance":
            release_readiness = {
                "switchCompatibilityReceiptRef": args.switch_compatibility_receipt_ref,
                "callbackDrainReceiptRef": args.callback_drain_receipt_ref,
                "lastGoodReceiptRef": args.last_good_receipt_ref,
                "rollbackReceiptRef": args.rollback_receipt_ref,
                "prodBindingPreflightReceiptRef": args.prod_binding_preflight_receipt_ref,
            }
            if not all(release_readiness.values()):
                raise ValueError(
                    "Gamma user_acceptance requires all five non-sensitive release receipt references"
                )
            evidence["releaseReadiness"] = release_readiness
        evidence_path = run_dir / f"{stem}.evidence.json"
        _write_json(evidence_path, evidence)
    except (OSError, subprocess.CalledProcessError, ValueError) as exc:
        print(f"[provider_conformance_runner] FAIL: {exc}", file=sys.stderr)
        return 1
    if execution_gate_blocked:
        print(
            "[provider_conformance_runner] GATE_BLOCK: "
            f"{user_acceptance_prerequisite['reason_code']}; register the controlled "
            "Remote chat @ assistant device journey before executing this cell",
            file=sys.stderr,
        )
        return 1
    print(f"[provider_conformance_runner] evidence={evidence_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
