"""generic substitute 运行时装载、离线原生中继与支撑场景执行。"""
from __future__ import annotations

import json
import os
import secrets
import subprocess
from collections.abc import Mapping, Sequence
from urllib import parse

from quwoquan_ops.ci.provider_conformance.native_case_result import (
    _ASSERTION_MARKER,
    _CLEANUP_MARKER,
)
from quwoquan_ops.ci.provider_conformance.run_provider_patrol_uat import (
    _load_nonprod_runtime_identity,
)
from quwoquan_ops.cli.lib.deployment_candidate_manifest import load_candidate_manifest
from quwoquan_ops.cli.lib.environment_topology import (
    get_target,
    load_environment_topology,
)
from quwoquan_ops.cli.lib.external_provider_governance import load_and_compile
from quwoquan_ops.cli.lib.local_environment_auth import load_local_environment_auth
from quwoquan_ops.cli.lib.output_paths import active_deployment_candidate
from quwoquan_ops.cli.lib.port_manifest import canonical_port, load_port_manifest
from quwoquan_ops.cli.lib.public_domain_tls import root_certificate_path

from quwoquan_ops.ci.provider_conformance.generic_protocol_substitute_lib.evidence_helpers import (
    _aggregate_assertion,
    _load_provider_material,
    _owner_dependency,
    _packaged_binding,
    _provider_workload,
    _receipt_ref,
    _required_assertion_ids,
    _required_environment,
    _sha256_text,
    _validate_success,
)
from quwoquan_ops.ci.provider_conformance.generic_protocol_substitute_lib.models import (
    ROLE,
    ROOT,
    ConformanceBlocked,
    InvocationEvidence,
    RuntimeContext,
    SupportedRun,
    SUPPORTED_PUBLIC_ASSERTIONS,
)
from quwoquan_ops.ci.provider_conformance.generic_protocol_substitute_lib.protocol_client import (
    ProtocolClient,
)

def execute_offline_local_contract(*, process_runner=subprocess.run) -> None:
    """Relay exact markers emitted by the workload-owned Go native harness."""

    environment = _required_environment("QWQ_PROVIDER_CONFORMANCE_ENVIRONMENT")
    capability_id = _required_environment("QWQ_PROVIDER_CONFORMANCE_CAPABILITY_ID")
    adapter_id = _required_environment("QWQ_PROVIDER_CONFORMANCE_ADAPTER_ID")
    typed_port = _required_environment("QWQ_PROVIDER_CONFORMANCE_TYPED_PORT")
    contract_ref = _required_environment("QWQ_PROVIDER_CONFORMANCE_CONTRACT_REF")
    if environment not in {"alpha", "beta", "gamma"}:
        raise ConformanceBlocked("generic substitute is limited to Alpha/Beta/Gamma")
    compiled, issues = load_and_compile()
    if issues:
        raise ConformanceBlocked(
            "compiled Provider Bindings are invalid: "
            + "; ".join(issue.render() for issue in issues)
        )
    selected = compiled.get("selectedBindings")
    scope = selected.get(environment) if isinstance(selected, Mapping) else None
    binding = scope.get(capability_id) if isinstance(scope, Mapping) else None
    if (
        not isinstance(binding, Mapping)
        or binding.get("state") != "enabled"
        or binding.get("adapter_id") != adapter_id
        or binding.get("endpoint_ref") != f"local_topology:{ROLE}"
    ):
        raise ConformanceBlocked("source Binding does not select the generic substitute")
    _owner_dependency(
        contract_ref=contract_ref,
        capability_id=capability_id,
        adapter_id=adapter_id,
        typed_port=typed_port,
    )
    cache_root = ROOT / ".qwq_output/env/repo/local"
    go_cache = cache_root / "go-build/generic-provider-conformance"
    go_tmp = cache_root / "go-tmp/generic-provider-conformance"
    go_cache.mkdir(parents=True, exist_ok=True)
    go_tmp.mkdir(parents=True, exist_ok=True)
    command = (
        "go",
        "-C",
        "quwoquan_ops/external/provider-protocol-substitute",
        "run",
        "./cmd/provider-protocol-conformance",
    )
    forwarded_names = (
        "QWQ_PROVIDER_CONFORMANCE_ENVIRONMENT",
        "QWQ_PROVIDER_CONFORMANCE_CAPABILITY_ID",
        "QWQ_PROVIDER_CONFORMANCE_ASSERTION_IDS",
    )
    execution_environment = {
        key: value
        for key in ("PATH", "HOME", "TMPDIR", "GOROOT", "GOPATH", "GOENV")
        if (value := os.environ.get(key, ""))
    }
    execution_environment.update(
        {
            "GOCACHE": str(go_cache),
            "GOTMPDIR": str(go_tmp),
            **{name: _required_environment(name) for name in forwarded_names},
        }
    )
    completed = process_runner(
        command,
        cwd=ROOT,
        env=execution_environment,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise ConformanceBlocked(
            "generic substitute offline native suite failed; no CaseResult was emitted"
        )
    marker_lines = _validated_native_marker_lines(
        completed.stdout,
        expected_assertions=_required_assertion_ids(),
    )
    for line in marker_lines:
        print(line)


def _validated_native_marker_lines(
    stdout: bytes,
    *,
    expected_assertions: Sequence[str],
) -> tuple[str, ...]:
    """Validate coverage while preserving the exact native marker payload bytes."""

    if not isinstance(stdout, bytes):
        raise ConformanceBlocked("offline native harness stdout must be bytes")
    assertion_ids: list[str] = []
    cleanup_count = 0
    marker_lines: list[str] = []
    for raw_line in stdout.decode("utf-8", errors="strict").splitlines():
        line = raw_line.strip()
        if line.startswith(_ASSERTION_MARKER):
            try:
                payload = json.loads(line.removeprefix(_ASSERTION_MARKER))
            except json.JSONDecodeError as exc:
                raise ConformanceBlocked(
                    "offline native harness emitted malformed assertion marker"
                ) from exc
            if not isinstance(payload, Mapping) or not isinstance(
                payload.get("assertionId"), str
            ):
                raise ConformanceBlocked(
                    "offline native harness emitted malformed assertion receipt"
                )
            assertion_ids.append(payload["assertionId"])
            marker_lines.append(line)
        elif line.startswith(_CLEANUP_MARKER):
            cleanup_count += 1
            marker_lines.append(line)
    if tuple(assertion_ids) != tuple(expected_assertions) or cleanup_count != 1:
        raise ConformanceBlocked(
            "offline native harness markers do not exactly cover source assertions"
        )
    return tuple(marker_lines)


def load_runtime_context() -> RuntimeContext:
    environment = _required_environment("QWQ_PROVIDER_CONFORMANCE_ENVIRONMENT")
    layer = _required_environment("QWQ_PROVIDER_CONFORMANCE_LAYER")
    capability_id = _required_environment("QWQ_PROVIDER_CONFORMANCE_CAPABILITY_ID")
    adapter_id = _required_environment("QWQ_PROVIDER_CONFORMANCE_ADAPTER_ID")
    typed_port = _required_environment("QWQ_PROVIDER_CONFORMANCE_TYPED_PORT")
    contract_ref = _required_environment("QWQ_PROVIDER_CONFORMANCE_CONTRACT_REF")
    if environment not in {"alpha", "beta", "gamma"}:
        raise ConformanceBlocked("generic substitute is limited to Alpha/Beta/Gamma")
    if layer not in {"local_contract", "api_integration"}:
        raise ConformanceBlocked("generic substitute runner only owns local/API layers")
    target = f"{environment}-local"
    runtime_identity = _load_nonprod_runtime_identity(environment, target)
    active = active_deployment_candidate(target)
    if not isinstance(active, Mapping):
        raise ConformanceBlocked("active immutable candidate is unavailable")
    manifest = load_candidate_manifest(
        environment,
        target,
        runtime_identity.baseline_id,
        require_full=True,
    )
    provider_runtime = manifest.get("providerRuntime")
    composition = (
        provider_runtime.get("composition")
        if isinstance(provider_runtime, Mapping)
        else None
    )
    if not isinstance(composition, Mapping):
        raise ConformanceBlocked("packaged Provider composition is unavailable")
    binding = _packaged_binding(composition, capability_id)
    if (
        binding.get("state") != "enabled"
        or binding.get("adapterId") != adapter_id
        or binding.get("endpointRef") != f"local_topology:{ROLE}"
    ):
        raise ConformanceBlocked("selected Binding is not the packaged generic substitute")

    dependency = _owner_dependency(
        contract_ref=contract_ref,
        capability_id=capability_id,
        adapter_id=adapter_id,
        typed_port=typed_port,
    )
    if binding.get("endpointEnvironmentKeys") != dependency["endpointEnvs"]:
        raise ConformanceBlocked("packaged Binding endpoint roles drifted from owner contract")
    operations = tuple(dependency["operations"])
    workload = _provider_workload(composition)
    if (
        capability_id not in workload.get("capabilityIds", [])
        or adapter_id not in workload.get("adapterIds", [])
    ):
        raise ConformanceBlocked("packaged generic workload does not own the selected Binding")

    active_config, material = _load_provider_material(target)
    if (
        active_config.get("schema") != "stackctl-provider-config"
        or active_config.get("environment") != environment
        or active_config.get("target") != target
        or active_config.get("runtimeCompositionDigest")
        != composition.get("runtimeCompositionDigest")
        or active_config.get("missingKeys") != []
        or active_config.get("invalidKeys") != []
    ):
        raise ConformanceBlocked("rendered Provider config is not bound to the active runtime")
    endpoint_values = {
        alias: str(material.get(key) or "").strip()
        for alias, key in dependency["endpointEnvs"].items()
    }
    if any(not value for value in endpoint_values.values()):
        raise ConformanceBlocked("selected generic Binding endpoint material is missing")

    topology_target = get_target(load_environment_topology(), target)
    profile_name = str(topology_target.get("portProfile") or "")
    port_manifest = load_port_manifest()
    role = port_manifest.get("roles", {}).get(ROLE)
    if not isinstance(role, Mapping) or role.get("scheme") != "https":
        raise ConformanceBlocked("generic substitute role is not canonical HTTPS")
    port = canonical_port(port_manifest, profile_name, ROLE)
    host_origin = parse.urlunsplit(("https", f"localhost:{port}", "", "", ""))
    ca_path = root_certificate_path(target)
    auth = load_local_environment_auth(environment, target)
    operator_token = auth.environment.get("PROVIDER_SUBSTITUTE_OPERATOR_TOKEN", "")
    if len(operator_token) < 24:
        raise ConformanceBlocked("target-managed generic substitute operator material is missing")
    return RuntimeContext(
        environment=environment,
        target=target,
        baseline_id=runtime_identity.baseline_id,
        attempt_id=runtime_identity.attempt_id,
        runtime_config_digest=runtime_identity.runtime_config_digest,
        runtime_composition_digest=runtime_identity.provider_runtime_digest,
        capability_id=capability_id,
        adapter_id=adapter_id,
        typed_port=typed_port,
        operations=operations,
        endpoint_values=endpoint_values,
        host_origin=host_origin,
        ca_path=ca_path,
        operator_token=operator_token,
    )


def execute_supported_scenes(
    context: RuntimeContext,
    *,
    client_factory=ProtocolClient,
) -> SupportedRun:
    expected_assertions = _required_assertion_ids()
    capability_assertions = tuple(
        assertion_id
        for assertion_id in expected_assertions
        if assertion_id not in SUPPORTED_PUBLIC_ASSERTIONS
    )
    if len(capability_assertions) != 1:
        raise ConformanceBlocked("source must declare exactly one capability assertion")
    client = client_factory(context)
    evidence_by_assertion: dict[str, list[InvocationEvidence]] = {
        assertion_id: []
        for assertion_id in (*SUPPORTED_PUBLIC_ASSERTIONS, *capability_assertions)
    }
    canary = "redaction-canary-" + secrets.token_hex(12)
    primary_failure: BaseException | None = None
    try:
        client.health()
        for operation in context.operations:
            success, result = client.invoke_raw(operation, canary=canary)
            _validate_success(context.capability_id, operation, result)
            if success.outcome != "success" or success.status not in {200, 202}:
                raise ConformanceBlocked("generic substitute success scene failed")
            evidence_by_assertion["provider.success"].append(success)
            evidence_by_assertion[capability_assertions[0]].append(success)
            expected_dns_digest = _sha256_text("dns\nlocalhost")
            if (
                success.network_host_digest != expected_dns_digest
                or success.tls_server_name_digest != expected_dns_digest
                or success.tls_version != "TLSv1.3"
            ):
                raise ConformanceBlocked(
                    "generic substitute network/DNS scene lacks TLS authority readback"
                )
            evidence_by_assertion["provider.network_dns"].append(success)

            for assertion_id, scenario, parameters, expected_status, expected_outcome in (
                ("provider.validation", "validation", {}, 400, "validation_rejected"),
                ("provider.auth", "auth", {}, 401, "auth_rejected"),
                (
                    "provider.timeout",
                    "delay_timeout",
                    {"delayMillis": 10},
                    504,
                    "timeout",
                ),
                (
                    "provider.throttle",
                    "throttle",
                    {"retryAfterSeconds": 1},
                    429,
                    "throttled",
                ),
            ):
                lease = client.acquire(
                    operation=operation,
                    scenario=scenario,
                    parameters=parameters,
                    max_matches=1,
                )
                invocation, fault_result = client.invoke_raw(operation, canary=canary)
                state = client.read_lease(str(lease["leaseId"]))
                cleanup = state.get("cleanupReceipt")
                if (
                    fault_result.status != expected_status
                    or invocation.outcome != expected_outcome
                    or invocation.lease_id != lease["leaseId"]
                    or state.get("state") != "exhausted"
                    or not isinstance(cleanup, Mapping)
                    or cleanup.get("status") != "restored"
                ):
                    raise ConformanceBlocked(
                        f"generic substitute {scenario} scene did not restore"
                    )
                evidence_by_assertion[assertion_id].append(invocation)

            retry_lease = client.acquire(
                operation=operation,
                scenario="transient_then_success",
                parameters={"remainingFailures": 1},
                max_matches=2,
            )
            first_retry, first_result = client.invoke_raw(operation, canary=canary)
            second_retry, second_result = client.invoke_raw(operation, canary=canary)
            _validate_success(context.capability_id, operation, second_result)
            retry_state = client.read_lease(str(retry_lease["leaseId"]))
            if (
                first_result.status != 503
                or first_retry.outcome != "transient_unavailable"
                or second_result.status not in {200, 202}
                or second_retry.outcome != "success"
                or retry_state.get("state") != "exhausted"
                or not isinstance(retry_state.get("cleanupReceipt"), Mapping)
            ):
                raise ConformanceBlocked("generic substitute retry/recovery scene failed")
            evidence_by_assertion["provider.retry"].extend(
                (first_retry, second_retry)
            )

            before_idempotency = client.readback()
            scope = f"{context.capability_id}/{operation}"
            before_effects = int(
                (before_idempotency.get("effects") or {}).get(scope, 0)
            )
            idempotency_key = "pc-idempotency-" + secrets.token_hex(12)
            first_idempotent, first_idempotent_result = client.invoke_raw(
                operation,
                canary=canary,
                idempotency_key=idempotency_key,
            )
            replay_idempotent, replay_idempotent_result = client.invoke_raw(
                operation,
                canary=canary,
                idempotency_key=idempotency_key,
            )
            conflict_idempotent, conflict_idempotent_result = client.invoke_raw(
                operation,
                canary=canary,
                idempotency_key=idempotency_key,
                extra_query="conformanceConflict=1",
            )
            after_idempotency = client.readback()
            after_effects = int(
                (after_idempotency.get("effects") or {}).get(scope, 0)
            )
            if (
                first_idempotent_result.status not in {200, 202}
                or replay_idempotent_result.status != first_idempotent_result.status
                or replay_idempotent_result.body != first_idempotent_result.body
                or conflict_idempotent_result.status != 409
                or first_idempotent.idempotency_state != "new"
                or replay_idempotent.idempotency_state != "replay"
                or conflict_idempotent.idempotency_state != "conflict"
                or first_idempotent.effect_ordinal <= 0
                or replay_idempotent.effect_ordinal
                != first_idempotent.effect_ordinal
                or conflict_idempotent.effect_ordinal
                != first_idempotent.effect_ordinal
                or after_effects - before_effects != 1
            ):
                raise ConformanceBlocked(
                    "generic substitute idempotency scene did not prove one effect"
                )
            evidence_by_assertion["provider.idempotency"].extend(
                (
                    first_idempotent,
                    replay_idempotent,
                    conflict_idempotent,
                )
            )

            channel = client.acquire_callback_channel(
                operation=operation,
                max_callbacks=2,
            )
            channel_id = str(channel["channelId"])
            callback_first, callback_first_result = client.invoke_raw(
                operation,
                canary=canary + "-callback-1",
                callback_channel=channel_id,
            )
            callback_second, callback_second_result = client.invoke_raw(
                operation,
                canary=canary + "-callback-2",
                callback_channel=channel_id,
            )
            callback_state = client.read_callback_channel(channel_id)
            callback_events = callback_state.get("events")
            if (
                callback_first_result.status not in {200, 202}
                or callback_second_result.status not in {200, 202}
                or callback_state.get("state") != "exhausted"
                or not isinstance(callback_events, list)
                or len(callback_events) != 2
                or not all(isinstance(item, Mapping) for item in callback_events)
                or [item.get("sequence") for item in callback_events] != [1, 2]
                or not isinstance(callback_events[0].get("callOrdinal"), int)
                or not isinstance(callback_events[1].get("callOrdinal"), int)
                or callback_events[0]["callOrdinal"]
                >= callback_events[1]["callOrdinal"]
                or callback_events[0].get("effectOrdinal")
                != callback_first.effect_ordinal
                or callback_events[1].get("effectOrdinal")
                != callback_second.effect_ordinal
                or callback_events[0].get("requestDigest")
                != callback_first.request_digest
                or callback_events[1].get("requestDigest")
                != callback_second.request_digest
                or callback_events[0].get("traceDigest")
                != callback_first.trace_digest
                or callback_events[1].get("traceDigest")
                != callback_second.trace_digest
                or not isinstance(callback_state.get("cleanupReceipt"), Mapping)
                or callback_state["cleanupReceipt"].get("status") != "restored"
            ):
                raise ConformanceBlocked(
                    "generic substitute callback ordering scene is incomplete"
                )
            evidence_by_assertion["provider.callback_ordering"].extend(
                (callback_first, callback_second)
            )

        readback = client.readback()
        encoded_readback = json.dumps(
            readback,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        if context.operator_token in encoded_readback or canary in encoded_readback:
            raise ConformanceBlocked("generic substitute readback leaked protected material")
        all_invocations = [
            item
            for values in evidence_by_assertion.values()
            for item in values
        ]
        if not all_invocations:
            raise ConformanceBlocked("generic substitute produced no invocation evidence")
        evidence_by_assertion["provider.redaction"] = list(all_invocations)
        evidence_by_assertion["provider.observability"] = list(all_invocations)
        readback_digest = _sha256_text(encoded_readback)
    except BaseException as exc:  # cleanup must also run for interrupts/failures
        primary_failure = exc
        raise
    finally:
        try:
            client.release_all()
            final = client.readback()
            active = [
                item
                for item in final.get("faultLeases", [])
                if isinstance(item, Mapping) and item.get("state") == "active"
            ]
            if active:
                raise ConformanceBlocked("generic substitute retained active fault leases")
        except BaseException as cleanup_error:
            if primary_failure is None:
                raise
            raise ConformanceBlocked(
                f"generic substitute cleanup failed after scene error: {cleanup_error}"
            ) from primary_failure

    assertions = {
        assertion_id: _aggregate_assertion(assertion_id, invocations)
        for assertion_id, invocations in evidence_by_assertion.items()
        if invocations
    }
    blocked = tuple(
        assertion_id
        for assertion_id in expected_assertions
        if assertion_id not in assertions
    )
    cleanup_receipts = tuple(sorted(set(client.cleanup_receipts)))
    expected_cleanup_count = len(context.operations) * 6
    if (
        len(cleanup_receipts) != expected_cleanup_count
        or any(
            not receipt.startswith(
                (
                    "receipt:provider-fault-cleanup:",
                    "receipt:provider-callback-cleanup:",
                )
            )
            or len(receipt.rsplit(":", 1)[-1]) != 24
            for receipt in cleanup_receipts
        )
    ):
        raise ConformanceBlocked(
            "generic substitute cleanup receipts do not cover every fault lease"
        )
    cleanup_receipt = _receipt_ref(
        "provider-protocol-cleanup",
        {
            "target": context.target,
            "attemptId": context.attempt_id,
            "runtime": context.runtime_composition_digest,
            "receipts": list(cleanup_receipts),
        },
    )
    return SupportedRun(
        assertions=assertions,
        cleanup_receipt=cleanup_receipt,
        supported_assertion_ids=tuple(
            assertion_id for assertion_id in expected_assertions if assertion_id in assertions
        ),
        blocked_assertion_ids=blocked,
        readback_digest=readback_digest,
    )


def emit_markers(run: SupportedRun, *, expected_assertions: Sequence[str]) -> None:
    missing = [
        assertion_id
        for assertion_id in expected_assertions
        if assertion_id not in run.assertions
    ]
    if missing:
        raise ConformanceBlocked(
            "required generic Provider assertions have no real mechanism: "
            + ",".join(missing)
        )
    for assertion_id in expected_assertions:
        print(
            _ASSERTION_MARKER
            + json.dumps(
                run.assertions[assertion_id].marker(),
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
        )
    print(
        _CLEANUP_MARKER
        + json.dumps(
            {"status": "restored", "receiptRef": run.cleanup_receipt},
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    )
