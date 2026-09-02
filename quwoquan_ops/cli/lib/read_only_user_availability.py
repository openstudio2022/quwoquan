"""stackctl status/inspect/health 的严格只读用户可用性聚合。"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = "stackctl.read_only_user_availability"
LAYERS = (
    "build_ready",
    "runtime_full_ready",
    "provider_ready",
    "release_active",
    "content_exact_queries_ready",
    "device_bound",
    "content_live_passed",
)
LAYER_STATES = frozenset({"ready", "blocked", "unavailable"})
FIRST_BLOCKER_CLASSES = frozenset(
    {
        "none",
        "build",
        "toolchain_capability",
        "signature_invalid",
        "startup_identity",
        "provider",
        "release",
        "content_exact_queries",
        "device",
        "content_live",
    }
)


def read_only_user_availability_report(target_name: str) -> dict[str, Any]:
    """读取既有证据并实时派生分层；不得创建、刷新或修复环境事实。"""

    import quwoquan_ops.cli.stackctl as _stackctl

    topology = _stackctl.load_environment_topology()
    target = _stackctl.get_target(topology, target_name)
    environment = str(target.get("env") or "")
    observed_at = datetime.now(timezone.utc)
    issues: dict[str, list[str]] = {layer: [] for layer in LAYERS}

    candidate = _candidate_report(target_name)
    mutable_startup = _startup_report(
        loader=_stackctl.load_test_live_startup_attempt,
        target_name=target_name,
        mode="test_live",
    )
    immutable_startup = _startup_report(
        loader=_stackctl.read_startup_attempt,
        target_name=target_name,
        mode="immutable_candidate",
    )
    selected_mode, startup = _select_runtime(
        candidate=candidate,
        mutable_startup=mutable_startup,
        immutable_startup=immutable_startup,
    )

    build_ready = candidate.get("status") == "validated" or _startup_identity_ready(
        mutable_startup,
        mode="test_live",
        target_name=target_name,
        environment=environment,
    )
    if not build_ready:
        issues["build_ready"].extend(candidate.get("issues", []))
        issues["build_ready"].append("no validated candidate or mutable build identity")

    runtime_ready = _startup_identity_ready(
        startup,
        mode=selected_mode,
        target_name=target_name,
        environment=environment,
        candidate_baseline=str(candidate.get("baselineId") or ""),
    )
    if not runtime_ready:
        issues["runtime_full_ready"].append(
            "selected startup identity is absent, mismatched, stopped, or not full"
        )
    # receipt 身份对得上，只说明启动过；必需容器事后退出不会回写任何 receipt，
    # 因此必须复验现况，否则「可用」这个结论会在无人察觉下保持数小时。
    liveness = _runtime_liveness_report(startup)
    if runtime_ready and liveness["status"] not in {"healthy", "not_applicable"}:
        runtime_ready = False
        issues["runtime_full_ready"].extend(liveness["issues"])

    provider = _provider_report(
        target_name=target_name,
        environment=environment,
        mode=selected_mode,
        candidate=candidate,
        startup=startup,
    )
    provider_ready = provider["ready"]
    if not provider_ready:
        issues["provider_ready"].extend(provider["issues"])

    content = _content_report(
        target_name=target_name,
        mode=selected_mode,
        startup=startup,
        observed_at=observed_at,
    )
    release_active = content["releaseActive"]
    exact_queries_ready = content["exactQueriesReady"]
    if not release_active:
        issues["release_active"].extend(content["issues"])
    if not exact_queries_ready:
        issues["content_exact_queries_ready"].extend(content["issues"])

    leases = _consumer_lease_report(target_name, content=content)
    trust = _device_trust_report(target_name, leases=leases)
    device_bound = leases["ready"] and trust["ready"]
    if not device_bound:
        issues["device_bound"].extend(leases["issues"])
        issues["device_bound"].extend(trust["issues"])

    distribution = _distribution_report(target_name)
    content_live = _content_live_report(
        target_name=target_name,
        candidate=candidate,
        startup=startup,
        content=content,
        leases=leases,
        observed_at=observed_at,
    )
    content_live_passed = content_live["passed"]
    if not content_live_passed:
        issues["content_live_passed"].extend(content_live["issues"])

    ready_by_layer = {
        "build_ready": build_ready,
        "runtime_full_ready": runtime_ready,
        "provider_ready": provider_ready,
        "release_active": release_active,
        "content_exact_queries_ready": exact_queries_ready,
        "device_bound": device_bound,
        "content_live_passed": content_live_passed,
    }
    layers = [
        {
            "name": name,
            "status": "ready" if ready_by_layer[name] else "blocked",
            "issues": _deduplicate(issues[name]),
        }
        for name in LAYERS
    ]
    first_blocker_class = _first_blocker_class(layers)
    first_blocker = next(
        (
            layer["issues"][0]
            for layer in layers
            if layer["status"] != "ready" and layer["issues"]
        ),
        "",
    )
    overall_status = "ready" if first_blocker_class == "none" else "failed"
    payload = {
        "schema": SCHEMA,
        "target": target_name,
        "environment": environment,
        "observedAt": observed_at.isoformat().replace("+00:00", "Z"),
        "status": overall_status,
        "firstBlockerClass": first_blocker_class,
        "firstBlocker": first_blocker,
        "userAvailability": layers,
        "metrics": _metrics(
            target_name=target_name,
            layers=layers,
            overall_status=overall_status,
            first_blocker_class=first_blocker_class,
        ),
        "evidence": {
            "candidate": candidate,
            "runtime": {
                "selectedMode": selected_mode,
                "candidates": {
                    "immutable_candidate": immutable_startup,
                    "test_live": mutable_startup,
                },
                "startupReceipt": startup,
                "containerLiveness": liveness,
            },
            "providerComposition": provider,
            "content": content,
            "consumerLeases": leases,
            "deviceTrust": trust,
            "distribution": distribution,
            "contentLive": content_live,
        },
    }
    return validate_read_only_user_availability_report(payload)


def validate_read_only_user_availability_report(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise TypeError("read-only availability report must be an object")
    required = {
        "schema",
        "target",
        "environment",
        "observedAt",
        "status",
        "firstBlockerClass",
        "firstBlocker",
        "userAvailability",
        "metrics",
        "evidence",
    }
    if set(payload) != required or payload.get("schema") != SCHEMA:
        raise ValueError("read-only availability report fields mismatch")
    layers = payload.get("userAvailability")
    names = (
        [item.get("name") for item in layers if isinstance(item, Mapping)]
        if isinstance(layers, list)
        else []
    )
    if names != list(LAYERS):
        raise ValueError("read-only availability layer order mismatch")
    for layer in layers:
        if (
            not isinstance(layer, dict)
            or set(layer) != {"name", "status", "issues"}
            or layer.get("status") not in LAYER_STATES
            or not isinstance(layer.get("issues"), list)
        ):
            raise ValueError("read-only availability layer shape mismatch")
    blocker_class = payload.get("firstBlockerClass")
    if blocker_class not in FIRST_BLOCKER_CLASSES:
        raise ValueError("read-only availability firstBlockerClass is invalid")
    expected_status = "ready" if blocker_class == "none" else "failed"
    if payload.get("status") != expected_status:
        raise ValueError("read-only availability overall status mismatch")
    metrics = payload.get("metrics")
    if not isinstance(metrics, list) or len(metrics) != len(LAYERS) + 1:
        raise ValueError("read-only availability metrics are incomplete")
    for metric in metrics:
        labels = metric.get("labels") if isinstance(metric, dict) else None
        if (
            not isinstance(metric, dict)
            or set(metric) != {"name", "labels", "value"}
            or not isinstance(labels, dict)
            or metric.get("value") != 1
        ):
            raise ValueError("read-only availability metric shape mismatch")
        if metric["name"] == "stackctl_user_availability":
            if set(labels) != {"target", "layer", "status"}:
                raise ValueError(
                    "user availability metric labels are not low-cardinality"
                )
        elif metric["name"] == "stackctl_first_blocker":
            if set(labels) != {"target", "status", "firstBlockerClass"}:
                raise ValueError("first blocker metric labels are not low-cardinality")
        else:
            raise ValueError("read-only availability metric name is invalid")
    return payload


def _candidate_report(target_name: str) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    try:
        candidate = _stackctl.active_deployment_candidate_snapshot(target_name)
    except (OSError, RuntimeError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return {"status": "unavailable", "issues": [str(exc)]}
    if not isinstance(candidate, Mapping):
        return {"status": "missing", "issues": ["active candidate is absent"]}
    manifest = candidate.get("manifest")
    manifest = manifest if isinstance(manifest, Mapping) else {}
    environment_artifact = manifest.get("environmentArtifact")
    environment_artifact = (
        environment_artifact if isinstance(environment_artifact, Mapping) else {}
    )
    return {
        "status": "validated",
        "baselineId": str(candidate.get("baselineId") or ""),
        "candidateDir": str(candidate.get("candidateDir") or ""),
        "packageDigest": str(manifest.get("packageDigest") or ""),
        "sourceRevision": str(manifest.get("sourceRevision") or ""),
        "releaseTrainId": str(environment_artifact.get("releaseTrainId") or ""),
        "providerRuntime": manifest.get("providerRuntime", {}),
        "issues": [],
    }


def _startup_report(
    *,
    loader: Callable[[str], dict[str, Any] | None],
    target_name: str,
    mode: str,
) -> dict[str, Any]:
    try:
        receipt = loader(target_name)
    except (OSError, RuntimeError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return {"mode": mode, "status": "unreadable", "error": str(exc)}
    if not isinstance(receipt, Mapping):
        return {"mode": mode, "status": "missing"}
    return {"mode": mode, **dict(receipt)}


def _select_runtime(
    *,
    candidate: Mapping[str, Any],
    mutable_startup: Mapping[str, Any],
    immutable_startup: Mapping[str, Any],
) -> tuple[str, dict[str, Any]]:
    mutable_running = mutable_startup.get("status") == "running"
    immutable_running = immutable_startup.get("status") == "running"
    if mutable_running and not immutable_running:
        return "test_live", dict(mutable_startup)
    if immutable_running and not mutable_running:
        return "immutable_candidate", dict(immutable_startup)
    if mutable_running and immutable_running:
        return "test_live", dict(mutable_startup)
    if candidate.get("status") == "validated":
        return "immutable_candidate", dict(immutable_startup)
    return "test_live", dict(mutable_startup)


def _runtime_liveness_report(startup: Mapping[str, Any]) -> dict[str, Any]:
    """复验 running receipt 所声明 runtime 的容器现况（只读）。"""
    import quwoquan_ops.cli.stackctl as _stackctl
    from quwoquan_ops.cli.lib.runtime_container_liveness import (
        ComposeProjectAbsent,
        verify_running_receipt_liveness,
    )

    try:
        report = verify_running_receipt_liveness(startup, runner=_stackctl.run)
    except ComposeProjectAbsent:
        # receipt 合法性归 startup receipt 契约（composeProject 是必填非空），
        # 这里不重复判定，只如实记为未命中，避免建立第二真相源。
        return {
            "status": "not_applicable",
            "composeProject": "",
            "blocker": "",
            "containers": [],
            "issues": [],
        }
    except (OSError, RuntimeError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return {
            "status": "unavailable",
            "composeProject": str(startup.get("composeProject") or ""),
            "blocker": "",
            "containers": [],
            "issues": [f"runtime container liveness is unverifiable: {exc}"],
        }
    if report is None:
        # receipt 不是 running：没有「启动过」这个前提，现况复验不适用。
        return {
            "status": "not_applicable",
            "composeProject": str(startup.get("composeProject") or ""),
            "blocker": "",
            "containers": [],
            "issues": [],
        }
    return {
        "status": report.status,
        "composeProject": report.compose_project,
        "blocker": report.blocker,
        "containers": [
            {
                "service": item.service or item.name,
                "state": item.state,
                "health": item.health,
                "exitCode": item.exit_code,
                "live": item.is_live,
                "completedTask": item.is_completed_task,
            }
            for item in report.containers
        ],
        "issues": report.issues(),
    }


def _startup_identity_ready(
    startup: Mapping[str, Any],
    *,
    mode: str,
    target_name: str,
    environment: str,
    candidate_baseline: str = "",
) -> bool:
    environment_field = "env" if mode == "immutable_candidate" else "environment"
    identity_ready = (
        startup.get("status") == "running"
        and startup.get("target") == target_name
        and startup.get(environment_field) == environment
        and startup.get("workload") == "full"
        and bool(str(startup.get("attemptId") or "").strip())
    )
    if mode == "immutable_candidate":
        return (
            identity_ready
            and bool(candidate_baseline)
            and startup.get("candidateDigest") == candidate_baseline
        )
    return identity_ready


def _provider_report(
    *,
    target_name: str,
    environment: str,
    mode: str,
    candidate: Mapping[str, Any],
    startup: Mapping[str, Any],
) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    issues: list[str] = []
    composition: Mapping[str, Any] = {}
    try:
        if mode == "immutable_candidate" and candidate.get("status") == "validated":
            provider_runtime = candidate.get("providerRuntime")
            raw = (
                provider_runtime.get("composition")
                if isinstance(provider_runtime, Mapping)
                else None
            )
            composition = _stackctl.validate_provider_runtime_composition(
                raw,
                expected_environment=environment,
                expected_target=target_name,
                require_current_contracts=False,
            )
        elif mode == "test_live":
            composition = _stackctl.compile_provider_runtime_composition(
                environment=environment,
                target=target_name,
            )
    except (OSError, RuntimeError, TypeError, ValueError, json.JSONDecodeError) as exc:
        issues.append(f"Provider composition is unavailable: {exc}")
    digest = str(composition.get("runtimeCompositionDigest") or "")
    if not digest or startup.get("providerRuntimeDigest") != digest:
        issues.append("startup Provider generation does not match selected composition")
    bindings = composition.get("bindings")
    raw_workloads = composition.get("workloads")
    workloads = raw_workloads if isinstance(raw_workloads, list) else []
    return {
        "ready": not issues,
        "runtimeCompositionDigest": digest,
        "bindingCount": len(bindings) if isinstance(bindings, list) else 0,
        "workloadRoles": sorted(
            str(item.get("role") or "")
            for item in workloads
            if isinstance(item, Mapping) and str(item.get("role") or "")
        ),
        "issues": _deduplicate(issues),
    }


def _content_report(
    *,
    target_name: str,
    mode: str,
    startup: Mapping[str, Any],
    observed_at: datetime,
) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    issues: list[str] = []
    binding: dict[str, Any] = {}
    readiness: dict[str, Any] = {}
    readiness_path: Path | None = None
    try:
        if mode == "test_live":
            binding = _stackctl.load_test_live_content_binding(target_name) or {}
            if not binding:
                raise ValueError("test-live content binding is absent")
            _, readiness, readiness_path, _ = (
                _stackctl._resolve_test_live_app_content_evidence(
                    target_name,
                    binding,
                )
            )
        else:
            _, readiness, readiness_path, _ = (
                _stackctl._resolve_active_app_content_evidence(target_name)
            )
    except (OSError, RuntimeError, TypeError, ValueError, json.JSONDecodeError) as exc:
        issues.append(f"content release evidence is unavailable: {exc}")
    release_id = str(readiness.get("releaseId") or binding.get("releaseId") or "")
    manifest_digest = str(
        readiness.get("manifestDigest") or binding.get("manifestDigest") or ""
    )
    exact_queries_ready = False
    if readiness:
        try:
            if mode == "test_live":
                plan = binding.get("appUatPlan")
                if (
                    not isinstance(plan, Mapping)
                    or not str(binding.get("releaseUatSamplePlanRef") or "").strip()
                    or not str(binding.get("releaseUatSamplePlanDigest") or "").startswith(
                        "sha256:"
                    )
                ):
                    raise ValueError("test-live ReleaseUatSamplePlan binding is incomplete")
            else:
                active = _stackctl.active_deployment_candidate(target_name) or {}
                candidate_manifest = _stackctl._read_json_object(
                    str(Path(str(active.get("candidateDir") or "")) / "manifest.json")
                )
                release_binding = candidate_manifest.get("release")
                release_candidate = (
                    release_binding.get("candidate")
                    if isinstance(release_binding, Mapping)
                    else None
                )
                if not isinstance(release_candidate, Mapping):
                    raise ValueError(
                        "active candidate does not bind a Data candidate release"
                    )
                release = _stackctl._load_active_release_uat_contract(
                    release_candidate
                )
                plan = _stackctl._app_content_uat_sample_plan(
                    release_contract=release,
                    readiness=readiness,
                )
            exact_queries_ready = bool(
                isinstance(plan, Mapping)
                and plan.get("orderedSamples")
                and plan.get("requiredCasePlan")
            )
        except (OSError, TypeError, ValueError) as exc:
            issues.append(f"exact query evidence is invalid: {exc}")
    readiness_digest = ""
    if readiness_path is not None:
        try:
            readiness_digest = (
                "sha256:" + hashlib.sha256(readiness_path.read_bytes()).hexdigest()
            )
        except OSError as exc:
            issues.append(f"readiness receipt bytes are unreadable: {exc}")
    generation_match = bool(readiness) and (
        mode != "test_live"
        or (
            binding.get("startupAttemptId") == startup.get("attemptId")
            and binding.get("readinessReceiptDigest") == readiness_digest
        )
    )
    if readiness and not generation_match:
        issues.append("content readiness belongs to another runtime generation")
    return {
        "releaseActive": generation_match
        and bool(release_id)
        and bool(manifest_digest),
        "exactQueriesReady": generation_match and exact_queries_ready,
        "releaseId": release_id,
        "manifestDigest": manifest_digest,
        "readinessPhase": str(
            readiness.get("readinessPhase") or binding.get("readinessPhase") or ""
        ),
        "readinessReceiptRef": (
            _stackctl.relpath(readiness_path) if readiness_path is not None else ""
        ),
        "readinessReceiptDigest": readiness_digest,
        "exactQueryReceiptAgeSeconds": _receipt_age_seconds(
            readiness,
            observed_at=observed_at,
        ),
        "generationMatch": generation_match,
        "startupAttemptId": str(startup.get("attemptId") or ""),
        "issues": _deduplicate(issues),
    }


def _consumer_lease_report(
    target_name: str,
    *,
    content: Mapping[str, Any],
) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    try:
        leases = _stackctl.inspect_consumer_leases(target_name)
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        return {
            "ready": False,
            "leases": [],
            "issues": [f"consumer leases are unreadable: {exc}"],
        }
    release_id = str(content.get("releaseId") or "")
    manifest_digest = str(content.get("manifestDigest") or "")
    readiness_digest = str(content.get("readinessReceiptDigest") or "")
    summaries: list[dict[str, Any]] = []
    ready = False
    for lease in leases:
        state = str(lease.get("state") or "")
        generation_match = (
            state in {"active", "build_grace", "released"}
            and bool(release_id)
            and lease.get("releaseId") == release_id
            and lease.get("manifestDigest") == manifest_digest
            and lease.get("readinessReceiptDigest") == readiness_digest
        )
        summaries.append(
            {
                "leaseId": str(lease.get("leaseId") or ""),
                "device": str(lease.get("device") or ""),
                "platform": str(lease.get("platform") or ""),
                "state": state,
                "generationMatch": generation_match,
            }
        )
        ready = ready or generation_match
    issues = []
    if leases and not ready:
        issues.append(
            "consumer lease is stale or belongs to another release generation"
        )
    if not leases:
        issues.append("no consumer lease receipt exists")
    return {"ready": ready, "leases": summaries, "issues": issues}


def _device_trust_report(
    target_name: str,
    *,
    leases: Mapping[str, Any],
) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    issues: list[str] = []
    receipts: list[dict[str, Any]] = []
    for lease in leases.get("leases", []):
        if not isinstance(lease, Mapping) or lease.get("generationMatch") is not True:
            continue
        platform = str(lease.get("platform") or "")
        trust_platform = {
            "android": "android-emulator",
            "ios-simulator": "ios-simulator",
        }.get(platform, "")
        if not trust_platform:
            continue
        device = str(lease.get("device") or "")
        path = _stackctl.device_trust_receipt_path(
            target_name,
            trust_platform,
            device,
        )
        try:
            receipt = _stackctl.read_device_trust_receipt(path)
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            issues.append(f"device trust receipt is unreadable: {exc}")
            continue
        if not isinstance(receipt, Mapping):
            issues.append("device trust receipt is missing")
            continue
        generation_match = (
            receipt.get("target") == target_name
            and receipt.get("platform") == trust_platform
            and receipt.get("device") == device
            and receipt.get("status") == "installed"
            and receipt.get("systemTrustStore") is True
            and str(lease.get("leaseId") or "") in (receipt.get("leases") or [])
        )
        receipts.append(
            {
                "platform": trust_platform,
                "device": device,
                "status": str(receipt.get("status") or ""),
                "generationMatch": generation_match,
            }
        )
    ready = any(receipt["generationMatch"] for receipt in receipts)
    if not ready and not issues:
        issues.append("no exact consumer lease has installed system trust")
    return {"ready": ready, "receipts": receipts, "issues": issues}


def _distribution_report(target_name: str) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    try:
        inspection, root, explicitly_configured = (
            _stackctl._inspect_distribution_for_target(
                argparse.Namespace(
                    distribution_root="",
                    verify_hosted=False,
                ),
                target_name=target_name,
            )
        )
    except (
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
        _stackctl.OfficialDistributionReleaseError,
    ) as exc:
        return {"status": "unavailable", "ready": False, "issues": [str(exc)]}
    return {
        "status": str(inspection.get("status") or ""),
        "ready": inspection.get("status") == "ready",
        "distributionRoot": str(root),
        "explicitlyConfigured": explicitly_configured,
        "web": inspection.get("web", {}),
        "android": inspection.get("android", {}),
        "issues": list(inspection.get("issues") or []),
    }


def _content_uat_report_candidates(
    roots: tuple[Path, ...],
) -> list[tuple[float, Path]]:
    """Enumerate canonical direct run reports without descending other outputs."""

    candidates: list[tuple[float, Path]] = []
    for root in roots:
        try:
            run_directories = tuple(root.iterdir())
        except OSError:
            continue
        for run_directory in run_directories:
            try:
                if run_directory.is_symlink() or not run_directory.is_dir():
                    continue
                report = run_directory / "report.json"
                if report.is_symlink() or not report.is_file():
                    continue
                candidates.append((report.stat().st_mtime, report))
            except OSError:
                continue
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates


def _content_live_report(
    *,
    target_name: str,
    candidate: Mapping[str, Any],
    startup: Mapping[str, Any],
    content: Mapping[str, Any],
    leases: Mapping[str, Any],
    observed_at: datetime,
) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    environment = (
        target_name.removesuffix("-local") if target_name.endswith("-local") else "prod"
    )
    release_id = str(content.get("releaseId") or "")
    manifest_digest = str(content.get("manifestDigest") or "")
    readiness_digest = str(content.get("readinessReceiptDigest") or "")
    package_baseline = str(candidate.get("baselineId") or "")
    release_train_id = str(candidate.get("releaseTrainId") or "")
    startup_candidate_digest = str(startup.get("candidateDigest") or "")
    expected_lease_ids = {
        str(item.get("leaseId") or "")
        for item in leases.get("leases", [])
        if isinstance(item, Mapping) and item.get("generationMatch") is True
    }
    matches: list[dict[str, Any]] = []
    # 一次 App 内容 UAT 可同时绑定多个 target，聚合回执因此落在 repo 级 runs 根而不是
    # 任一单环境根。只扫环境根会让 content_live 层永远读不到回执，于是两处都扫：target
    # 归属仍由回执内 runtimeBindings 与 startupAttemptId 判定，放宽的只是查找范围。
    # 跨根之后路径序不再等价于时间序，改按修改时间取最新优先。
    candidates = _content_uat_report_candidates(
        (_stackctl.env_runs_root(environment), _stackctl.repo_runs_root())
    )
    startup_started_at = _timestamp(str(startup.get("startedAt") or ""))
    for modified_at, path in candidates:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if (
            not isinstance(payload, Mapping)
            or payload.get("schema") != "quwoquan_ops.app_content_uat_receipt"
        ):
            continue
        runtime_bindings = payload.get("runtimeBindings")
        runtime_binding = (
            runtime_bindings.get(target_name)
            if isinstance(runtime_bindings, Mapping)
            else None
        )
        package_baselines = payload.get("packageBaselines")
        report_time = datetime.fromtimestamp(modified_at, timezone.utc)
        not_older_than_startup = (
            startup_started_at is not None and report_time >= startup_started_at
        )
        generation_match = (
            # 写入方（app_preflight_uat_receipt）的状态闭集是 planned/gate_block/
            # complete；green 语义对应 complete，而不是并不存在的 passed。
            payload.get("status") == "complete"
            and payload.get("releaseId") == release_id
            and payload.get("manifestDigest") == manifest_digest
            and readiness_digest in (payload.get("readinessReceiptDigests") or [])
            and bool(expected_lease_ids)
            and expected_lease_ids.issubset(set(payload.get("consumerLeaseIds") or []))
            and isinstance(runtime_binding, Mapping)
            and runtime_binding.get("startupAttemptId") == startup.get("attemptId")
            and bool(package_baseline)
            and bool(release_train_id)
            and startup_candidate_digest == package_baseline
            and payload.get("releaseTrainId") == release_train_id
            and isinstance(package_baselines, Mapping)
            and package_baselines.get(target_name) == package_baseline
            and runtime_binding.get("candidateDigest") == startup_candidate_digest
            and not_older_than_startup
        )
        matches.append(
            {
                "reportRef": _stackctl.relpath(path),
                "status": str(payload.get("status") or ""),
                "generationMatch": generation_match,
                "targetPackageBaseline": str(package_baselines.get(target_name) or "")
                if isinstance(package_baselines, Mapping)
                else "",
                "startupCandidateDigest": startup_candidate_digest,
                "receiptAgeSeconds": max(
                    0,
                    int((observed_at - report_time).total_seconds()),
                ),
            }
        )
        if generation_match:
            return {"passed": True, "matches": matches, "issues": []}
        if len(matches) >= 5:
            break
    issue = (
        "content-live receipt is old or belongs to another runtime generation"
        if matches
        else "no App content UAT receipt exists"
    )
    return {"passed": False, "matches": matches, "issues": [issue]}


def _receipt_age_seconds(
    receipt: Mapping[str, Any],
    *,
    observed_at: datetime,
) -> int | None:
    for field in ("verifiedAt", "generatedAt", "updatedAt", "boundAt"):
        timestamp = _timestamp(str(receipt.get(field) or ""))
        if timestamp is not None:
            return max(0, int((observed_at - timestamp).total_seconds()))
    return None


def _timestamp(raw: str) -> datetime | None:
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _first_blocker_class(layers: list[dict[str, Any]]) -> str:
    first_issue = next(
        (
            str(issue)
            for layer in layers
            if layer.get("status") != "ready"
            for issue in layer.get("issues", [])
        ),
        "",
    )
    if "GATE_BLOCK[OPENSSL_3_ED25519_RAWIN_CAPABILITY]" in first_issue:
        return "toolchain_capability"
    if "signature" in first_issue.lower() and (
        "invalid" in first_issue.lower()
        or "verification failed" in first_issue.lower()
    ):
        return "signature_invalid"
    mapping = {
        "build_ready": "startup_identity",
        "runtime_full_ready": "startup_identity",
        "provider_ready": "provider",
        "release_active": "release",
        "content_exact_queries_ready": "content_exact_queries",
        "device_bound": "device",
        "content_live_passed": "content_live",
    }
    for layer in layers:
        if layer["status"] != "ready":
            return mapping[layer["name"]]
    return "none"


def _metrics(
    *,
    target_name: str,
    layers: list[dict[str, Any]],
    overall_status: str,
    first_blocker_class: str,
) -> list[dict[str, Any]]:
    return [
        {
            "name": "stackctl_user_availability",
            "labels": {
                "target": target_name,
                "layer": layer["name"],
                "status": layer["status"],
            },
            "value": 1,
        }
        for layer in layers
    ] + [
        {
            "name": "stackctl_first_blocker",
            "labels": {
                "target": target_name,
                "status": overall_status,
                "firstBlockerClass": first_blocker_class,
            },
            "value": 1,
        }
    ]


def _deduplicate(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
