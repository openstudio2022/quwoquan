"""canonical App 执行期间的设备互斥与精确 runtime consumer lease。

不启动/停止共享栈，不安装 reverse，不签发 managed/promotable receipt。
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import signal
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import urlparse

from .arguments import CanonicalExecutorError, build_parser
from .launch_io import load_handoff

ROOT = Path(__file__).resolve().parents[4]
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")


@contextlib.contextmanager
def runtime_authority_environment() -> Iterator[None]:
    """Hermetic 的证据/依赖 HOME 不得重定向宿主 runtime authority。"""
    host_home = os.environ.get("QWQ_LAUNCH_HOST_HOME")
    previous = dict(os.environ)
    try:
        if host_home:
            os.environ["HOME"] = host_home
            os.environ["QWQ_OUTPUT_ROOT"] = str(
                Path(host_home) / ".cache/quwoquan/runtime-output"
            )
        yield
    finally:
        os.environ.clear()
        os.environ.update(previous)


def running_generation(target: str) -> str:
    """仅只读 canonical mutable/immutable receipt；acquire 会持锁重新判定。"""
    from quwoquan_ops.cli.lib.startup_attempt_receipt import load_startup_attempt
    from quwoquan_ops.cli.lib.test_live_startup_attempt_receipt import (
        load_test_live_startup_attempt,
    )

    if target not in {"alpha-local", "beta-local", "gamma-local"}:
        raise CanonicalExecutorError("OPS.LEASE.runtime_identity_unavailable: unsupported target")
    try:
        attempts = [load_startup_attempt(target), load_test_live_startup_attempt(target)]
        active = [item for item in attempts if item and item.get("status") != "stopped"]
        if len(active) != 1 or active[0].get("status") != "running":
            raise ValueError("exactly one running mutable or immutable receipt is required")
        receipt = active[0]
        generation = receipt.get("attemptId")
        if (receipt.get("target") != target or not isinstance(generation, str)
                or not generation or generation != generation.strip()
                or any(char in generation for char in "\x00\n\r/\\")):
            raise ValueError("selected target/startupAttemptId identity is invalid")
        return generation
    except (OSError, ValueError) as error:
        raise CanonicalExecutorError(
            f"OPS.LEASE.runtime_identity_unavailable: {error}"
        ) from error


def public_android_ports(target: str) -> list[int]:
    from quwoquan_ops.cli.lib.environment_topology import get_target, load_environment_topology

    resolved = get_target(load_environment_topology(), target)
    if resolved.get("backend") != "local":
        raise CanonicalExecutorError("APP.LAUNCH.transport_unavailable: target is not local")
    bases = resolved.get("publicBases")
    if not isinstance(bases, dict) or not bases:
        raise CanonicalExecutorError("APP.LAUNCH.transport_unavailable: public bases missing")
    ports = set()
    for base in bases.values():
        parsed = urlparse(base)
        if parsed.scheme not in {"https", "wss"} or not parsed.hostname or not parsed.port:
            raise CanonicalExecutorError("APP.LAUNCH.transport_unavailable: public base is invalid")
        ports.add(parsed.port)
    return sorted(ports)


def require_prepared_android_reverse(device: str, ports: list[int]) -> None:
    result = subprocess.run(
        ["adb", "-s", device, "reverse", "--list"],
        capture_output=True, text=True, check=False, timeout=10,
    )
    # 两端必须相同；tcp:public -> tcp:other 并不构成已准备的映射。
    mappings = {
        (int(local), int(remote))
        for local, remote in re.findall(r"\btcp:(\d+)\s+tcp:(\d+)\b", result.stdout)
    }
    if result.returncode != 0 or not ports or any((port, port) not in mappings for port in ports):
        raise CanonicalExecutorError(
            "APP.LAUNCH.transport_unavailable: selected device public reverse mappings must already be prepared"
        )


def consumer_action(action: str, **values: object) -> dict[str, object]:
    """复用 stackctl 同一 action：其 acquire 在 use lock 内重读 generation。"""
    from quwoquan_ops.cli import stackctl
    from quwoquan_ops.cli.lib.host_locks import require_canonical_runtime_authority

    with runtime_authority_environment():
        require_canonical_runtime_authority()
        command = ["consumer-lease", action]
        for key, value in values.items():
            command.extend(["--" + key.replace("_", "-"), str(value)])
        args = stackctl.build_parser().parse_args(command)
        payload = stackctl.command_consumer_lease(args)
    if payload.get("exitCode") != 0:
        raise CanonicalExecutorError(
            "OPS.LEASE.action_blocked: " + "; ".join(str(item) for item in payload.get("details", []))
        )
    return payload


@contextlib.contextmanager
def direct_runtime_lease(*, target: str, device: str, application_id: str,
                         device_kind: str, handoff_digest: str) -> Iterator[None]:
    with runtime_authority_environment():
        generation = running_generation(target)
    ports = public_android_ports(target) if device_kind.startswith("android") else []
    if ports:
        require_prepared_android_reverse(device, ports)
    # consumer 标识只标识前台进程；runtime generation 严禁从 PID 推断。
    identity = dict(target=target, device=device, consumer=f"flutter-direct-{os.getpid()}",
                    instance_generation=generation)
    platform = "android" if device_kind.startswith("android") else device_kind
    payload = consumer_action(
        "acquire", **identity, platform=platform, package_name=application_id,
        bundle_id=application_id, ports=",".join(map(str, ports)),
    )
    lease = payload.get("lease")
    if not isinstance(lease, dict) or not isinstance(lease.get("leaseId"), str) or not _DIGEST.fullmatch(lease["leaseId"]):
        raise CanonicalExecutorError("OPS.LEASE.receipt_invalid: acquired leaseId missing; reconcile required")
    exact = {**identity, "lease_id": lease["leaseId"]}
    try:
        if any(lease.get(key) != value for key, value in (
            ("target", target), ("device", device), ("consumer", identity["consumer"]),
            ("instanceGeneration", generation), ("packageName", application_id),
        )):
            raise CanonicalExecutorError("OPS.LEASE.receipt_invalid: acquired identity drifted")
        consumer_action("bind", **exact, handoff_digest=handoff_digest)
        yield
    finally:
        consumer_action("release", **exact)


@contextlib.contextmanager
def selected_device_lock(device: str, application_id: str) -> Iterator[None]:
    from quwoquan_ops.cli.lib.host_locks import acquire_device_lock, HostLockBusyError

    try:
        # git identity 只用作 holder 诊断；设备锁的路径不含环境，跨环境同设备互斥。
        with runtime_authority_environment():
            lock = acquire_device_lock(device=device, app=application_id)
    except HostLockBusyError as error:
        raise CanonicalExecutorError(f"APP.LAUNCH.device_in_use: {error}") from error
    with lock:
        yield


def _terminate(_signum: int, _frame: object) -> None:
    raise KeyboardInterrupt


def run_canonical(*, acquire_runtime: bool = True) -> int:
    """不新增 launcher：共用原参数、handoff 和 run_app_instance.main()。"""
    import run_app_instance
    from quwoquan_ops.cli.lib.app_launch_manifest_contract import load_launch_manifest_contract

    previous_handler = signal.signal(signal.SIGTERM, _terminate)
    try:
        args = build_parser().parse_args()
        handoff = load_handoff(args.handoff_file)
        environment, target = handoff.get("environment"), handoff.get("target")
        contract = load_launch_manifest_contract()
        if contract["target_environment"].get(target) != environment:
            raise CanonicalExecutorError("APP.LAUNCH.identity_invalid: handoff target/environment mismatch")
        source = contract["content_source_policy"].get(environment)
        if source not in {"remote", "bundled_snapshot"}:
            raise CanonicalExecutorError("APP.LAUNCH.identity_invalid: content source policy missing")
        with selected_device_lock(args.device, args.application_id):
            lease = (
                direct_runtime_lease(
                    target=str(target), device=args.device, application_id=args.application_id,
                    device_kind=args.device_kind,
                    handoff_digest=str(handoff.get("effectiveLaunchManifestDigest") or ""),
                ) if acquire_runtime and source == "remote" else contextlib.nullcontext()
            )
            with lease:
                return run_app_instance.main()
    except KeyboardInterrupt:
        return 130
    except (OSError, RuntimeError, ValueError) as error:
        print(f"[canonical-executor] GATE_BLOCK: {error}", file=sys.stderr, flush=True)
        return 2
    finally:
        signal.signal(signal.SIGTERM, previous_handler)
