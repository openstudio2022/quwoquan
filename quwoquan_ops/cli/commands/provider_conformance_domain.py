"""stackctl `provider-conformance` 子命令域: Provider Conformance 九格单元
执行、运行时身份选择与本地功能就绪证据。

从 stackctl.py 逐字迁出: `_provider_conformance_runner` / `_provider_conformance`
（延迟 import 桥）、`_provider_conformance_runtime_environment`、
`_command_provider_conformance_unlocked`、`command_provider_conformance`。

测试经 ``mock.patch.object(stackctl, ...)`` patch 本模块符号与协作符号，
因此函数体内一律经函数内延迟导入 `_stackctl` 属性访问（含本模块符号互调），
保持 monkeypatch 语义并避免顶层循环 import。
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import subprocess

from pathlib import Path
from typing import Any
from typing import Mapping


def _provider_conformance_runner():
    from quwoquan_ops.cli import provider_conformance_runner

    return provider_conformance_runner


def _provider_conformance():
    from quwoquan_ops.cli.lib import provider_conformance

    return provider_conformance


def _provider_conformance_runtime_environment(
    environment: str,
) -> dict[str, str]:
    import quwoquan_ops.cli.stackctl as _stackctl

    if environment not in {"alpha", "beta", "gamma"}:
        return {}
    target_name = f"{environment}-local"
    auth = _stackctl.load_local_environment_auth(environment, target_name)
    values = dict(os.environ)
    values.update(auth.environment)
    mutable_receipt = _stackctl.load_test_live_startup_attempt(target_name)
    if (
        isinstance(mutable_receipt, Mapping)
        and mutable_receipt.get("status") == "running"
    ):
        if (
            mutable_receipt.get("environment") != environment
            or mutable_receipt.get("target") != target_name
            or mutable_receipt.get("workload") != "full"
            or not str(mutable_receipt.get("attemptId") or "").strip()
            or mutable_receipt.get("failure") not in {None, ""}
            or mutable_receipt.get("cleanupFailure") not in {None, ""}
        ):
            raise RuntimeError(
                f"GATE_BLOCK: {target_name} test_live runtime identity drifted"
            )
        composition = _stackctl.compile_provider_runtime_composition(
            environment=environment,
            target=target_name,
        )
        if (
            mutable_receipt.get("providerRuntimeDigest")
            != composition.get("runtimeCompositionDigest")
        ):
            raise RuntimeError(
                f"GATE_BLOCK: {target_name} test_live Provider runtime drifted"
            )
        runtime_identity: dict[str, Any] = {
            "schema": "stackctl.provider_conformance_runtime_identity",
            "runtimeMode": "test_live",
            "environment": environment,
            "target": target_name,
            "workload": "full",
            "startupAttemptId": mutable_receipt["attemptId"],
            "providerRuntimeDigest": mutable_receipt["providerRuntimeDigest"],
            "failureFree": True,
            "nonPromotable": True,
            "mutableComposeDigest": mutable_receipt.get("composeDigest"),
            "mutableConfigurationDigest": mutable_receipt.get(
                "configurationDigest"
            ),
            "mutableStateDigest": mutable_receipt.get("mutableStateDigest"),
            "mutableWorkspaceStatusDigest": mutable_receipt.get(
                "workspaceStatusDigest"
            ),
            "mutableResolverHandoffDigest": mutable_receipt.get(
                "resolverHandoffDigest"
            ),
            "mutableSourceRevision": mutable_receipt.get("sourceRevision"),
        }
    else:
        immutable_runtime = _stackctl._active_provider_runtime(
            environment,
            target_name,
        )
        composition = immutable_runtime["composition"]
        immutable_receipt = _stackctl.load_startup_attempt(target_name)
        if (
            not isinstance(immutable_receipt, Mapping)
            or immutable_receipt.get("status") != "running"
            or immutable_receipt.get("env") != environment
            or immutable_receipt.get("target") != target_name
            or immutable_receipt.get("workload") != "full"
            or not str(immutable_receipt.get("attemptId") or "").strip()
            or immutable_receipt.get("candidateDigest")
            != immutable_runtime.get("baselineId")
            or immutable_receipt.get("providerRuntimeDigest")
            != composition.get("runtimeCompositionDigest")
            or immutable_receipt.get("failure") not in {None, ""}
            or immutable_receipt.get("cleanupFailure") not in {None, ""}
        ):
            raise RuntimeError(
                f"GATE_BLOCK: {target_name} immutable runtime does not match "
                "the active candidate"
            )
        runtime_identity = {
            "schema": "stackctl.provider_conformance_runtime_identity",
            "runtimeMode": "immutable_candidate",
            "environment": environment,
            "target": target_name,
            "workload": "full",
            "startupAttemptId": immutable_receipt["attemptId"],
            "providerRuntimeDigest": immutable_receipt[
                "providerRuntimeDigest"
            ],
            "failureFree": True,
            "nonPromotable": False,
            "candidateDigest": immutable_runtime["baselineId"],
        }
    digest_fields = [
        value
        for key, value in runtime_identity.items()
        if key.endswith("Digest")
    ]
    if (
        any(
            re.fullmatch(r"sha256:[0-9a-f]{64}", str(value or "")) is None
            for value in digest_fields
        )
        or runtime_identity["runtimeMode"] == "test_live"
        and re.fullmatch(
            r"[0-9a-f]{40}",
            str(runtime_identity.get("mutableSourceRevision") or ""),
        )
        is None
    ):
        raise RuntimeError(
            f"GATE_BLOCK: {target_name} Provider conformance runtime identity "
            "is incomplete"
        )
    error = _stackctl._bind_local_external_provider_environment(
        values,
        environment_name=environment,
        target_name=target_name,
        storage_prefix=environment.upper(),
        runtime_composition=composition,
    )
    if error:
        raise RuntimeError(error)
    values[_stackctl.PROVIDER_CONFORMANCE_RUNTIME_IDENTITY_ENV] = json.dumps(
        runtime_identity,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    projected = {
        key: value
        for key, value in values.items()
        if os.environ.get(key) != value
    }
    # This field is the mandatory stackctl -> runner contract, not an optional
    # environment delta.  Preserve it even when a parent process happens to
    # contain the same value so direct and matrix execution cannot lose the
    # selected canonical runtime identity.
    projected[_stackctl.PROVIDER_CONFORMANCE_RUNTIME_IDENTITY_ENV] = values[
        _stackctl.PROVIDER_CONFORMANCE_RUNTIME_IDENTITY_ENV
    ]
    return projected



def _redact_rehearsal_detail(value: object) -> str:
    """Keep target reports diagnostic without exposing endpoint or secret values."""
    detail = str(value or "").strip()
    detail = re.sub(r"https?://[^\s,;]+", "[redacted-endpoint]", detail)
    detail = re.sub(
        r"(?i)\b(?:token|secret|password|api[_-]?key)\b\s*=\s*[^\s,;]+",
        "[redacted-secret]",
        detail,
    )
    return detail or "unspecified Provider rehearsal failure"


def _prod_sim_rehearsal_identity() -> tuple[dict[str, Any], Mapping[str, Any]]:
    """Freeze prod-sim at one candidate/full-startup/runtime/config identity."""
    import quwoquan_ops.cli.stackctl as _stackctl

    environment = "prod"
    target_name = "prod-sim"
    runtime = _stackctl._active_provider_runtime(environment, target_name)
    if not isinstance(runtime, Mapping):
        raise ValueError("prod-sim active Provider runtime is unavailable")
    baseline_id = str(runtime.get("baselineId") or "")
    composition = runtime.get("composition")
    if re.fullmatch(r"sha256:[0-9a-f]{64}", baseline_id) is None or not isinstance(
        composition, Mapping
    ):
        raise ValueError("prod-sim active Provider runtime identity is incomplete")
    candidate = _stackctl.load_candidate_manifest(
        environment,
        target_name,
        baseline_id,
        require_full=True,
    )
    receipt = _stackctl.load_startup_attempt(target_name)
    candidate_runtime = (
        candidate.get("providerRuntime") if isinstance(candidate, Mapping) else None
    )
    candidate_composition = (
        candidate_runtime.get("composition")
        if isinstance(candidate_runtime, Mapping)
        else None
    )
    candidate_config_digest = (
        str(candidate.get("configurationDigest") or "")
        if isinstance(candidate, Mapping)
        else ""
    )
    if (
        not isinstance(candidate, Mapping)
        or not isinstance(candidate_runtime, Mapping)
        or not isinstance(receipt, Mapping)
        or candidate.get("environment") != environment
        or candidate.get("target") != target_name
        or candidate.get("baselineId") != baseline_id
        or candidate_composition != composition
        or candidate_runtime.get("rehearsal")
        != {"kind": "local-provider-substitute", "nonPromotable": True}
        or receipt.get("status") != "running"
        or receipt.get("env") != environment
        or receipt.get("target") != target_name
        or receipt.get("workload") != "full"
        or receipt.get("candidateDigest") != baseline_id
        or receipt.get("providerRuntimeDigest")
        != composition.get("runtimeCompositionDigest")
        or receipt.get("configurationDigest") != candidate_config_digest
        or receipt.get("failure") not in {None, ""}
        or receipt.get("cleanupFailure") not in {None, ""}
        or not str(receipt.get("attemptId") or "").strip()
        or re.fullmatch(r"sha256:[0-9a-f]{64}", candidate_config_digest) is None
    ):
        raise ValueError(
            "prod-sim active candidate/startup/provider runtime/config identity mismatch"
        )
    identity = {
        "candidateDigest": baseline_id,
        "startupAttemptId": str(receipt["attemptId"]),
        "providerRuntimeDigest": str(receipt["providerRuntimeDigest"]),
        "configDigest": candidate_config_digest,
    }
    return identity, composition


def _prod_sim_rehearsal_required_capabilities(
    composition: Mapping[str, Any],
) -> list[dict[str, str]]:
    """Enumerate required capabilities from the sealed runtime composition only."""
    import quwoquan_ops.cli.stackctl as _stackctl

    bindings = composition.get("bindings")
    if not isinstance(bindings, list) or not bindings:
        raise ValueError("prod-sim Provider runtime composition has no bindings")
    required: list[dict[str, str]] = []
    seen: set[str] = set()
    for binding in bindings:
        if not isinstance(binding, Mapping):
            raise ValueError("prod-sim Provider runtime composition binding is invalid")
        capability_id = str(binding.get("capabilityId") or "").strip()
        adapter_id = str(binding.get("adapterId") or "").strip()
        state = str(binding.get("state") or "").strip()
        if not capability_id or capability_id in seen or not state:
            raise ValueError("prod-sim Provider runtime composition binding identity is invalid")
        seen.add(capability_id)
        if not _stackctl._external_provider_governance().requires_provider_conformance(
            {"state": state, "adapter_id": adapter_id}
        ):
            continue
        if state != "enabled" or not adapter_id:
            raise ValueError(
                f"prod-sim required capability {capability_id} has no enabled Provider Binding"
            )
        required.append({"capabilityId": capability_id, "adapterId": adapter_id})
    if not required:
        raise ValueError("prod-sim runtime requires no Provider conformance capabilities")
    return sorted(required, key=lambda item: item["capabilityId"])


def _prod_sim_first_party_source(
    source: Mapping[str, Any] | None,
    *,
    capability_id: str,
) -> Mapping[str, Any]:
    """Reject substitute-only sources before any rehearsal invocation begins."""
    if not isinstance(source, Mapping):
        raise ValueError(
            f"GATE_BLOCK: prod-sim/{capability_id} has no source-declared first-party blackbox runner"
        )
    declaration = source.get("prodSimFirstParty")
    command = source.get("command")
    test_source = str(source.get("testSource") or "")
    test_target = str(source.get("target") or "")
    if (
        not isinstance(declaration, Mapping)
        or set(declaration) != {"service"}
        or not re.fullmatch(r"[a-z][a-z0-9-]*", str(declaration.get("service") or ""))
        or "/service_ops/" not in test_source
        or not isinstance(command, list)
        or not command
        or any(
            re.search(r"(?i)(?:substitute|fixture|--token|--secret|https?://)", value)
            for value in (*[str(item) for item in command], test_target)
        )
    ):
        raise ValueError(
            f"GATE_BLOCK: prod-sim/{capability_id} lacks a first-party service/Integration blackbox source"
        )
    return source


def _validate_prod_sim_first_party_case(
    payload: object,
    *,
    capability: Mapping[str, str],
    identity: Mapping[str, str],
    source: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate invocation/effect/readback/cleanup/observability evidence."""
    if not isinstance(payload, Mapping) or set(payload) != {
        "schema",
        "status",
        "capabilityId",
        "adapterId",
        "candidateDigest",
        "startupAttemptId",
        "providerRuntimeDigest",
        "configDigest",
        "invocations",
    }:
        raise ValueError("first-party runner emitted an invalid prod-sim case result")
    if (
        payload.get("schema") != "provider-conformance-prod-sim-first-party-case-results"
        or payload.get("status") != "passed"
        or payload.get("capabilityId") != capability["capabilityId"]
        or payload.get("adapterId") != capability["adapterId"]
        or any(payload.get(key) != value for key, value in identity.items())
    ):
        raise ValueError("first-party runner case identity does not match prod-sim rehearsal")
    invocations = payload.get("invocations")
    declared_service = source["prodSimFirstParty"]["service"]
    if not isinstance(invocations, list) or not invocations:
        raise ValueError("first-party runner reported zero Provider invocations")
    for invocation in invocations:
        observability = invocation.get("observabilityRefs") if isinstance(invocation, Mapping) else None
        if (
            not isinstance(invocation, Mapping)
            or set(invocation) != {
                "firstPartyService",
                "operation",
                "invocationRef",
                "effectReadbackRef",
                "cleanupReceipt",
                "observabilityRefs",
            }
            or invocation.get("firstPartyService") != declared_service
            or not all(
                isinstance(invocation.get(field), str) and invocation[field].strip()
                for field in ("operation", "invocationRef", "effectReadbackRef", "cleanupReceipt")
            )
            or not isinstance(observability, Mapping)
            or set(observability) != {"logs", "traces", "metrics"}
            or any(
                not isinstance(observability.get(kind), list)
                or not observability[kind]
                or not all(isinstance(ref, str) and ref.strip() for ref in observability[kind])
                for kind in ("logs", "traces", "metrics")
            )
        ):
            raise ValueError(
                "first-party runner must prove invocation/effect/readback/cleanup/observability"
            )
    return dict(payload)


def _command_prod_sim_provider_rehearsal(
    args: argparse.Namespace,
) -> dict[str, Any]:
    """Run only target-bound, permanently non-promotable prod-sim rehearsal."""
    import quwoquan_ops.cli.stackctl as _stackctl

    report_dir = _stackctl.resolve_report_dir(args, "prod", "prod-sim")
    report_dir = _stackctl.validate_env_run_evidence_dir(
        report_dir,
        env_name="prod",
    )
    report_dir.mkdir(parents=True, exist_ok=True)
    issues: list[str] = []
    findings: list[dict[str, str]] = []
    identity: dict[str, str] = {}
    required: list[dict[str, str]] = []
    completed: list[dict[str, Any]] = []
    try:
        if (
            not bool(args.execute)
            or bool(args.matrix)
            or bool(args.environment_matrix)
            or str(args.env or "").strip() not in {"", "prod"}
            or str(args.target or "").strip() not in {"", "prod-sim"}
            or any(
                str(value or "").strip()
                for value in (args.adapter_id, args.capability_id, args.layer, args.image_digest, args.data_digest)
            )
        ):
            raise ValueError(
                "--prod-sim-rehearsal requires --execute and only the prod-sim target; "
                "matrix/cell/image/data inputs are forbidden"
            )
        identity, composition = _prod_sim_rehearsal_identity()
        required = _prod_sim_rehearsal_required_capabilities(composition)
        conformance = _stackctl._provider_conformance()
        sources, source_issues = conformance.discover_test_sources()
        if source_issues:
            raise ValueError("; ".join(str(issue) for issue in source_issues))
        selections = [
            (
                capability,
                _prod_sim_first_party_source(
                    conformance.source_for_cell(
                        capability_id=capability["capabilityId"],
                        adapter_id=capability["adapterId"],
                        layer="prod-sim-rehearsal",
                        sources=sources,
                    ),
                    capability_id=capability["capabilityId"],
                ),
            )
            for capability in required
        ]
        runtime_environment = _stackctl._prod_sim_provider_rehearsal_environment(
            composition=composition
        )
        for capability, source in selections:
            case_path = report_dir / (
                "prod-sim-first-party-"
                + capability["capabilityId"].replace(".", "-")
                + ".case-results.json"
            )
            if case_path.exists():
                raise ValueError("prod-sim rehearsal case artifact already exists")
            environment = {
                **os.environ,
                **runtime_environment,
                "QWQ_PROVIDER_CONFORMANCE_PROD_SIM_RESULT_PATH": str(case_path),
                "QWQ_PROVIDER_CONFORMANCE_PROD_SIM_IDENTITY": json.dumps(
                    identity, ensure_ascii=False, separators=(",", ":"), sort_keys=True
                ),
                "QWQ_PROVIDER_CONFORMANCE_CAPABILITY_ID": capability["capabilityId"],
                "QWQ_PROVIDER_CONFORMANCE_ADAPTER_ID": capability["adapterId"],
            }
            result = subprocess.run(
                list(source["command"]),
                cwd=_stackctl.ROOT,
                capture_output=True,
                text=True,
                env=environment,
            )
            if result.returncode != 0 or not case_path.is_file():
                runner_output = (result.stderr or result.stdout or "").strip()
                runner_detail = _redact_rehearsal_detail(
                    runner_output.splitlines()[-1] if runner_output else "no runner output"
                )
                raise ValueError(
                    "GATE_BLOCK: prod-sim/"
                    + capability["capabilityId"]
                    + " first-party runner failed without accepted evidence: "
                    + runner_detail
                )
            try:
                case_payload = json.loads(case_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise ValueError(
                    f"prod-sim/{capability['capabilityId']} first-party case result is unreadable"
                ) from exc
            case = _validate_prod_sim_first_party_case(
                case_payload,
                capability=capability,
                identity=identity,
                source=source,
            )
            completed.append(
                {
                    "capabilityId": capability["capabilityId"],
                    "adapterId": capability["adapterId"],
                    "firstPartyService": source["prodSimFirstParty"]["service"],
                    "invocationCount": len(case["invocations"]),
                    "testSource": source["testSource"],
                    "testSourceDigest": source["testSourceDigest"],
                }
            )
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        detail = _redact_rehearsal_detail(exc)
        issues.append(detail)
        findings.append({"code": "GATE_BLOCK", "detail": detail})
    passed = not issues and len(completed) == len(required) and bool(required)
    payload = {
        "schema": "stackctl-provider-conformance-prod-sim-rehearsal",
        "readinessScope": "local_rehearsal",
        "releasePromotionClaimed": False,
        "nonPromotable": True,
        "status": "passed" if passed else "gate_block",
        "environment": "prod",
        "target": "prod-sim",
        "identity": identity,
        "requiredCapabilityCount": len(required),
        "requiredCapabilities": required,
        "completedCapabilities": completed,
        "issues": issues,
    }
    _stackctl.write_json(report_dir / "report.json", payload)
    _stackctl.write_json(
        report_dir / "findings.json",
        {
            "schema": "stackctl-provider-conformance-prod-sim-rehearsal-findings",
            "readinessScope": "local_rehearsal",
            "nonPromotable": True,
            "findings": findings,
        },
    )
    return {
        **payload,
        "exitCode": 0 if passed else 2,
        "summary": (
            "stackctl prod-sim Provider rehearsal passed"
            if passed
            else "stackctl prod-sim Provider rehearsal is GATE_BLOCK"
        ),
        "details": issues or [
            f"capabilities={len(required)}",
            f"firstPartyInvocations={sum(item['invocationCount'] for item in completed)}",
        ],
        "reportDir": _stackctl.relpath(report_dir),
    }


def _prod_sim_provider_rehearsal_environment(
    *,
    composition: Mapping[str, Any],
) -> dict[str, str]:
    """Project target-scoped local credentials without returning their values."""
    import quwoquan_ops.cli.stackctl as _stackctl

    values = dict(os.environ)
    auth = _stackctl.load_local_environment_auth("prod", "prod-sim")
    values.update(auth.environment)
    error = _stackctl._bind_local_external_provider_environment(
        values,
        environment_name="prod",
        target_name="prod-sim",
        storage_prefix="PROD_SIM",
        runtime_composition=composition,
    )
    if error:
        raise RuntimeError(error)
    return {
        key: value
        for key, value in values.items()
        if os.environ.get(key) != value
    }

def _command_provider_conformance_unlocked(
    args: argparse.Namespace,
) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    environment_matrix = bool(getattr(args, "environment_matrix", False))
    if bool(getattr(args, "prod_sim_rehearsal", False)):
        return _stackctl._command_prod_sim_provider_rehearsal(args)
    if bool(args.matrix) and environment_matrix:
        return {
            "exitCode": 2,
            "summary": "stackctl provider-conformance is GATE_BLOCK",
            "details": ["--matrix and --environment-matrix are mutually exclusive"],
        }
    if environment_matrix:
        environment = str(args.env or "").strip()
        target_name = _stackctl.DEFAULT_TARGET_BY_ENV.get(environment, "")
        report_dir = _stackctl.resolve_report_dir(args, environment or "repo", target_name or "repo")
        governance = _stackctl._external_provider_governance()
        conformance = _stackctl._provider_conformance()
        issues: list[str] = []
        cells: list[dict[str, Any]] = []
        binding_capability_count = 0
        capability_count = 0
        attempt_evidence_count = 0
        try:
            if environment not in {"alpha", "beta", "gamma"}:
                raise ValueError(
                    "--environment-matrix requires --env alpha, beta, or gamma"
                )
            if not bool(args.execute):
                raise ValueError(
                    "--environment-matrix requires --execute; dry-run is not evidence"
                )
            if any(
                str(value or "").strip()
                for value in (args.adapter_id, args.capability_id, args.layer)
            ):
                raise ValueError(
                    "environment matrix derives adapter/capability/layer from generated Bindings"
                )
            compiled, governance_issues = governance.load_and_compile()
            if governance_issues:
                raise ValueError(
                    "; ".join(issue.render() for issue in governance_issues)
                )
            selected = (compiled.get("selectedBindings") or {}).get(environment)
            if not isinstance(selected, dict) or not selected:
                raise ValueError(
                    f"generated Binding has no capabilities for {environment}"
                )
            binding_capability_count = len(selected)
            expected_cells = conformance.expected_required_cell_keys(compiled)
            capability_ids = sorted(
                {
                    capability_id
                    for capability_id, cell_environment, _ in expected_cells
                    if cell_environment == environment
                    and isinstance(selected.get(capability_id), dict)
                    and governance.requires_provider_conformance(
                        selected[capability_id]
                    )
                }
            )
            capability_count = len(capability_ids)
            sources, source_issues = conformance.discover_test_sources()
            if source_issues:
                raise ValueError("; ".join(source_issues))
            runner = _stackctl._provider_conformance_runner()
            runtime_environment = _stackctl._provider_conformance_runtime_environment(
                environment
            )
            attempt_evidence_paths: list[Path] = []
            runner.preflight_environment_matrix(
                environment=environment,
                registry=governance.load_registry(),
                compiled=compiled,
                sources=sources,
                runtime_environment=runtime_environment,
            )
            for capability_id in capability_ids:
                binding = selected.get(capability_id)
                if not isinstance(binding, dict):
                    raise ValueError(
                        f"{environment}/{capability_id} selected Binding is invalid"
                    )
                adapter_id = str(binding.get("adapter_id") or "")
                if not adapter_id or binding.get("state") != "enabled":
                    raise ValueError(
                        f"{environment}/{capability_id} has no enabled selected adapter"
                    )
                for layer in _stackctl.PROVIDER_CONFORMANCE_LAYERS:
                    runner_args = [
                        "--adapter-id",
                        adapter_id,
                        "--capability-id",
                        capability_id,
                        "--environment",
                        environment,
                        "--layer",
                        layer,
                        "--execute",
                    ]
                    exit_code = runner.main(
                        runner_args,
                        evidence_paths_out=attempt_evidence_paths,
                        runtime_environments={
                            environment: runtime_environment,
                        },
                    )
                    cells.append(
                        {
                            "capabilityId": capability_id,
                            "adapterId": adapter_id,
                            "layer": layer,
                            "exitCode": exit_code,
                        }
                    )
                    if exit_code != 0:
                        raise ValueError(
                            f"{environment}/{capability_id}/{layer} failed"
                        )
            attempt_evidence, local_readiness_issues = (
                conformance.load_validate_local_functional_readiness(
                    tuple(attempt_evidence_paths),
                    environment=environment,
                    compiled=compiled,
                    registry=governance.load_registry(),
                    sources=sources,
                )
            )
            attempt_evidence_count = len(attempt_evidence)
            issues.extend(str(item) for item in local_readiness_issues)
            if attempt_evidence_count != capability_count * len(
                _stackctl.PROVIDER_CONFORMANCE_LAYERS
            ):
                issues.append(
                    f"{environment} current Provider attempt emitted "
                    f"{attempt_evidence_count} evidence artifacts"
                )
        except (OSError, RuntimeError, ValueError) as exc:
            issues.append(str(exc))
        expected_cells = capability_count * len(_stackctl.PROVIDER_CONFORMANCE_LAYERS)
        passed = (
            not issues
            and capability_count > 0
            and len(cells) == expected_cells
            and all(int(cell.get("exitCode") or 0) == 0 for cell in cells)
        )
        payload = {
            "schema": "stackctl-provider-conformance-environment-matrix",
            "readinessScope": "local_functional",
            "releasePromotionClaimed": False,
            "status": "passed" if passed else "gate_block",
            "environment": environment,
            "target": target_name,
            "bindingCapabilityCount": binding_capability_count,
            "capabilityCount": capability_count,
            "expectedCells": expected_cells,
            "executed": len(cells),
            "skipped": 0,
            "attemptEvidenceCount": attempt_evidence_count,
            "cells": cells,
            "issues": issues,
        }
        _stackctl.write_json(report_dir / "report.json", payload)
        _stackctl.write_json(report_dir / "findings.json", {"issues": issues})
        return {
            **payload,
            "exitCode": 0 if passed else 2,
            "summary": (
                f"stackctl provider-conformance passed {len(cells)} cells for {environment}"
                if passed
                else f"stackctl provider-conformance is GATE_BLOCK for {environment}"
            ),
            "details": issues or [
                f"capabilities={capability_count}",
                f"executed={len(cells)}",
                "skipped=0",
            ],
            "reportDir": _stackctl.relpath(report_dir),
        }

    runner_args: list[str] = []
    if args.matrix:
        runner_args.extend(("--matrix", "--capability-id", args.capability_id))
    else:
        runner_args.extend(
            (
                "--adapter-id",
                args.adapter_id,
                "--environment",
                args.env,
                "--layer",
                args.layer,
            )
        )
    if args.execute:
        runner_args.append("--execute")
    for option, value in (
        ("--image-digest", args.image_digest),
        ("--data-digest", args.data_digest),
    ):
        if value:
            runner_args.extend((option, value))
    try:
        runtime_environments: dict[str, dict[str, str]] = {}
        if bool(args.execute):
            requested_environments = (
                tuple(_stackctl._provider_conformance().ENVIRONMENTS)
                if bool(args.matrix)
                else (str(args.env or "").strip(),)
            )
            runtime_environments = {
                cell_environment: _stackctl._provider_conformance_runtime_environment(
                    cell_environment
                )
                for cell_environment in requested_environments
            }
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        return {
            "exitCode": 2,
            "summary": "stackctl provider-conformance is GATE_BLOCK",
            "details": [str(exc)],
        }
    exit_code = _stackctl._provider_conformance_runner().main(
        runner_args,
        runtime_environments=runtime_environments,
    )
    return {
        "exitCode": exit_code,
        "summary": (
            "stackctl provider-conformance passed"
            if exit_code == 0
            else "stackctl provider-conformance failed"
        ),
        "details": [
            f"adapter={args.adapter_id or '<binding-derived>'}",
            f"capability={args.capability_id or '<single-cell>'}",
            f"environment={args.env or '<matrix>'}",
            f"layer={args.layer or '<matrix>'}",
            f"matrix={args.matrix}",
            f"executed={args.execute}",
        ],
    }


def command_provider_conformance(args: argparse.Namespace) -> dict[str, Any]:
    """Run local Provider evidence while sharing the BuildKit/runtime lock."""
    import quwoquan_ops.cli.stackctl as _stackctl


    if not bool(getattr(args, "execute", False)):
        return _stackctl._command_provider_conformance_unlocked(args)
    if bool(getattr(args, "prod_sim_rehearsal", False)):
        target_names = ("prod-sim",)
    elif bool(getattr(args, "matrix", False)):
        target_names = _stackctl.LOCAL_BUILD_CACHE_TARGETS
    else:
        environment = str(getattr(args, "env", "") or "").strip()
        target_name = _stackctl.DEFAULT_TARGET_BY_ENV.get(environment, "")
        target_names = (
            (target_name,) if target_name in _stackctl.LOCAL_BUILD_CACHE_TARGETS else ()
        )
    # 矩阵逐 target 持有独立租约；中途获取失败也只释放本次已获取的租约。
    with contextlib.ExitStack() as locks:
        try:
            for target_name in target_names:
                runtime_use_lock = _stackctl.acquire_local_runtime_use_lock(
                    target=target_name,
                    purpose=(
                        "provider-conformance-prod-sim-rehearsal"
                        if bool(getattr(args, "prod_sim_rehearsal", False))
                        else "provider-conformance-uat"
                    ),
                )
                locks.callback(runtime_use_lock.close)
        except RuntimeError as exc:
            return {
                "exitCode": 2,
                "summary": "stackctl provider-conformance is GATE_BLOCK",
                "details": [str(exc)],
            }
        return _stackctl._command_provider_conformance_unlocked(args)


def register_parser(subparsers: "argparse._SubParsersAction") -> None:
    """向 stackctl build_parser 注册本域子命令（从 build_parser 逐字迁出）。"""
    import quwoquan_ops.cli.stackctl as _stackctl

    provider_conformance_parser = subparsers.add_parser(
        "provider-conformance",
        help="执行一个 Provider Conformance 九格单元并写入受证明证据",
    )
    provider_conformance_parser.add_argument("--report-dir", default=argparse.SUPPRESS)
    provider_conformance_parser.add_argument("--adapter-id", default="")
    provider_conformance_parser.add_argument("--capability-id", default="")
    provider_conformance_parser.add_argument(
        "--env",
        default="",
        choices=("", *_stackctl.PROVIDER_CONFORMANCE_EVIDENCE_ENVIRONMENTS),
    )
    provider_conformance_parser.add_argument(
        "--layer",
        default="",
        choices=("", *_stackctl.PROVIDER_CONFORMANCE_LAYERS),
    )
    provider_conformance_parser.add_argument("--matrix", action="store_true")
    provider_conformance_parser.add_argument(
        "--prod-sim-rehearsal",
        action="store_true",
        help=(
            "对 active immutable prod-sim candidate 执行第一方黑盒 Provider 演练；"
            "结果永久 non-promotable，绝不进入 hosted release readiness"
        ),
    )
    provider_conformance_parser.add_argument(
        "--target",
        default="",
        choices=("", "prod-sim", "prod-hosted"),
        help="仅 --prod-sim-rehearsal 可指定，且只接受 prod-sim",
    )
    provider_conformance_parser.add_argument(
        "--environment-matrix",
        action="store_true",
        help=(
            "按 generated ContractGraph/Binding 动态执行指定环境全部 capability "
            "的 local_contract/api_integration/user_acceptance 三层单元"
        ),
    )
    provider_conformance_parser.add_argument("--execute", action="store_true")
    provider_conformance_parser.add_argument("--image-digest", default="")
    provider_conformance_parser.add_argument("--data-digest", default="")
