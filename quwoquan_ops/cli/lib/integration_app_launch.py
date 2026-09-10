"""Alpha 的独立必需证据：双端离线页面 raw 闭包与 exact release API 回读。

离线页面保留 rehearsal/nonPromotable；服务身份只由真实服务/API 轴提供。
旧 direct 启动观察函数仅供开发诊断，不再参与 acceptance authority。
HTTP 与 TLS 复用 content-api-consumer，设备执行由 stackctl app-content-uat 拥有。
"""

from __future__ import annotations

import hashlib
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


def content_readback(*, expected_release: Mapping[str, str], target: str = "alpha-local",
                     timeout_seconds: float = 12.0) -> dict[str, Any]:
    """回读页面及普通视频，必须 exact 匹配 candidate attestation 的 release/cohort。"""
    expected_identity = (expected_release.get("releaseId"), expected_release.get("releaseDigest"))
    if (not expected_identity[0] or not isinstance(expected_identity[1], str)
            or re.fullmatch(r"sha256:[0-9a-f]{64}", expected_identity[1]) is None):
        raise IntegrationAppLaunchError(READBACK_BLOCKER, "expected candidate release identity is required")

    api_base = _topology_api_base(target)
    ca_file = _tls_ca_file(target)
    results: dict[str, Any] = {}
    failures: list[str] = []
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
        if identity != expected_identity:
            failures.append(f"{name}: content identity differs from expected candidate release")
    return {
        "apiBase": api_base, "results": results, "failures": failures,
        "passed": not failures, "countScope": "observed-pages", "traversalComplete": False,
    }


def _validate_offline_execution_refs(*, execution: Mapping[str, Any], receipt: Mapping[str, Any]) -> None:
    """只校验执行文档指向本次 receipt 的三项 exact 身份，不读取下一阶段证据。"""
    expected_refs = {"targetUatBinding": receipt["targetUatBindingRefs"]["alpha-local"],
                     "launchBinding": receipt["launchBindingRef"], "nativeDriverBinding": receipt["nativeDriverBindingRef"]}
    if any(execution.get(key) != ref for key, ref in expected_refs.items()):
        raise ValueError("offline execution binding drifted")


def _validate_offline_execution_identity(*, plan: Mapping[str, Any], launch: Mapping[str, Any],
                                         binding: Mapping[str, Any], candidate: Mapping[str, Any]) -> None:
    expected = {"candidateDigest": candidate["candidateId"], "artifactDigest": binding["artifact"]["digest"],
                "deviceId": binding["device"]["identity"], "platform": binding["platform"], "applicationId": binding["artifact"]["applicationId"]}
    if any(plan.get(key) != value or launch.get(key) != value for key, value in expected.items()):
        raise ValueError("offline execution candidate/artifact/device drifted")


def _validate_offline_launch_identity(*, plan: Mapping[str, Any], launch: Mapping[str, Any], result: Mapping[str, Any],
                                    binding: Mapping[str, Any], candidate: Mapping[str, Any],
                                    snapshot: Mapping[str, Any], attempt: Mapping[str, Any]) -> None:
    from quwoquan_ops.cli.commands.app_preflight_uat_offline_pages import document_digest

    expected_plan = {"caseId": result["caseId"], "route": result["target"]["id"], "carrier": result["carrier"],
                     "canonicalProcessId": launch.get("canonicalProcessId"),
                     "launchAttemptId": launch.get("launchAttemptId"), "snapshotDigest": document_digest(snapshot)}
    expected_launch = {"launchAttemptDigest": document_digest(attempt), "launchAttemptId": attempt.get("attemptId"),
                       "sourceGitSha": candidate["commit"], "runtimeConfigPackageDigest": binding["runtimeConfigDigest"]}
    if (any(plan.get(key) != value for key, value in expected_plan.items())
            or any(launch.get(key) != value for key, value in expected_launch.items())):
        raise ValueError("offline execution plan/launch candidate identity drifted")


def _validate_offline_installed_artifact(*, aut: Mapping[str, Any], binding: Mapping[str, Any], launch: Mapping[str, Any]) -> None:
    from quwoquan_ops.cli.smoke.environment_patrol_smoke.artifact_binding import validate_tested_app_artifact_binding

    comparison = validate_tested_app_artifact_binding(aut)
    if (aut.get("deviceId") != binding["device"]["identity"] or aut.get("platform") != binding["platform"]
            or any(comparison[key] != launch[key] for key in ("applicationId", "artifactDigest"))):
        raise ValueError("offline installed artifact identity drifted")


def _offline_execution(*, read: Any, page: Mapping[str, Any], result: Mapping[str, Any],
                       receipt: Mapping[str, Any], binding: Mapping[str, Any], candidate: Mapping[str, Any]) -> None:
    from quwoquan_ops.cli.commands.app_preflight_uat_offline_pages import native_page_screenshot, validate_native_page_result

    if (result.get("receiptRef") or result.get("artifactPath")) != page["evidence"]["ref"]:
        raise ValueError("offline raw execution evidence ref drifted")
    execution = read(page["evidence"])
    _validate_offline_execution_refs(execution=execution, receipt=receipt)
    plan, launch, native = read(execution["plan"]), read(execution["launchBinding"]), read(execution["nativeResult"])
    _validate_offline_execution_identity(plan=plan, launch=launch, binding=binding, candidate=candidate)
    snapshot, attempt = read(binding["snapshot"]), read(binding["launchAttempt"])
    _validate_offline_launch_identity(plan=plan, launch=launch, result=result, binding=binding,
                                    candidate=candidate, snapshot=snapshot, attempt=attempt)
    validate_native_page_result("QWQ_OFFLINE_PAGE " + json.dumps(native), plan=plan, launch=launch)
    read(execution["nativeDriverBinding"])
    for field in ("autBefore", "autAfter"):
        _validate_offline_installed_artifact(aut=execution[field], binding=binding, launch=launch)
    if execution["command"].get("exitCode") != 0:
        raise ValueError("offline native command failed")
    screenshot = read(execution["screenshot"], binary=True)
    log = read(execution["log"], binary=True).decode("utf-8")
    if validate_native_page_result(log, plan=plan, launch=launch) != native:
        raise ValueError("offline native raw log differs from result")
    if native_page_screenshot(log, native) != screenshot:
        raise ValueError("offline screenshot differs from native foreground observation")


def _offline_evidence_path(root: Path, exact: Mapping[str, str]) -> Path:
    """先验证 exact ref 形状与词法边界，再允许读取文件或查询 symlink。"""
    if not isinstance(exact, Mapping) or set(exact) != {"ref", "digest"}:
        raise ValueError("offline evidence requires exact ref/digest")
    relative = Path(exact["ref"])
    if (relative.is_absolute() or any(part in {".", ".."} for part in relative.parts) or not relative.parts
            or relative.as_posix() != exact["ref"] or any(char in exact["ref"] for char in "\x00\n\r\\")):
        raise ValueError("offline evidence ref escapes output root")
    return root / relative


def _read_offline_evidence_bytes(root: Path, exact: Mapping[str, str]) -> tuple[bytes, str]:
    path = _offline_evidence_path(root, exact)
    relative = path.relative_to(root)
    if any((root / Path(*relative.parts[:index])).is_symlink() for index in range(1, len(relative.parts) + 1)):
        raise ValueError("offline evidence symlink is forbidden")
    encoded = path.read_bytes()
    digest = "sha256:" + hashlib.sha256(encoded).hexdigest()
    if digest != exact["digest"]:
        raise ValueError("offline evidence exact bytes drifted: " + exact["ref"])
    return encoded, digest


def _validate_offline_receipt_status(receipt: Mapping[str, Any]) -> None:
    if (receipt.get("schema") != "quwoquan_ops.app_content_uat_receipt" or receipt.get("profile") != "rehearsal"
            or receipt.get("status") != "passed" or receipt.get("exitCode") != 0
            or receipt.get("contentSource") != "bundled_snapshot" or receipt.get("nonPromotable") is not True
            or receipt.get("targets") != ["alpha-local"] or receipt.get("firstBlocker")
            or receipt.get("dryRun") is True):
        raise ValueError("offline receipt is not an executed complete result")


def _offline_receipt_pages(receipt: Mapping[str, Any]) -> tuple[list[Any], list[Any], list[Any]]:
    raw_refs = receipt["rawResultRefs"]["alpha-local"]
    raw_digests = receipt["rawResultDigests"]["alpha-local"]
    pages = receipt["pageResultRefs"]
    if (not isinstance(pages, list) or not pages or len(raw_refs) != len(pages) or len(raw_digests) != len(pages)
            or len({row["slotId"] for row in pages}) != len(pages)):
        raise ValueError("offline rawResultRefs are absent or incomplete")
    return raw_refs, raw_digests, pages


def _validate_offline_raw_projection(*, slot: str, exact_raw: Mapping[str, str], raw_ref: Mapping[str, str],
                                     raw_digest: Mapping[str, str]) -> None:
    if (raw_ref != {"slotId": slot, "ref": exact_raw["ref"]}
            or raw_digest != {"slotId": slot, "digest": exact_raw["digest"]}):
        raise ValueError("offline raw ref/digest projection drifted")


def offline_receipt_evidence(*, root: Path, receipts: Mapping[str, Mapping[str, str]],
                             candidate: Mapping[str, Any], devices: Mapping[str, str]) -> dict[str, Any]:
    """逐字节消费双端 raw 与绑定闭包；parent receipt 的 complete 不是页面 verdict。"""
    from quwoquan_ops.cli.commands.app_preflight_uat_offline_pages import validate_offline_page_coverage

    files: dict[str, str] = {}

    def read(exact: Mapping[str, str], *, binary: bool = False) -> Any:
        encoded, digest = _read_offline_evidence_bytes(root, exact)
        files[exact["ref"]] = digest
        if binary:
            return encoded
        value = json.loads(encoded)
        if not isinstance(value, dict):
            raise ValueError("offline evidence must be an object")
        return value

    if set(receipts) != {"android", "ios"} or set(devices) != set(receipts) or not all(devices.values()):
        raise ValueError("offline page requires two explicit platform devices and receipts")
    results, bindings, case_refs = [], [], []
    for platform, exact in receipts.items():
        receipt = read(exact)
        _validate_offline_receipt_status(receipt)
        binding_ref = receipt["targetUatBindingRefs"]["alpha-local"]
        binding = read(binding_ref)
        if binding["platform"] != platform or binding["device"]["identity"] != devices[platform]:
            raise ValueError("offline receipt device differs from explicit selector")
        bindings.append(binding)
        raw_refs, raw_digests, pages = _offline_receipt_pages(receipt)
        for index, page in enumerate(pages):
            slot, exact_raw = page["slotId"], page["result"]
            _validate_offline_raw_projection(slot=slot, exact_raw=exact_raw, raw_ref=raw_refs[index], raw_digest=raw_digests[index])
            result = read(exact_raw)
            if result.get("platform") != platform or slot != platform + ":" + result["caseId"]:
                raise ValueError("offline raw platform differs from receipt")
            _offline_execution(read=read, page=page, result=result, receipt=receipt, binding=binding, candidate=candidate)
            results.append(result)
            case_refs.append(dict(exact_raw))
    validate_offline_page_coverage(results=results, bindings=bindings, candidate=candidate)
    if len({binding["snapshot"]["digest"] for binding in bindings}) != 1:
        raise ValueError("offline platforms bind different snapshots")
    return {"files": [{"ref": ref, "digest": digest} for ref, digest in sorted(files.items())],
            "cases": case_refs, "results": results, "bindings": bindings}


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
