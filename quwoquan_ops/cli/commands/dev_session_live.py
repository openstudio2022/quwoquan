"""stackctl dev-session mutable test-live 运行时域: 启动与在运行恢复。

从 stackctl.py 逐字迁出（改写规则与 down_domain 相同）:
`_start_mutable_test_live_runtime` / `_dev_session_regular_json` /
`_dev_session_resume_running_mutable_runtime`。

测试经 ``mock.patch.object(stackctl, ...)`` patch 本模块符号与协作符号，
因此函数体内一律经函数内延迟导入 `_stackctl` 属性访问（含本模块符号互调），
保持 monkeypatch 语义并避免顶层循环 import。
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import time

from pathlib import Path
from typing import Any
from typing import Mapping


_VERSION_PINNED_QUWOQUAN_INFRA_IMAGE_PREFIXES = (
    "quwoquan/elasticsearch-cjk:",
)


def _start_mutable_test_live_runtime(
    *,
    environment: str,
    target: str,
    report_dir: Path,
    workspace_snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    """Render and start one current-worktree runtime; health is evaluated later."""
    import quwoquan_ops.cli.stackctl as _stackctl


    phases: list[dict[str, Any]] = []
    try:
        rendered = _stackctl._dev_session_render_runtime_inputs(
            environment=environment,
            target=target,
            report_dir=report_dir,
            workspace_snapshot=workspace_snapshot,
        )
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        return {
            "exitCode": 2,
            "blockerKind": "mutable_runtime_materialization_failed",
            "details": [str(exc)],
            "phases": phases,
        }
    plan = rendered["plan"]
    phases.append(
        {
            "name": "mutable-materialize",
            "exitCode": 0,
            "summary": "current workspace runtime inputs materialized",
            "details": [
                f"composeProject={plan['composeProject']}",
                f"composeDigest={plan['composeDigest']}",
            ],
            "reportDir": _stackctl.relpath(report_dir),
        }
    )
    base_command = [
        "docker",
        "compose",
        "-p",
        str(plan["composeProject"]),
        *_stackctl.compose_file_args(list(rendered["composeFiles"])),
    ]
    for profile in rendered["composeProfiles"]:
        base_command.extend(("--profile", str(profile)))
    render_command = [*base_command, "config", "--format", "json"]
    render_result = _stackctl.run(
        render_command,
        env=dict(rendered["environment"]),
        timeout_seconds=90,
    )
    if render_result.returncode != 0:
        render_failure_details = [
            f"docker compose config exited {render_result.returncode}",
            "rendered Compose output omitted from evidence",
        ]
        phases.append(
            {
                "name": "compose-render",
                "exitCode": render_result.returncode,
                "summary": "mutable Compose render failed",
                "details": render_failure_details,
                "reportDir": _stackctl.relpath(report_dir),
            }
        )
        return {
            "exitCode": 2,
            "blockerKind": "mutable_compose_render_failed",
            "details": render_failure_details,
            "phases": phases,
        }
    try:
        compose_model = json.loads(render_result.stdout)
        if not isinstance(compose_model, Mapping):
            raise ValueError("runtime Compose model must be a JSON object")
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        invalid_model_details = [
            "rendered Compose model is not a valid JSON object",
            f"errorType={type(exc).__name__}",
        ]
        phases.append(
            {
                "name": "compose-render",
                "exitCode": 2,
                "summary": "mutable Compose model validation failed",
                "details": invalid_model_details,
                "reportDir": _stackctl.relpath(report_dir),
            }
        )
        return {
            "exitCode": 2,
            "blockerKind": "mutable_compose_ownership_invalid",
            "details": invalid_model_details,
            "phases": phases,
        }
    phases.append(
        {
            "name": "compose-render",
            "exitCode": 0,
            "summary": "mutable Compose render validated",
            "details": [
                "rendered Compose values omitted from evidence",
                f"serviceCount={len(compose_model.get('services') or {})}",
                f"networkCount={len(compose_model.get('networks') or {})}",
                f"volumeCount={len(compose_model.get('volumes') or {})}",
            ],
            "reportDir": _stackctl.relpath(report_dir),
        }
    )
    try:
        plan = _stackctl._dev_session_finalize_runtime_plan(
            runtime_plan=plan,
            compose_model=compose_model,
            report_dir=report_dir,
        )
        rendered = {**rendered, "plan": plan}
    except (OSError, RuntimeError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return {
            "exitCode": 2,
            "blockerKind": "mutable_compose_ownership_invalid",
            "details": [str(exc)],
            "phases": phases,
        }
    try:
        previous_mutable_attempt = _stackctl.load_test_live_startup_attempt(target)
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        return {
            "exitCode": 2,
            "blockerKind": "mutable_startup_retry_failed",
            "details": [f"interrupted mutable startup attempt is not retryable: {exc}"],
            "phases": phases,
        }
    if previous_mutable_attempt is not None and previous_mutable_attempt.get(
        "status"
    ) in {"prepared", "partial", "running"}:
        return {
            "exitCode": 2,
            "blockerKind": "mutable_startup_attempt_active",
            "details": [
                "existing mutable startup attempt must be receipt-bound stopped before retry",
                f"attemptId={previous_mutable_attempt['attemptId']}",
                f"status={previous_mutable_attempt['status']}",
                f"runRoot={previous_mutable_attempt['runRoot']}",
                (
                    "recoveryCommand=python3 quwoquan_ops/cli/stackctl.py "
                    f"down --target {target}"
                ),
            ],
            "phases": phases,
            "startupAttempt": dict(previous_mutable_attempt),
        }
    attempt_seed = hashlib.sha256(
        (
            f"{environment}\0{target}\0{report_dir}\0"
            f"{time.time_ns()}\0{os.getpid()}"
        ).encode("utf-8")
    ).hexdigest()
    attempt_id = f"{environment}-test-live-{attempt_seed[:32]}"
    try:
        prepared_receipt = _stackctl.transition_test_live_startup_attempt(
            environment=environment,
            target=target,
            attempt_id=attempt_id,
            status="prepared",
            runtime_plan=plan,
            run_root=report_dir,
        )
        partial_receipt = _stackctl.transition_test_live_startup_attempt(
            environment=environment,
            target=target,
            attempt_id=attempt_id,
            status="partial",
            runtime_plan=plan,
            run_root=report_dir,
        )
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        return {
            "exitCode": 2,
            "blockerKind": "mutable_startup_receipt_failed",
            "details": [f"mutable startup receipt could not enter partial: {exc}"],
            "phases": phases,
        }
    phases.append(
        {
            "name": "mutable-startup-partial",
            "exitCode": 0,
            "summary": "target-scoped mutable startup receipt entered partial",
            "details": [
                f"attemptId={attempt_id}",
                f"configurationDigest={prepared_receipt['configurationDigest']}",
            ],
            "reportDir": _stackctl.relpath(report_dir),
        }
    )
    compose_up_timeout = float(
        rendered["environment"].get(
            "LOCAL_GAMMA_COMPOSE_UP_TIMEOUT_SECONDS", "420"
        )
    )
    build_timeout = max(
        float(
            rendered["environment"].get(
                "LOCAL_GAMMA_COMPOSE_BUILD_TIMEOUT_SECONDS", "3600"
            )
        ),
        compose_up_timeout,
    )
    # A brand-new target has no Product Ops ExperimentPolicyActivated fact.
    # Recommendation intentionally refuses a full runtime without that fact,
    # while Product Ops readiness requires the service-core hosted User account
    # security authority.  Start service-core without its Recommendation
    # dependency closure: the exact account-security health path is already a
    # pre-admission route, and Product Ops' registered readiness probe consumes
    # it with the canonical service credential.  Product Ops itself is then
    # waited healthy before the existing public command activates the exact
    # run-bound policies.  This is not a DB seed, private Recommendation
    # fallback, or pre-admission business-route bypass.
    policy_owner_steps = (
        (
            "test-live-policy-owner-dependencies",
            "Product Ops data dependencies became healthy",
            [
                *base_command,
                "up",
                "-d",
                "--wait",
                "--wait-timeout",
                str(max(1, int(compose_up_timeout))),
                "postgres",
                "mongodb",
                "redis",
                "elasticsearch",
            ],
        ),
        (
            "test-live-policy-owner-mongo-init",
            "Product Ops Mongo initialization completed",
            [*base_command, "up", "--no-deps", "mongo-init"],
        ),
        (
            "test-live-policy-authority-bootstrap",
            "service-core account security authority bootstrap completed",
            [
                *base_command,
                "up",
                "--build",
                "-d",
                "--no-deps",
                "service-core",
            ],
        ),
        (
            "test-live-policy-owner-bootstrap",
            "Product Ops policy command owner became ready",
            [
                *base_command,
                "up",
                "--build",
                "-d",
                "--wait",
                "--wait-timeout",
                str(max(1, int(compose_up_timeout))),
                "--no-deps",
                "product-ops-service",
            ],
        ),
    )
    for phase_name, phase_summary, policy_owner_command in policy_owner_steps:
        policy_owner_result = _stackctl.run(
            policy_owner_command,
            env=dict(rendered["environment"]),
            timeout_seconds=build_timeout,
        )
        phases.append(
            {
                "name": phase_name,
                "exitCode": policy_owner_result.returncode,
                "summary": phase_summary,
                "details": _stackctl._command_details(policy_owner_result),
                "reportDir": _stackctl.relpath(report_dir),
            }
        )
        if policy_owner_result.returncode == 0:
            continue
        failure = (
            f"{phase_summary} exited {policy_owner_result.returncode}: "
            + "; ".join(_stackctl._command_details(policy_owner_result))
        )
        try:
            partial_receipt = _stackctl.transition_test_live_startup_attempt(
                environment=environment,
                target=target,
                attempt_id=attempt_id,
                status="partial",
                runtime_plan=plan,
                run_root=report_dir,
                failure=failure,
            )
        except (OSError, RuntimeError, TypeError, ValueError):
            pass
        return {
            "exitCode": 2,
            "blockerKind": "test_live_policy_owner_bootstrap_failed",
            "details": _stackctl._command_details(policy_owner_result),
            "phases": phases,
            "startupAttempt": partial_receipt,
        }
    try:
        product_ops_port = _stackctl.require_published_endpoint_port(
            plan["publishedPorts"],
            role="product-ops-service",
            protocol="tcp",
        )
        policy_receipt = _stackctl.activate_test_live_experiment_policies(
            environment=environment,
            target=target,
            product_ops_published_port=product_ops_port,
            attempt_id=attempt_id,
            configuration_digest=str(plan["configurationDigest"]),
        )
        policy_receipt_path = report_dir / "experiment-policy-activation.json"
        _stackctl.write_json(policy_receipt_path, policy_receipt)
    except (
        _stackctl.ExperimentPolicyActivationError,
        KeyError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
    ) as exc:
        failure = f"test-live experiment policy activation failed: {exc}"
        try:
            partial_receipt = _stackctl.transition_test_live_startup_attempt(
                environment=environment,
                target=target,
                attempt_id=attempt_id,
                status="partial",
                runtime_plan=plan,
                run_root=report_dir,
                failure=failure,
            )
        except (OSError, RuntimeError, TypeError, ValueError):
            pass
        phases.append(
            {
                "name": "test-live-experiment-policy-activation",
                "exitCode": 2,
                "summary": "run-bound Product Ops policy activation failed",
                "details": [failure],
                "reportDir": _stackctl.relpath(report_dir),
            }
        )
        return {
            "exitCode": 2,
            "blockerKind": "test_live_experiment_policy_activation_failed",
            "details": [failure],
            "phases": phases,
            "startupAttempt": partial_receipt,
        }
    phases.append(
        {
            "name": "test-live-experiment-policy-activation",
            "exitCode": 0,
            "summary": "run-bound Product Ops policies activated",
            "details": [
                f"receipt={_stackctl.relpath(policy_receipt_path)}",
                f"runtimeIdentityDigest={policy_receipt['runtimeIdentityDigest']}",
            ],
            "reportDir": _stackctl.relpath(report_dir),
        }
    )
    # Build is deliberately independent of service-health dependencies.  The
    # project-wide command only builds services that author a build stanza;
    # registry-backed infrastructure images remain untouched.
    build_command = [*base_command, "build"]
    build_result = _stackctl.run(
        build_command,
        env=dict(rendered["environment"]),
        timeout_seconds=build_timeout,
    )
    phases.append(
        {
            "name": "compose-build",
            "exitCode": build_result.returncode,
            "summary": "mutable current-worktree images built without health dependencies",
            "details": _stackctl._command_details(build_result),
            "reportDir": _stackctl.relpath(report_dir),
        }
    )
    if build_result.returncode != 0:
        receipt_details: list[str] = []
        try:
            partial_receipt = _stackctl.transition_test_live_startup_attempt(
                environment=environment,
                target=target,
                attempt_id=attempt_id,
                status="partial",
                runtime_plan=plan,
                run_root=report_dir,
                failure=(
                    f"docker compose build exited {build_result.returncode}: "
                    + "; ".join(_stackctl._command_details(build_result))
                ),
            )
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            receipt_details.append(
                f"mutable startup partial failure receipt could not be updated: {exc}"
            )
        return {
            "exitCode": 2,
            "blockerKind": "mutable_compose_build_failed",
            "details": [*_stackctl._command_details(build_result), *receipt_details],
            "phases": phases,
            "startupAttempt": partial_receipt,
        }

    replace_command = [
        *base_command,
        "up",
        "-d",
        "--no-deps",
    ]
    replace_result = _stackctl.run(
        replace_command,
        env=dict(rendered["environment"]),
        timeout_seconds=build_timeout,
    )
    phases.append(
        {
            "name": "compose-replace-buildable-services",
            "exitCode": replace_result.returncode,
            "summary": "mutable buildable services replaced without waiting on old health",
            "details": _stackctl._command_details(replace_result),
            "reportDir": _stackctl.relpath(report_dir),
        }
    )
    if replace_result.returncode != 0:
        failure = (
            f"docker compose no-deps replacement exited {replace_result.returncode}: "
            + "; ".join(_stackctl._command_details(replace_result))
        )
        try:
            partial_receipt = _stackctl.transition_test_live_startup_attempt(
                environment=environment,
                target=target,
                attempt_id=attempt_id,
                status="partial",
                runtime_plan=plan,
                run_root=report_dir,
                failure=failure,
            )
        except (OSError, RuntimeError, TypeError, ValueError):
            pass
        return {
            "exitCode": 2,
            "blockerKind": "mutable_compose_service_replacement_failed",
            "details": _stackctl._command_details(replace_result),
            "phases": phases,
            "startupAttempt": partial_receipt,
        }

    up_command = [*base_command, "up", "-d", "--remove-orphans"]
    up_result = _stackctl.run(
        up_command,
        env=dict(rendered["environment"]),
        timeout_seconds=build_timeout,
    )
    phases.append(
        {
            "name": "compose-up",
            "exitCode": up_result.returncode,
            "summary": "mutable current-worktree Compose dependencies restored",
            "details": _stackctl._command_details(up_result),
            "reportDir": _stackctl.relpath(report_dir),
        }
    )
    if up_result.returncode != 0:
        failure = (
            f"docker compose up exited {up_result.returncode}: "
            + "; ".join(_stackctl._command_details(up_result))
        )
        try:
            partial_receipt = _stackctl.transition_test_live_startup_attempt(
                environment=environment,
                target=target,
                attempt_id=attempt_id,
                status="partial",
                runtime_plan=plan,
                run_root=report_dir,
                failure=failure,
            )
        except (OSError, RuntimeError, TypeError, ValueError):
            pass
        return {
            "exitCode": 2,
            "blockerKind": "mutable_compose_up_failed",
            "details": _stackctl._command_details(up_result),
            "phases": phases,
            "startupAttempt": partial_receipt,
        }
    try:
        running_receipt = _stackctl.transition_test_live_startup_attempt(
            environment=environment,
            target=target,
            attempt_id=attempt_id,
            status="running",
            runtime_plan=plan,
            run_root=report_dir,
        )
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        return {
            "exitCode": 2,
            "blockerKind": "mutable_startup_receipt_commit_failed",
            "details": [
                "mutable Compose up completed but its running receipt could not be committed",
                str(exc),
            ],
            "runtimeMayBeRunning": True,
            "phases": phases,
            "startupAttempt": partial_receipt,
        }
    phases.append(
        {
            "name": "mutable-startup-running",
            "exitCode": 0,
            "summary": "target-scoped mutable startup receipt entered running",
            "details": [f"attemptId={attempt_id}"],
            "reportDir": _stackctl.relpath(report_dir),
        }
    )
    return {
        "exitCode": 0,
        "blockerKind": "",
        "details": [],
        "phases": phases,
        "runtime": plan,
        "startupAttempt": running_receipt,
    }


def _dev_session_regular_json(path: Path, *, label: str) -> dict[str, Any]:
    """Read one execution artifact without following a replacement or symlink."""

    try:
        before = path.lstat()
    except FileNotFoundError as exc:
        raise ValueError(f"{label} is missing") from exc
    if not stat.S_ISREG(before.st_mode) or path.is_symlink():
        raise ValueError(f"{label} must be a regular non-symlink file")
    try:
        payload = json.loads(path.read_bytes())
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is unreadable JSON") from exc
    after = path.lstat()
    if (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    ) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ):
        raise ValueError(f"{label} changed while it was read")
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    return payload


def _dev_session_resume_running_mutable_runtime(
    *,
    environment: str,
    target: str,
    workspace_snapshot: Mapping[str, Any],
    required_running_services: frozenset[str] = frozenset(),
) -> tuple[dict[str, Any] | None, list[str]]:
    """Reuse one verified running test-live attempt for a run-bound operation.

    Alpha/Beta/Gamma are mutable test environments: a current-worktree digest
    change is reported as a warning while the receipt continues to identify the
    exact already-deployed runtime.  Compose, configuration, image and container
    identity are still verified below before the attempt can be reused for
    business-data apply or explicit content binding.
    """
    import quwoquan_ops.cli.stackctl as _stackctl


    receipt = _stackctl.load_test_live_startup_attempt(target)
    if not isinstance(receipt, dict) or receipt.get("status") != "running":
        return None, []
    if (
        receipt.get("launchPolicy") != "test_live"
        or receipt.get("nonPromotable") is not True
        or receipt.get("environment") != environment
        or receipt.get("target") != target
        or receipt.get("workload") != "full"
    ):
        raise ValueError("running mutable receipt is outside the test-live resume boundary")

    current_digest = str(workspace_snapshot.get("mutableStateDigest") or "")
    resume_warnings: list[str] = []
    if receipt.get("mutableStateDigest") != current_digest:
        resume_warnings.append(
            "running mutable workspace digest changed; reusing the exact "
            "verified deployed runtime for the run-bound operation"
        )

    run_root = Path(str(receipt.get("runRoot") or ""))
    try:
        run_root_metadata = run_root.lstat()
    except FileNotFoundError as exc:
        raise ValueError("running mutable receipt runRoot is missing") from exc
    if not stat.S_ISDIR(run_root_metadata.st_mode) or run_root.is_symlink():
        raise ValueError("running mutable receipt runRoot must be a regular directory")
    runtime_plan = _stackctl._dev_session_regular_json(
        run_root / "mutable-runtime-plan.json",
        label="running mutable runtime plan",
    )
    if runtime_plan.get("schema") != "stackctl.mutable_test_live_runtime":
        raise ValueError("running mutable runtime plan schema mismatch")
    if runtime_plan.get("serviceCoreModules") != sorted(_stackctl.SERVICE_CORE_MODULE_SET):
        raise ValueError("running mutable runtime service-core closure mismatch")

    for field in (
        "environment",
        "target",
        "composeProject",
        "composeDigest",
        "configurationDigest",
        "providerRuntimeDigest",
        "observabilityLogSinkDigest",
        "portProfile",
        "portBlock",
        "publishedPorts",
        "tlsProfile",
        "resolverHandoffDigest",
        "publicWebPackage",
    ):
        if runtime_plan.get(field) != receipt.get(field):
            raise ValueError(f"running mutable receipt/plan drift: {field}")
    plan_workspace = runtime_plan.get("workspaceIdentity")
    if not isinstance(plan_workspace, Mapping):
        raise ValueError("running mutable runtime plan has no workspace identity")
    for receipt_field, plan_field in (
        ("sourceRevision", "sourceRevision"),
        ("workspaceStatusDigest", "workspaceStatusDigest"),
        ("mutableStateDigest", "mutableStateDigest"),
    ):
        if receipt.get(receipt_field) != plan_workspace.get(plan_field):
            raise ValueError(
                f"running mutable receipt/plan drift: {receipt_field}"
            )

    execution_refs = runtime_plan.get("executionComposeFiles")
    if not isinstance(execution_refs, list) or not execution_refs:
        raise ValueError("running mutable runtime plan has no execution Compose files")
    expected_services: set[str] = set()
    environment_keys: dict[str, set[str]] = {}
    completed_services: set[str] = set()
    health_checked_services: set[str] = set()
    for index, raw_ref in enumerate(execution_refs):
        ref = Path(str(raw_ref or ""))
        path = ref if ref.is_absolute() else _stackctl.ROOT / ref
        path = Path(os.path.abspath(path))
        if not path.is_relative_to(run_root):
            raise ValueError("running mutable execution Compose file escapes runRoot")
        compose = _stackctl._dev_session_regular_json(
            path,
            label=f"running mutable execution Compose file {index}",
        )
        source_refs = runtime_plan.get("composeFiles")
        if not isinstance(source_refs, list) or len(source_refs) != len(execution_refs):
            raise ValueError("running mutable source/execution Compose closure drifted")
        if str(source_refs[index]) == (
            "quwoquan_service/services/product-ops-service/deploy/"
            "local-elasticsearch.compose.yaml"
        ) and "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest() != str(
            receipt["observabilityLogSinkDigest"]
        ):
            raise ValueError(
                "running mutable observability log-sink composition drifted"
            )
        services = compose.get("services")
        if services is not None and not isinstance(services, dict):
            raise ValueError("running mutable execution Compose services are invalid")
        for service, definition in (services or {}).items():
            if not isinstance(service, str) or not service or not isinstance(definition, dict):
                raise ValueError("running mutable execution Compose service is invalid")
            expected_services.add(service)
            if "healthcheck" in definition:
                healthcheck = definition.get("healthcheck")
                if (
                    isinstance(healthcheck, Mapping)
                    and healthcheck.get("disable") is not True
                ):
                    health_checked_services.add(service)
                else:
                    health_checked_services.discard(service)
            depends_on = definition.get("depends_on")
            if isinstance(depends_on, Mapping):
                for dependency, dependency_rule in depends_on.items():
                    if (
                        isinstance(dependency, str)
                        and isinstance(dependency_rule, Mapping)
                        and dependency_rule.get("condition")
                        == "service_completed_successfully"
                    ):
                        completed_services.add(dependency)
            raw_environment = definition.get("environment")
            if isinstance(raw_environment, dict):
                environment_keys.setdefault(service, set()).update(
                    str(key) for key in raw_environment
                )
    mandatory_services = {_stackctl.SERVICE_CORE_WORKLOAD, "sms-provider-substitute"}
    if not mandatory_services.issubset(expected_services):
        raise ValueError("running mutable full workload service roster is incomplete")
    if not required_running_services.issubset(expected_services):
        raise ValueError("running mutable required service roster is incomplete")

    project = str(receipt["composeProject"])
    lookup = _stackctl.run(
        [
            "docker",
            "ps",
            "-aq",
            "--filter",
            f"label=com.docker.compose.project={project}",
        ],
        timeout_seconds=30,
    )
    container_ids = [line.strip() for line in lookup.stdout.splitlines() if line.strip()]
    if lookup.returncode != 0 or not container_ids:
        raise ValueError("running mutable Compose project has no inspectable containers")
    inspected = _stackctl.run(["docker", "inspect", *container_ids], timeout_seconds=30)
    if inspected.returncode != 0:
        raise ValueError("running mutable Compose project inspection failed")
    try:
        containers = json.loads(inspected.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError("running mutable Compose project inspection is not JSON") from exc
    if not isinstance(containers, list):
        raise ValueError("running mutable Compose project inspection is invalid")

    actual_services: set[str] = set()
    expected_image_suffix = str(receipt["mutableStateDigest"]).removeprefix(
        "sha256:"
    )[:16]
    for container in containers:
        try:
            config = container["Config"]
            labels = config["Labels"]
            service = str(labels["com.docker.compose.service"])
            state = container["State"]
            image_ref = str(config["Image"])
            env_rows = config.get("Env") or []
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("running mutable container inspection is invalid") from exc
        if (
            labels.get("com.docker.compose.project") != project
            or labels.get("com.docker.compose.oneoff") == "True"
            or not str(labels.get("com.docker.compose.config-hash") or "")
            or service not in expected_services
            or service in actual_services
        ):
            raise ValueError(
                f"running mutable container is not bound to this attempt: {service}"
            )
        if service in completed_services:
            if state.get("Status") != "exited" or state.get("ExitCode") != 0:
                raise ValueError(
                    "running mutable completed service did not exit successfully: "
                    + service
                )
        else:
            state_issue = ""
            if state.get("Status") != "running" or state.get("Restarting") is True:
                state_issue = "not running"
            if service in health_checked_services:
                health = state.get("Health")
                if not isinstance(health, Mapping) or health.get("Status") != "healthy":
                    state_issue = "not healthy"
            if state_issue and service in required_running_services:
                raise ValueError(
                    f"running mutable required service is {state_issue}: {service}"
                )
            if state_issue:
                resume_warnings.append(
                    "running mutable non-critical service state warning: "
                    f"{service} status={state.get('Status') or 'missing'} "
                    f"exitCode={state.get('ExitCode', 'unknown')}"
                )
        actual_services.add(service)
        environment_values = {
            row.split("=", 1)[0]: row.split("=", 1)[1]
            for row in env_rows
            if isinstance(row, str) and "=" in row
        }
        required_keys = environment_keys.get(service, set())
        if "IMAGE_VERSION" in required_keys and environment_values.get(
            "IMAGE_VERSION"
        ) != receipt.get("mutableStateDigest"):
            raise ValueError(f"running mutable image identity drifted: {service}")
        for digest_key in (
            "PROVIDER_SUBSTITUTE_CONFIGURATION_DIGEST",
            "SMS_SUBSTITUTE_CONFIGURATION_DIGEST",
        ):
            if digest_key in required_keys and environment_values.get(
                digest_key
            ) != receipt.get("configurationDigest"):
                raise ValueError(
                    f"running mutable configuration identity drifted: {service}"
                )
        if (
            image_ref.startswith("quwoquan/")
            and not image_ref.startswith(
                _VERSION_PINNED_QUWOQUAN_INFRA_IMAGE_PREFIXES
            )
            and not (
                image_ref.endswith(":" + expected_image_suffix)
                or image_ref.endswith(
                    f":{environment}-test-live-{expected_image_suffix}"
                )
            )
        ):
            raise ValueError(f"running mutable image ref drifted: {service}")
    if actual_services != expected_services:
        raise ValueError("running mutable Compose service roster drifted")

    return (
        {
            "exitCode": 0,
            "blockerKind": "",
            "details": [],
            "phases": [
                {
                    "name": "mutable-runtime-resume",
                    "exitCode": 0,
                    "summary": "unchanged running test-live runtime reused",
                    "details": [f"attemptId={receipt['attemptId']}"],
                    "reportDir": _stackctl.relpath(run_root),
                }
            ],
            "runtime": runtime_plan,
            "runtimeRunRoot": str(run_root),
            "startupAttempt": receipt,
        },
        resume_warnings,
    )
