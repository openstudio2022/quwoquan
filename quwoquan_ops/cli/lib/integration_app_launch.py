"""integrate Alpha 准入的 App 启动与内容 readback 证据（`alpha.app-launch` 阶段）。

"服务健康"不等于"App 能起来、首页与视频书有内容"。当 candidate 的影响面含 `app` 时，
Alpha 环境在 health 之后必须：

1. 在一台 iOS 模拟器上以 canonical launcher（`quwoquan_app/run.sh --env alpha`）真实
   编译、安装、激活并启动 App，观察到 `QWQ_APP_LAUNCH_PHASE status=launched` 与
   `ios_startup_safe_terminal surface=router_shell … configurationState=complete`；
2. 对同一 Alpha 网关做推荐频道、视频书精品频道及普通视频浏览的 Remote readback，
   HTTP 200、规范 content envelope、Post items 非空且内容身份一致。

两者各形成一份 raw `ReadinessCaseResult`，进入 Alpha `EnvironmentAcceptanceFact` 的
`caseResultRefs`；任一失败即 typed blocker，不得降级为 PASS。没有可用模拟器同样阻断。
本模块只编排与观察，不解释业务结论；HTTP 与 TLS 只复用 content-api-consumer 的同一实现。
"""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.content_api_consumer import (  # noqa: E402
    ContentApiConsumerError,
    _default_http_request,
)
from quwoquan_ops.cli.lib.content_api_consumer_authority import (  # noqa: E402
    _tls_ca_file,
    _topology_api_base,
)

APP_LAUNCH_SPEC_REF = (
    "specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#req-003"
)
CONTENT_READBACK_SPEC_REF = (
    "specs/feature-tree/runtime/development-workflow-governance/local-continuous-integration/spec.md#req-004"
)
LAUNCHED_MARKER = "QWQ_APP_LAUNCH_PHASE status=launched"
SAFE_TERMINAL_MARKER = "ios_startup_safe_terminal"
ROUTER_SHELL_MARKER = "surface=router_shell"
CONFIGURATION_COMPLETE_MARKER = "configurationState=complete"
DEVICE_BLOCKER = "INTEGRATION_RUN.APP_LAUNCH_DEVICE_UNAVAILABLE"
LAUNCH_BLOCKER = "INTEGRATION_RUN.APP_LAUNCH_FAILED"
READBACK_BLOCKER = "INTEGRATION_RUN.CONTENT_READBACK_FAILED"
_PHASE_RE = re.compile(r"QWQ_APP_LAUNCH_PHASE status=([a-z_]+)")

# 首页与视频书只读实际页面的频道；普通视频浏览不能代替精品供给。
CONTENT_READBACK_QUERIES: tuple[tuple[str, dict[str, str], str], ...] = (
    ("home-feed", {"sort": "recommend", "channelId": "recommend", "limit": "20"}, "items"),
    ("video-book", {"sort": "recommend", "channelId": "premium", "limit": "20"}, "items"),
    ("video-browse", {"identity": "work", "type": "video", "limit": "20"}, "items"),
)


class IntegrationAppLaunchError(RuntimeError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class SimulatorDevice:
    udid: str
    name: str
    state: str


@dataclass
class LaunchObservation:
    device: SimulatorDevice
    phases: list[str] = field(default_factory=list)
    launched: bool = False
    router_shell: bool = False
    configuration_complete: bool = False
    exit_code: int | None = None
    first_blocker: str = ""
    log_path: Path | None = None
    started_at: str = ""
    completed_at: str = ""

    @property
    def passed(self) -> bool:
        return self.launched and self.router_shell and self.configuration_complete and not self.first_blocker


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def select_ios_simulator(*, preferred_udid: str = "") -> SimulatorDevice:
    """选择一台可用 iOS 模拟器：显式 udid > 已 Booted > 第一台可用 iPhone（会被 boot）。"""

    if sys.platform != "darwin":
        raise IntegrationAppLaunchError(DEVICE_BLOCKER, "iOS simulator launch requires a darwin host")
    completed = subprocess.run(
        ["xcrun", "simctl", "list", "devices", "available", "-j"],
        capture_output=True, text=True, check=False,
    )
    if completed.returncode != 0:
        raise IntegrationAppLaunchError(DEVICE_BLOCKER, f"simctl list failed: {completed.stderr.strip()[:200]}")
    try:
        devices_by_runtime = json.loads(completed.stdout).get("devices", {})
    except json.JSONDecodeError as exc:
        raise IntegrationAppLaunchError(DEVICE_BLOCKER, "simctl list produced invalid JSON") from exc
    candidates: list[SimulatorDevice] = []
    for runtime, devices in devices_by_runtime.items():
        if "iOS" not in str(runtime):
            continue
        for item in devices or []:
            if not isinstance(item, Mapping) or item.get("isAvailable") is not True:
                continue
            name = str(item.get("name") or "")
            if "iPhone" not in name:
                continue
            candidates.append(SimulatorDevice(udid=str(item.get("udid") or ""), name=name, state=str(item.get("state") or "")))
    if preferred_udid:
        for candidate in candidates:
            if candidate.udid == preferred_udid:
                return _ensure_booted(candidate)
        raise IntegrationAppLaunchError(DEVICE_BLOCKER, f"preferred simulator {preferred_udid} is not available")
    booted = [candidate for candidate in candidates if candidate.state == "Booted"]
    if booted:
        return booted[0]
    if not candidates:
        raise IntegrationAppLaunchError(DEVICE_BLOCKER, "no available iPhone simulator; install one via Xcode before integrate")
    return _ensure_booted(candidates[0])


def _ensure_booted(device: SimulatorDevice) -> SimulatorDevice:
    if device.state == "Booted":
        return device
    boot = subprocess.run(["xcrun", "simctl", "boot", device.udid], capture_output=True, text=True, check=False)
    if boot.returncode != 0 and "Unable to boot device in current state: Booted" not in boot.stderr:
        raise IntegrationAppLaunchError(DEVICE_BLOCKER, f"simctl boot {device.name} failed: {boot.stderr.strip()[:200]}")
    subprocess.run(["xcrun", "simctl", "bootstatus", device.udid, "-b"], capture_output=True, text=True, check=False, timeout=300)
    return SimulatorDevice(udid=device.udid, name=device.name, state="Booted")


def launch_and_observe(
    *,
    repo_root: Path,
    device: SimulatorDevice,
    log_dir: Path,
    environment: str = "alpha",
    timeout_seconds: float = 900.0,
    settle_seconds: float = 3.0,
) -> LaunchObservation:
    """以 canonical launcher 真实启动 App 并观察到 launched + router_shell + complete 后结束会话。"""

    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"app-launch-{environment}.log"
    observation = LaunchObservation(device=device, log_path=log_path, started_at=_now())
    run_sh = repo_root / "quwoquan_app/run.sh"
    if not os.access(run_sh, os.X_OK):
        raise IntegrationAppLaunchError(LAUNCH_BLOCKER, f"canonical launcher is not executable: {run_sh}")
    command = [str(run_sh), "--env", environment, "-d", device.udid]
    process_env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "QWQ_APP_LAUNCH_TIMEOUT_SECONDS": str(int(timeout_seconds))}
    deadline = time.monotonic() + timeout_seconds
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            command, cwd=repo_root, env=process_env, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, start_new_session=True,
        )
        try:
            assert process.stdout is not None
            for line in process.stdout:
                log.write(line)
                log.flush()
                stripped = line.strip()
                phase = _PHASE_RE.search(stripped)
                if phase:
                    observation.phases.append(phase.group(1))
                if LAUNCHED_MARKER in stripped:
                    observation.launched = True
                if SAFE_TERMINAL_MARKER in stripped and ROUTER_SHELL_MARKER in stripped:
                    observation.router_shell = True
                if CONFIGURATION_COMPLETE_MARKER in stripped:
                    observation.configuration_complete = True
                if "GATE_BLOCK" in stripped and not observation.first_blocker:
                    observation.first_blocker = stripped[:300]
                if observation.passed:
                    time.sleep(settle_seconds)
                    break
                if time.monotonic() > deadline:
                    observation.first_blocker = observation.first_blocker or f"{LAUNCH_BLOCKER}: launched state not observed within {int(timeout_seconds)}s"
                    break
        finally:
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    process.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=10)
            observation.exit_code = process.returncode
    observation.completed_at = _now()
    if not observation.passed and not observation.first_blocker:
        observation.first_blocker = (
            f"{LAUNCH_BLOCKER}: launcher exited with {observation.exit_code} before "
            f"launched/router_shell/complete (phases={observation.phases})"
        )
    return observation


def _content_page_identity(payload: Mapping[str, Any], items: list[Any]) -> tuple[str, str]:
    """不把非空集合、重复对象或半份 release 身份误判为可用内容。"""
    if payload.get("outcome") != "content" or payload.get("emptyReason") is not None:
        raise ValueError("nonempty page has an invalid outcome envelope")
    post_ids = [item.get("postId") if isinstance(item, dict) else None for item in items]
    if any(not isinstance(post_id, str) or not post_id.strip() or post_id != post_id.strip() for post_id in post_ids):
        raise ValueError("items lack canonical Post identities")
    if len(set(post_ids)) != len(post_ids):
        raise ValueError("items contain duplicate Post identities")
    release_id, digest = payload.get("releaseId"), payload.get("manifestDigest")
    if (
        not isinstance(release_id, str) or not release_id.strip() or release_id != release_id.strip()
        or not isinstance(digest, str) or re.fullmatch(r"sha256:[0-9a-f]{64}", digest) is None
    ):
        raise ValueError("content identity is absent or invalid")
    return release_id, digest


def content_readback(*, target: str = "alpha-local", timeout_seconds: float = 12.0) -> dict[str, Any]:
    """回读真实页面及普通视频，要求非空规范结果且全部绑定同一内容版本。"""

    api_base = _topology_api_base(target)
    ca_file = _tls_ca_file(target)
    results: dict[str, Any] = {}
    failures: list[str] = []
    accepted_identity: tuple[str, str] | None = None
    for name, query, collection in CONTENT_READBACK_QUERIES:
        try:
            observation = _default_http_request(
                api_base=api_base, ca_file=ca_file,
                method="GET", path="content/feed", page_id="content.feed.list", query=query,
                timeout_seconds=timeout_seconds,
            )
        except ContentApiConsumerError as exc:
            failures.append(f"{name}: {exc}")
            results[name] = {"status": "transport_failed", "detail": str(exc)}
            continue
        items = observation.payload.get(collection)
        count = len(items) if isinstance(items, list) else 0
        results[name] = {
            "status": observation.status,
            "path": observation.path,
            "query": dict(query),
            "collection": collection,
            "itemCount": count,
            "requestId": observation.request_id,
            "traceId": observation.trace_id,
            "durationMs": observation.duration_ms,
        }
        if observation.status != 200:
            failures.append(f"{name}: HTTP {observation.status}")
            continue
        if count == 0:
            failures.append(f"{name}: {collection} is empty")
            continue
        try:
            identity = _content_page_identity(observation.payload, items)
        except ValueError as exc:
            failures.append(f"{name}: {exc}")
            continue
        release_id, digest = identity
        results[name].update({"releaseId": release_id, "manifestDigest": digest})
        if accepted_identity is None:
            accepted_identity = identity
        elif identity != accepted_identity:
            failures.append(f"{name}: content identity differs between queries")
    return {
        "apiBase": api_base, "results": results, "failures": failures,
        "passed": not failures, "countScope": "observed-pages", "traversalComplete": False,
    }


def case_result(
    *,
    case_id: str,
    object_id: str,
    spec_ref: str,
    target_id: str,
    environment: str,
    candidate: Mapping[str, str],
    runtime: Mapping[str, str],
    started_at: str,
    completed_at: str,
    artifact_sha256: str,
    receipt_ref: str,
) -> dict[str, Any]:
    return {
        "objectId": object_id,
        "specRef": spec_ref,
        "caseId": case_id,
        "producer": "ops",
        "layer": "environment_acceptance",
        "status": "passed",
        "target": {"kind": "operation", "id": target_id},
        "commitSha": runtime["commitSha"],
        "contractGraphSourceHash": runtime["contractGraphSourceHash"],
        "deploymentTarget": f"{environment}-local",
        "baselineId": runtime["baselineId"],
        "packageDigest": runtime["packageDigest"],
        "configurationDigest": runtime["configurationDigest"],
        "candidateManifestSha256": runtime["candidateManifestSha256"],
        "candidateDigest": candidate["candidateId"],
        "environment": environment,
        "provider": "first-party-https",
        "startedAt": started_at,
        "completedAt": completed_at,
        "runnerIdentity": "integration-run",
        "artifactSha256": artifact_sha256,
        "receiptRef": receipt_ref,
    }
