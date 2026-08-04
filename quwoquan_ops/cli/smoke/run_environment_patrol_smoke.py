#!/usr/bin/env python3
"""Run page-level Patrol smoke tests for one environment target."""

from __future__ import annotations

import argparse
import atexit
import base64
import datetime as dt
import fcntl
import hashlib
import json
import os
import queue
import re
import signal
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
from pathlib import Path
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from quwoquan_ops.ci.device_matrix.evidence import (
    capture_device_screenshot,
    repo_relative,
    sanitize_device_id,
    write_device_manifest,
    write_discovered_devices_snapshot,
    write_json,
)
from quwoquan_ops.ci.device_matrix.android import resolve_android_debug_bridge
from quwoquan_ops.cli.lib.local_runtime_reservation import (
    acquire_local_runtime_use_lock,
)
from quwoquan_ops.cli.lib.local_runtime_consumer_lease import (
    acquire_consumer_lease,
    release_consumer_lease,
)
from quwoquan_ops.cli.lib.local_controlled_edge_fault import (
    CONTROLLED_EDGE_SERVICES,
    ControlledEdgeFault,
    begin_controlled_edge_fault,
)
from quwoquan_ops.cli.lib.patrol_cli import resolve_patrol_cli
from quwoquan_ops.cli.lib.environment_topology import (
    get_target,
    load_environment_topology,
)
from quwoquan_ops.cli.lib.flutter_android_device_proxy import (
    ANDROID_DEVICE_INVENTORY_ENV,
    REAL_FLUTTER_ENV,
)
from quwoquan_ops.cli.lib.video_playback_evidence import (
    read_native_video_playback_evidence,
)


APP_DIR = REPO_ROOT / "quwoquan_app"
DEFAULT_REPORT = REPO_ROOT / ".qwq_output" / "env" / "repo" / "runs" / "device-matrix" / "environment-smoke" / "report.json"
DEFAULT_TARGET = (
    "test/user_acceptance/patrol/environment/"
    "video_playback_canary__user_acceptance_test.dart"
)
CORE_READBACK_TARGET = (
    "test/user_acceptance/patrol/environment/"
    "app_core_readback__user_acceptance_test.dart"
)
FEED_LOAD_TARGET = (
    "test/user_acceptance/patrol/discovery/"
    "feed_load__user_acceptance_test.dart"
)
FEED_CONTENT_EVIDENCE_PREFIX = "QWQ_FEED_CONTENT_EVIDENCE "
CONTROLLED_EDGE_FAULT_TARGET = (
    "test/user_acceptance/patrol/discovery/"
    "feed_controlled_edge_recovery__user_acceptance_test.dart"
)
CONTROLLED_EDGE_RESTORE_REQUEST_PREFIX = (
    "QWQ_APP_CONTENT_EDGE_RESTORE_REQUEST "
)
CONTROLLED_EDGE_FAULT_EVIDENCE_PREFIX = "QWQ_APP_CONTENT_FAULT_EVIDENCE "
CONTROLLED_EDGE_FAULT_COPY_KEYS = frozenset(
    {
        "connectionUnavailable",
        "requestTimedOut",
        "serviceUnavailable",
        "guestSessionUnavailable",
    }
)
RELEASE_APP_UAT_DEFINES = (
    ("data_release_id", "DATA_RELEASE_ID"),
    ("data_release_class", "DATA_RELEASE_CLASS"),
    ("product_lifecycle_state", "PRODUCT_LIFECYCLE_STATE"),
    ("data_release_homepage_id", "DATA_RELEASE_HOMEPAGE_ID"),
    ("data_release_homepage_title", "DATA_RELEASE_HOMEPAGE_TITLE"),
    ("data_release_article_work_id", "DATA_RELEASE_ARTICLE_WORK_ID"),
    ("data_release_article_title", "DATA_RELEASE_ARTICLE_TITLE"),
    ("data_release_image_work_id", "DATA_RELEASE_IMAGE_WORK_ID"),
    ("data_release_image_title", "DATA_RELEASE_IMAGE_TITLE"),
    ("data_release_creator_name", "DATA_RELEASE_CREATOR_NAME"),
    ("data_release_tag_label", "DATA_RELEASE_TAG_LABEL"),
    ("data_release_video_attribution", "DATA_RELEASE_VIDEO_ATTRIBUTION"),
)
BASIC_VIABILITY_TARGET = (
    "test/user_acceptance/patrol/environment/"
    "basic_viability__user_acceptance_test.dart"
)
ACCOUNT_CLOSURE_TARGET = (
    "test/user_acceptance/patrol/settings/"
    "account_closure_journey__user_acceptance_test.dart"
)
RUNTIME_RECOVERY_TARGET = (
    "test/user_acceptance/patrol/environment/"
    "runtime_recovery_journey__user_acceptance_test.dart"
)
RUNTIME_RECOVERY_EVIDENCE_PREFIX = "QWQ_RUNTIME_RECOVERY_EVIDENCE "
RUNTIME_RECOVERY_EVIDENCE_FIELDS = frozenset(
    {
        "authenticatedBefore",
        "authenticatedAfter",
        "sameOwner",
        "samePersona",
        "homeRestored",
        "secondFaultNoReentry",
    }
)
ACCOUNT_ENFORCEMENT_TARGETS = {
    "suspended": (
        "test/user_acceptance/patrol/user/"
        "account_enforcement_suspended__user_acceptance_test.dart"
    ),
    "restored": (
        "test/user_acceptance/patrol/user/"
        "account_enforcement_restored__user_acceptance_test.dart"
    ),
}
ACCOUNT_ENFORCEMENT_EVIDENCE_PREFIX = "QWQ_ACCOUNT_ENFORCEMENT_EVIDENCE "
ACCOUNT_ENFORCEMENT_CANDIDATE_DIGEST_PATTERN = re.compile(
    r"^sha256:[0-9a-f]{64}$"
)
ACCOUNT_ENFORCEMENT_EXPECTED_EVIDENCE: dict[str, dict[str, Any]] = {
    "suspended": {
        "phase": "suspended",
        "remoteCode": "USER.AUTH.account_suspended",
        "sessionCredentialsCleared": True,
        "restrictionSurfaceVisible": True,
    },
    "restored": {
        "phase": "restored",
        "remoteProfileRead": True,
        "sessionAuthenticated": True,
        "safeHomeVisible": True,
    },
}
IOS_SDK_VERSION_PATTERN = re.compile(r"iOS[- ](\d+)(?:[-._](\d+))?")
IOS_RUNTIME_VERSION_PATTERN = re.compile(r"^\d+\.\d+(?:\.\d+)?$")
XCODE_IOS_SIMULATOR_SDK_PATTERN = re.compile(
    r"-sdk\s+iphonesimulator(\d+)(?:\.(\d+))?"
)
XCTEST_EXECUTION_SUMMARY_PATTERN = re.compile(
    r"Executed\s+(?P<executed>\d+)\s+tests?,\s+with\s+(?P<failed>\d+)\s+failures?",
)
PATROL_EXECUTION_SUMMARY_PATTERN = re.compile(
    r"📝\s+Total:\s*(?P<executed>\d+).*?"
    r"❌\s+Failed:\s*(?P<failed>\d+)",
    re.DOTALL,
)
XCODE_GLOBAL_PRODUCTS_DIR = Path.home() / "Library" / "Developer" / "Xcode" / "XcodeDerivedData" / "Build" / "Products"
PATROL_IOS_PRODUCTS_DIR = APP_DIR / "build" / "ios_integ" / "Build" / "Products"
LOCAL_TARGETS = {"alpha-local", "beta-local", "gamma-local", "prod-sim"}
LOCAL_ENVIRONMENT_ALIAS_TARGETS = {
    "alpha": "alpha-local",
    "beta": "beta-local",
    "gamma": "gamma-local",
    "prod": "prod-hosted",
    "local-alpha": "alpha-local",
    "local-beta": "beta-local",
    "local-gamma": "gamma-local",
    "local-prod-sim": "prod-sim",
}
RUNTIME_ANONYMOUS_SESSION_MODES = {
    "local-beta": "beta_local_anonymous_runtime",
    "beta-local": "beta_local_anonymous_runtime",
    "local-gamma": "gamma_local_anonymous_runtime",
    "gamma-local": "gamma_local_anonymous_runtime",
    "local-prod-sim": "prod_sim_anonymous_runtime",
    "prod-sim": "prod_sim_anonymous_runtime",
}
FORBIDDEN_PROD_PLAYBACK_CANARY_TOKENS = frozenset(
    {"fixture", "mock", "seed", "test"}
)
IOS_RELEASE_UAT_BUNDLE_IDS = (
    "com.example.quwoquanApp",
    "com.example.quwoquanApp.RunnerUITests.xctrunner",
)
ANDROID_RELEASE_UAT_PACKAGE = "com.quwoquan.quwoquan_app"
PATROL_FLUTTER_COMMAND_ENV = "PATROL_FLUTTER_COMMAND"
PATROL_EXECUTION_LOCK = (
    REPO_ROOT
    / ".qwq_output"
    / "env"
    / "repo"
    / "local"
    / "locks"
    / "environment-patrol-smoke.lock"
)
ANDROID_DEVICE_PROXY = (
    REPO_ROOT / "quwoquan_ops" / "cli" / "lib" / "flutter_android_device_proxy.py"
)


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _acquire_patrol_execution_lock(
    *,
    env_name: str,
    target: str,
    lock_path: Path = PATROL_EXECUTION_LOCK,
) -> Any:
    """Serialize Patrol builds that share Flutter/Xcode build directories."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+", encoding="utf-8")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as error:
        handle.seek(0)
        holder = handle.read().strip() or "unknown"
        handle.close()
        raise RuntimeError(
            f"Patrol build workspace is already in use: {holder}",
        ) from error
    handle.seek(0)
    handle.truncate()
    handle.write(
        f"pid={os.getpid()} env={env_name.strip()} "
        f"target={target.strip()} startedAt={utc_now()}\n",
    )
    handle.flush()
    os.fsync(handle.fileno())
    return handle


def _runtime_env_for_alias(alias: str) -> str:
    normalized = alias.strip().lower()
    if normalized in {"prod", "prod-sim", "prod-hosted"}:
        return "prod"
    if "gamma" in normalized:
        return "gamma"
    if "beta" in normalized:
        return "beta"
    return "alpha"


def _evidence_class_for_runtime(runtime_env: str) -> str:
    del runtime_env
    return "user_acceptance_remote"


def _requires_native_video_playback_signals(device: dict[str, Any]) -> bool:
    return str(device.get("targetPlatform") or "").lower().startswith("android")


def _read_video_playback_evidence(patrol_log: Path) -> dict[str, bool]:
    return read_native_video_playback_evidence(patrol_log)


def _read_feed_content_evidence(patrol_log: Path) -> dict[str, Any]:
    if not patrol_log.is_file():
        return {}
    for line in reversed(patrol_log.read_text(encoding="utf-8").splitlines()):
        marker = line.find(FEED_CONTENT_EVIDENCE_PREFIX)
        if marker < 0:
            continue
        encoded = line[marker + len(FEED_CONTENT_EVIDENCE_PREFIX) :].strip()
        try:
            payload = json.loads(encoded)
        except json.JSONDecodeError:
            return {}
        if not isinstance(payload, dict):
            return {}
        environment = str(payload.get("environment") or "").strip()
        visible_keys = payload.get("visibleCardKeys")
        visible_count = payload.get("visibleCardCount")
        if (
            environment not in {"alpha", "beta", "gamma"}
            or not isinstance(visible_keys, list)
            or not visible_keys
            or any(not isinstance(item, str) or not item for item in visible_keys)
            or len(set(visible_keys)) != len(visible_keys)
            or visible_count != len(visible_keys)
        ):
            return {}
        return {
            "environment": environment,
            "visibleCardCount": visible_count,
            "visibleCardKeys": visible_keys,
        }
    return {}


def _read_controlled_edge_fault_evidence(patrol_log: Path) -> dict[str, Any]:
    if not patrol_log.is_file():
        return {}
    for line in reversed(patrol_log.read_text(encoding="utf-8").splitlines()):
        marker = line.find(CONTROLLED_EDGE_FAULT_EVIDENCE_PREFIX)
        if marker < 0:
            continue
        encoded = line[
            marker + len(CONTROLLED_EDGE_FAULT_EVIDENCE_PREFIX) :
        ].strip()
        try:
            payload = json.loads(encoded)
        except json.JSONDecodeError:
            return {}
        if not isinstance(payload, dict):
            return {}
        environment = str(payload.get("environment") or "").strip()
        copy_key = str(payload.get("copyKey") or "").strip()
        recovered_count = payload.get("recoveredVisibleCardCount")
        if (
            environment not in {"alpha", "beta", "gamma"}
            or copy_key not in CONTROLLED_EDGE_FAULT_COPY_KEYS
            or payload.get("singlePrimaryAction") is not True
            or payload.get("forbiddenBrandAbsent") is not True
            or payload.get("technicalDetailsAbsent") is not True
            or payload.get("blockedRetryCount") != 5
            or payload.get("blockingErrorRetained") is not True
            or payload.get("sameInstallRecovery") is not True
            or not isinstance(recovered_count, int)
            or recovered_count <= 0
        ):
            return {}
        return {
            "environment": environment,
            "copyKey": copy_key,
            "singlePrimaryAction": True,
            "forbiddenBrandAbsent": True,
            "technicalDetailsAbsent": True,
            "blockedRetryCount": 5,
            "blockingErrorRetained": True,
            "sameInstallRecovery": True,
            "recoveredVisibleCardCount": recovered_count,
        }
    return {}


def _is_feed_load_target(args: argparse.Namespace) -> bool:
    target = str(getattr(args, "target", "") or "").replace("\\", "/")
    return target.endswith(FEED_LOAD_TARGET)


def _is_controlled_edge_fault_target(args: argparse.Namespace) -> bool:
    target = str(getattr(args, "target", "") or "").replace("\\", "/")
    return target.endswith(CONTROLLED_EDGE_FAULT_TARGET)


def _local_target_for_environment_alias(env_name: str) -> str:
    """Resolve a public environment alias to its concrete local deployment target."""
    normalized = env_name.strip().lower()
    return LOCAL_ENVIRONMENT_ALIAS_TARGETS.get(normalized, normalized)


def _uses_public_video_canary_anonymous_session(
    args: argparse.Namespace,
) -> bool:
    """本地 beta/gamma 的公开视频 canary 无凭据时以 guest 执行只读验收。"""

    target_name = _local_target_for_environment_alias(args.env_name)
    if target_name not in {"beta-local", "gamma-local"}:
        return False
    target = str(getattr(args, "target", "") or "").replace("\\", "/")
    if not target.endswith(DEFAULT_TARGET):
        return False
    supplied = (
        args.test_auth_token,
        args.test_refresh_token,
        _resolved_owner_id(args),
        _resolved_persona_id(args),
    )
    return not any(str(value).strip() for value in supplied)


def _requires_video_playback_canary(args: argparse.Namespace) -> bool:
    target = str(getattr(args, "target", "") or "").replace("\\", "/")
    return any(
        target.endswith(candidate)
        for candidate in (
            DEFAULT_TARGET,
            CORE_READBACK_TARGET,
            BASIC_VIABILITY_TARGET,
        )
    )


def _requires_account_closure(args: argparse.Namespace) -> bool:
    target = str(getattr(args, "target", "") or "").replace("\\", "/")
    return target.endswith(ACCOUNT_CLOSURE_TARGET)


def _is_runtime_recovery_target(args: argparse.Namespace) -> bool:
    target = str(getattr(args, "target", "") or "").replace("\\", "/")
    return target.endswith(RUNTIME_RECOVERY_TARGET)


def _account_enforcement_phase(args: argparse.Namespace) -> str:
    target = str(getattr(args, "target", "") or "").replace("\\", "/")
    return next(
        (
            phase
            for phase, expected_target in ACCOUNT_ENFORCEMENT_TARGETS.items()
            if target.endswith(expected_target)
        ),
        "",
    )


def _is_account_enforcement_target(args: argparse.Namespace) -> bool:
    return bool(_account_enforcement_phase(args))


def _account_enforcement_subject_digest(args: argparse.Namespace) -> str:
    if not _is_account_enforcement_target(args):
        return ""
    owner_id = _resolved_owner_id(args).strip()
    if not owner_id:
        return ""
    return f"sha256:{hashlib.sha256(owner_id.encode('utf-8')).hexdigest()}"


def _uses_persisted_device_session(args: argparse.Namespace) -> bool:
    return bool(getattr(args, "persisted_device_session", False))


def _validate_account_closure_execution(
    args: argparse.Namespace,
    runtime_env: str,
) -> None:
    if not _requires_account_closure(args):
        return
    install_id = str(getattr(args, "patrol_install_id", "") or "").strip()
    if not install_id or "{device}" not in install_id:
        raise ValueError(
            "account closure Patrol requires --patrol-install-id with a "
            "{device} placeholder"
        )
    if runtime_env != "prod":
        return
    if _uses_runtime_anonymous_session(args):
        raise ValueError(
            "prod account closure Patrol requires an injected disposable session"
        )
    if not bool(getattr(args, "account_closure_disposable_ack", False)):
        raise ValueError(
            "prod account closure Patrol requires "
            "--account-closure-disposable-ack"
        )


def _uses_runtime_anonymous_session(args: argparse.Namespace) -> bool:
    return (
        args.env_name.strip().lower() in RUNTIME_ANONYMOUS_SESSION_MODES
        and not _uses_public_video_canary_anonymous_session(args)
        and not _uses_persisted_device_session(args)
        and not _is_account_enforcement_target(args)
    )


def _runtime_anonymous_session_mode(args: argparse.Namespace) -> str:
    alias = args.env_name.strip().lower()
    try:
        return RUNTIME_ANONYMOUS_SESSION_MODES[alias]
    except KeyError as exc:
        raise ValueError(
            f"{alias or '<empty>'} does not support runtime anonymous login"
        ) from exc


def _public_video_canary_session_mode(args: argparse.Namespace) -> str:
    target_name = _local_target_for_environment_alias(args.env_name)
    if target_name == "beta-local":
        return "beta_local_anonymous_public_video"
    if target_name == "gamma-local":
        return "gamma_local_anonymous_public_video"
    raise ValueError(f"{target_name} does not support anonymous public video canary")


def _is_local_target(env_name: str) -> bool:
    return _local_target_for_environment_alias(env_name) in LOCAL_TARGETS


def _resolved_media_base_urls(args: argparse.Namespace) -> dict[str, str]:
    """解析四类显式注入的媒体 authority；禁止单一 media base 回退。"""
    return {
        "mediaAvatarBaseUrl": str(
            getattr(args, "media_avatar_base_url", "") or ""
        ).strip(),
        "mediaImageBaseUrl": str(
            getattr(args, "media_image_base_url", "") or ""
        ).strip(),
        "mediaVideoBaseUrl": str(
            getattr(args, "media_video_base_url", "") or ""
        ).strip(),
        "mediaUploadBaseUrl": str(
            getattr(args, "media_upload_base_url", "") or ""
        ).strip(),
    }


def _effective_base_urls_for_device(
    args: argparse.Namespace,
    device: dict[str, Any],
) -> dict[str, str]:
    # 本地 target 也必须保留 topology 投影的 canonical public authority。
    # Android/iOS 由 DNS-01 公共证书和本地连接投影到运行栈；把 URL 改成
    # localhost 会破坏证书 hostname 校验，并重新引入已退役的私有 CA 路径。
    del device
    gateway_base_url = args.gateway_base_url.strip()
    product_ops_base_url = args.product_ops_base_url.strip()
    rtc_media_connection_url = args.rtc_media_connection_url.strip()
    media_urls = _resolved_media_base_urls(args)
    target_name = _local_target_for_environment_alias(args.env_name)
    public_bases = get_target(
        load_environment_topology(),
        target_name,
    )["publicBases"]
    supplied_by_role = {
        "api": gateway_base_url,
        "productOps": product_ops_base_url,
        "rtc": rtc_media_connection_url,
        "mediaAvatar": media_urls["mediaAvatarBaseUrl"],
        "mediaImage": media_urls["mediaImageBaseUrl"],
        "mediaVideo": media_urls["mediaVideoBaseUrl"],
        "mediaUpload": media_urls["mediaUploadBaseUrl"],
    }
    mismatched = [
        role
        for role, supplied in supplied_by_role.items()
        if supplied.rstrip("/") != str(public_bases[role]).rstrip("/")
    ]
    if mismatched:
        raise ValueError(
            "runtime URL arguments must equal canonical topology projection: "
            + ", ".join(sorted(mismatched))
        )
    return {
        "gatewayBaseUrl": gateway_base_url,
        "legalBaseUrl": str(public_bases["legal"]),
        "productOpsBaseUrl": product_ops_base_url,
        "rtcMediaConnectionUrl": rtc_media_connection_url,
        **media_urls,
    }


def _resolved_owner_id(args: argparse.Namespace) -> str:
    return str(getattr(args, "current_owner_id", "") or "").strip()


def _resolved_persona_id(args: argparse.Namespace) -> str:
    return str(getattr(args, "current_persona_id", "") or "").strip()


def _validate_video_playback_canary_work_id(
    args: argparse.Namespace,
    runtime_env: str,
) -> str:
    work_id = str(
        getattr(args, "video_playback_canary_work_id", "") or ""
    ).strip()
    if not work_id:
        raise ValueError("video playback canary work id is required")
    if runtime_env == "prod" and any(
        token in work_id.lower()
        for token in FORBIDDEN_PROD_PLAYBACK_CANARY_TOKENS
    ):
        raise ValueError(
            "prod playback canary must reference a published release work, not fixture/mock/seed/test data"
        )
    return work_id


def _device_command_env(args: argparse.Namespace, device: dict[str, Any]) -> dict[str, str]:
    env = dict(os.environ)
    runtime_env = args.runtime_env.strip() or _runtime_env_for_alias(args.env_name)
    env["QWQ_APP_RUNTIME_ENV"] = runtime_env
    target = str(device.get("targetPlatform", "")).strip().lower()
    if target.startswith("android"):
        device_id = str(device.get("id", "")).strip()
        if not device_id:
            raise RuntimeError(
                "GATE_BLOCK: Android Patrol requires an explicit device id"
            )
        env["QWQ_RUN_DEVICE_ID"] = device_id
        env["ANDROID_SERIAL"] = device_id
        adb = resolve_android_debug_bridge()
        if adb:
            adb_directory = str(Path(adb).parent)
            existing_path = env.get("PATH", "")
            path_entries = existing_path.split(os.pathsep) if existing_path else []
            if adb_directory not in path_entries:
                env["PATH"] = (
                    f"{adb_directory}{os.pathsep}{existing_path}"
                    if existing_path
                    else adb_directory
                )
        real_flutter = shutil.which("flutter", path=env.get("PATH", ""))
        if real_flutter is None:
            raise RuntimeError(
                "GATE_BLOCK: Flutter executable is required for Android Patrol"
            )
        proxy_devices = [
            {
                "id": str(device.get("id", "")).strip(),
                "name": str(device.get("name", "")).strip(),
                "targetPlatform": str(device.get("targetPlatform", "")).strip(),
                "emulator": bool(device.get("emulator", False)),
                "isSupported": True,
            }
        ]
        env[PATROL_FLUTTER_COMMAND_ENV] = f"{sys.executable} {ANDROID_DEVICE_PROXY}"
        env[REAL_FLUTTER_ENV] = str(Path(real_flutter).resolve())
        env[ANDROID_DEVICE_INVENTORY_ENV] = json.dumps(
            proxy_devices,
            ensure_ascii=False,
            separators=(",", ":"),
        )
    elif (
        target == "ios"
        and bool(device.get("emulator", False))
        and _is_local_target(args.env_name)
    ):
        device_id = str(device.get("id", "")).strip()
        if not device_id:
            raise RuntimeError(
                "GATE_BLOCK: local iOS Simulator Patrol requires an explicit device id"
            )
        env["QWQ_IOS_SIMULATOR_UDID"] = device_id
    return env


def _local_tls_trust_evidence(*, dry_run: bool) -> dict[str, str]:
    """Describe the public-CA boundary without mutating device trust state."""

    if dry_run:
        return {"status": "skipped", "reason": "not-required"}
    return {"status": "system-public-ca", "reason": "dns-01"}


def _prepare_android_local_port_reverse(
    args: argparse.Namespace,
    device: dict[str, Any],
) -> dict[str, Any]:
    """反向映射 canonical HTTPS/WSS authority 使用的本地 target 端口。"""

    target_platform = str(device.get("targetPlatform", "")).strip().lower()
    if not (
        _is_local_target(args.env_name) and target_platform.startswith("android")
    ):
        return {"status": "skipped", "reason": "not-required"}
    adb = resolve_android_debug_bridge()
    device_id = str(device.get("id", "")).strip()
    if not adb:
        raise RuntimeError(
            "GATE_BLOCK: adb is required to reverse local target ports for Android Patrol "
            "(set ANDROID_SDK_ROOT/ANDROID_HOME or install platform-tools)",
        )
    if not device_id:
        raise RuntimeError(
            "GATE_BLOCK: Android Patrol device is missing an explicit device id",
        )
    base_urls = _effective_base_urls_for_device(args, device)
    ports: set[int] = set()
    for value in base_urls.values():
        parsed = urllib.parse.urlsplit(value)
        if parsed.scheme not in {"https", "wss"} or not parsed.hostname:
            continue
        ports.add(parsed.port or 443)
    if not ports:
        raise RuntimeError(
            "GATE_BLOCK: no secure HTTP/WebSocket local target ports are available for Android Patrol",
        )
    mappings: list[dict[str, int]] = []
    for port in sorted(ports):
        command = [
            adb,
            "-s",
            device_id,
            "reverse",
            f"tcp:{port}",
            f"tcp:{port}",
        ]
        result = subprocess.run(
            command,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            raise RuntimeError(
                "GATE_BLOCK: failed to configure Android local target port "
                f"reverse tcp:{port}: {detail or result.returncode}",
            )
        mappings.append({"devicePort": port, "hostPort": port})
    return {
        "status": "installed",
        "deviceId": device_id,
        "mappings": mappings,
    }


def _acquire_patrol_consumer_lease(
    args: argparse.Namespace,
    device: dict[str, Any],
    android_port_reverse: dict[str, Any],
    command_env: dict[str, str],
) -> tuple[str, str, str, str] | None:
    """Bind one Android or iOS Simulator Patrol build to its local runtime."""

    target_platform = str(device.get("targetPlatform", "")).strip().lower()
    is_android = target_platform.startswith("android")
    is_ios_simulator = target_platform == "ios" and bool(device.get("emulator", False))
    if not _is_local_target(args.env_name) or not (
        is_android or is_ios_simulator
    ):
        return None
    device_id = str(device.get("id", "")).strip()
    if not device_id:
        raise RuntimeError("GATE_BLOCK: Patrol consumer device identity is missing")
    mappings = android_port_reverse.get("mappings") if is_android else []
    if is_android and not isinstance(mappings, list):
        raise RuntimeError(
            "GATE_BLOCK: Android Patrol must install local port reverse before "
            "acquiring its runtime consumer lease",
        )
    ports = sorted(
        {
            int(mapping.get("devicePort") or 0)
            for mapping in mappings
            if isinstance(mapping, dict) and int(mapping.get("devicePort") or 0) > 0
        }
    )
    if is_android and not ports:
        raise RuntimeError(
            "GATE_BLOCK: Android Patrol local runtime consumer lease has no ports",
        )
    target_name = _local_target_for_environment_alias(args.env_name)
    consumer = f"environment-patrol-{os.getpid()}-{sanitize_device_id(device_id)}"
    lease = acquire_consumer_lease(
        target=target_name,
        device=device_id,
        consumer=consumer,
        package_name=(
            "com.quwoquan.quwoquan_app"
            if is_android
            else "com.example.quwoquanApp"
        ),
        ports=ports,
        platform="android" if is_android else "ios-simulator",
    )
    command_env.update(
        {
            "QWQ_RUN_CONSUMER_ID": consumer,
            "QWQ_CONSUMER_LEASE_ACQUIRED": "1",
        }
    )
    if is_android:
        command_env["QWQ_ANDROID_LOCAL_PORTS"] = ",".join(
            str(port) for port in ports
        )
    return target_name, device_id, consumer, str(lease["leaseId"])


def _reset_release_uat_device_state(
    args: argparse.Namespace,
    device: dict[str, Any],
) -> dict[str, Any]:
    """Guarantee release-bound journeys start without a persisted App session."""
    if not str(getattr(args, "release_uat_cases", "") or "").strip():
        return {"status": "skipped", "reason": "not-release-bound"}
    if args.dry_run:
        return {"status": "planned", "reason": "release-bound-cold-start"}

    device_id = str(device.get("id", "")).strip()
    target = str(device.get("targetPlatform", "")).strip().lower()
    if not device_id:
        raise RuntimeError("release-bound UAT device identity is empty")

    reset_rows: list[dict[str, Any]] = []
    if target == "ios":
        if not bool(device.get("emulator", False)):
            raise RuntimeError(
                "release-bound iOS UAT requires a simulator with resettable App state"
            )
        for bundle_id in IOS_RELEASE_UAT_BUNDLE_IDS:
            command = ["xcrun", "simctl", "uninstall", device_id, bundle_id]
            result = subprocess.run(command, text=True, capture_output=True, check=False)
            output = ((result.stdout or "") + (result.stderr or "")).strip()
            absent = "not installed" in output.lower() or "no such file" in output.lower()
            if result.returncode != 0 and not absent:
                raise RuntimeError(
                    f"release-bound iOS UAT App reset failed for {bundle_id}: "
                    f"{summarize_output(output)}"
                )
            reset_rows.append(
                {
                    "bundleId": bundle_id,
                    "exitCode": result.returncode,
                    "alreadyAbsent": result.returncode != 0,
                }
            )
    elif target.startswith("android"):
        adb = resolve_android_debug_bridge()
        if adb is None:
            raise RuntimeError("release-bound Android UAT requires adb for App state reset")
        package_path_command = [
            str(adb),
            "-s",
            device_id,
            "shell",
            "pm",
            "path",
            ANDROID_RELEASE_UAT_PACKAGE,
        ]
        package_path = subprocess.run(
            package_path_command,
            text=True,
            capture_output=True,
            check=False,
        )
        package_path_output = (
            (package_path.stdout or "") + (package_path.stderr or "")
        ).strip()
        installed = package_path.returncode == 0 and package_path_output.startswith(
            "package:"
        )
        if not installed and package_path.returncode not in (0, 1):
            raise RuntimeError(
                "release-bound Android UAT App presence check failed: "
                f"{summarize_output(package_path_output)}"
            )
        if installed:
            clear_command = [
                str(adb),
                "-s",
                device_id,
                "shell",
                "pm",
                "clear",
                ANDROID_RELEASE_UAT_PACKAGE,
            ]
            clear_result = subprocess.run(
                clear_command,
                text=True,
                capture_output=True,
                check=False,
            )
            clear_output = (
                (clear_result.stdout or "") + (clear_result.stderr or "")
            ).strip()
            if clear_result.returncode != 0 or "success" not in clear_output.lower():
                raise RuntimeError(
                    "release-bound Android UAT App reset failed: "
                    f"{summarize_output(clear_output)}"
                )
        reset_rows.append(
            {
                "package": ANDROID_RELEASE_UAT_PACKAGE,
                "exitCode": 0,
                "alreadyAbsent": not installed,
            }
        )
    else:
        raise RuntimeError(
            f"release-bound UAT does not support non-mobile target platform: {target}"
        )
    return {
        "status": "reset",
        "reason": "release-bound-cold-start",
        "applications": reset_rows,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--target", default=DEFAULT_TARGET)
    parser.add_argument(
        "--remote-api-evidence-report",
        default="",
        help="已通过的 Remote API UAT report；写入同一设备 CaseResult 的 requestId/traceId 证据。",
    )
    parser.add_argument("--timeout-seconds", type=int, default=1200)
    parser.add_argument("--env-name", "--environment-alias", dest="env_name", default="local-gamma")
    parser.add_argument(
        "--rollout-stage",
        choices=("gray-initial", "carry-on", "full"),
        default="",
        help="Prod rollout stage; it is evidence metadata, never a fifth environment.",
    )
    parser.add_argument("--runtime-env", default="")
    parser.add_argument("--api-contract-env", default="")
    parser.add_argument(
        "--candidate-digest",
        default=os.environ.get(
            "QWQ_ACCOUNT_ENFORCEMENT_GAMMA_CANDIDATE_DIGEST", ""
        ).strip(),
        help=(
            "Immutable candidate digest required by the Gamma account-enforcement "
            "physical-device UAT."
        ),
    )
    parser.add_argument("--gateway-base-url", default="")
    parser.add_argument("--product-ops-base-url", default="")
    parser.add_argument("--media-avatar-base-url", default="")
    parser.add_argument("--media-image-base-url", default="")
    parser.add_argument("--media-video-base-url", default="")
    parser.add_argument("--media-upload-base-url", default="")
    parser.add_argument("--rtc-media-connection-url", default="")
    parser.add_argument(
        "--video-playback-canary-work-id",
        default=os.environ.get("VIDEO_PLAYBACK_CANARY_WORK_ID", "").strip(),
    )
    for destination, define_name in RELEASE_APP_UAT_DEFINES:
        parser.add_argument(
            f"--{destination.replace('_', '-')}",
            dest=destination,
            default=os.environ.get(define_name, "").strip(),
        )
    parser.add_argument(
        "--patrol-install-id",
        default=os.environ.get("QWQ_PATROL_INSTALL_ID", "").strip(),
        help=(
            "Optional one-run install identity template. Destructive account-closure "
            "journeys require a {device} placeholder."
        ),
    )
    parser.add_argument(
        "--account-closure-disposable-ack",
        action="store_true",
        help="Acknowledge irreversible closure of the injected disposable prod account.",
    )
    parser.add_argument(
        "--unauthenticated-auth-entry",
        action="store_true",
        help="Run a login Provider journey without preloading an authenticated session.",
    )
    parser.add_argument(
        "--persisted-device-session",
        action="store_true",
        help=(
            "Use the production auth restore path on a pre-provisioned physical "
            "device; valid only for the runtime-recovery UAT target."
        ),
    )
    parser.add_argument("--test-auth-token", default=os.environ.get("TEST_AUTH_TOKEN", "").strip())
    parser.add_argument(
        "--test-refresh-token",
        default=os.environ.get("TEST_REFRESH_TOKEN", "").strip(),
    )
    parser.add_argument(
        "--release-uat-cases",
        default="",
        help="Gamma data-release 生成的 homepage_verification_cases.json；用于 release-bound 实体主页真实消费验证",
    )
    parser.add_argument(
        "--current-owner-id",
        default=os.environ.get("APP_CURRENT_OWNER_ID", "").strip(),
    )
    parser.add_argument(
        "--current-persona-id",
        default=os.environ.get("APP_CURRENT_PERSONA_ID", "").strip(),
    )
    parser.add_argument("--platform", choices=("android", "ios", "all"), default="all")
    parser.add_argument("--device-id", action="append", default=[])
    parser.add_argument(
        "--stackctl-controlled-edge-fault",
        action="store_true",
        help=(
            "Internal app-content-uat mode: stop the receipt-bound local API Edge "
            "and restore it when the Patrol recovery handshake is observed."
        ),
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def _load_release_uat_cases_b64(path_value: str) -> str:
    """Validate a runtime-only Gamma UAT manifest before injecting it into Patrol."""
    path = Path(path_value).expanduser()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"release UAT cases unreadable: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError("release UAT cases must be an object")
    allowed = {
        "schema",
        "environment",
        "releaseId",
        "runId",
        "importerReportRef",
        "generatedAt",
        "cases",
    }
    if set(payload) != allowed:
        raise ValueError("release UAT cases has an invalid field set")
    if payload.get("schema") != "quwoquan_data.homepage_verification_case_manifest":
        raise ValueError("release UAT cases schema is invalid")
    if payload.get("environment") != "gamma":
        raise ValueError("release UAT cases must target gamma")
    for field in ("releaseId", "runId", "importerReportRef", "generatedAt"):
        if not isinstance(payload.get(field), str) or not payload[field].strip():
            raise ValueError(f"release UAT cases {field} is invalid")
    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("release UAT cases must contain at least one case")
    entity_refs: set[str] = set()
    homepage_ids: set[str] = set()
    for index, case in enumerate(cases):
        if not isinstance(case, dict) or set(case) != {"entityRef", "homepageId", "title"}:
            raise ValueError(f"release UAT case {index} has an invalid field set")
        entity_ref = case.get("entityRef")
        homepage_id = case.get("homepageId")
        title = case.get("title")
        if not all(isinstance(value, str) and value.strip() for value in (entity_ref, homepage_id, title)):
            raise ValueError(f"release UAT case {index} has invalid values")
        if entity_ref in entity_refs or homepage_id in homepage_ids:
            raise ValueError(f"release UAT case {index} duplicates entity or homepage identity")
        entity_refs.add(entity_ref)
        homepage_ids.add(homepage_id)
    return base64.b64encode(path.read_bytes()).decode("ascii")


def _redact_command(command: list[str]) -> list[str]:
    secret_defines = {
        "--dart-define=TEST_AUTH_TOKEN=": "--dart-define=TEST_AUTH_TOKEN=<redacted>",
        "--dart-define=TEST_REFRESH_TOKEN=": "--dart-define=TEST_REFRESH_TOKEN=<redacted>",
        "--dart-define=APP_CURRENT_OWNER_ID=": (
            "--dart-define=APP_CURRENT_OWNER_ID=<redacted>"
        ),
        "--dart-define=APP_CURRENT_PERSONA_ID=": (
            "--dart-define=APP_CURRENT_PERSONA_ID=<redacted>"
        ),
        "--dart-define=APP_CURRENT_USER_ID=": (
            "--dart-define=APP_CURRENT_USER_ID=<redacted>"
        ),
    }
    redacted: list[str] = []
    for item in command:
        if item.startswith("--dart-define-from-file="):
            replacement = "--dart-define-from-file=<ephemeral-secret-file>"
        else:
            replacement = next(
                (
                    placeholder
                    for prefix, placeholder in secret_defines.items()
                    if item.startswith(prefix)
                ),
                item,
            )
        redacted.append(replacement)
    return redacted


def _redact_text(output: str, secret_values: tuple[str, ...]) -> str:
    redacted = output
    for value in secret_values:
        if value:
            redacted = redacted.replace(value, "<redacted>")
    return redacted


def summarize_output(output: str, *, max_lines: int = 120) -> str:
    lines = output.splitlines()
    if len(lines) <= max_lines:
        return output
    return "\n".join(
        [
            f"... omitted {len(lines) - max_lines} earlier lines ...",
            *lines[-max_lines:],
        ]
    )


def _read_runtime_recovery_evidence(path: Path) -> dict[str, bool]:
    if not path.is_file():
        return {}
    for line in reversed(path.read_text(encoding="utf-8").splitlines()):
        marker = line.find(RUNTIME_RECOVERY_EVIDENCE_PREFIX)
        if marker < 0:
            continue
        encoded = line[marker + len(RUNTIME_RECOVERY_EVIDENCE_PREFIX) :].strip()
        try:
            payload = json.loads(encoded)
        except json.JSONDecodeError:
            return {}
        if (
            not isinstance(payload, dict)
            or set(payload) != RUNTIME_RECOVERY_EVIDENCE_FIELDS
            or any(not isinstance(value, bool) for value in payload.values())
        ):
            return {}
        return {str(key): bool(value) for key, value in payload.items()}
    return {}


def _read_account_enforcement_evidence(
    path: Path,
    *,
    phase: str,
    candidate_digest: str,
) -> dict[str, Any]:
    if not path.is_file() or phase not in ACCOUNT_ENFORCEMENT_EXPECTED_EVIDENCE:
        return {}
    expected = {
        **ACCOUNT_ENFORCEMENT_EXPECTED_EVIDENCE[phase],
        "candidateDigest": candidate_digest,
    }
    for line in reversed(path.read_text(encoding="utf-8").splitlines()):
        marker = line.find(ACCOUNT_ENFORCEMENT_EVIDENCE_PREFIX)
        if marker < 0:
            continue
        encoded = line[
            marker + len(ACCOUNT_ENFORCEMENT_EVIDENCE_PREFIX) :
        ].strip()
        try:
            payload = json.loads(encoded)
        except json.JSONDecodeError:
            return {}
        if not isinstance(payload, dict) or payload != expected:
            return {}
        return payload
    return {}


def _validate_runtime_recovery_device_matrix(
    args: argparse.Namespace,
    devices: list[dict[str, Any]],
) -> None:
    if not _is_runtime_recovery_target(args) or args.dry_run:
        return
    physical_android = any(
        str(device.get("targetPlatform") or "").lower().startswith("android")
        and not bool(device.get("emulator"))
        for device in devices
    )
    physical_ios = any(
        str(device.get("targetPlatform") or "").lower() == "ios"
        and not bool(device.get("emulator"))
        for device in devices
    )
    if not physical_android or not physical_ios:
        raise RuntimeError(
            "GATE_BLOCK: runtime recovery UAT requires one physical Android "
            "device and one physical iPhone in the same CaseResult matrix"
        )


def _validate_account_enforcement_device_matrix(
    args: argparse.Namespace,
    devices: list[dict[str, Any]],
) -> None:
    if not _is_account_enforcement_target(args) or args.dry_run:
        return
    physical_android = any(
        str(device.get("targetPlatform") or "").lower().startswith("android")
        and not bool(device.get("emulator"))
        for device in devices
    )
    physical_ios = any(
        str(device.get("targetPlatform") or "").lower() == "ios"
        and not bool(device.get("emulator"))
        for device in devices
    )
    if not physical_android or not physical_ios:
        raise RuntimeError(
            "GATE_BLOCK: account-enforcement Gamma UAT requires one physical "
            "Android device and one physical iPhone in the same CaseResult matrix"
        )


def patrol_test_execution_summary(output: str) -> dict[str, Any]:
    """Prefer XCTest's executed-test record over Patrol's known zero summary."""

    xctest = XCTEST_EXECUTION_SUMMARY_PATTERN.search(output)
    if xctest is not None:
        return {
            "framework": "xctest",
            "executed": int(xctest.group("executed")),
            "failed": int(xctest.group("failed")),
        }
    patrol = PATROL_EXECUTION_SUMMARY_PATTERN.search(output)
    if patrol is not None:
        return {
            "framework": "patrol",
            "executed": int(patrol.group("executed")),
            "failed": int(patrol.group("failed")),
        }
    return {"framework": "unknown", "executed": None, "failed": None}


def load_remote_api_evidence(path_value: str) -> dict[str, Any]:
    """Load only a passed search Remote UAT report; no raw query is accepted."""

    normalized = path_value.strip()
    if not normalized:
        return {}
    path = Path(normalized).expanduser()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        evidence = payload["cases"]["searchAndFeedbackRoundtrip"]["evidence"]
        tag_filter = payload["cases"]["tagFilterPositiveAndNegative"]["evidence"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ValueError(
            "remote API evidence report is unreadable or not a search Remote UAT report"
        ) from exc
    if (
        payload.get("schema") != "search-remote-api-uat-report"
        or payload.get("status") != "passed"
        or evidence.get("schema") != "search-remote-api-evidence"
        or evidence.get("status") != "passed"
        or not str(evidence.get("searchRequestId") or "").strip()
        or tag_filter.get("schema") != "search-tag-filter-remote-evidence"
        or tag_filter.get("status") != "passed"
        or tag_filter.get("positiveHitCount") != 1
        or tag_filter.get("negativeHitCount") != 0
    ):
        raise ValueError("remote API evidence report is not a passed search Remote UAT")
    events = evidence.get("events")
    if not isinstance(events, list) or any(
        not isinstance(event, dict)
        or not str(event.get("requestId") or "").strip()
        or not str(event.get("traceId") or "").strip()
        or event.get("succeeded") is not True
        for event in events
    ):
        raise ValueError("remote API evidence report lacks successful requestId/traceId events")
    feedback_events = evidence.get("feedbackEvents")
    if not isinstance(feedback_events, list):
        raise ValueError("remote API evidence report lacks typed feedback events")
    click_events = [
        event
        for event in feedback_events
        if isinstance(event, dict) and event.get("eventType") == "click"
    ]
    dwell_events = [
        event
        for event in feedback_events
        if isinstance(event, dict) and event.get("eventType") == "dwell"
    ]
    if (
        len(click_events) != 1
        or not str(click_events[0].get("objectId") or "").strip()
        or not str(click_events[0].get("target") or "").strip()
        or not isinstance(click_events[0].get("rankPosition"), int)
        or click_events[0]["rankPosition"] <= 0
        or len(dwell_events) != 1
        or not str(dwell_events[0].get("objectId") or "").strip()
        or dwell_events[0].get("dwellMs") != 3000
    ):
        raise ValueError(
            "remote API evidence report must assert one ranked click and 3-second dwell"
        )
    return {
        "reportPath": _output_evidence_ref(path),
        "searchRequestId": evidence["searchRequestId"],
        "events": events,
        "feedbackEvents": feedback_events,
        "tagFilter": tag_filter,
    }


def run_command(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    timeout_seconds: int | None = None,
    log_path: Path | None = None,
    secret_values: tuple[str, ...] = (),
    output_line_handler: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    process: subprocess.Popen[str] | None = None
    try:
        process = subprocess.Popen(
            command,
            cwd=str(cwd),
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        if output_line_handler is None:
            output, _ = process.communicate(timeout=timeout_seconds)
            output = output or ""
            exit_code = process.returncode
            timed_out = False
        else:
            output_queue: queue.Queue[str | None] = queue.Queue()

            def read_output() -> None:
                assert process is not None and process.stdout is not None
                try:
                    for line in process.stdout:
                        output_queue.put(line)
                finally:
                    output_queue.put(None)

            reader = threading.Thread(target=read_output, daemon=True)
            reader.start()
            deadline = (
                time.monotonic() + timeout_seconds
                if timeout_seconds is not None
                else None
            )
            chunks: list[str] = []
            handler_error: Exception | None = None
            timed_out = False
            stream_ended = False
            while not stream_ended:
                if deadline is not None and time.monotonic() >= deadline:
                    timed_out = True
                    break
                wait_seconds = (
                    min(0.25, max(0.01, deadline - time.monotonic()))
                    if deadline is not None
                    else 0.25
                )
                try:
                    line = output_queue.get(timeout=wait_seconds)
                except queue.Empty:
                    if process.poll() is not None and not reader.is_alive():
                        break
                    continue
                if line is None:
                    stream_ended = True
                    continue
                chunks.append(line)
                try:
                    output_line_handler(line)
                except Exception as error:  # noqa: BLE001
                    handler_error = error
                    break
            if timed_out or handler_error is not None:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    process.wait()
            else:
                process.wait()
            reader.join(timeout=10)
            while True:
                try:
                    line = output_queue.get_nowait()
                except queue.Empty:
                    break
                if line is not None:
                    chunks.append(line)
            output = "".join(chunks)
            if handler_error is not None:
                output += f"\ncontrolled output handler failed: {handler_error}\n"
                exit_code = 2
            elif timed_out:
                exit_code = 124
            else:
                exit_code = int(process.returncode or 0)
            if process.stdout is not None:
                process.stdout.close()
    except subprocess.TimeoutExpired:
        if process is not None:
            output = _terminate_process_group(process)
        else:
            output = ""
        exit_code = 124
        timed_out = True
    except KeyboardInterrupt:
        if process is not None:
            _terminate_process_group(process)
        raise
    redacted_output = _redact_text(output, secret_values)
    result = {
        "command": _redact_command(command),
        "cwd": str(cwd),
        "exitCode": exit_code,
        "timedOut": timed_out,
        "durationMs": int((time.monotonic() - started) * 1000),
        "outputSummary": summarize_output(redacted_output),
    }
    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(redacted_output, encoding="utf-8")
        result["logPath"] = repo_relative(log_path)
    return result


def _terminate_process_group(process: subprocess.Popen[str]) -> str:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        output, _ = process.communicate(timeout=10)
        return output or ""
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        output, _ = process.communicate()
        return output or ""


def ios_sdk_version(device: dict[str, Any]) -> tuple[int, int] | None:
    sdk = str(device.get("sdk", "")).strip()
    match = IOS_SDK_VERSION_PATTERN.search(sdk)
    if match is None:
        return None
    major = int(match.group(1))
    minor = int(match.group(2) or 0)
    return (major, minor)


def _enrich_ios_simulator_runtime_versions(
    devices: list[dict[str, Any]],
    *,
    xcrun_path: str | None = None,
    command_runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> list[dict[str, Any]]:
    simulators = [
        device
        for device in devices
        if str(device.get("targetPlatform", "")).strip().lower() == "ios"
        and bool(device.get("emulator", False))
    ]
    if not simulators:
        return devices
    executable = xcrun_path or shutil.which("xcrun")
    if not executable:
        raise RuntimeError(
            "GATE_BLOCK: xcrun is required to resolve the exact iOS Simulator runtime"
        )
    result = command_runner(
        [executable, "simctl", "list", "--json"],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        detail = ((result.stderr or result.stdout) or "unknown simctl failure").strip()
        raise RuntimeError(
            "GATE_BLOCK: cannot resolve iOS Simulator runtimes: " + detail
        )
    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "GATE_BLOCK: simctl returned invalid iOS Simulator runtime JSON"
        ) from exc
    runtime_versions = {
        str(runtime.get("identifier") or "").strip(): str(
            runtime.get("version") or ""
        ).strip()
        for runtime in payload.get("runtimes") or []
        if isinstance(runtime, dict)
        and bool(runtime.get("isAvailable", True))
        and IOS_RUNTIME_VERSION_PATTERN.fullmatch(
            str(runtime.get("version") or "").strip()
        )
    }
    device_versions: dict[str, str] = {}
    raw_devices = payload.get("devices")
    if isinstance(raw_devices, dict):
        for runtime_identifier, runtime_devices in raw_devices.items():
            version = runtime_versions.get(str(runtime_identifier).strip(), "")
            if not version or not isinstance(runtime_devices, list):
                continue
            for device in runtime_devices:
                if not isinstance(device, dict) or not bool(
                    device.get("isAvailable", True)
                ):
                    continue
                device_id = str(device.get("udid") or "").strip()
                if device_id:
                    device_versions[device_id] = version
    enriched: list[dict[str, Any]] = []
    for device in devices:
        if device not in simulators:
            enriched.append(device)
            continue
        device_id = str(device.get("id") or "").strip()
        version = device_versions.get(device_id, "")
        if not version:
            raise RuntimeError(
                "GATE_BLOCK: exact iOS Simulator runtime is unavailable for "
                f"device {device_id or '<empty>'}"
            )
        enriched.append({**device, "runtimeVersion": version})
    return enriched


def patrol_ios_runtime_argument(device: dict[str, Any]) -> str | None:
    """Return Patrol's explicit simulator runtime argument for an iOS device."""
    if str(device.get("targetPlatform", "")).strip().lower() != "ios":
        return None
    if not bool(device.get("emulator", False)):
        return None
    runtime_version = str(device.get("runtimeVersion") or "").strip()
    if runtime_version:
        if not IOS_RUNTIME_VERSION_PATTERN.fullmatch(runtime_version):
            raise ValueError(
                f"invalid iOS simulator runtime version: {runtime_version!r}"
            )
        return f"--ios={runtime_version}"
    version = ios_sdk_version(device)
    if version is None:
        raise ValueError("iOS simulator runtime is missing or unparseable")
    return f"--ios={version[0]}.{version[1]}"


def xcode_ios_simulator_sdk_version() -> tuple[int, int]:
    result = subprocess.run(
        ["xcodebuild", "-showsdks"],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError("xcodebuild -showsdks failed")
    versions = [
        (int(match.group(1)), int(match.group(2) or 0))
        for match in XCODE_IOS_SIMULATOR_SDK_PATTERN.finditer(result.stdout)
    ]
    if not versions:
        raise RuntimeError("Xcode reports no iOS Simulator SDK")
    return max(versions)


def _select_compatible_ios_devices(
    devices: list[dict[str, Any]],
    *,
    simulator_sdk_version: tuple[int, int],
) -> list[dict[str, Any]]:
    simulators = [
        device
        for device in devices
        if str(device.get("targetPlatform", "")).strip().lower() == "ios"
        and bool(device.get("emulator", False))
    ]
    compatible_versions = [
        version
        for device in simulators
        for version in [ios_sdk_version(device)]
        if version is not None and version <= simulator_sdk_version
    ]
    if simulators and not compatible_versions:
        requested = ", ".join(
            sorted({str(device.get("sdk", "")).strip() for device in simulators})
        )
        supported = f"{simulator_sdk_version[0]}.{simulator_sdk_version[1]}"
        raise RuntimeError(
            f"no discovered iOS simulator runtime is compatible with Xcode SDK {supported}: {requested}"
        )
    if not compatible_versions:
        return devices
    selected_version = max(compatible_versions)
    selected = [
        device
        for device in devices
        if not (
            str(device.get("targetPlatform", "")).strip().lower() == "ios"
            and bool(device.get("emulator", False))
        )
        or ios_sdk_version(device) == selected_version
    ]
    patrol_keys: set[tuple[tuple[int, int] | None, str]] = set()
    for device in selected:
        if str(device.get("targetPlatform", "")).strip().lower() != "ios":
            continue
        key = (ios_sdk_version(device), str(device.get("name", "")).strip())
        if key in patrol_keys:
            raise RuntimeError(
                "Patrol cannot select duplicate iOS devices with the same runtime and name: "
                f"{key[1]} iOS {key[0]}"
            )
        patrol_keys.add(key)
    return selected


def _explicit_android_devices(device_ids: list[str]) -> list[dict[str, Any]]:
    """Resolve explicitly selected Android devices directly from ADB.

    A running Flutter development session may hold the Flutter tool lock for a
    long time.  Explicit Patrol destinations do not need global Flutter device
    discovery, so ADB is the narrower and authoritative boundary here.
    """
    requested = tuple(dict.fromkeys(item.strip() for item in device_ids if item.strip()))
    if not requested:
        return []
    adb = resolve_android_debug_bridge()
    result = subprocess.run(
        [adb, "devices", "-l"],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError("adb devices -l failed:\n" + summarize_output(result.stderr or ""))
    inventory: dict[str, dict[str, str]] = {}
    for line in result.stdout.splitlines()[1:]:
        fields = line.split()
        if len(fields) < 2 or fields[1] != "device":
            continue
        properties = {
            key: value
            for field in fields[2:]
            if ":" in field
            for key, value in [field.split(":", 1)]
        }
        inventory[fields[0]] = properties
    missing = [device_id for device_id in requested if device_id not in inventory]
    if missing:
        raise RuntimeError(
            "explicit Android Patrol devices are unavailable: " + ", ".join(missing)
        )
    return [
        {
            "id": device_id,
            "name": inventory[device_id].get("model") or device_id,
            "targetPlatform": _android_target_platform(inventory[device_id]),
            "sdk": inventory[device_id].get("device") or "adb",
            "emulator": device_id.startswith("emulator-"),
            "ephemeral": False,
            "category": "mobile",
        }
        for device_id in requested
    ]


def _android_target_platform(properties: dict[str, str]) -> str:
    descriptor = " ".join(properties.values()).lower()
    if "arm64" in descriptor or "aarch64" in descriptor:
        return "android-arm64"
    if "x86_64" in descriptor or "x64" in descriptor:
        return "android-x64"
    if "x86" in descriptor:
        return "android-x86"
    return "android-arm"


def discover_devices(platform: str, device_ids: list[str]) -> list[dict[str, Any]]:
    allowed_ids = {item for item in device_ids if item}
    if platform == "android" and allowed_ids:
        return _explicit_android_devices(device_ids)
    payload = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "quwoquan_app" / "scripts" / "device" / "discover_flutter_mobile_devices.py"),
        ],
        cwd=str(REPO_ROOT),
        text=True,
        capture_output=True,
        check=False,
    )
    if payload.returncode != 0:
        raise RuntimeError(
            "discover_flutter_mobile_devices.py failed:\n"
            + summarize_output((payload.stdout or "") + (payload.stderr or ""))
        )
    data = json.loads(payload.stdout)
    devices = list(data.get("devices") or [])
    selected: list[dict[str, Any]] = []
    for device in devices:
        target = str(device.get("targetPlatform", "")).lower()
        device_id = str(device.get("id", "")).strip()
        if not device_id:
            continue
        if allowed_ids and device_id not in allowed_ids:
            continue
        if platform == "android" and not target.startswith("android"):
            continue
        if platform == "ios" and target != "ios":
            continue
        if platform == "all" and target != "ios" and not target.startswith("android"):
            continue
        selected.append(device)
    selected = _enrich_ios_simulator_runtime_versions(selected)
    if not allowed_ids and platform in ("ios", "all"):
        selected = _select_compatible_ios_devices(
            selected,
            simulator_sdk_version=xcode_ios_simulator_sdk_version(),
        )
    return selected


def _prepare_execution_session(args: argparse.Namespace) -> str:
    runtime_env = args.runtime_env.strip() or _runtime_env_for_alias(args.env_name)
    _validate_account_closure_execution(args, runtime_env)
    if _uses_persisted_device_session(args):
        if not _is_runtime_recovery_target(args):
            raise ValueError(
                "--persisted-device-session is only valid for runtime recovery UAT"
            )
        supplied = (
            args.test_auth_token,
            args.test_refresh_token,
            _resolved_owner_id(args),
            _resolved_persona_id(args),
        )
        if any(str(value).strip() for value in supplied):
            raise ValueError(
                "persisted-device-session UAT forbids injected auth tokens or actor identities"
            )
        if runtime_env not in {"beta", "gamma"}:
            raise ValueError(
                "runtime recovery persisted-session UAT only accepts beta or gamma"
            )
        return "persisted_device_session"
    if _is_runtime_recovery_target(args):
        raise ValueError(
            "runtime recovery UAT requires --persisted-device-session"
        )
    if bool(getattr(args, "unauthenticated_auth_entry", False)):
        supplied = (
            args.test_auth_token,
            args.test_refresh_token,
            _resolved_owner_id(args),
            _resolved_persona_id(args),
        )
        if any(str(value).strip() for value in supplied):
            raise ValueError(
                "unauthenticated auth-entry Patrol cannot preload a session"
            )
        return "unauthenticated_auth_entry"
    if _uses_public_video_canary_anonymous_session(args):
        return _public_video_canary_session_mode(args)
    if _uses_runtime_anonymous_session(args):
        supplied = {
            "test_auth_token": args.test_auth_token,
            "test_refresh_token": args.test_refresh_token,
            "current_owner_id": _resolved_owner_id(args),
            "current_persona_id": _resolved_persona_id(args),
        }
        if any(str(value).strip() for value in supplied.values()):
            raise ValueError(
                "local Remote Patrol must use device-runtime anonymous login; "
                "do not inject auth tokens or actor identities"
            )
        return _runtime_anonymous_session_mode(args)
    return "provided_remote_session"


def _create_patrol_secret_define_file(args: argparse.Namespace) -> Path:
    fd, raw_path = tempfile.mkstemp(prefix="qwq-patrol-secrets-", suffix=".json")
    path = Path(raw_path)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            definitions = {
                "TEST_AUTH_TOKEN": args.test_auth_token.strip(),
                "TEST_REFRESH_TOKEN": args.test_refresh_token.strip(),
                "APP_CURRENT_OWNER_ID": _resolved_owner_id(args),
                "APP_CURRENT_PERSONA_ID": _resolved_persona_id(args),
                "APP_CURRENT_USER_ID": _resolved_persona_id(args),
            }
            provider_define_keys = tuple(
                key.strip()
                for key in os.environ.get(
                    "QWQ_PROVIDER_UAT_DART_DEFINE_KEYS", ""
                ).split(",")
                if key.strip()
            )
            invalid_provider_keys = [
                key
                for key in provider_define_keys
                if not re.fullmatch(r"QWQ_PROVIDER_UAT_[A-Z0-9_]+", key)
            ]
            if invalid_provider_keys:
                raise ValueError(
                    "Provider UAT Dart define keys must use the "
                    "QWQ_PROVIDER_UAT_* namespace"
                )
            missing_provider_keys = [
                key
                for key in provider_define_keys
                if not os.environ.get(key, "").strip()
            ]
            if missing_provider_keys:
                raise ValueError(
                    "Provider UAT Dart define values are required: "
                    + ", ".join(missing_provider_keys)
                )
            definitions.update(
                {key: os.environ[key].strip() for key in provider_define_keys}
            )
            json.dump(definitions, handle, ensure_ascii=False)
            handle.write("\n")
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return path


def _provider_uat_secret_values() -> tuple[str, ...]:
    keys = tuple(
        key.strip()
        for key in os.environ.get(
            "QWQ_PROVIDER_UAT_DART_DEFINE_KEYS", ""
        ).split(",")
        if key.strip()
    )
    return tuple(
        value
        for value in (os.environ.get(key, "").strip() for key in keys)
        if value
    )


def patrol_command(
    device: dict[str, Any],
    args: argparse.Namespace,
    patrol_executable: str,
    *,
    dart_define_file: Path | None,
) -> list[str]:
    runtime_env = args.runtime_env.strip() or _runtime_env_for_alias(args.env_name)
    api_contract_env = args.api_contract_env.strip() or runtime_env
    base_urls = _effective_base_urls_for_device(args, device)
    gateway_base_url = base_urls["gatewayBaseUrl"]
    product_ops_base_url = base_urls["productOpsBaseUrl"]
    media_avatar_base_url = base_urls["mediaAvatarBaseUrl"]
    media_image_base_url = base_urls["mediaImageBaseUrl"]
    media_video_base_url = base_urls["mediaVideoBaseUrl"]
    media_upload_base_url = base_urls["mediaUploadBaseUrl"]
    rtc_media_connection_url = base_urls["rtcMediaConnectionUrl"]
    legal_base_url = base_urls["legalBaseUrl"]
    video_playback_canary_work_id = str(
        getattr(args, "video_playback_canary_work_id", "") or ""
    ).strip()
    patrol_install_id = str(getattr(args, "patrol_install_id", "") or "").strip()
    _validate_account_closure_execution(args, runtime_env)
    if patrol_install_id:
        patrol_install_id = patrol_install_id.replace(
            "{device}",
            sanitize_device_id(str(device["id"])),
        )
    command = [
        patrol_executable,
        "test",
        "--verbose",
        "-t",
        args.target,
        "-d",
        str(device["id"]),
        "--dart-define=RUN_T4_PATROL=true",
        "--dart-define=REQUIRE_NATIVE_VIDEO_PLAYBACK_SIGNALS="
        + (
            "true"
            if _requires_native_video_playback_signals(device)
            else "false"
        ),
        f"--dart-define=APP_RUNTIME_ENV={runtime_env}",
        f"--dart-define=API_CONTRACT_ENV={api_contract_env}",
        f"--dart-define=CLOUD_GATEWAY_BASE_URL={gateway_base_url}",
        f"--dart-define=APP_LEGAL_BASE_URL={legal_base_url}",
        f"--dart-define=API_CONTRACT_BASE_URL={gateway_base_url}",
        f"--dart-define=API_CONTRACT_PRODUCT_OPS_BASE_URL={product_ops_base_url}",
        f"--dart-define=RTC_MEDIA_CONNECTION_URL={rtc_media_connection_url}",
        f"--dart-define=VIDEO_PLAYBACK_CANARY_WORK_ID={video_playback_canary_work_id}",
    ]
    ios_runtime_argument = patrol_ios_runtime_argument(device)
    if ios_runtime_argument:
        command.append(ios_runtime_argument)
    if patrol_install_id:
        command.append(f"--dart-define=QWQ_PATROL_INSTALL_ID={patrol_install_id}")
    if _requires_account_closure(args) and runtime_env == "prod":
        command.append(
            "--dart-define=QWQ_ACCOUNT_CLOSURE_DISPOSABLE_ACK=true"
        )
    if _is_account_enforcement_target(args):
        command.append(
            "--dart-define=QWQ_ACCEPTANCE_CANDIDATE_DIGEST="
            + str(getattr(args, "candidate_digest", "") or "").strip()
        )
    if _uses_public_video_canary_anonymous_session(args):
        command.append(
            "--dart-define=QWQ_PATROL_SESSION_MODE="
            f"{_public_video_canary_session_mode(args)}"
        )
    elif _uses_runtime_anonymous_session(args):
        command.append(
            "--dart-define=QWQ_PATROL_SESSION_MODE="
            f"{_runtime_anonymous_session_mode(args)}"
        )
    elif _uses_persisted_device_session(args):
        pass
    else:
        if dart_define_file is None:
            raise ValueError("remote Patrol session requires a private Dart define file")
        command.extend(
            [
                f"--dart-define-from-file={dart_define_file}",
            ]
        )
    # Patrol 4.4 uses Xcode's SDK when `--ios` is omitted.  That is not the
    # booted simulator runtime, so always pass the runtime parsed from device
    # discovery and let Xcode resolve the destination against that device.
    if media_avatar_base_url or media_image_base_url or media_video_base_url or media_upload_base_url:
        command.extend(
            [
                f"--dart-define=MEDIA_AVATAR_CDN_BASE_URL={media_avatar_base_url}",
                f"--dart-define=MEDIA_IMAGE_CDN_BASE_URL={media_image_base_url}",
                f"--dart-define=MEDIA_VIDEO_CDN_BASE_URL={media_video_base_url}",
                f"--dart-define=MEDIA_UPLOAD_BASE_URL={media_upload_base_url}",
            ]
        )
    release_uat_cases_b64 = str(getattr(args, "release_uat_cases_b64", "") or "")
    if release_uat_cases_b64:
        command.append(f"--dart-define=QWQ_RELEASE_HOMEPAGE_UAT_CASES_B64={release_uat_cases_b64}")
    if Path(args.target).name == Path(CORE_READBACK_TARGET).name:
        release_defines = {
            define_name: str(getattr(args, destination, "") or "").strip()
            for destination, define_name in RELEASE_APP_UAT_DEFINES
        }
        missing = sorted(
            name for name, value in release_defines.items() if not value
        )
        if missing:
            raise ValueError(
                "app core readback requires one immutable release envelope: "
                + ", ".join(missing)
            )
        command.extend(
            f"--dart-define={name}={value}"
            for name, value in release_defines.items()
        )
    return command


def _output_evidence_ref(path: Path) -> str:
    """Expose runtime output references relative to QWQ_OUTPUT_ROOT, not repo root."""
    relative = repo_relative(path)
    prefix = ".qwq_output/"
    return relative[len(prefix) :] if relative.startswith(prefix) else relative


def ensure_patrol_ios_products_bridge() -> None:
    """Bridge Patrol's expected ios_integ products path to Xcode 26 global products."""
    patrol_products = PATROL_IOS_PRODUCTS_DIR
    patrol_products.parent.mkdir(parents=True, exist_ok=True)
    if patrol_products.is_symlink():
        try:
            if patrol_products.resolve() == XCODE_GLOBAL_PRODUCTS_DIR.resolve():
                return
        except FileNotFoundError:
            patrol_products.unlink()
    elif patrol_products.exists():
        return
    patrol_products.symlink_to(XCODE_GLOBAL_PRODUCTS_DIR)


def dry_run_devices(args: argparse.Namespace) -> list[dict[str, Any]]:
    raw_ids = args.device_id or ["dry-run-device"]
    devices = []
    for device_id in raw_ids:
        target_platform = "ios" if args.platform == "ios" else "android-arm64"
        if args.platform == "all":
            target_platform = "ios"
        devices.append(
            {
                "id": device_id,
                "name": "Dry Run Device",
                "targetPlatform": target_platform,
                "sdk": "dry-run",
                "emulator": True,
                "screenClass": "phone",
            }
        )
    return devices


def write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _missing_required_args(args: argparse.Namespace) -> list[str]:
    required = [
        ("gateway_base_url", args.gateway_base_url),
        ("product_ops_base_url", args.product_ops_base_url),
        ("media_avatar_base_url", getattr(args, "media_avatar_base_url", "")),
        ("media_image_base_url", getattr(args, "media_image_base_url", "")),
        ("media_video_base_url", getattr(args, "media_video_base_url", "")),
        ("media_upload_base_url", getattr(args, "media_upload_base_url", "")),
        (
            "rtc_media_connection_url",
            getattr(args, "rtc_media_connection_url", ""),
        ),
    ]
    if _requires_video_playback_canary(args):
        required.append(
            (
                "video_playback_canary_work_id",
                getattr(args, "video_playback_canary_work_id", ""),
            )
        )
    if not (
        bool(getattr(args, "unauthenticated_auth_entry", False)) or
        _uses_runtime_anonymous_session(args) or
        _uses_public_video_canary_anonymous_session(args) or
        _uses_persisted_device_session(args)
    ):
        required.extend(
            [
                ("test_auth_token", args.test_auth_token),
                ("test_refresh_token", args.test_refresh_token),
                ("current_owner_id", _resolved_owner_id(args)),
                ("current_persona_id", _resolved_persona_id(args)),
            ]
        )
    return [name for name, value in required if not str(value).strip()]


def main() -> int:
    args = parse_args()
    report_path = Path(args.report)
    if not report_path.is_absolute():
        report_path = REPO_ROOT / report_path
    execution_lock = None
    runtime_use_lock = None
    if not args.dry_run:
        try:
            execution_lock = _acquire_patrol_execution_lock(
                env_name=args.env_name,
                target=args.target,
            )
            atexit.register(execution_lock.close)
            if _is_local_target(args.env_name):
                runtime_use_lock = acquire_local_runtime_use_lock(
                    target=_local_target_for_environment_alias(args.env_name),
                    purpose="environment-patrol-smoke",
                )
                atexit.register(runtime_use_lock.close)
        except RuntimeError as exc:
            if runtime_use_lock is not None:
                runtime_use_lock.close()
            if execution_lock is not None:
                execution_lock.close()
            print(f"GATE_BLOCK: {exc}", file=sys.stderr)
            return 2

    runtime_env = args.runtime_env.strip() or _runtime_env_for_alias(args.env_name)
    api_contract_env = args.api_contract_env.strip() or runtime_env
    report: dict[str, Any] = {
        "suiteId": "environment_page_smoke",
        "status": "failed",
        "startedAt": utc_now(),
        "endedAt": "",
        "environmentAlias": args.env_name,
        "rolloutStage": getattr(args, "rollout_stage", ""),
        "runtimeEnv": runtime_env,
        "apiContractEnv": api_contract_env,
        "composition": "production_remote",
        "evidenceClass": _evidence_class_for_runtime(runtime_env),
        "target": args.target,
        "platform": args.platform,
        "gatewayBaseUrl": args.gateway_base_url,
        "productOpsBaseUrl": args.product_ops_base_url,
        "rtcMediaConnectionUrl": args.rtc_media_connection_url,
        **_resolved_media_base_urls(args),
        "videoPlaybackCanaryWorkId": str(
            getattr(args, "video_playback_canary_work_id", "") or ""
        ).strip(),
        "accountClosureDisposableAck": (
            bool(getattr(args, "account_closure_disposable_ack", False))
            if _requires_account_closure(args)
            else False
        ),
        "persistedDeviceSession": _uses_persisted_device_session(args),
        "candidateDigest": str(getattr(args, "candidate_digest", "") or "").strip(),
        "controlledEdgeFault": {
            "requested": bool(getattr(args, "stackctl_controlled_edge_fault", False)),
            "receipt": {},
        },
        "controlledSubjectDigest": _account_enforcement_subject_digest(args),
        "hasCurrentOwnerIdentity": bool(_resolved_owner_id(args)),
        "hasCurrentPersonaIdentity": bool(_resolved_persona_id(args)),
        "sessionSource": "",
        "releaseUatCasesPath": "",
        "remoteApiEvidence": {},
        "devices": [],
        "runs": [],
        "caseResults": [],
        "failureReason": "",
        "deviceInventoryPath": "",
        "evidenceRoot": "",
    }
    if bool(getattr(args, "stackctl_controlled_edge_fault", False)):
        controlled_edge_issues: list[str] = []
        if not _is_controlled_edge_fault_target(args):
            controlled_edge_issues.append(
                "controlled edge fault requires the canonical feed recovery Patrol target"
            )
        if _local_target_for_environment_alias(args.env_name) not in {
            "alpha-local",
            "beta-local",
            "gamma-local",
        }:
            controlled_edge_issues.append(
                "controlled edge fault accepts only Alpha/Beta/Gamma local targets"
            )
        if len([item for item in args.device_id if str(item).strip()]) != 1:
            controlled_edge_issues.append(
                "controlled edge fault requires exactly one explicit device"
            )
        if controlled_edge_issues:
            report["status"] = "gate_block"
            report["failureReason"] = "; ".join(controlled_edge_issues)
            report["endedAt"] = utc_now()
            write_report(report_path, report)
            return 2
    if _is_account_enforcement_target(args):
        account_enforcement_issues = []
        if args.dry_run:
            account_enforcement_issues.append(
                "account-enforcement Gamma UAT forbids dry-run evidence"
            )
        if runtime_env != "gamma" or api_contract_env != "gamma":
            account_enforcement_issues.append(
                "account-enforcement UAT requires Gamma runtime and Gamma API contract"
            )
        if ACCOUNT_ENFORCEMENT_CANDIDATE_DIGEST_PATTERN.fullmatch(
            report["candidateDigest"]
        ) is None:
            account_enforcement_issues.append(
                "account-enforcement UAT requires a canonical immutable candidate digest"
            )
        if account_enforcement_issues:
            report["status"] = "gate_block"
            report["failureReason"] = "; ".join(account_enforcement_issues)
            report["endedAt"] = utc_now()
            write_report(report_path, report)
            return 2
    try:
        report["remoteApiEvidence"] = load_remote_api_evidence(
            str(getattr(args, "remote_api_evidence_report", "") or "")
        )
    except ValueError as exc:
        report["status"] = "gate_block"
        report["failureReason"] = str(exc)
        report["endedAt"] = utc_now()
        write_report(report_path, report)
        return 2
    if not args.dry_run:
        try:
            report["sessionSource"] = _prepare_execution_session(args)
        except Exception as exc:  # noqa: BLE001
            report["status"] = "gate_block"
            report["failureReason"] = str(exc)
            report["endedAt"] = utc_now()
            write_report(report_path, report)
            return 2
        report["hasCurrentOwnerIdentity"] = bool(_resolved_owner_id(args))
        report["hasCurrentPersonaIdentity"] = bool(
            _resolved_persona_id(args)
        )
    else:
        report["sessionSource"] = "dry_run"
    patrol_resolution = resolve_patrol_cli()
    patrol_executable = patrol_resolution.executable or "patrol"
    report["patrolCli"] = patrol_resolution.as_report(required=not args.dry_run)

    if args.release_uat_cases:
        try:
            args.release_uat_cases_b64 = _load_release_uat_cases_b64(args.release_uat_cases)
        except ValueError as exc:
            report["status"] = "gate_block"
            report["failureReason"] = str(exc)
            report["endedAt"] = utc_now()
            write_report(report_path, report)
            return 2
        report["releaseUatCasesPath"] = _output_evidence_ref(Path(args.release_uat_cases).expanduser())
    else:
        args.release_uat_cases_b64 = ""

    if not args.dry_run:
        if patrol_resolution.executable is None:
            report["status"] = "gate_block"
            report["failureReason"] = patrol_resolution.error
            report["endedAt"] = utc_now()
            write_report(report_path, report)
            return 2
        missing = _missing_required_args(args)
        if missing:
            report["status"] = "gate_block"
            report["failureReason"] = f"missing required args: {', '.join(missing)}"
            report["endedAt"] = utc_now()
            write_report(report_path, report)
            return 2
        if _requires_video_playback_canary(args):
            try:
                args.video_playback_canary_work_id = (
                    _validate_video_playback_canary_work_id(args, runtime_env)
                )
            except ValueError as exc:
                report["status"] = "gate_block"
                report["failureReason"] = str(exc)
                report["endedAt"] = utc_now()
                write_report(report_path, report)
                return 2

    try:
        devices = dry_run_devices(args) if args.dry_run else discover_devices(args.platform, args.device_id)
    except Exception as exc:  # noqa: BLE001
        report["status"] = "failed"
        report["failureReason"] = str(exc)
        report["endedAt"] = utc_now()
        write_report(report_path, report)
        return 1

    if not devices:
        report["status"] = "gate_block"
        report["failureReason"] = "no mobile Flutter devices available on self-hosted Mac runner"
        report["endedAt"] = utc_now()
        write_report(report_path, report)
        return 2
    try:
        _validate_runtime_recovery_device_matrix(args, devices)
        _validate_account_enforcement_device_matrix(args, devices)
    except RuntimeError as exc:
        report["status"] = "gate_block"
        report["failureReason"] = str(exc)
        report["devices"] = devices
        report["endedAt"] = utc_now()
        write_report(report_path, report)
        return 2

    report["devices"] = devices
    evidence_root = report_path.parent / "runs"
    report["evidenceRoot"] = repo_relative(evidence_root)
    report["deviceInventoryPath"] = write_discovered_devices_snapshot(
        report_path.parent / "discovered_devices.json",
        devices,
        suite="environment-page-smoke",
        requested_environments=[args.env_name],
        extra={
            "target": args.target,
            "runtimeEnv": runtime_env,
            "platform": args.platform,
            "reportPath": repo_relative(report_path),
        },
    )
    failed = False
    gate_blocked = False
    for device in devices:
        run_dir = evidence_root / sanitize_device_id(str(device.get("id", "")))
        run_dir.mkdir(parents=True, exist_ok=True)
        device_manifest_path = write_device_manifest(
            run_dir / "device.json",
            device,
            env_name=args.env_name,
            suite="environment-page-smoke",
            extra={"target": args.target, "runtimeEnv": runtime_env},
        )
        if (
            not args.dry_run
            and str(device.get("targetPlatform", "")).lower() == "ios"
        ):
            ensure_patrol_ios_products_bridge()
        tls_trust = _local_tls_trust_evidence(dry_run=args.dry_run)
        android_port_reverse = {"status": "skipped", "reason": "not-required"}
        if (
            not args.dry_run
            and str(device.get("targetPlatform", "")).lower().startswith("android")
        ):
            try:
                android_port_reverse = _prepare_android_local_port_reverse(
                    args,
                    device,
                )
            except RuntimeError as exc:
                android_port_reverse = {
                    "status": "failed",
                    "reason": str(exc),
                }
                report["runs"].append(
                    {
                        "device": device,
                        "exitCode": 2,
                        "timedOut": False,
                        "durationMs": 0,
                        "outputSummary": str(exc),
                        "preflightFailed": True,
                        "evidence": {
                            "runDirectory": repo_relative(run_dir),
                            "deviceManifestPath": device_manifest_path,
                            "localTlsTrust": tls_trust,
                            "androidPortReverse": android_port_reverse,
                        },
                    }
                )
                failed = True
                gate_blocked = True
                continue
        try:
            release_uat_state_reset = _reset_release_uat_device_state(args, device)
        except RuntimeError as exc:
            release_uat_state_reset = {"status": "failed", "reason": str(exc)}
            report["runs"].append(
                {
                    "device": device,
                    "exitCode": 2,
                    "timedOut": False,
                    "durationMs": 0,
                    "outputSummary": str(exc),
                    "preflightFailed": True,
                    "evidence": {
                        "runDirectory": repo_relative(run_dir),
                        "deviceManifestPath": device_manifest_path,
                        "localTlsTrust": tls_trust,
                        "androidPortReverse": android_port_reverse,
                        "releaseUatStateReset": release_uat_state_reset,
                    },
                }
            )
            failed = True
            gate_blocked = True
            continue
        secret_define_path: Path | None = None
        if args.dry_run:
            secret_define_path = run_dir / "dry-run-patrol-secrets.json"
        elif not (
            _uses_runtime_anonymous_session(args)
            or _uses_persisted_device_session(args)
        ):
            secret_define_path = _create_patrol_secret_define_file(args)
        command = patrol_command(
            device,
            args,
            patrol_executable,
            dart_define_file=secret_define_path,
        )
        command_env = _device_command_env(args, device)
        consumer_lease: tuple[str, str, str, str] | None = None
        if not args.dry_run:
            consumer_lease = _acquire_patrol_consumer_lease(
                args,
                device,
                android_port_reverse,
                command_env,
            )
        command_path = write_json(
            run_dir / "command.json",
            {
                "capturedAt": utc_now(),
                "target": args.target,
                "deviceId": device["id"],
                "command": _redact_command(command),
                "environment": {},
                "androidPortReverse": android_port_reverse,
                "releaseUatStateReset": release_uat_state_reset,
            },
        )
        before_screenshot = (
            {"status": "skipped", "reason": "dry-run"}
            if args.dry_run
            else capture_device_screenshot(device, run_dir / "before.png")
        )
        print(
            f"[environment-page-smoke] run {args.env_name} on "
            f"{device['name']} ({device['id']}, {device['targetPlatform']})",
            flush=True,
        )
        if args.dry_run:
            log_path = run_dir / "patrol.log"
            log_path.write_text("dry-run\n", encoding="utf-8")
            result = {
                "command": _redact_command(command),
                "cwd": str(APP_DIR),
                "exitCode": 0,
                "timedOut": False,
                "durationMs": 0,
                "outputSummary": "dry-run",
                "logPath": repo_relative(log_path),
            }
            if bool(getattr(args, "stackctl_controlled_edge_fault", False)):
                report["controlledEdgeFault"]["receipt"] = {
                    "status": "planned",
                    "target": _local_target_for_environment_alias(args.env_name),
                    "services": list(CONTROLLED_EDGE_SERVICES),
                }
        else:
            controlled_fault: ControlledEdgeFault | None = None
            restore_request_count = 0
            restore_error = ""

            def handle_controlled_edge_output(line: str) -> None:
                nonlocal restore_request_count
                marker = line.find(CONTROLLED_EDGE_RESTORE_REQUEST_PREFIX)
                if marker < 0:
                    return
                encoded = line[
                    marker + len(CONTROLLED_EDGE_RESTORE_REQUEST_PREFIX) :
                ].strip()
                try:
                    payload = json.loads(encoded)
                except json.JSONDecodeError as error:
                    raise RuntimeError(
                        "controlled edge restore request is not valid JSON"
                    ) from error
                if (
                    not isinstance(payload, dict)
                    or payload.get("environment") != runtime_env
                    or payload.get("observed") is not True
                    or payload.get("blockedRetryCount") != 5
                ):
                    raise RuntimeError(
                        "controlled edge restore request identity is invalid"
                    )
                restore_request_count += 1
                if restore_request_count != 1 or controlled_fault is None:
                    raise RuntimeError(
                        "controlled edge restore request must occur exactly once"
                    )
                report["controlledEdgeFault"]["receipt"] = (
                    controlled_fault.restore()
                )

            try:
                if bool(getattr(args, "stackctl_controlled_edge_fault", False)):
                    controlled_fault = begin_controlled_edge_fault(
                        _local_target_for_environment_alias(args.env_name)
                    )
                    report["controlledEdgeFault"]["receipt"] = (
                        controlled_fault.receipt()
                    )
                try:
                    result = run_command(
                        command,
                        cwd=APP_DIR,
                        env=command_env,
                        timeout_seconds=args.timeout_seconds,
                        log_path=run_dir / "patrol.log",
                        secret_values=(
                            args.test_auth_token.strip(),
                            args.test_refresh_token.strip(),
                            _resolved_owner_id(args),
                            _resolved_persona_id(args),
                            *_provider_uat_secret_values(),
                        ),
                        output_line_handler=(
                            handle_controlled_edge_output
                            if controlled_fault is not None
                            else None
                        ),
                    )
                except Exception as error:  # noqa: BLE001
                    result = {
                        "command": _redact_command(command),
                        "cwd": str(APP_DIR),
                        "exitCode": 2,
                        "timedOut": False,
                        "durationMs": 0,
                        "outputSummary": f"controlled edge UAT failed: {error}",
                        "logPath": repo_relative(run_dir / "patrol.log"),
                    }
            except Exception as error:  # noqa: BLE001
                result = {
                    "command": _redact_command(command),
                    "cwd": str(APP_DIR),
                    "exitCode": 2,
                    "timedOut": False,
                    "durationMs": 0,
                    "outputSummary": f"controlled edge setup failed: {error}",
                    "logPath": repo_relative(run_dir / "patrol.log"),
                }
            finally:
                if controlled_fault is not None and not controlled_fault.restored:
                    try:
                        report["controlledEdgeFault"]["receipt"] = (
                            controlled_fault.restore()
                        )
                    except Exception as error:  # noqa: BLE001
                        restore_error = str(error)
                if consumer_lease is not None:
                    release_consumer_lease(
                        target=consumer_lease[0],
                        device=consumer_lease[1],
                        consumer=consumer_lease[2],
                    )
                if secret_define_path is not None:
                    secret_define_path.unlink(missing_ok=True)
            if restore_error:
                result["exitCode"] = 2
                result["outputSummary"] = (
                    str(result.get("outputSummary") or "")
                    + "\ncontrolled edge fail-safe restore failed: "
                    + restore_error
                ).strip()
            if controlled_fault is not None and restore_request_count != 1:
                result["exitCode"] = 1
                result["outputSummary"] = (
                    str(result.get("outputSummary") or "")
                    + "\ncontrolled edge UAT did not emit exactly one restore request"
                ).strip()
        after_screenshot = (
            capture_device_screenshot(device, run_dir / "after.png")
            if result["exitCode"] == 0 and not args.dry_run
            else {"status": "skipped", "reason": "command failed"}
        )
        failure_screenshot = (
            capture_device_screenshot(device, run_dir / "failure.png")
            if result["exitCode"] != 0 and not args.dry_run
            else {"status": "skipped", "reason": "command passed"}
        )
        result["device"] = device
        raw_log_path = run_dir / "patrol.log"
        result["testExecution"] = patrol_test_execution_summary(
            raw_log_path.read_text(encoding="utf-8")
            if raw_log_path.is_file()
            else ""
        )
        runtime_recovery_evidence = _read_runtime_recovery_evidence(
            raw_log_path,
        )
        feed_content_evidence = _read_feed_content_evidence(raw_log_path)
        controlled_edge_fault_evidence = _read_controlled_edge_fault_evidence(
            raw_log_path
        )
        controlled_edge_log = (
            raw_log_path.read_text(encoding="utf-8")
            if raw_log_path.is_file()
            else ""
        )
        controlled_edge_runtime_errors = [
            token
            for token in (
                "[bootstrap] source=zone_guarded exception=",
                "feed recovery did not leave blocking error",
            )
            if token in controlled_edge_log
        ]
        account_enforcement_phase = _account_enforcement_phase(args)
        account_enforcement_evidence = _read_account_enforcement_evidence(
            raw_log_path,
            phase=account_enforcement_phase,
            candidate_digest=report["candidateDigest"],
        )
        if _is_runtime_recovery_target(args) and (
            set(runtime_recovery_evidence) != RUNTIME_RECOVERY_EVIDENCE_FIELDS
            or not all(runtime_recovery_evidence.values())
        ):
            result["exitCode"] = 1
            result["outputSummary"] = (
                str(result.get("outputSummary") or "")
                + "\nruntime recovery UAT did not emit a complete passed evidence marker"
            ).strip()
        if (
            _is_feed_load_target(args)
            and not args.dry_run
            and not feed_content_evidence
        ):
            result["exitCode"] = 1
            result["outputSummary"] = (
                str(result.get("outputSummary") or "")
                + "\nfeed UAT did not emit a release-bound visible-card evidence marker"
            ).strip()
        if _is_account_enforcement_target(args) and not account_enforcement_evidence:
            result["exitCode"] = 1
            result["outputSummary"] = (
                str(result.get("outputSummary") or "")
                + "\naccount-enforcement UAT did not emit its exact passed evidence marker"
            ).strip()
        controlled_edge_receipt = report["controlledEdgeFault"].get("receipt")
        if (
            _is_controlled_edge_fault_target(args)
            and bool(getattr(args, "stackctl_controlled_edge_fault", False))
            and not args.dry_run
            and (
                not controlled_edge_fault_evidence
                or not isinstance(controlled_edge_receipt, dict)
                or controlled_edge_receipt.get("status") != "restored"
                or bool(controlled_edge_runtime_errors)
            )
        ):
            result["exitCode"] = 1
            result["outputSummary"] = (
                str(result.get("outputSummary") or "")
                + "\ncontrolled edge UAT lacks complete copy and same-install recovery evidence"
                + (
                    "; forbidden runtime errors="
                    + ",".join(controlled_edge_runtime_errors)
                    if controlled_edge_runtime_errors
                    else ""
                )
            ).strip()
        result["evidence"] = {
            "runDirectory": repo_relative(run_dir),
            "deviceManifestPath": device_manifest_path,
            "commandPath": command_path,
            "rawLogPath": result.get("logPath", ""),
            "videoPlayback": _read_video_playback_evidence(
                run_dir / "patrol.log",
            ),
            "feedContent": feed_content_evidence,
            "controlledEdgeFault": controlled_edge_fault_evidence,
            "controlledEdgeFaultReceipt": controlled_edge_receipt or {},
            "beforeScreenshot": before_screenshot,
            "afterScreenshot": after_screenshot,
            "failureScreenshot": failure_screenshot,
            "localTlsTrust": tls_trust,
            "androidPortReverse": android_port_reverse,
            "releaseUatStateReset": release_uat_state_reset,
            "consumerLease": (
                {
                    "target": consumer_lease[0],
                    "deviceId": consumer_lease[1],
                    "consumer": consumer_lease[2],
                    "leaseId": consumer_lease[3],
                    "releasedAfterRun": True,
                }
                if consumer_lease is not None
                else {"status": "not-required"}
            ),
            "runtimeRecovery": runtime_recovery_evidence,
            "accountEnforcement": account_enforcement_evidence,
        }
        report["runs"].append(result)
        report["caseResults"].append(
            {
                "caseId": (
                    f"patrol:{args.target}:{sanitize_device_id(str(device.get('id', '')))}"
                ),
                "status": "passed" if result["exitCode"] == 0 else "failed",
                "deviceId": device.get("id", ""),
                "testExecution": result["testExecution"],
                "evidence": {
                    "commandPath": command_path,
                    "patrolLogPath": result.get("logPath", ""),
                    "remoteApi": report["remoteApiEvidence"],
                    "runtimeRecovery": runtime_recovery_evidence,
                    "accountEnforcement": account_enforcement_evidence,
                    "controlledEdgeFault": controlled_edge_fault_evidence,
                },
            }
        )
        failed = failed or result["exitCode"] != 0

    report["status"] = "gate_block" if gate_blocked else ("failed" if failed else "passed")
    if failed:
        report["failureReason"] = (
            "local TLS preflight blocked one or more Patrol runs"
            if gate_blocked
            else "one or more Patrol runs failed"
        )
    report["endedAt"] = utc_now()
    write_report(report_path, report)
    return 2 if gate_blocked else (1 if failed else 0)


if __name__ == "__main__":
    raise SystemExit(main())
