#!/usr/bin/env python3
"""执行声明的 Provider Conformance 测试并生成受 CI 证明保护的证据。"""
from __future__ import annotations

import argparse
import contextlib
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
from typing import Any, Mapping


sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib import external_provider_governance as governance
from quwoquan_ops.cli.lib import provider_conformance
from quwoquan_ops.cli.lib.output_paths import env_run_dir, output_root
from quwoquan_ops.cli.lib.startup_attempt_receipt import startup_attempt_path


_RUNTIME_IDENTITY_ENV = "QWQ_PROVIDER_CONFORMANCE_RUNTIME_IDENTITY"
_RUNTIME_IDENTITY_SCHEMA = "stackctl.provider_conformance_runtime_identity"
_RUNTIME_IDENTITY_COMMON_FIELDS = frozenset(
    {
        "schema",
        "runtimeMode",
        "environment",
        "target",
        "workload",
        "startupAttemptId",
        "providerRuntimeDigest",
        "failureFree",
        "nonPromotable",
    }
)
_RUNTIME_IDENTITY_IMMUTABLE_FIELDS = frozenset({"candidateDigest"})
_RUNTIME_IDENTITY_MUTABLE_FIELDS = frozenset(
    {
        "mutableComposeDigest",
        "mutableConfigurationDigest",
        "mutableStateDigest",
        "mutableWorkspaceStatusDigest",
        "mutableResolverHandoffDigest",
        "mutableSourceRevision",
    }
)


@dataclass(frozen=True)
class _FrozenRuntimeIdentity:
    runtime_mode: str
    environment: str
    target: str
    startup_attempt_id: str
    provider_runtime_digest: str
    candidate_digest: str = ""


def _freeze_nonprod_runtime_identity(environment: str) -> _FrozenRuntimeIdentity:
    raw = os.environ.get(_RUNTIME_IDENTITY_ENV, "").strip()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"{environment} Provider conformance runtime identity handoff is invalid"
        ) from exc
    if not isinstance(payload, Mapping):
        raise ValueError(
            f"{environment} Provider conformance runtime identity handoff is invalid"
        )
    runtime_mode = str(payload.get("runtimeMode") or "").strip()
    mode_fields = (
        _RUNTIME_IDENTITY_IMMUTABLE_FIELDS
        if runtime_mode == "immutable_candidate"
        else _RUNTIME_IDENTITY_MUTABLE_FIELDS
        if runtime_mode == "test_live"
        else frozenset()
    )
    expected_target = f"{environment}-local"
    if (
        not mode_fields
        or set(payload) != _RUNTIME_IDENTITY_COMMON_FIELDS | mode_fields
        or payload.get("schema") != _RUNTIME_IDENTITY_SCHEMA
        or payload.get("environment") != environment
        or payload.get("target") != expected_target
        or payload.get("workload") != "full"
        or payload.get("failureFree") is not True
        or payload.get("nonPromotable") is not (runtime_mode == "test_live")
        or not str(payload.get("startupAttemptId") or "").strip()
    ):
        raise ValueError(
            f"{environment} Provider conformance runtime identity handoff "
            "does not match the cell"
        )
    digest_fields = [
        value for key, value in payload.items() if key.endswith("Digest")
    ]
    if any(
        provider_conformance.SHA256_PATTERN.fullmatch(str(value or "")) is None
        for value in digest_fields
    ):
        raise ValueError(
            f"{environment} Provider conformance runtime identity handoff "
            "contains an invalid digest"
        )
    if runtime_mode == "test_live" and re.fullmatch(
        r"[0-9a-f]{40}",
        str(payload.get("mutableSourceRevision") or ""),
    ) is None:
        raise ValueError(
            f"{environment} Provider conformance mutable source identity is invalid"
        )
    return _FrozenRuntimeIdentity(
        runtime_mode=runtime_mode,
        environment=environment,
        target=expected_target,
        startup_attempt_id=str(payload["startupAttemptId"]),
        provider_runtime_digest=str(payload["providerRuntimeDigest"]),
        candidate_digest=str(payload.get("candidateDigest") or ""),
    )


@contextlib.contextmanager
def _scoped_process_environment(values: Mapping[str, str]):
    previous = {key: os.environ.get(key) for key in values}
    os.environ.update({key: str(value) for key, value in values.items()})
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _runtime_environment_for_cell(
    runtime_environments: Mapping[str, Mapping[str, str]] | None,
    *,
    environment: str,
    execute: bool,
) -> dict[str, str]:
    if not execute or environment not in provider_conformance.ENVIRONMENTS:
        return {}
    selected = (
        runtime_environments.get(environment)
        if isinstance(runtime_environments, Mapping)
        else None
    )
    if (
        not isinstance(selected, Mapping)
        or not str(selected.get(_RUNTIME_IDENTITY_ENV) or "").strip()
    ):
        raise ValueError(
            f"{environment} Provider conformance runtime identity handoff is missing"
        )
    return {str(key): str(value) for key, value in selected.items()}


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


def _current_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        check=True,
        text=True,
    )
    return result.stdout.strip()


def _require_formal_promotability(identity: Mapping[str, object]) -> None:
    if (
        os.environ.get(
            "QWQ_PROVIDER_CONFORMANCE_REQUIRE_PROMOTABLE",
            "",
        ).strip().lower()
        == "true"
        and identity.get("nonPromotable") is not False
    ):
        raise ValueError(
            "formal Provider producer requires clean reviewed CI authority "
            "and a canonical active candidate receipt"
        )


def _resolve_immutable_execution_candidate(
    runtime_identity: _FrozenRuntimeIdentity,
    *,
    registry: Mapping[str, Any],
    commit: str,
    image_digest: str,
    contract_graph_digest: str,
) -> dict[str, object]:
    if runtime_identity.runtime_mode != "immutable_candidate":
        raise ValueError("only immutable execution can resolve candidate evidence")
    binding = provider_conformance.resolve_nonprod_active_candidate(
        environment=runtime_identity.environment,
        registry=registry,
        commit=commit,
        image_digest=image_digest,
        contract_graph_digest=contract_graph_digest,
    )
    if binding.get("active") is not True:
        raise ValueError(
            "selected immutable Provider runtime is no longer the canonical "
            f"active candidate: {binding.get('reason') or 'identity mismatch'}"
        )
    receipt_path = startup_attempt_path(runtime_identity.target)
    try:
        receipt_raw = receipt_path.read_bytes()
        receipt = json.loads(receipt_raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(
            "selected immutable Provider startup receipt is unreadable"
        ) from exc
    if (
        not isinstance(receipt, Mapping)
        or receipt.get("status") != "running"
        or receipt.get("env") != runtime_identity.environment
        or receipt.get("target") != runtime_identity.target
        or receipt.get("workload") != "full"
        or receipt.get("candidateDigest") != runtime_identity.candidate_digest
        or receipt.get("attemptId") != runtime_identity.startup_attempt_id
        or receipt.get("providerRuntimeDigest")
        != runtime_identity.provider_runtime_digest
        or receipt.get("failure") not in {None, ""}
        or receipt.get("cleanupFailure") not in {None, ""}
        or binding.get("receiptDigest") != _digest_bytes(receipt_raw)
    ):
        raise ValueError(
            "selected immutable Provider runtime drifted from the frozen "
            "candidate/startup/provider identity"
        )
    return dict(binding)


def _postrun_nonprod_candidate(
    runtime_identity: _FrozenRuntimeIdentity,
    *,
    pre_run_candidate: Mapping[str, object] | None,
    case_result_path: Path,
    registry: Mapping[str, Any],
    commit: str,
    image_digest: str,
    contract_graph_digest: str,
) -> dict[str, object]:
    if runtime_identity.runtime_mode == "test_live":
        return {
            "active": False,
            "receiptRef": "",
            "receiptDigest": "",
            "reason": "mutable test_live evidence is never promotable",
        }
    try:
        post_run_candidate = _resolve_immutable_execution_candidate(
            runtime_identity,
            registry=registry,
            commit=commit,
            image_digest=image_digest,
            contract_graph_digest=contract_graph_digest,
        )
        if (
            not isinstance(pre_run_candidate, Mapping)
            or pre_run_candidate.get("active") is not True
            or post_run_candidate.get("receiptRef")
            != pre_run_candidate.get("receiptRef")
            or post_run_candidate.get("receiptDigest")
            != pre_run_candidate.get("receiptDigest")
        ):
            raise ValueError(
                "immutable Provider candidate receipt changed during execution"
            )
        return post_run_candidate
    except (OSError, ValueError):
        # A CaseResult written after the runtime identity drifted is not valid
        # evidence and must not remain available for later aggregation.
        case_result_path.unlink(missing_ok=True)
        raise


def _evidence_identity_for_runtime(
    runtime_identity: _FrozenRuntimeIdentity | None,
    *,
    commit: str,
    candidate: Mapping[str, object],
) -> dict[str, object]:
    candidate_bound = bool(
        runtime_identity is None
        or runtime_identity.runtime_mode == "immutable_candidate"
    ) and candidate.get("active") is True
    return provider_conformance.evidence_identity(
        commit=commit,
        candidate_receipt_bound=candidate_bound,
        candidate_receipt_ref=(
            str(candidate.get("receiptRef") or "") if candidate_bound else ""
        ),
        candidate_receipt_digest=(
            str(candidate.get("receiptDigest") or "") if candidate_bound else ""
        ),
    )


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
    parser.add_argument("--adapter-id", default="")
    parser.add_argument("--capability-id", default="")
    parser.add_argument(
        "--environment",
        default="",
        choices=("", *provider_conformance.EVIDENCE_ENVIRONMENTS),
    )
    parser.add_argument(
        "--layer",
        default="",
        choices=("", *provider_conformance.LAYERS),
    )
    parser.add_argument(
        "--matrix",
        action="store_true",
        help="execute the selected Binding across Alpha/Beta/Gamma × three layers",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="run the source-declared test command; dry-run evidence is forbidden",
    )
    parser.add_argument(
        "--image-digest",
        default="",
        help="immutable deployment image digest; required for a passed cell",
    )
    parser.add_argument(
        "--data-digest",
        default="",
        help="deprecated; the test-owned CaseResult must provide dataDigest",
    )
    return parser


def _binding_runtime_material(
    runtime_environment: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Read injected keys from the bound runtime delta, not leftover host env.

    service-core 把 assistant 等模块收进单进程后, ASSISTANT_* 只存在于
    stackctl 绑定的 runtime_environment, 不再出现在宿主机 os.environ。
    """
    material = {str(key): str(value) for key, value in os.environ.items()}
    if runtime_environment:
        material.update(
            {str(key): str(value) for key, value in runtime_environment.items()}
        )
    return material


def _require_binding_runtime_material(
    binding: Mapping[str, Any],
    *,
    environment: str,
    layer: str,
    runtime_environment: Mapping[str, str] | None = None,
) -> None:
    if layer == "local_contract":
        return
    endpoint_envs = binding.get("endpoint_envs")
    secret_refs = binding.get("secret_refs")
    if not isinstance(endpoint_envs, Mapping) or not isinstance(secret_refs, list):
        raise ValueError("selected Binding has invalid endpoint/secret declarations")
    endpoint_keys = sorted(str(value) for value in endpoint_envs.values())
    secret_keys = sorted(str(value) for value in secret_refs)
    required_keys = sorted(set(endpoint_keys) | set(secret_keys))
    material = _binding_runtime_material(runtime_environment)
    missing = [key for key in required_keys if not material.get(key, "").strip()]
    if missing:
        raise ValueError(
            f"{environment} selected Binding is missing injected runtime keys: "
            + ", ".join(missing)
        )
    if environment in provider_conformance.RELEASE_READINESS_ENVIRONMENTS:
        local_markers = (
            "fixture.local",
            "localhost",
            "127.0.0.1",
            ".localhost",
            "file://",
        )
        local_endpoints = [
            key
            for key in endpoint_keys
            if any(
                marker in material[key].strip().lower()
                for marker in local_markers
            )
        ]
        if local_endpoints:
            raise ValueError(
                f"{environment} release evidence forbids local Provider endpoints: "
                + ", ".join(local_endpoints)
            )
    missing_files = [
        key
        for key in secret_keys
        if key.endswith("_FILE") and not Path(material[key]).expanduser().is_file()
    ]
    if missing_files:
        raise ValueError(
            f"{environment} selected Binding secret files are unavailable: "
            + ", ".join(missing_files)
        )


def preflight_environment_matrix(
    *,
    environment: str,
    registry: Mapping[str, Any],
    compiled: Mapping[str, Any],
    sources: Mapping[tuple[str, str, str], Mapping[str, Any]],
    runtime_environment: Mapping[str, str],
) -> str:
    """Fail the complete environment matrix before emitting any partial evidence."""
    issues: list[str] = []
    try:
        image_digest = provider_conformance.candidate_image_digest(
            environment,
            registry=registry,
        )
    except ValueError as exc:
        image_digest = ""
        issues.append(str(exc))
    commit = _current_commit()
    contract_graph_digest = _contract_graph_digest()
    try:
        with _scoped_process_environment(runtime_environment):
            runtime_identity = _freeze_nonprod_runtime_identity(environment)
        if runtime_identity.runtime_mode == "immutable_candidate":
            _resolve_immutable_execution_candidate(
                runtime_identity,
                registry=registry,
                commit=commit,
                image_digest=image_digest,
                contract_graph_digest=contract_graph_digest,
            )
    except (OSError, ValueError) as exc:
        issues.append(str(exc))
    selected = (compiled.get("selectedBindings") or {}).get(environment)
    if not isinstance(selected, Mapping):
        issues.append(f"compiled provider binding receipt has no {environment} environment")
    else:
        for capability_id, binding in sorted(selected.items()):
            if not isinstance(binding, Mapping):
                issues.append(f"{environment}/{capability_id} selected Binding is invalid")
                continue
            if not governance.requires_provider_conformance(binding):
                continue
            adapter_id = str(binding.get("adapter_id") or "")
            if binding.get("state") != "enabled" or not adapter_id:
                issues.append(
                    f"{environment}/{capability_id} has no enabled selected adapter"
                )
                continue
            try:
                _require_binding_runtime_material(
                    binding,
                    environment=environment,
                    layer="api_integration",
                    runtime_environment=runtime_environment,
                )
            except ValueError as exc:
                issues.append(str(exc))
            for layer in provider_conformance.LAYERS:
                if (
                    provider_conformance.source_for_cell(
                        capability_id=str(capability_id),
                        adapter_id=adapter_id,
                        layer=layer,
                        sources=sources,
                    )
                    is None
                ):
                    issues.append(
                        f"{environment}/{capability_id}/{layer} has no "
                        "self-describing executable source"
                    )
    if issues:
        raise ValueError("; ".join(dict.fromkeys(issues)))
    return image_digest


def _execute_cell(
    args: argparse.Namespace,
    *,
    registry: Mapping[str, Any],
    compiled: Mapping[str, Any],
    sources: Mapping[tuple[str, str, str], Mapping[str, Any]],
) -> Path:
    if not args.execute:
        raise ValueError("dry-run cannot emit Provider Conformance evidence; pass --execute")
    if args.data_digest:
        raise ValueError(
            "--data-digest is forbidden; the test-owned CaseResult must report dataDigest"
        )
    runtime_identity = (
        _freeze_nonprod_runtime_identity(args.environment)
        if args.environment in provider_conformance.ENVIRONMENTS
        else None
    )
    requested_image_digest = str(args.image_digest or "").strip()
    if args.environment in provider_conformance.ENVIRONMENTS:
        image_digest = provider_conformance.candidate_image_digest(
            args.environment,
            registry=registry,
        )
        configured_expected = os.environ.get(
            "QWQ_PROVIDER_CONFORMANCE_EXPECTED_IMAGE_DIGEST",
            "",
        ).strip()
        if configured_expected and configured_expected != image_digest:
            raise ValueError(
                "configured expected image digest does not match packaged candidate"
            )
        if requested_image_digest and requested_image_digest != image_digest:
            raise ValueError(
                "--image-digest does not match the packaged immutable candidate"
            )
    else:
        if not provider_conformance.SHA256_PATTERN.fullmatch(requested_image_digest):
            raise ValueError("--image-digest must be an immutable sha256 digest")
        expected_image_digest = os.environ.get(
            "QWQ_PROVIDER_CONFORMANCE_EXPECTED_IMAGE_DIGEST",
            "",
        )
        if not provider_conformance.SHA256_PATTERN.fullmatch(expected_image_digest):
            raise ValueError(
                "QWQ_PROVIDER_CONFORMANCE_EXPECTED_IMAGE_DIGEST is required for Prod hosted evidence"
            )
        if requested_image_digest != expected_image_digest:
            raise ValueError("--image-digest does not match the active immutable image")
        image_digest = requested_image_digest
    adapter_candidates = [
        item
        for item in registry.get("adapters", [])
        if isinstance(item, Mapping)
        and item.get("adapter_id") == args.adapter_id
        and (
            not str(getattr(args, "capability_id", "") or "").strip()
            or item.get("capability_id") == getattr(args, "capability_id", "")
        )
    ]
    if len(adapter_candidates) != 1:
        detail = (
            "capability-id is required to disambiguate a shared adapter"
            if adapter_candidates
            else "adapter/capability pair is not registered"
        )
        raise ValueError(f"{args.adapter_id}: {detail}")
    adapter = adapter_candidates[0]
    if not isinstance(adapter, Mapping):
        raise ValueError(f"unregistered adapter: {args.adapter_id}")
    capability_id = adapter.get("capability_id")
    if not isinstance(capability_id, str):
        raise ValueError(f"adapter {args.adapter_id} is missing capability metadata")
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
    if binding.get("state") != "enabled":
        raise ValueError(
            f"{capability_id} Binding is not enabled in {args.environment}; "
            "a blocked Binding cannot emit Provider Conformance evidence"
        )
    if not governance.requires_provider_conformance(binding):
        raise ValueError(
            f"{capability_id} uses a first-party authority Binding and is outside "
            "Provider Conformance"
        )
    _require_binding_runtime_material(
        binding,
        environment=args.environment,
        layer=args.layer,
    )
    source = provider_conformance.source_for_cell(
        capability_id=capability_id,
        adapter_id=args.adapter_id,
        layer=args.layer,
        sources=sources,
    )
    if source is None:
        raise ValueError(
            "no self-describing executable source exists for the selected "
            "capability/adapter/layer; static should-block/GATE_BLOCK tests are not evidence"
        )
    if source.get("typedPort") != capability.get("canonical_port"):
        raise ValueError("test source typedPort does not match the canonical capability Port")
    if source.get("contractRef") != capability.get("source"):
        raise ValueError("test source contractRef does not match the capability contract")
    expected_capability_assertion = provider_conformance.capability_assertion_id(
        capability
    )
    if expected_capability_assertion not in source.get("assertionIds", []):
        raise ValueError(
            "test source omits the capability-specific conformance assertion "
            f"{expected_capability_assertion}"
        )
    if not (ROOT / str(source["contractRef"])).is_file():
        raise ValueError("test source contractRef does not resolve to a tracked contract")
    execution_profile = provider_conformance.execution_profile_for(
        args.environment,
        args.layer,
    )
    if execution_profile is None:
        raise ValueError(
            "environment/layer is not an executable Provider Conformance cell"
        )
    binding_root_records = provider_conformance.compiled_capability_binding_roots(
        compiled,
        capability_id=capability_id,
    )
    binding_roots = [root["root_id"] for root in binding_root_records]
    config_digest = provider_conformance.binding_config_digest(binding, binding_root_records)
    adapter_path = ROOT / str(adapter.get("implementation_path"))
    adapter_digest = provider_conformance.implementation_digest(adapter_path)
    if adapter_digest is None:
        raise ValueError(f"adapter implementation path is missing: {adapter_path}")
    contract_graph_digest = _contract_graph_digest()
    commit = _current_commit()
    pre_run_candidate = (
        _resolve_immutable_execution_candidate(
            runtime_identity,
            registry=registry,
            commit=commit,
            image_digest=image_digest,
            contract_graph_digest=contract_graph_digest,
        )
        if runtime_identity is not None
        and runtime_identity.runtime_mode == "immutable_candidate"
        else None
    )
    run_dir = env_run_dir(
        args.environment,
        "provider-conformance",
        target=f"{args.adapter_id}-{args.layer}",
    )
    run_dir.mkdir(parents=True, exist_ok=True)
    stem = f"provider-conformance-{args.adapter_id.replace('.', '-')}-{args.layer}"
    case_result_path = run_dir / f"{stem}.case-results.json"
    if case_result_path.exists():
        raise ValueError(f"CaseResult artifact already exists: {case_result_path}")
    command = list(source["command"])
    environment = {
        **os.environ,
        "QWQ_PROVIDER_CONFORMANCE_RESULT_PATH": str(case_result_path),
        "QWQ_PROVIDER_CONFORMANCE_ADAPTER_ID": args.adapter_id,
        "QWQ_PROVIDER_CONFORMANCE_CAPABILITY_ID": capability_id,
        "QWQ_PROVIDER_CONFORMANCE_ENVIRONMENT": args.environment,
        "QWQ_PROVIDER_CONFORMANCE_LAYER": args.layer,
        "QWQ_PROVIDER_CONFORMANCE_TYPED_PORT": str(source["typedPort"]),
        "QWQ_PROVIDER_CONFORMANCE_CONTRACT_REF": str(source["contractRef"]),
        "QWQ_PROVIDER_CONFORMANCE_CONFIG_DIGEST": config_digest,
        "QWQ_PROVIDER_CONFORMANCE_ASSERTION_IDS": json.dumps(source["assertionIds"]),
        "QWQ_PROVIDER_CONFORMANCE_CONTRACT_GRAPH_DIGEST": contract_graph_digest,
        "QWQ_PROVIDER_CONFORMANCE_ADAPTER_DIGEST": adapter_digest,
    }
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, env=environment)
    if result.returncode != 0:
        stderr_tail = (result.stderr or "")[-4000:]
        stdout_tail = (result.stdout or "")[-2000:]
        if stdout_tail.strip():
            print(stdout_tail, file=sys.stderr)
        if stderr_tail.strip():
            print(stderr_tail, file=sys.stderr)
        raise ValueError(
            f"source-declared command failed for target {source['target']} (exit {result.returncode}); "
            "no Provider Conformance evidence was emitted"
        )
    if not case_result_path.is_file():
        raise ValueError(
            "source-declared command did not write QWQ_PROVIDER_CONFORMANCE_RESULT_PATH"
        )
    if runtime_identity is not None:
        active_candidate = _postrun_nonprod_candidate(
            runtime_identity,
            pre_run_candidate=pre_run_candidate,
            case_result_path=case_result_path,
            registry=registry,
            commit=commit,
            image_digest=image_digest,
            contract_graph_digest=contract_graph_digest,
        )
    else:
        active_candidate = {}
    case_result, case_result_issues = provider_conformance.load_case_results(
        case_result_path,
        source=source,
        environment=args.environment,
        config_digest=config_digest,
    )
    if case_result_issues or case_result is None:
        raise ValueError("; ".join(case_result_issues))
    executed_at = datetime.now(timezone.utc).isoformat()
    case_result_bytes = case_result_path.read_bytes()
    if runtime_identity is None:
        active_candidate = provider_conformance.resolve_prod_active_candidate(
            case_result_path=case_result_path,
            case_result=case_result,
            capability_id=capability_id,
            adapter_id=args.adapter_id,
            image_digest=image_digest,
            config_digest=config_digest,
            contract_graph_digest=contract_graph_digest,
            adapter_digest=adapter_digest,
        )
    identity = _evidence_identity_for_runtime(
        runtime_identity,
        commit=commit,
        candidate=active_candidate,
    )
    _require_formal_promotability(identity)
    report: dict[str, Any] = {
        "schema": provider_conformance.EXECUTION_REPORT_SCHEMA,
        "adapterId": args.adapter_id,
        "capabilityId": capability_id,
        "bindingRoots": binding_roots,
        "environment": args.environment,
        "testLayer": args.layer,
        "executionProfile": execution_profile,
        "status": "passed",
        "executedAt": executed_at,
        "commit": commit,
        **identity,
        "imageDigest": image_digest,
        "configDigest": config_digest,
        "contractGraphDigest": contract_graph_digest,
        "adapterDigest": adapter_digest,
        "testArtifactRef": _evidence_ref(case_result_path),
        "testArtifactDigest": _digest_bytes(case_result_bytes),
        "testSourceDigest": source["testSourceDigest"],
        "testTarget": source["target"],
        "typedPort": source["typedPort"],
        "contractRef": source["contractRef"],
        "assertionIds": source["assertionIds"],
        "networkBoundary": source["networkBoundary"],
        "dataDigest": case_result["dataDigest"],
        "testSource": source["testSource"],
        "testCommand": shlex.join(command),
        "exitCode": 0,
    }
    report_path = run_dir / f"{stem}.report.json"
    report_bytes = _write_json(report_path, report)
    evidence: dict[str, Any] = {
        "schema": "provider-conformance-evidence",
        "adapterId": args.adapter_id,
        "capabilityId": capability_id,
        "bindingRoots": binding_roots,
        "environment": args.environment,
        "testLayer": args.layer,
        "executionProfile": report["executionProfile"],
        "status": "passed",
        "executedAt": executed_at,
        "artifactRef": _evidence_ref(report_path),
        "artifactDigest": _digest_bytes(report_bytes),
        "artifactAttestation": provider_conformance.attest_execution_report(
            report_bytes,
            identity=identity,
        ),
        **identity,
        "testArtifactRef": report["testArtifactRef"],
        "testArtifactDigest": report["testArtifactDigest"],
        "testSource": report["testSource"],
        "testSourceDigest": report["testSourceDigest"],
        "testCommand": report["testCommand"],
        "testTarget": report["testTarget"],
        "typedPort": report["typedPort"],
        "contractRef": report["contractRef"],
        "commit": report["commit"],
        "imageDigest": image_digest,
        "configDigest": config_digest,
        "contractGraphDigest": report["contractGraphDigest"],
        "adapterDigest": report["adapterDigest"],
        "assertionCount": len(source["assertionIds"]),
        "assertionIds": source["assertionIds"],
        "networkBoundary": report["networkBoundary"],
        "dataDigest": report["dataDigest"],
        "cleanupReceipt": case_result["cleanupReceipt"],
        "acceptanceRefs": source["acceptanceRefs"],
        "observabilityRefs": case_result["observabilityRefs"],
    }
    if provider_conformance.requires_release_readiness(
        args.environment,
        args.layer,
    ):
        release_readiness = case_result.get("releaseReadiness")
        if not isinstance(release_readiness, Mapping) or not provider_conformance._release_readiness_valid(
            case_result
        ):
            raise ValueError(
                "Prod Remote user_acceptance CaseResult must own non-sensitive "
                "adapter-health, switch and rollback receipt references"
            )
        if not provider_conformance.RELEASE_ASSERTION_IDS.issubset(
            set(source["assertionIds"])
        ):
            raise ValueError(
                "Prod Remote user_acceptance source must execute "
                "adapter health/switch/rollback assertions"
            )
        evidence["releaseReadiness"] = dict(release_readiness)
    evidence_path = run_dir / f"{stem}.evidence.json"
    _write_json(evidence_path, evidence)
    return evidence_path


def main(
    argv: list[str] | None = None,
    *,
    evidence_paths_out: list[Path] | None = None,
    runtime_environments: Mapping[str, Mapping[str, str]] | None = None,
) -> int:
    args = _build_parser().parse_args(argv)
    try:
        registry = governance.load_registry()
        compiled, issues = governance.load_and_compile()
        if issues:
            raise ValueError("; ".join(issue.render() for issue in issues))
        sources, source_issues = provider_conformance.discover_test_sources()
        if source_issues:
            raise ValueError("; ".join(source_issues))
        evidence_paths: list[Path] = []
        if args.matrix:
            if not args.capability_id or args.adapter_id or args.environment or args.layer:
                raise ValueError(
                    "--matrix requires --capability-id only; adapter/environment/layer derive from actual Bindings"
                )
            if args.execute and set(runtime_environments or {}) != set(
                provider_conformance.ENVIRONMENTS
            ):
                raise ValueError(
                    "Provider conformance matrix runtime identity handoff is incomplete"
                )
            for environment in provider_conformance.ENVIRONMENTS:
                binding = _selected_binding(
                    compiled,
                    capability_id=args.capability_id,
                    environment=environment,
                )
                adapter_id = binding.get("adapter_id")
                if not isinstance(adapter_id, str):
                    raise ValueError(
                        f"{args.capability_id} has no actual selected Binding in {environment}"
                    )
                for layer in provider_conformance.LAYERS:
                    cell_args = argparse.Namespace(
                        **{
                            **vars(args),
                            "adapter_id": adapter_id,
                            "environment": environment,
                            "layer": layer,
                        }
                    )
                    runtime_environment = _runtime_environment_for_cell(
                        runtime_environments,
                        environment=environment,
                        execute=bool(args.execute),
                    )
                    with _scoped_process_environment(runtime_environment):
                        evidence_paths.append(
                            _execute_cell(
                                cell_args,
                                registry=registry,
                                compiled=compiled,
                                sources=sources,
                            )
                        )
        else:
            if not all((args.adapter_id, args.environment, args.layer)):
                raise ValueError(
                    "single-cell execution requires --adapter-id --environment --layer; "
                    "--capability-id may disambiguate an adapter shared by typed Ports"
                )
            if (
                args.execute
                and args.environment in provider_conformance.ENVIRONMENTS
                and set(runtime_environments or {}) != {args.environment}
            ):
                raise ValueError(
                    "single-cell Provider conformance runtime identity handoff "
                    "is incomplete"
                )
            runtime_environment = _runtime_environment_for_cell(
                runtime_environments,
                environment=args.environment,
                execute=bool(args.execute),
            )
            with _scoped_process_environment(runtime_environment):
                evidence_paths.append(
                    _execute_cell(
                        args,
                        registry=registry,
                        compiled=compiled,
                        sources=sources,
                    )
                )
    except (OSError, subprocess.CalledProcessError, ValueError) as exc:
        print(f"[provider_conformance_runner] GATE_BLOCK: {exc}", file=sys.stderr)
        return 1
    if evidence_paths_out is not None:
        evidence_paths_out.extend(evidence_paths)
    for evidence_path in evidence_paths:
        print(f"[provider_conformance_runner] evidence={evidence_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
