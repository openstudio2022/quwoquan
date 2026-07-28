"""stackctl matrix --profile local-env-gate：串行四环境 + L0 编排。"""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

from quwoquan_ops.cli.lib.local_env_gate_timing import (
    PhaseTimer,
    load_local_env_matrix_budgets,
    utc_now,
    write_timing_bundle,
)
from quwoquan_ops.cli.lib.local_postgres_migration_drift import (
    format_drift_gate_block,
    probe_migration_drift,
    wipe_local_postgres_volumes,
)
from quwoquan_ops.cli.lib.output_paths import output_root


ROOT = Path(__file__).resolve().parents[3]
PROFILE_LOCAL_ENV_GATE = "local-env-gate"

EnvRunner = Callable[..., dict[str, Any]]


def _repo_matrix_dir() -> Path:
    path = output_root() / "env" / "repo" / "runs" / "local-env-gate"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _docker_image_present(image: str) -> bool:
    result = subprocess.run(
        ["docker", "image", "inspect", image],
        text=True,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def _package_bound_image_ref(service: str, *, env_name: str = "gamma") -> str:
    """Match stackctl `_packaged_service_source_image_ref` tag convention."""
    from quwoquan_ops.cli.lib.output_paths import service_deployment_package_dir

    report_path = service_deployment_package_dir(env_name, service) / "provenance.json"
    if not report_path.is_file():
        return ""
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
        source_digest = str(report["digests"]["sourceTree"])
    except (OSError, json.JSONDecodeError, KeyError, TypeError):
        return ""
    if not source_digest.startswith("sha256:") or len(source_digest) < 19:
        return ""
    repository = service.replace("-", "_")
    return f"localhost/quwoquan_service_{repository}:{source_digest[7:19]}"

def gamma_images_warm() -> bool:
    """True only when package-bound digest tags exist (not merely :latest)."""
    required_services = (
        "content-service",
        "user-service",
        "recommendation-service",
    )
    for service in required_services:
        image = _package_bound_image_ref(service, env_name="gamma")
        if not image or not _docker_image_present(image):
            return False
    return True


def beta_images_warm() -> bool:
    image = _package_bound_image_ref("content-service", env_name="beta")
    if image:
        return _docker_image_present(image)
    return _docker_image_present(
        "localhost/quwoquan_service_content_service:latest"
    ) or _docker_image_present("localhost/quwoquan_service_content-service:latest")
def _host_listener_pids(port: int) -> list[str]:
    """Return host PIDs listening on port, excluding docker-proxy / Colima plumbing."""
    listed = subprocess.run(
        ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN"],
        text=True,
        capture_output=True,
        check=False,
    )
    pids: list[str] = []
    for line in listed.stdout.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 2:
            continue
        command = parts[0].lower()
        pid = parts[1]
        # Only reclaim host-managed runtimes (Python/go/caddy). Never touch Colima
        # ssh forwards, docker-proxy, or lima helpers — killing those bricks the sock.
        if command not in {"python", "python3", "go", "caddy"}:
            continue
        pids.append(pid)
    return sorted(set(pids))

def _force_release_target_ports(target_name: str) -> list[str]:
    """Kill leftover host listeners that keep localResourceGroup exclusive locks."""
    from urllib.parse import urlparse

    from quwoquan_ops.cli.lib.environment_topology import (
        get_target,
        load_environment_topology,
    )

    details: list[str] = []
    try:
        target = get_target(load_environment_topology(), target_name)
    except Exception as exc:  # noqa: BLE001 - cleanup best-effort
        return [f"topology lookup failed: {exc}"]
    origins = target.get("origins") or {}
    if not isinstance(origins, dict):
        return details
    for key, raw_url in origins.items():
        parsed = urlparse(str(raw_url or ""))
        if parsed.hostname not in {"127.0.0.1", "localhost"} or parsed.port is None:
            continue
        port = int(parsed.port)
        pids = _host_listener_pids(port)
        if not pids:
            continue
        subprocess.run(["kill", "-TERM", *pids], check=False, capture_output=True)
        time.sleep(0.4)
        remain = _host_listener_pids(port)
        if remain:
            subprocess.run(["kill", "-KILL", *remain], check=False, capture_output=True)
        details.append(f"released {key} port {port} hostPids={','.join(pids)}")
    return details

def _clear_stale_operation_lock() -> list[str]:
    """Remove operation lock only when holder is dead or is a nested stackctl up."""
    from quwoquan_ops.cli.lib.output_paths import repo_local_dir

    details: list[str] = []
    lock_path = repo_local_dir("local-runtime") / "process" / ".stackctl-operation.lock"
    if not lock_path.is_file():
        return details
    text = lock_path.read_text(encoding="utf-8").strip()
    pid = 0
    for part in text.replace("\n", " ").split():
        if part.startswith("pid="):
            try:
                pid = int(part.split("=", 1)[1])
            except ValueError:
                pid = 0
    if pid <= 0:
        lock_path.unlink(missing_ok=True)
        return [f"cleared malformed operation lock {lock_path}"]
    alive = subprocess.run(
        ["kill", "-0", str(pid)],
        check=False,
        capture_output=True,
    )
    if alive.returncode != 0:
        lock_path.unlink(missing_ok=True)
        return [f"removed dead operation lock pid={pid}"]
    # Only terminate nested stackctl up/down leftovers; never touch unrelated holders.
    cmdline = subprocess.run(
        ["ps", "-p", str(pid), "-o", "command="],
        text=True,
        capture_output=True,
        check=False,
    ).stdout.strip()
    if "stackctl.py" in cmdline and (
        " up " in f" {cmdline} " or cmdline.rstrip().endswith(" up")
    ):
        subprocess.run(["kill", "-TERM", str(pid)], check=False, capture_output=True)
        time.sleep(0.3)
        subprocess.run(["kill", "-KILL", str(pid)], check=False, capture_output=True)
        lock_path.unlink(missing_ok=True)
        details.append(f"terminated nested stackctl up pid={pid}")
        return details
    details.append(f"operation lock held by live pid={pid}; left intact")
    return details


def force_cleanup_target(target_name: str, *, down_fn: EnvRunner) -> dict[str, Any]:
    lock_details = _clear_stale_operation_lock()
    payload = down_fn(
        _namespace(
            command="down",
            target=target_name,
            output_format="json",
            report_dir="",
        )
    )
    # Consumer leases protect a live app session independently from the short
    # operation lock. A matrix cleanup must preserve that hard boundary: it may
    # neither retry around the gate nor reclaim the leased target's host ports.
    if payload.get("reason") == "active_consumer_lease":
        if lock_details:
            details = list(payload.get("details") or [])
            details.extend(lock_details)
            payload["details"] = details
        return payload
    # down may be GATE_BLOCK while a nested verify/up still holds the lock.
    if int(payload.get("exitCode") or 0) != 0:
        lock_details.extend(_clear_stale_operation_lock())
        if int(payload.get("exitCode") or 0) != 0:
            # Retry down only after clearing a nested stackctl holder.
            payload = down_fn(
                _namespace(
                    command="down",
                    target=target_name,
                    output_format="json",
                    report_dir="",
                )
            )
            if payload.get("reason") == "active_consumer_lease":
                if lock_details:
                    details = list(payload.get("details") or [])
                    details.extend(lock_details)
                    payload["details"] = details
                return payload
    # Host listeners only (never docker-proxy). Safe for exclusive port reclaim.
    released = _force_release_target_ports(target_name)
    if lock_details or released:
        details = list(payload.get("details") or [])
        details.extend([*lock_details, *released])
        payload["details"] = details
    return payload
def _namespace(**kwargs: Any) -> Any:
    import argparse

    return argparse.Namespace(**kwargs)


def _run_commit_gate() -> dict[str, Any]:
    started = time.monotonic()
    result = subprocess.run(
        ["make", "commit-gate"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    summary_path = ROOT / ".qwq_output" / "env" / "repo" / "runs" / "commit-gate" / "summary.json"
    summary: dict[str, Any] = {}
    if summary_path.exists():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    return {
        "exitCode": result.returncode,
        "durationMs": int((time.monotonic() - started) * 1000),
        "summary": summary,
        "stdout": result.stdout[-2000:],
        "stderr": result.stderr[-2000:],
        "reportDir": str(summary_path.parent.relative_to(ROOT))
        if summary_path.exists()
        else "",
    }


def _docker_daemon_ready() -> tuple[bool, str]:
    result = subprocess.run(
        ["docker", "info"],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode == 0:
        return True, "docker daemon ready"
    detail = (result.stderr or result.stdout or "docker info failed").strip()
    return False, detail[:300]


def run_local_env_gate_matrix(
    *,
    package_fn: EnvRunner,
    up_fn: EnvRunner,
    health_fn: EnvRunner,
    verify_fn: EnvRunner,
    down_fn: EnvRunner,
    include_l0: bool = True,
    cache_mode: str = "auto",
    auto_wipe_drift: bool = True,
) -> dict[str, Any]:
    """串行：L0 → alpha → beta → gamma → prod(package/purity/release)。"""
    budgets = load_local_env_matrix_budgets()
    matrix_dir = _repo_matrix_dir()
    wall_started = time.monotonic()
    phases: list[dict[str, Any]] = []
    env_results: dict[str, Any] = {}
    hard = int(budgets["hardBudgetSeconds"])
    claim = "LOCAL_ENV_GATE_GREEN"
    overall_exit = 0
    failure_category = ""

    resolved_cache = cache_mode
    if cache_mode == "auto":
        resolved_cache = "warm" if gamma_images_warm() and beta_images_warm() else "cold"

    docker_timer = PhaseTimer("docker_daemon_preflight")
    docker_ok, docker_detail = _docker_daemon_ready()
    phases.append(
        docker_timer.finish(
            status="ok" if docker_ok else "failed",
            details=[docker_detail],
        )
    )
    if not docker_ok:
        overall_exit = 2
        failure_category = "docker"
        claim = "LOCAL_ENV_GATE_DOCKER_UNAVAILABLE"
        wall = time.monotonic() - wall_started
        timing_path = write_timing_bundle(
            matrix_dir,
            phases=phases,
            wall_clock_seconds=wall,
            budgets=budgets,
            claim=claim,
            cache_mode=resolved_cache,
            extras={"failureCategory": failure_category},
        )
        (matrix_dir / "matrix.json").write_text(
            json.dumps(
                {
                    "schema": "local-env-gate-matrix",
                    "generatedAt": utc_now(),
                    "claim": claim,
                    "cacheMode": resolved_cache,
                    "wallClockSeconds": round(wall, 3),
                    "softBudgetSeconds": budgets["softBudgetSeconds"],
                    "hardBudgetSeconds": budgets["hardBudgetSeconds"],
                    "failureCategory": failure_category,
                    "timingPath": str(timing_path.relative_to(ROOT)),
                    "phases": phases,
                    "prod_hosted_deploy": "NOT_RUN",
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return {
            "exitCode": overall_exit,
            "summary": f"stackctl matrix {PROFILE_LOCAL_ENV_GATE} {claim}",
            "details": [docker_detail, f"timing={timing_path.relative_to(ROOT)}"],
            "reportDir": str(matrix_dir.relative_to(ROOT)),
            "claim": claim,
            "wallClockSeconds": round(wall, 3),
        }

    def _budget_exhausted() -> bool:
        return (time.monotonic() - wall_started) > hard

    if include_l0:
        timer = PhaseTimer("L0_commit_gate")
        if _budget_exhausted():
            phases.append(timer.finish(status="skipped", details=["hard budget exhausted"]))
            overall_exit = 2
            failure_category = "budget"
            claim = "LOCAL_ENV_GATE_BUDGET_EXCEEDED"
        else:
            l0 = _run_commit_gate()
            status = "ok" if l0["exitCode"] == 0 else "failed"
            phases.append(
                timer.finish(
                    status=status,
                    details=[f"exit={l0['exitCode']}"],
                    report_dir=l0.get("reportDir", ""),
                )
            )
            env_results["L0"] = l0
            if l0["exitCode"] != 0:
                overall_exit = l0["exitCode"]
                failure_category = "l0"
                claim = "LOCAL_ENV_GATE_L0_FAILED"

    env_plan = (
        (
            "alpha",
            "alpha-local",
            "content-release",
            "smoke",
            True,
        ),
        (
            "beta",
            "beta-local",
            "content-release",
            "integration",
            True,
        ),
        (
            "gamma",
            "gamma-local",
            "full",
            "integration",
            True,
        ),
        (
            "prod",
            "prod-hosted",
            "",
            "release",
            False,
        ),
    )

    for env_name, target_name, workload, profile, do_up in env_plan:
        if overall_exit != 0 and failure_category in {"l0", "budget", "docker"}:
            break
        if _budget_exhausted():
            phases.append(
                PhaseTimer(f"{env_name}_skipped").finish(
                    status="skipped",
                    details=["hard budget exhausted before environment"],
                )
            )
            overall_exit = 2
            failure_category = "budget"
            claim = "LOCAL_ENV_GATE_BUDGET_EXCEEDED"
            break
        docker_ok, docker_detail = _docker_daemon_ready()
        if not docker_ok:
            phases.append(
                PhaseTimer(f"{env_name}_docker_preflight").finish(
                    status="failed",
                    details=[docker_detail],
                )
            )
            overall_exit = 2
            failure_category = "docker"
            claim = "LOCAL_ENV_GATE_DOCKER_UNAVAILABLE"
            break

        env_block: dict[str, Any] = {"target": target_name, "profile": profile}
        # Exclusive switch: down other local runtimes first.
        if do_up:
            lock_clear = _clear_stale_operation_lock()
            if lock_clear:
                phases.append(
                    PhaseTimer(f"{env_name}_clear_operation_lock").finish(
                        status="ok",
                        details=lock_clear,
                    )
                )
            for other in ("alpha-local", "beta-local", "gamma-local"):
                if other == target_name:
                    continue
                switch_timer = PhaseTimer(f"{env_name}_down_{other}")
                down_payload = force_cleanup_target(other, down_fn=down_fn)
                phases.append(
                    switch_timer.finish(
                        status="ok" if down_payload.get("exitCode", 1) == 0 else "warn",
                        details=[down_payload.get("summary", "")]
                        + list(down_payload.get("details") or [])[:3],
                        report_dir=str(down_payload.get("reportDir") or ""),
                    )
                )
            # Also ensure the target itself is not mid-up from a previous aborted matrix.
            self_clean = force_cleanup_target(target_name, down_fn=down_fn)
            phases.append(
                PhaseTimer(f"{env_name}_pre_up_self_down").finish(
                    status="ok" if self_clean.get("exitCode", 1) == 0 else "warn",
                    details=[self_clean.get("summary", "")]
                    + list(self_clean.get("details") or [])[:3],
                    report_dir=str(self_clean.get("reportDir") or ""),
                )
            )

        # Package
        pkg_timer = PhaseTimer(f"{env_name}_package")
        package_payload = package_fn(
            _namespace(
                command="package",
                kind="runtime",
                env=env_name,
                service="",
                include_services=True,
                target=target_name,
                output_format="json",
                report_dir="",
                apk_path="",
                verify_remote_apk=False,
            )
        )
        phases.append(
            pkg_timer.finish(
                status="ok" if package_payload.get("exitCode") == 0 else "failed",
                details=list(package_payload.get("details") or [])[:5],
                report_dir=str(package_payload.get("reportDir") or ""),
            )
        )
        env_block["package"] = package_payload
        if package_payload.get("exitCode") != 0:
            overall_exit = int(package_payload.get("exitCode") or 1)
            failure_category = "package"
            claim = "LOCAL_ENV_GATE_PACKAGE_FAILED"
            env_results[env_name] = env_block
            break

        if env_name == "prod":
            purity = subprocess.run(
                ["python3", "quwoquan_app/scripts/env/verify_prod_package_purity.py"],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            purity_timer = PhaseTimer("prod_package_purity")
            phases.append(
                purity_timer.finish(
                    status="ok" if purity.returncode == 0 else "failed",
                    details=[(purity.stdout or purity.stderr or "")[:200]],
                )
            )
            env_block["purityExitCode"] = purity.returncode
            if purity.returncode != 0:
                overall_exit = purity.returncode
                failure_category = "purity"
                claim = "LOCAL_ENV_GATE_PURITY_FAILED"
                env_results[env_name] = env_block
                break

        if do_up:
            # Drift probe + optional wipe
            if target_name in {"alpha-local", "beta-local"}:
                drift_timer = PhaseTimer(f"{env_name}_migration_drift_probe")
                # Ensure postgres exists briefly? Probe may be unavailable before first up.
                # We probe after a quick compose-less check: if container exists.
                drift = probe_migration_drift(target_name)
                wiped = False
                if drift.has_drift and auto_wipe_drift:
                    ok, wipe_detail = wipe_local_postgres_volumes(target_name)
                    wiped = ok
                    phases.append(
                        drift_timer.finish(
                            status="wiped" if ok else "failed",
                            details=[format_drift_gate_block(drift), wipe_detail],
                        )
                    )
                    if not ok:
                        overall_exit = 2
                        failure_category = "drift"
                        claim = "LOCAL_ENV_GATE_DRIFT_WIPE_FAILED"
                        env_results[env_name] = env_block
                        break
                else:
                    phases.append(
                        drift_timer.finish(
                            status=drift.status,
                            details=[drift.detail],
                        )
                    )

            # Decide skip-build AFTER package so digest tags match current provenance.
            skip_build = resolved_cache == "warm"
            if target_name == "gamma-local":
                skip_build = resolved_cache == "warm" and gamma_images_warm()
            elif target_name == "beta-local":
                skip_build = resolved_cache == "warm" and beta_images_warm()
            elif target_name == "alpha-local":
                skip_build = True  # alpha only builds when image missing

            up_env = os.environ.copy()
            if target_name == "gamma-local" and resolved_cache == "warm":
                up_env["LOCAL_GAMMA_REUSE_DATA_PLANE"] = "1"
                up_env["LOCAL_GAMMA_SKIP_GATE"] = "1"

            up_timer = PhaseTimer(f"{env_name}_up")
            # Inject env for child processes via os.environ temporarily.
            previous_env = {
                key: os.environ.get(key)
                for key in ("LOCAL_GAMMA_REUSE_DATA_PLANE", "LOCAL_GAMMA_SKIP_GATE")
            }

            def _invoke_up(*, skip_build_flag: bool) -> dict[str, Any]:
                try:
                    if target_name == "gamma-local":
                        os.environ["LOCAL_GAMMA_REUSE_DATA_PLANE"] = up_env.get(
                            "LOCAL_GAMMA_REUSE_DATA_PLANE", ""
                        )
                        os.environ["LOCAL_GAMMA_SKIP_GATE"] = "1"
                    return up_fn(
                        _namespace(
                            command="up",
                            env=env_name,
                            target="",
                            workload=workload,
                            skip_app=True,
                            skip_build=skip_build_flag,
                            build_only=False,
                            build_services="",
                            device_id="",
                            output_format="json",
                            report_dir="",
                        )
                    )
                finally:
                    for key, value in previous_env.items():
                        if value is None:
                            os.environ.pop(key, None)
                        else:
                            os.environ[key] = value

            up_payload = _invoke_up(skip_build_flag=skip_build)

            # Digest tag missing under --skip-build: rebuild once then continue warm path.
            if (
                up_payload.get("exitCode") != 0
                and skip_build
                and target_name == "gamma-local"
            ):
                detail_text = " ".join(up_payload.get("details") or [])
                if "packaged image is unavailable" in detail_text:
                    phases.append(
                        PhaseTimer(f"{env_name}_skip_build_miss_rebuild").finish(
                            status="rebuild",
                            details=["package-bound digest image missing; rebuild once"],
                        )
                    )
                    skip_build = False
                    up_payload = _invoke_up(skip_build_flag=False)

            # One retry after wipe if up failed and we haven't wiped yet for drift.
            if (
                up_payload.get("exitCode") != 0
                and target_name in {"alpha-local", "beta-local"}
                and auto_wipe_drift
            ):
                stderr = " ".join(up_payload.get("details") or [])
                if "checksum drift" in stderr or "migration checksum" in stderr:
                    wipe_ok, wipe_detail = wipe_local_postgres_volumes(target_name)
                    phases.append(
                        PhaseTimer(f"{env_name}_drift_retry_wipe").finish(
                            status="ok" if wipe_ok else "failed",
                            details=[wipe_detail],
                        )
                    )
                    if wipe_ok:
                        up_payload = _invoke_up(skip_build_flag=skip_build)

            phases.append(
                up_timer.finish(
                    status="ok" if up_payload.get("exitCode") == 0 else "failed",
                    details=list(up_payload.get("details") or [])[:8],
                    report_dir=str(up_payload.get("reportDir") or ""),
                )
            )
            env_block["up"] = up_payload
            env_block["skipBuild"] = skip_build
            if up_payload.get("exitCode") != 0:
                overall_exit = int(up_payload.get("exitCode") or 1)
                failure_category = "up"
                claim = "LOCAL_ENV_GATE_UP_FAILED"
                env_results[env_name] = env_block
                break
            if target_name == "gamma-local":
                os.environ["STACKCTL_GAMMA_VERIFY_SKIP_SEED"] = "1"

            health_timer = PhaseTimer(f"{env_name}_health")
            health_payload = health_fn(
                _namespace(
                    command="health",
                    target=target_name,
                    output_format="json",
                    report_dir="",
                    request_timeout_seconds=0,
                    retry_attempts=0,
                    retry_sleep_seconds=-1.0,
                )
            )
            phases.append(
                health_timer.finish(
                    status="ok" if health_payload.get("exitCode") == 0 else "failed",
                    details=list(health_payload.get("details") or [])[:8],
                    report_dir=str(health_payload.get("reportDir") or ""),
                )
            )
            env_block["health"] = health_payload
            if health_payload.get("exitCode") != 0:
                overall_exit = int(health_payload.get("exitCode") or 1)
                failure_category = "health"
                claim = "LOCAL_ENV_GATE_HEALTH_FAILED"
                env_results[env_name] = env_block
                break

        verify_timer = PhaseTimer(f"{env_name}_verify_{profile}")
        verify_kwargs = dict(
            command="verify",
            kind="all",
            env=env_name,
            target=target_name,
            profile=profile,
            service="",
            output_format="json",
            report_dir="",
            reuse_package=True,
            backup_recovery_receipt="",
        )
        previous_skip_nested = os.environ.get("STACKCTL_SKIP_NESTED_UP")
        if do_up:
            # health already passed; forbid nested up that can steal the operation lock.
            os.environ["STACKCTL_SKIP_NESTED_UP"] = "1"
        try:
            verify_payload = verify_fn(_namespace(**verify_kwargs))
        finally:
            if previous_skip_nested is None:
                os.environ.pop("STACKCTL_SKIP_NESTED_UP", None)
            else:
                os.environ["STACKCTL_SKIP_NESTED_UP"] = previous_skip_nested
        # Prod release GATE_BLOCK for provider is expected / honest.
        verify_exit = int(verify_payload.get("exitCode") or 0)
        verify_status = "ok"
        if env_name == "prod" and verify_exit == 2:
            verify_status = "release_provider_gate_block"
            env_block["release"] = "RELEASE_PROVIDER_GATE_BLOCK"
            env_block["packagePurity"] = "PACKAGE_PURITY_PASS"
        elif verify_exit != 0:
            verify_status = "failed"
            overall_exit = verify_exit
            failure_category = "verify"
            claim = "LOCAL_ENV_GATE_VERIFY_FAILED"
        phases.append(
            verify_timer.finish(
                status=verify_status,
                details=list(verify_payload.get("details") or [])[:8],
                report_dir=str(verify_payload.get("reportDir") or ""),
            )
        )
        env_block["verify"] = verify_payload

        if do_up:
            down_timer = PhaseTimer(f"{env_name}_down")
            down_payload = force_cleanup_target(target_name, down_fn=down_fn)
            phases.append(
                down_timer.finish(
                    status="ok" if down_payload.get("exitCode", 1) == 0 else "warn",
                    details=[down_payload.get("summary", "")],
                    report_dir=str(down_payload.get("reportDir") or ""),
                )
            )
            env_block["down"] = down_payload

        env_results[env_name] = env_block
        if overall_exit != 0 and failure_category == "verify" and env_name != "prod":
            break

    wall = time.monotonic() - wall_started
    if overall_exit == 0:
        claim = "LOCAL_ENV_GATE_GREEN"
    if wall > hard and claim == "LOCAL_ENV_GATE_GREEN":
        claim = "LOCAL_ENV_GATE_GREEN_OVER_HARD"
        overall_exit = 2
        failure_category = "budget"

    timing_path = write_timing_bundle(
        matrix_dir,
        phases=phases,
        wall_clock_seconds=wall,
        budgets=budgets,
        claim=claim,
        cache_mode=resolved_cache,
        extras={
            "failureCategory": failure_category,
            "environments": {
                name: {
                    "packageReport": (block.get("package") or {}).get("reportDir"),
                    "upReport": (block.get("up") or {}).get("reportDir"),
                    "verifyReport": (block.get("verify") or {}).get("reportDir"),
                    "release": block.get("release"),
                    "skipBuild": block.get("skipBuild"),
                }
                for name, block in env_results.items()
                if isinstance(block, dict)
            },
        },
    )

    matrix_payload = {
        "schema": "local-env-gate-matrix",
        "generatedAt": utc_now(),
        "claim": claim,
        "cacheMode": resolved_cache,
        "wallClockSeconds": round(wall, 3),
        "softBudgetSeconds": budgets["softBudgetSeconds"],
        "hardBudgetSeconds": budgets["hardBudgetSeconds"],
        "failureCategory": failure_category,
        "timingPath": str(timing_path.relative_to(ROOT)),
        "phases": phases,
        "prod_hosted_deploy": "NOT_RUN",
    }
    (matrix_dir / "matrix.json").write_text(
        json.dumps(matrix_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (matrix_dir / "matrix.md").write_text(
        "\n".join(
            [
                "# local-env-gate matrix",
                "",
                f"- claim: `{claim}`",
                f"- cacheMode: `{resolved_cache}`",
                f"- wallClockSeconds: `{round(wall, 3)}`",
                f"- soft/hard: `{budgets['softBudgetSeconds']}/{budgets['hardBudgetSeconds']}`",
                f"- timing: `{timing_path.relative_to(ROOT)}`",
                f"- failureCategory: `{failure_category or 'none'}`",
                "",
            ]
        ),
        encoding="utf-8",
    )

    return {
        "exitCode": overall_exit,
        "summary": (
            f"stackctl matrix {PROFILE_LOCAL_ENV_GATE} {claim} "
            f"in {round(wall, 1)}s (soft={budgets['softBudgetSeconds']} "
            f"hard={budgets['hardBudgetSeconds']})"
        ),
        "details": [
            f"claim={claim}",
            f"cacheMode={resolved_cache}",
            f"timing={timing_path.relative_to(ROOT)}",
            f"failureCategory={failure_category or 'none'}",
        ],
        "reportDir": str(matrix_dir.relative_to(ROOT)),
        "claim": claim,
        "wallClockSeconds": round(wall, 3),
    }
