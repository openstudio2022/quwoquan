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


def _command_provider_conformance_unlocked(
    args: argparse.Namespace,
) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    environment_matrix = bool(getattr(args, "environment_matrix", False))
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
                if not governance.requires_provider_conformance(binding):
                    continue
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
    if bool(getattr(args, "matrix", False)):
        target_name = ",".join(_stackctl.LOCAL_BUILD_CACHE_TARGETS)
    else:
        environment = str(getattr(args, "env", "") or "").strip()
        target_name = _stackctl.DEFAULT_TARGET_BY_ENV.get(environment, "")
    if target_name not in {*_stackctl.LOCAL_BUILD_CACHE_TARGETS, ",".join(_stackctl.LOCAL_BUILD_CACHE_TARGETS)}:
        return _stackctl._command_provider_conformance_unlocked(args)
    try:
        runtime_use_lock = _stackctl.acquire_local_runtime_use_lock(
            target=target_name,
            purpose="provider-conformance-uat",
        )
    except RuntimeError as exc:
        return {
            "exitCode": 2,
            "summary": "stackctl provider-conformance is GATE_BLOCK",
            "details": [str(exc)],
        }
    with contextlib.closing(runtime_use_lock):
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

