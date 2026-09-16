"""canonical App 执行期间的设备互斥与精确 runtime consumer lease。

不启动/停止共享栈，不安装 reverse，不签发 managed/promotable receipt。
"""

from __future__ import annotations

import contextlib
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


def _control_lock_manifest(*, control_ref: str, handoff: dict[str, object], device: str, device_kind: str):
    import build_launcher_handoff as control_contract
    from quwoquan_ops.cli.lib.package_reuse.input_capsule import verify_package_input_capsule
    from quwoquan_ops.cli.commands.app_preflight_uat_launch import verify_app_content_launch_projection

    # Supervisor 已创建 attempt；此处不重复 fresh-output 预检，仅复验现役控制和来源。
    if control_ref:
        control = control_contract._read_private_launch_control(
            Path(control_ref), Path(os.environ["QWQ_OUTPUT_ROOT"]).resolve())
        offline = control_contract._validate_launch_control_fields(control)
        control_contract._validate_launch_control_identity(
            control, os.environ.get("QWQ_CANONICAL_LAUNCH_CONTROL_DIGEST", ""))
        control_contract._validate_launch_control_digests(control, offline)
        control_contract._validate_launch_control_source_paths(
            control, ROOT, os.environ.get("QWQ_PACKAGE_SOURCE_CAPSULE_MANIFEST", ""))
        control_contract._validate_launch_control_projection_evidence(control)
        projection = verify_app_content_launch_projection(
            projection_root=ROOT, evidence_path=Path(control["sourceProjectionEvidenceRef"]),
            reject_unmanifested=False)
        for field in ("candidateDigest", "sourceRevision", "sourceCapsuleDigest", "sourceCapsuleManifestDigest",
                      "sourceCapsuleManifestRef", "sourceProjectionRoot"):
            if projection.get(field) != control.get(field):
                raise CanonicalExecutorError("APP.LAUNCH.identity_invalid: control/projection identity drifted")
        platform = {"android_emulator": "android", "android_physical": "android-physical"}.get(device_kind, device_kind)
        if any(control.get(key) != value for key, value in (
            ("environment", handoff.get("environment")), ("target", handoff.get("target")),
            ("deviceId", device), ("platform", platform),
        )):
            raise CanonicalExecutorError("APP.LAUNCH.identity_invalid: control/invocation identity drifted")
        manifest_ref = Path(control["sourceCapsuleManifestRef"])
        manifest = verify_package_input_capsule(manifest_ref.parent)
        if (manifest.get("sourceRevision") != control["sourceRevision"]
                or manifest.get("deploymentInputDigest") != control["sourceCapsuleDigest"]):
            raise CanonicalExecutorError("APP.LAUNCH.identity_invalid: control/capsule identity drifted")
        return manifest


def _workspace_lock_manifest(workspace_manifest: str):
    from quwoquan_ops.cli.lib.package_reuse.input_capsule import verify_package_input_capsule
    from quwoquan_ops.cli.commands.app_preflight_uat_launch import _projection_manifest_entries

    if workspace_manifest:
        # run.sh 已准备依赖/生成文件，复验 source CAS 而非要求投影仍是空白 source-only 树。
        manifest_ref = Path(workspace_manifest)
        output = Path(os.environ["QWQ_OUTPUT_ROOT"]).resolve()
        if (manifest_ref.is_symlink() or manifest_ref.name != "manifest.json"
                or not manifest_ref.resolve().is_relative_to(output) or not ROOT.is_relative_to(output)):
            raise CanonicalExecutorError("APP.LAUNCH.identity_invalid: workspace projection path is unsafe")
        manifest = verify_package_input_capsule(manifest_ref.parent)
        for entry in _projection_manifest_entries(manifest, capsule_root=manifest_ref.parent):
            path = ROOT / entry["repoRelative"]
            if path.parent.resolve() != path.parent:
                raise CanonicalExecutorError("APP.LAUNCH.identity_invalid: workspace source parent is linked")
            if entry["kind"] == "file":
                if (path.is_symlink() or not path.is_file() or path.read_bytes() != entry["content"]
                        or bool(path.stat().st_mode & 0o111) != bool(entry["projectionMode"] & 0o111)):
                    raise CanonicalExecutorError("APP.LAUNCH.identity_invalid: workspace source CAS drifted")
            elif (not path.is_symlink() or os.readlink(path).encode() != entry["content"]
                  or not path.resolve(strict=True).is_relative_to(ROOT)):
                raise CanonicalExecutorError("APP.LAUNCH.identity_invalid: workspace source link drifted")
        return manifest


def verified_lock_identity(*, handoff: dict[str, object], device: str, device_kind: str):
    """锁诊断只消费 worktree 或重新校验过的 immutable source，不信任裸 JSON。"""
    from quwoquan_ops.cli.lib.host_locks import HostLockOwner
    from quwoquan_ops.cli.lib.common import utc_now
    from quwoquan_ops.cli.lib.worktree_identity import resolve_worktree_identity

    control_ref = os.environ.get("QWQ_CANONICAL_LAUNCH_CONTROL", "")
    workspace_manifest = os.environ.get("QWQ_WORKSPACE_SOURCE_CAPSULE_MANIFEST", "")
    if control_ref:
        manifest = _control_lock_manifest(control_ref=control_ref, handoff=handoff, device=device, device_kind=device_kind)
    elif workspace_manifest:
        manifest = _workspace_lock_manifest(workspace_manifest)
    else:
        identity = resolve_worktree_identity(ROOT)
        if identity.worktree_root != str(ROOT):
            raise CanonicalExecutorError("APP.LAUNCH.identity_invalid: launcher root is not a worktree")
        return identity
    revision = str(manifest.get("sourceRevision") or "")
    if re.fullmatch(r"[0-9a-f]{40}", revision) is None:
        raise CanonicalExecutorError("APP.LAUNCH.identity_invalid: source revision is not exact")
    return HostLockOwner(pid=os.getpid(), worktree=str(ROOT), lane="immutable-source-projection",
                         head_sha=revision, started_at=utc_now())


@contextlib.contextmanager
def selected_device_lock(
    device: str, application_id: str, *, identity: object
) -> Iterator[None]:
    from quwoquan_ops.cli.lib.host_locks import (
        acquire_device_lock, HostLockBusyError,
    )
    try:
        with runtime_authority_environment():
            lock = acquire_device_lock(
                device=device, app=application_id, identity=identity
            )
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
        identity = verified_lock_identity(handoff=handoff, device=args.device, device_kind=args.device_kind)
        with selected_device_lock(args.device, args.application_id, identity=identity):
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
    except (OSError, RuntimeError, ValueError, KeyError, TypeError) as error:
        print(f"[canonical-executor] GATE_BLOCK: {error}", file=sys.stderr, flush=True)
        return 2
    finally:
        signal.signal(signal.SIGTERM, previous_handler)
