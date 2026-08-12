#!/usr/bin/env python3
"""Run page-level Patrol smoke tests for one environment target."""

from __future__ import annotations

import argparse
import atexit
import base64
import datetime as dt
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
import zipfile
from dataclasses import dataclass
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
from quwoquan_ops.cli.lib.patrol_execution_lock import (
    PATROL_EXECUTION_LOCK,
    acquire_patrol_execution_lock as _acquire_patrol_execution_lock,
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
from quwoquan_ops.cli.lib.test_live_content_binding import (
    load_test_live_content_binding,
)
from quwoquan_ops.cli.lib.test_live_startup_attempt_receipt import (
    load_test_live_startup_attempt,
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
    VIDEO_PLAYBACK_EVIDENCE_MARKER,
    read_native_video_playback_evidence,
)


APP_DIR = REPO_ROOT / "quwoquan_app"
APP_LAUNCHER_HANDOFF_BUILDER = (
    APP_DIR / "scripts" / "device" / "build_launcher_handoff.py"
)
PATROL_TEST_DIRECTORY = "test/user_acceptance/patrol"
DEFAULT_REPORT = REPO_ROOT / ".qwq_output" / "env" / "repo" / "runs" / "device-matrix" / "environment-smoke" / "report.json"
DEFAULT_TARGET = (
    "test/user_acceptance/journeys/home_video_playback/"
    "video_playback_canary__user_acceptance_test.dart"
)
HOME_VIDEO_PLAYBACK_TARGET = (
    "test/user_acceptance/journeys/home_video_playback/"
    "home_video_playback__user_acceptance_test.dart"
)
CORE_READBACK_TARGET = (
    "test/user_acceptance/journeys/app_startup/"
    "app_core_readback__user_acceptance_test.dart"
)
FEED_LOAD_TARGET = (
    "test/user_acceptance/service/content_service/content/feed_delivery_page/"
    "feed_load__user_acceptance_test.dart"
)
FEED_CONTENT_EVIDENCE_PREFIX = "QWQ_FEED_CONTENT_EVIDENCE "
CONTROLLED_EDGE_FAULT_TARGET = (
    "test/user_acceptance/service/content_service/content/feed_delivery_page/"
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
    ("data_release_creator_user_handle", "DATA_RELEASE_CREATOR_USER_HANDLE"),
    ("data_release_creator_persona_id", "DATA_RELEASE_CREATOR_PERSONA_ID"),
    (
        "data_release_creator_avatar_asset_id",
        "DATA_RELEASE_CREATOR_AVATAR_ASSET_ID",
    ),
    ("data_release_tag_label", "DATA_RELEASE_TAG_LABEL"),
    ("data_release_video_attribution", "DATA_RELEASE_VIDEO_ATTRIBUTION"),
)
BASIC_VIABILITY_TARGET = (
    "test/user_acceptance/journeys/app_startup/"
    "basic_viability__user_acceptance_test.dart"
)
ACCOUNT_CLOSURE_TARGET = (
    "test/user_acceptance/service/user_service/account/user_account/"
    "account_closure_remote__user_acceptance_test.dart"
)
RUNTIME_RECOVERY_TARGET = (
    "test/user_acceptance/journeys/app_startup/"
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
        "test/user_acceptance/journeys/account_enforcement/"
        "account_enforcement_suspended__user_acceptance_test.dart"
    ),
    "restored": (
        "test/user_acceptance/journeys/account_enforcement/"
        "account_enforcement_restored__user_acceptance_test.dart"
    ),
}
ACCOUNT_ENFORCEMENT_EVIDENCE_PREFIX = "QWQ_ACCOUNT_ENFORCEMENT_EVIDENCE "
ACCOUNT_ENFORCEMENT_CANDIDATE_DIGEST_PATTERN = re.compile(
    r"^sha256:[0-9a-f]{64}$"
)
CANONICAL_DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
PROVIDER_CONFORMANCE_RUNTIME_IDENTITY_ENV = (
    "QWQ_PROVIDER_CONFORMANCE_RUNTIME_IDENTITY"
)
PROVIDER_CONFORMANCE_RUNTIME_IDENTITY_SCHEMA = (
    "stackctl.provider_conformance_runtime_identity.v1"
)
PROVIDER_CONFORMANCE_RUNTIME_IDENTITY_COMMON_FIELDS = frozenset(
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
PROVIDER_CONFORMANCE_RUNTIME_IDENTITY_IMMUTABLE_FIELDS = frozenset(
    {"candidateDigest"}
)
PROVIDER_CONFORMANCE_RUNTIME_IDENTITY_MUTABLE_FIELDS = frozenset(
    {
        "mutableComposeDigest",
        "mutableConfigurationDigest",
        "mutableStateDigest",
        "mutableWorkspaceStatusDigest",
        "mutableResolverHandoffDigest",
        "mutableSourceRevision",
    }
)
CANONICAL_TEST_LIVE_DART_DEFINE_KEYS = frozenset(
    {
        "APP_RUNTIME_ENV",
        "QWQ_APP_LAUNCH_MODE",
        "APP_LAUNCH_POLICY",
        "CONTENT_BINDING_STATE",
        "CLOUD_GATEWAY_BASE_URL",
        "APP_LEGAL_BASE_URL",
        "PUBLIC_WEB_BASE_URL",
        "APP_DOWNLOAD_BASE_URL",
        "MEDIA_AVATAR_CDN_BASE_URL",
        "MEDIA_IMAGE_CDN_BASE_URL",
        "MEDIA_VIDEO_CDN_BASE_URL",
        "MEDIA_UPLOAD_BASE_URL",
        "RTC_MEDIA_CONNECTION_URL",
    }
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
    r"Executed\s+(?P<executed>\d+)\s+tests?,\s+with\s+"
    r"(?:(?P<skipped>\d+)\s+tests?\s+skipped\s+and\s+)?"
    r"(?P<failed>\d+)\s+failures?",
)
PATROL_EXECUTION_SUMMARY_PATTERN = re.compile(
    r"📝\s+Total:\s*(?P<executed>\d+).*?"
    r"❌\s+Failed:\s*(?P<failed>\d+).*?"
    r"⏩\s+Skipped:\s*(?P<skipped>\d+)",
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
    "local-beta": "runtime_anonymous_session",
    "beta-local": "runtime_anonymous_session",
    "local-gamma": "runtime_anonymous_session",
    "gamma-local": "runtime_anonymous_session",
    "local-prod-sim": "runtime_anonymous_session",
    "prod-sim": "runtime_anonymous_session",
}
TYPED_TEST_DATA_ACTOR_ENV = {
    "access_token": "QWQ_TEST_DATA_ACCESS_TOKEN",
    "refresh_token": "QWQ_TEST_DATA_REFRESH_TOKEN",
    "owner_id": "QWQ_TEST_DATA_OWNER_ID",
    "persona_id": "QWQ_TEST_DATA_PERSONA_ID",
}
TYPED_AUTHENTICATED_SESSION_TARGETS = (
    BASIC_VIABILITY_TARGET,
    CORE_READBACK_TARGET,
    HOME_VIDEO_PLAYBACK_TARGET,
)
ALPHA_APP_CONTENT_TYPED_SESSION_TARGETS = (
    FEED_LOAD_TARGET,
    DEFAULT_TARGET,
    CONTROLLED_EDGE_FAULT_TARGET,
)
FORBIDDEN_PROD_PLAYBACK_CANARY_TOKENS = frozenset(
    {"fixture", "mock", "seed", "test"}
)
IOS_RELEASE_UAT_BUNDLE_IDS = (
    "com.example.quwoquanApp",
    "com.example.quwoquanApp.RunnerUITests.xctrunner",
)
IOS_DEVICE_EVIDENCE_TOKENS = (
    FEED_CONTENT_EVIDENCE_PREFIX,
    VIDEO_PLAYBACK_EVIDENCE_MARKER,
    CONTROLLED_EDGE_RESTORE_REQUEST_PREFIX,
    CONTROLLED_EDGE_FAULT_EVIDENCE_PREFIX,
    RUNTIME_RECOVERY_EVIDENCE_PREFIX,
    ACCOUNT_ENFORCEMENT_EVIDENCE_PREFIX,
    "[bootstrap] source=zone_guarded exception=",
    "feed recovery did not leave blocking error",
)
ANDROID_RELEASE_UAT_PACKAGE = "com.quwoquan.quwoquan_app"
PATROL_FLUTTER_COMMAND_ENV = "PATROL_FLUTTER_COMMAND"
ANDROID_DEVICE_PROXY = (
    REPO_ROOT / "quwoquan_ops" / "cli" / "lib" / "flutter_android_device_proxy.py"
)


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


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


def _is_ios_device(device: dict[str, Any]) -> bool:
    return str(device.get("targetPlatform") or "").strip().lower() == "ios"


def _ios_device_evidence_command(
    device_id: str,
    *,
    xcrun_path: str | None = None,
) -> list[str]:
    exact_device_id = device_id.strip()
    if not exact_device_id:
        raise ValueError("iOS device evidence requires one exact Simulator UDID")
    executable = xcrun_path or shutil.which("xcrun")
    if not executable:
        raise RuntimeError(
            "GATE_BLOCK: xcrun is required for exact-device iOS UAT evidence"
        )
    predicate = 'process == "Runner" AND (' + " OR ".join(
        f'eventMessage CONTAINS "{token}"'
        for token in IOS_DEVICE_EVIDENCE_TOKENS
    ) + ")"
    return [
        executable,
        "simctl",
        "spawn",
        exact_device_id,
        "log",
        "stream",
        "--style",
        "compact",
        "--level",
        "debug",
        "--predicate",
        predicate,
    ]


class _IosDeviceEvidenceStream:
    """Capture whitelisted Flutter markers from one Simulator execution window."""

    def __init__(
        self,
        *,
        device_id: str,
        log_path: Path,
        output_line_handler: Callable[[str], None] | None = None,
        command: list[str] | None = None,
    ) -> None:
        self.device_id = device_id.strip()
        self.log_path = log_path
        self.output_line_handler = output_line_handler
        self.command = command or _ios_device_evidence_command(self.device_id)
        self.started_at = ""
        self.ended_at = ""
        self._process: subprocess.Popen[str] | None = None
        self._reader: threading.Thread | None = None
        self._handler_error: Exception | None = None
        self._log_file: Any | None = None

    def start(self) -> None:
        if self._process is not None:
            raise RuntimeError("iOS device evidence stream already started")
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._log_file = self.log_path.open("w", encoding="utf-8")
        self.started_at = utc_now()
        try:
            self._process = subprocess.Popen(
                self.command,
                cwd=str(REPO_ROOT),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        except BaseException:
            self._log_file.close()
            self._log_file = None
            raise

        def read_output() -> None:
            assert self._process is not None and self._process.stdout is not None
            assert self._log_file is not None
            try:
                for line in self._process.stdout:
                    if not any(token in line for token in IOS_DEVICE_EVIDENCE_TOKENS):
                        continue
                    self._log_file.write(line)
                    self._log_file.flush()
                    if self.output_line_handler is not None:
                        try:
                            self.output_line_handler(line)
                        except Exception as error:  # noqa: BLE001
                            self._handler_error = error
                            return
            finally:
                self._log_file.flush()

        self._reader = threading.Thread(target=read_output, daemon=True)
        self._reader.start()
        time.sleep(0.25)
        if self._process.poll() is not None:
            self.stop(grace_seconds=0)
            raise RuntimeError(
                "GATE_BLOCK: exact-device iOS evidence stream exited before Patrol"
            )

    def stop(self, *, grace_seconds: float = 1.0) -> dict[str, Any]:
        process = self._process
        if process is None:
            return {
                "status": "not-started",
                "deviceId": self.device_id,
            }
        if grace_seconds > 0 and process.poll() is None:
            time.sleep(grace_seconds)
        if process.poll() is None:
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
        if self._reader is not None:
            self._reader.join(timeout=10)
        if process.stdout is not None:
            process.stdout.close()
        if self._log_file is not None:
            self._log_file.close()
            self._log_file = None
        self.ended_at = utc_now()
        self._process = None
        if self._handler_error is not None:
            raise RuntimeError(
                f"iOS device evidence handler failed: {self._handler_error}"
            ) from self._handler_error
        return {
            "status": "captured",
            "deviceId": self.device_id,
            "startedAt": self.started_at,
            "endedAt": self.ended_at,
            "logPath": repo_relative(self.log_path),
        }


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
            HOME_VIDEO_PLAYBACK_TARGET,
            CORE_READBACK_TARGET,
        )
    )


def _requires_typed_authenticated_session(args: argparse.Namespace) -> bool:
    """Return whether this local UAT consumes one stackctl-owned Actor scope."""

    target_name = _local_target_for_environment_alias(args.env_name)
    if target_name not in {
        "alpha-local",
        "beta-local",
        "gamma-local",
    }:
        return False
    target = str(getattr(args, "target", "") or "").replace("\\", "/")
    shared_protected = any(
        target.endswith(candidate)
        for candidate in TYPED_AUTHENTICATED_SESSION_TARGETS
    )
    alpha_content_protected = target_name == "alpha-local" and any(
        target.endswith(candidate)
        for candidate in ALPHA_APP_CONTENT_TYPED_SESSION_TARGETS
    )
    return shared_protected or alpha_content_protected


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
        and not bool(getattr(args, "unauthenticated_auth_entry", False))
        and not _uses_public_video_canary_anonymous_session(args)
        and not _uses_persisted_device_session(args)
        and not _is_account_enforcement_target(args)
        and not _requires_typed_authenticated_session(args)
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
        return "anonymous_public_video_session"
    if target_name == "gamma-local":
        return "anonymous_public_video_session"
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


def _canonical_handoff_projection(
    handoff: dict[str, Any],
) -> tuple[dict[str, str], dict[str, str]]:
    """Project one already-validated launcher handoff to Dart and native build."""

    if handoff.get("schema") != "app-launcher-handoff":
        raise ValueError("canonical launcher handoff schema is invalid")
    effective = handoff.get("effectiveLaunchManifest")
    if not isinstance(effective, dict) or effective.get("schema") != (
        "app-effective-launch-manifest"
    ):
        raise ValueError("canonical effective launch manifest is invalid")
    for field, value in effective.items():
        if field != "schema" and handoff.get(field) != value:
            raise ValueError(
                "canonical launcher handoff/effective manifest mismatch: "
                f"{field}"
            )
    for field in (
        "dartDefinesDigest",
        "runtimeConfigDigest",
        "effectiveLaunchManifestDigest",
    ):
        if CANONICAL_DIGEST_PATTERN.fullmatch(str(handoff.get(field) or "")) is None:
            raise ValueError(f"canonical launcher handoff {field} is invalid")
    defines = handoff.get("dartDefines")
    if not isinstance(defines, dict) or any(
        not isinstance(key, str) or not isinstance(value, str)
        for key, value in defines.items()
    ):
        raise ValueError("canonical launcher handoff Dart defines are invalid")
    missing_defines = sorted(CANONICAL_TEST_LIVE_DART_DEFINE_KEYS - defines.keys())
    if missing_defines:
        raise ValueError(
            "canonical launcher handoff Dart defines are incomplete: "
            + ", ".join(missing_defines)
        )
    expected_define_values = {
        "APP_RUNTIME_ENV": str(handoff.get("environment") or ""),
        "QWQ_APP_LAUNCH_MODE": str(handoff.get("launchMode") or ""),
        "APP_LAUNCH_POLICY": str(handoff.get("launchPolicy") or ""),
        "CONTENT_BINDING_STATE": str(handoff.get("contentBindingState") or ""),
        "CLOUD_GATEWAY_BASE_URL": str(handoff.get("recoveryBaseUrl") or ""),
        "PUBLIC_WEB_BASE_URL": str(handoff.get("publicWebBaseUrl") or ""),
        "APP_DOWNLOAD_BASE_URL": str(handoff.get("appDownloadBaseUrl") or ""),
    }
    mismatched_defines = sorted(
        key
        for key, value in expected_define_values.items()
        if defines.get(key) != value
    )
    if mismatched_defines:
        raise ValueError(
            "canonical launcher handoff Dart define projection mismatch: "
            + ", ".join(mismatched_defines)
        )
    build_environment = {
        "QWQ_APP_RUNTIME_ENV": str(handoff["environment"]),
        "QWQ_LAUNCH_TARGET": str(handoff["target"]),
        "QWQ_APP_LAUNCH_MODE": str(handoff["launchMode"]),
        "QWQ_APP_LAUNCH_POLICY": str(handoff["launchPolicy"]),
        "QWQ_APP_BUILD_CONTEXT": "runtime",
        "QWQ_DART_DEFINES_DIGEST": str(handoff["dartDefinesDigest"]),
        "QWQ_EXPECTED_RUNTIME_CONFIG_DIGEST": str(
            handoff["runtimeConfigDigest"]
        ),
        "QWQ_EFFECTIVE_LAUNCH_MANIFEST_DIGEST": str(
            handoff["effectiveLaunchManifestDigest"]
        ),
        "QWQ_CONTENT_RELEASE_ID": str(handoff.get("contentReleaseId") or ""),
        "QWQ_CONTENT_MANIFEST_DIGEST": str(
            handoff.get("contentManifestDigest") or ""
        ),
        "QWQ_CONTENT_READINESS_RECEIPT_DIGEST": str(
            handoff.get("contentReadinessReceiptDigest") or ""
        ),
        "QWQ_APP_RECOVERY_BASE_URL": str(handoff["recoveryBaseUrl"]),
        "QWQ_APP_PUBLIC_WEB_URL": str(handoff["publicWebBaseUrl"]),
        "QWQ_APP_DOWNLOAD_BASE_URL": str(handoff["appDownloadBaseUrl"]),
        "QWQ_LAUNCH_HANDOFF_JSON": json.dumps(
            handoff,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ),
    }
    return dict(defines), build_environment


def _canonical_test_live_launcher_handoff(
    args: argparse.Namespace,
    device: dict[str, Any],
    command_env: dict[str, str],
    *,
    content_binding_mode: str = "current",
) -> dict[str, Any]:
    """Render one run-bound canonical handoff for both Patrol and Gradle."""

    runtime_env = args.runtime_env.strip() or _runtime_env_for_alias(args.env_name)
    if runtime_env not in {"alpha", "beta", "gamma"}:
        raise ValueError("test_live launcher handoff requires alpha, beta, or gamma")
    target_name = _local_target_for_environment_alias(args.env_name)
    get_target(load_environment_topology(), target_name)
    if content_binding_mode == "current":
        content_binding = load_test_live_content_binding(target_name) or {}
    elif content_binding_mode == "unbound":
        content_binding = {}
    else:
        raise ValueError("canonical test_live content binding mode is invalid")
    expected_content = {
        "contentReleaseId": str(content_binding.get("releaseId") or ""),
        "contentManifestDigest": str(content_binding.get("manifestDigest") or ""),
        "contentReadinessReceiptDigest": str(
            content_binding.get("readinessReceiptDigest") or ""
        ),
    }
    populated_content = [value for value in expected_content.values() if value]
    if populated_content and len(populated_content) != len(expected_content):
        raise ValueError("current test_live content binding is partial")
    base_urls = _effective_base_urls_for_device(args, device)
    command = [
        sys.executable,
        str(APP_LAUNCHER_HANDOFF_BUILDER),
        "--env",
        runtime_env,
        "--target",
        target_name,
        "--launch-mode",
        "canonical_launcher",
        "--launch-policy",
        "test_live",
        "--app-instance-namespace",
        f"{runtime_env}-test-live",
        "--gateway-base-url",
        base_urls["gatewayBaseUrl"],
        "--legal-base-url",
        base_urls["legalBaseUrl"],
        "--media-avatar-base-url",
        base_urls["mediaAvatarBaseUrl"],
        "--media-image-base-url",
        base_urls["mediaImageBaseUrl"],
        "--media-video-base-url",
        base_urls["mediaVideoBaseUrl"],
        "--media-upload-base-url",
        base_urls["mediaUploadBaseUrl"],
        "--rtc-media-connection-url",
        base_urls["rtcMediaConnectionUrl"],
    ]
    current_user_id = _resolved_owner_id(args)
    if current_user_id:
        command.extend(("--current-user-id", current_user_id))
    if populated_content:
        command.extend(
            (
                "--content-release-id",
                expected_content["contentReleaseId"],
                "--content-manifest-digest",
                expected_content["contentManifestDigest"],
                "--content-readiness-receipt-digest",
                expected_content["contentReadinessReceiptDigest"],
            )
        )
    is_android = str(device.get("targetPlatform") or "").lower().startswith(
        "android"
    )
    if is_android:
        transport_values = {
            "reverseExpectedPorts": command_env.get(
                "QWQ_ANDROID_REVERSE_EXPECTED_PORTS", ""
            ),
            "reverseActualPorts": command_env.get(
                "QWQ_ANDROID_REVERSE_ACTUAL_PORTS", ""
            ),
            "reverseReceiptDigest": command_env.get(
                "QWQ_ANDROID_REVERSE_RECEIPT_DIGEST", ""
            ),
            "consumerLeaseId": command_env.get("QWQ_CONSUMER_LEASE_ID", ""),
        }
        missing_transport = sorted(
            key for key, value in transport_values.items() if not value
        )
        if missing_transport:
            raise ValueError(
                "Android test_live launcher transport is incomplete: "
                + ", ".join(missing_transport)
            )
        command.extend(
            (
                "--transport-required",
                "--reverse-expected-ports",
                transport_values["reverseExpectedPorts"],
                "--reverse-actual-ports",
                transport_values["reverseActualPorts"],
                "--reverse-receipt-digest",
                transport_values["reverseReceiptDigest"],
                "--consumer-lease-id",
                transport_values["consumerLeaseId"],
            )
        )
    try:
        result = subprocess.run(
            command,
            cwd=APP_DIR,
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError(f"canonical test_live launcher handoff failed: {exc}") from exc
    if result.returncode != 0:
        raise ValueError(
            result.stderr.strip()
            or result.stdout.strip()
            or "canonical test_live launcher handoff failed"
        )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"canonical test_live launcher handoff is not JSON: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise ValueError("canonical test_live launcher handoff must be an object")
    _canonical_handoff_projection(payload)
    expected_state = "bound" if populated_content else "unbound"
    expected_identity = {
        "environment": runtime_env,
        "target": target_name,
        "launchMode": "canonical_launcher",
        "launchPolicy": "test_live",
        "contentBindingState": expected_state,
        **expected_content,
    }
    mismatched = sorted(
        field
        for field, value in expected_identity.items()
        if payload.get(field) != value
    )
    if mismatched:
        raise ValueError(
            "canonical test_live launcher handoff identity mismatch: "
            + ", ".join(mismatched)
        )
    if payload["runtimeConfigDigest"] != payload["dartDefinesDigest"]:
        raise ValueError(
            "test_live runtime config digest must equal the Dart defines digest"
        )
    expected_runtime_defines = {
        "APP_LEGAL_BASE_URL": base_urls["legalBaseUrl"],
        "MEDIA_AVATAR_CDN_BASE_URL": base_urls["mediaAvatarBaseUrl"],
        "MEDIA_IMAGE_CDN_BASE_URL": base_urls["mediaImageBaseUrl"],
        "MEDIA_VIDEO_CDN_BASE_URL": base_urls["mediaVideoBaseUrl"],
        "MEDIA_UPLOAD_BASE_URL": base_urls["mediaUploadBaseUrl"],
        "RTC_MEDIA_CONNECTION_URL": base_urls["rtcMediaConnectionUrl"],
    }
    defines = payload["dartDefines"]
    mismatched_runtime_defines = sorted(
        key
        for key, value in expected_runtime_defines.items()
        if defines.get(key) != value
    )
    if mismatched_runtime_defines:
        raise ValueError(
            "canonical test_live launcher handoff topology mismatch: "
            + ", ".join(mismatched_runtime_defines)
        )
    if is_android:
        transport = payload["effectiveLaunchManifest"].get("transport")
        if not isinstance(transport, dict) or transport.get("required") is not True:
            raise ValueError("Android test_live launcher transport is not required")
        for field, env_key in (
            ("reverseExpectedPorts", "QWQ_ANDROID_REVERSE_EXPECTED_PORTS"),
            ("reverseActualPorts", "QWQ_ANDROID_REVERSE_ACTUAL_PORTS"),
            ("reverseReceiptDigest", "QWQ_ANDROID_REVERSE_RECEIPT_DIGEST"),
            ("consumerLeaseId", "QWQ_CONSUMER_LEASE_ID"),
        ):
            if transport.get(field) != command_env.get(env_key, ""):
                raise ValueError(
                    f"Android test_live launcher transport mismatch: {field}"
                )
    return payload


def _validated_provider_patrol_runtime_identity(
    args: argparse.Namespace,
    command_env: dict[str, str],
) -> dict[str, Any] | None:
    """Freeze the stackctl-selected Provider rail before runtime side effects.

    Generic environment Patrol has no Provider runtime identity and retains its
    existing test_live launcher behavior. Provider Patrol must carry both the
    bounded identity envelope and the same explicit CLI mode.
    """

    explicit_runtime_mode = str(
        getattr(args, "runtime_mode", "") or ""
    ).strip()
    raw_identity = command_env.get(
        PROVIDER_CONFORMANCE_RUNTIME_IDENTITY_ENV,
        "",
    ).strip()
    if not raw_identity:
        if explicit_runtime_mode:
            raise ValueError(
                "Provider Patrol runtime identity handoff is required"
            )
        return None
    try:
        identity = json.loads(raw_identity)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "Provider Patrol runtime identity handoff is invalid"
        ) from exc
    if not isinstance(identity, dict):
        raise ValueError("Provider Patrol runtime identity handoff must be an object")
    runtime_mode = str(identity.get("runtimeMode") or "").strip()
    mode_fields = (
        PROVIDER_CONFORMANCE_RUNTIME_IDENTITY_IMMUTABLE_FIELDS
        if runtime_mode == "immutable_candidate"
        else PROVIDER_CONFORMANCE_RUNTIME_IDENTITY_MUTABLE_FIELDS
        if runtime_mode == "test_live"
        else frozenset()
    )
    runtime_env = args.runtime_env.strip() or _runtime_env_for_alias(args.env_name)
    target_name = _local_target_for_environment_alias(args.env_name)
    candidate_field = (
        "candidateDigest"
        if runtime_mode == "immutable_candidate"
        else "mutableComposeDigest"
    )
    selected_candidate = str(identity.get(candidate_field) or "").strip()
    expected_candidate = str(
        getattr(args, "candidate_digest", "") or ""
    ).strip()
    digest_fields = {"providerRuntimeDigest", candidate_field}
    if runtime_mode == "test_live":
        digest_fields.update(
            {
                "mutableConfigurationDigest",
                "mutableStateDigest",
                "mutableWorkspaceStatusDigest",
                "mutableResolverHandoffDigest",
            }
        )
    if (
        not mode_fields
        or explicit_runtime_mode != runtime_mode
        or set(identity)
        != PROVIDER_CONFORMANCE_RUNTIME_IDENTITY_COMMON_FIELDS | mode_fields
        or identity.get("schema")
        != PROVIDER_CONFORMANCE_RUNTIME_IDENTITY_SCHEMA
        or identity.get("environment") != runtime_env
        or identity.get("target") != target_name
        or identity.get("workload") != "full"
        or identity.get("failureFree") is not True
        or identity.get("nonPromotable") is not (runtime_mode == "test_live")
        or not str(identity.get("startupAttemptId") or "").strip()
        or not expected_candidate
        or selected_candidate != expected_candidate
        or any(
            CANONICAL_DIGEST_PATTERN.fullmatch(
                str(identity.get(field) or "")
            )
            is None
            for field in digest_fields
        )
        or (
            runtime_mode == "test_live"
            and re.fullmatch(
                r"[0-9a-f]{40}",
                str(identity.get("mutableSourceRevision") or ""),
            )
            is None
        )
    ):
        raise ValueError(
            "Provider Patrol runtime identity handoff does not match execution"
        )
    return identity


def _provider_patrol_launcher_handoff(
    args: argparse.Namespace,
    device: dict[str, Any],
    command_env: dict[str, str],
    *,
    runtime_identity: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build only the canonical launcher rail frozen before side effects."""

    if runtime_identity is None:
        return _canonical_test_live_launcher_handoff(args, device, command_env)
    if runtime_identity["runtimeMode"] == "immutable_candidate":
        return _canonical_test_live_launcher_handoff(
            args,
            device,
            command_env,
            content_binding_mode="unbound",
        )
    return _canonical_test_live_launcher_handoff(args, device, command_env)


def _apply_launcher_handoff_to_command_env(
    command_env: dict[str, str],
    handoff: dict[str, Any],
) -> None:
    _, projection = _canonical_handoff_projection(handoff)
    command_env.update(projection)


def _device_command_env(
    args: argparse.Namespace,
    device: dict[str, Any],
    *,
    launcher_handoff: dict[str, Any] | None = None,
) -> dict[str, str]:
    env = dict(os.environ)
    runtime_env = args.runtime_env.strip() or _runtime_env_for_alias(args.env_name)
    launch_target = _local_target_for_environment_alias(args.env_name)
    try:
        get_target(load_environment_topology(), launch_target)
    except KeyError as exc:
        raise ValueError(
            "environment alias does not resolve to a canonical launch target: "
            f"{args.env_name!r}"
        ) from exc
    env["QWQ_APP_RUNTIME_ENV"] = runtime_env
    env["QWQ_LAUNCH_TARGET"] = launch_target
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
    if launcher_handoff is not None:
        _apply_launcher_handoff_to_command_env(env, launcher_handoff)
        if env["QWQ_APP_RUNTIME_ENV"] != runtime_env:
            raise ValueError("launcher handoff environment does not match Patrol")
        if env["QWQ_LAUNCH_TARGET"] != launch_target:
            raise ValueError("launcher handoff target does not match Patrol")
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
            "QWQ_CONSUMER_LEASE_ID": str(lease["leaseId"]),
        }
    )
    if is_android:
        port_list = ",".join(str(port) for port in ports)
        reverse_receipt_digest = "sha256:" + hashlib.sha256(
            f"{target_name}\0{device_id}\0{port_list}".encode("utf-8")
        ).hexdigest()
        command_env.update(
            {
                "QWQ_ANDROID_LOCAL_PORTS": port_list,
                "QWQ_ANDROID_REVERSE_EXPECTED_PORTS": port_list,
                "QWQ_ANDROID_REVERSE_ACTUAL_PORTS": port_list,
                "QWQ_ANDROID_REVERSE_RECEIPT_DIGEST": reverse_receipt_digest,
            }
        )
    return target_name, device_id, consumer, str(lease["leaseId"])


def _bind_patrol_consumer_lease_to_handoff(
    args: argparse.Namespace,
    device: dict[str, Any],
    consumer_lease: tuple[str, str, str, str],
    command_env: dict[str, str],
    handoff: dict[str, Any],
) -> None:
    """Update the same deterministic lease with its exact launcher identity."""

    target_name, device_id, consumer, lease_id = consumer_lease
    is_android = str(device.get("targetPlatform") or "").lower().startswith(
        "android"
    )
    ports = [
        int(value)
        for value in command_env.get("QWQ_ANDROID_LOCAL_PORTS", "").split(",")
        if value.strip()
    ]
    rebound = acquire_consumer_lease(
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
        handoff_digest=str(handoff["effectiveLaunchManifestDigest"]),
        release_id=str(handoff.get("contentReleaseId") or ""),
        manifest_digest=str(handoff.get("contentManifestDigest") or ""),
        readiness_receipt_digest=str(
            handoff.get("contentReadinessReceiptDigest") or ""
        ),
    )
    if rebound.get("leaseId") != lease_id:
        raise RuntimeError(
            "GATE_BLOCK: runtime consumer lease identity changed while binding handoff"
        )
    command_env["QWQ_CONSUMER_LEASE_ID"] = lease_id


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
        choices=("canary", "5", "20", "50", "100"),
        default="",
        help="Prod rollout stage; it is evidence metadata, never a fifth environment.",
    )
    parser.add_argument("--runtime-env", default="")
    parser.add_argument(
        "--runtime-mode",
        choices=("immutable_candidate", "test_live"),
        default="",
        help="Explicit stackctl-selected Provider runtime rail.",
    )
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
    representations: set[str] = set()
    for value in secret_values:
        if not value:
            continue
        raw = value.encode("utf-8")
        standard = base64.b64encode(raw).decode("ascii")
        urlsafe = base64.urlsafe_b64encode(raw).decode("ascii")
        representations.update(
            {value, standard, standard.rstrip("="), urlsafe, urlsafe.rstrip("=")}
        )
    for value in sorted(representations, key=len, reverse=True):
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
    platform = str(args.platform or "").strip().lower()
    missing_android = platform in {"all", "android"} and not physical_android
    missing_ios = platform in {"all", "ios"} and not physical_ios
    if missing_android or missing_ios:
        required = (
            "one physical Android device and one physical iPhone"
            if platform == "all"
            else f"one physical {platform} device"
        )
        raise RuntimeError(
            f"GATE_BLOCK: runtime recovery UAT requires {required} "
            "in the selected CaseResult"
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
            "skipped": int(xctest.group("skipped") or 0),
        }
    patrol = PATROL_EXECUTION_SUMMARY_PATTERN.search(output)
    if patrol is not None:
        return {
            "framework": "patrol",
            "executed": int(patrol.group("executed")),
            "failed": int(patrol.group("failed")),
            "skipped": int(patrol.group("skipped")),
        }
    return {
        "framework": "unknown",
        "executed": None,
        "failed": None,
        "skipped": None,
    }


def patrol_test_execution_failure_reason(summary: dict[str, Any]) -> str:
    """Return why a real Patrol/XCTest summary cannot prove a passed run."""

    framework = summary.get("framework")
    executed = summary.get("executed")
    failed = summary.get("failed")
    skipped = summary.get("skipped")
    if framework not in {"xctest", "patrol"} or any(
        not isinstance(value, int) or isinstance(value, bool)
        for value in (executed, failed, skipped)
    ):
        return "Patrol/XCTest execution summary is missing or incomplete"
    if executed <= 0:
        return "Patrol/XCTest execution summary reports zero executed tests"
    if failed != 0:
        return f"Patrol/XCTest execution summary reports {failed} failed tests"
    if skipped != 0:
        return f"Patrol/XCTest execution summary reports {skipped} skipped tests"
    return ""


def apply_patrol_test_execution_summary(
    result: dict[str, Any],
    output: str,
    *,
    dry_run: bool,
) -> None:
    """Attach the summary and fail a real run that lacks passing test counts."""

    result["testExecution"] = patrol_test_execution_summary(output)
    if dry_run:
        return
    execution_failure = patrol_test_execution_failure_reason(
        result["testExecution"]
    )
    if not execution_failure:
        return
    result["exitCode"] = 1
    result["outputSummary"] = (
        str(result.get("outputSummary") or "") + "\n" + execution_failure
    ).strip()


def _first_typed_patrol_blocker(output: str) -> dict[str, Any]:
    """Extract the first canonical Cloud failure without copying its payload."""

    normalized = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", output)
    match = re.search(
        r"CloudException\(.*?statusCode:\s*(?P<status>null|[0-9]{3}),"
        r".*?code:\s*(?P<code>[A-Z][A-Za-z0-9_.]+),"
        r".*?sourceOperationId:\s*(?P<operation>[A-Za-z][A-Za-z0-9_.]+)\)",
        normalized,
        flags=re.DOTALL,
    )
    if match is None:
        return {}
    raw_status = match.group("status")
    return {
        "errorCode": match.group("code"),
        "sourceOperationId": match.group("operation"),
        "httpStatus": None if raw_status == "null" else int(raw_status),
    }


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
            str(
                REPO_ROOT
                / "quwoquan_app"
                / "scripts"
                / "tools"
                / "device"
                / "discover_flutter_mobile_devices.py"
            ),
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


@dataclass(frozen=True)
class TypedTestDataActor:
    access_token: str
    refresh_token: str
    owner_id: str
    persona_id: str

    def secret_values(self) -> tuple[str, ...]:
        return (
            self.access_token,
            self.refresh_token,
            self.owner_id,
            self.persona_id,
        )


def _typed_test_data_actor_from_environment() -> TypedTestDataActor | None:
    values = {
        field: os.environ.get(environment_key, "").strip()
        for field, environment_key in TYPED_TEST_DATA_ACTOR_ENV.items()
    }
    populated = [field for field, value in values.items() if value]
    if not populated:
        return None
    missing = sorted(set(values) - set(populated))
    if missing:
        raise ValueError(
            "typed test-data actor handoff is incomplete: " + ", ".join(missing)
        )
    return TypedTestDataActor(**values)


def _bind_typed_test_data_actor(args: argparse.Namespace) -> TypedTestDataActor:
    supplied = {
        "test_auth_token": args.test_auth_token,
        "test_refresh_token": args.test_refresh_token,
        "current_owner_id": _resolved_owner_id(args),
        "current_persona_id": _resolved_persona_id(args),
    }
    if any(str(value).strip() for value in supplied.values()):
        raise ValueError(
            "typed authenticated Patrol forbids caller-injected credentials"
        )
    actor = _typed_test_data_actor_from_environment()
    if actor is None:
        raise ValueError(
            "typed authenticated Patrol requires a stackctl TestDataSession actor handoff"
        )
    args.test_auth_token = actor.access_token
    args.test_refresh_token = actor.refresh_token
    args.current_owner_id = actor.owner_id
    args.current_persona_id = actor.persona_id
    args._typed_test_data_actor = actor
    return actor


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
    if _requires_typed_authenticated_session(args):
        _bind_typed_test_data_actor(args)
        return "test_data_protected_authenticated_session"
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


def _create_patrol_secret_define_file(
    args: argparse.Namespace,
) -> Path:
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
    values = tuple(
        (key, os.environ.get(key, "").strip())
        for key in keys
        if os.environ.get(key, "").strip()
    )
    return tuple(
        item
        for key, value in values
        for item in (value, f"{key}={value}")
    )


def _patrol_bundler_target(target: str) -> str:
    """Return a valid wrapper-shaped target after validating the real source."""

    normalized = target.strip().replace("\\", "/")
    if (
        not normalized
        or normalized.startswith("/")
        or re.match(r"^[A-Za-z]:/", normalized)
    ):
        raise ValueError("Patrol target must be a repository-relative path")
    parts = normalized.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("Patrol target must not contain path traversal")
    root_parts = ("test", "user_acceptance")
    if tuple(parts[: len(root_parts)]) != root_parts:
        raise ValueError("Patrol target must be under test/user_acceptance")
    if not normalized.endswith("_test.dart"):
        raise ValueError("Patrol target must name one canonical Dart test")
    if not (APP_DIR / normalized).is_file():
        raise ValueError("Patrol target does not exist in the App source tree")
    target_digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
    return (
        f"{PATROL_TEST_DIRECTORY}/"
        f"qwq_environment_smoke_{target_digest}_test.dart"
    )


def _create_patrol_target_wrapper(
    target: str,
    *,
    typed_actor: TypedTestDataActor | None = None,
) -> tuple[Path, str, Callable[[], None]]:
    """Securely create one temporary Patrol-shell wrapper for an external UAT."""

    _patrol_bundler_target(target)
    normalized = target.strip().replace("\\", "/")
    wrapper_directory = APP_DIR / PATROL_TEST_DIRECTORY
    if wrapper_directory.is_symlink() or not wrapper_directory.is_dir():
        raise RuntimeError("Patrol test directory is missing or unsafe")
    bundle_path = wrapper_directory / "test_bundle.dart"
    if bundle_path.is_symlink():
        raise RuntimeError("Patrol test bundle path is unsafe")
    bundle_preimage = bundle_path.read_bytes() if bundle_path.is_file() else None
    bundle_mode = (
        bundle_path.stat().st_mode & 0o777
        if bundle_preimage is not None
        else None
    )
    relative_import = os.path.relpath(
        APP_DIR / normalized,
        wrapper_directory,
    ).replace(os.sep, "/")
    if not relative_import.startswith("../"):
        raise RuntimeError("Patrol wrapper target must remain outside its shell directory")
    imports = [f"import '{relative_import}' as canonical_target;"]
    actor_module_path: Path | None = None
    actor_install = ""
    if typed_actor is not None:
        actor_descriptor, raw_actor_path = tempfile.mkstemp(
            prefix="qwq_typed_test_data_actor_",
            suffix=".dart",
            dir=wrapper_directory,
            text=True,
        )
        actor_module_path = Path(raw_actor_path)
        actor_constants = {
            "accessToken": typed_actor.access_token,
            "refreshToken": typed_actor.refresh_token,
            "ownerId": typed_actor.owner_id,
            "personaId": typed_actor.persona_id,
        }
        try:
            os.fchmod(actor_descriptor, 0o600)
            with os.fdopen(
                actor_descriptor,
                "w",
                encoding="utf-8",
                closefd=True,
            ) as actor_handle:
                actor_handle.write(
                    "// Ephemeral encoded typed actor; never commit this file.\n"
                )
                for name, value in actor_constants.items():
                    encoded_value = base64.b64encode(value.encode("utf-8")).decode(
                        "ascii"
                    )
                    actor_handle.write(
                        f"const String {name} = '{encoded_value}';\n"
                    )
                actor_handle.flush()
                os.fsync(actor_handle.fileno())
        except BaseException:
            try:
                os.close(actor_descriptor)
            except OSError:
                pass
            actor_module_path.unlink(missing_ok=True)
            raise
        imports = [
            "import 'dart:convert';",
            *imports,
            f"import '{actor_module_path.name}' as typed_actor;",
            "import '../../support/runtime/patrol/patrol_test_support.dart' "
            "as patrol_support;",
        ]
        actor_install = (
            "  String decode(String value) => "
            "utf8.decode(base64.decode(value));\n"
            "  patrol_support.installPatrolAcceptanceSessionForRunner(\n"
            "    accessToken: decode(typed_actor.accessToken),\n"
            "    refreshToken: decode(typed_actor.refreshToken),\n"
            "    ownerId: decode(typed_actor.ownerId),\n"
            "    personaId: decode(typed_actor.personaId),\n"
            "  );\n"
        )
    descriptor, raw_path = tempfile.mkstemp(
        prefix="qwq_environment_smoke_",
        suffix="_test.dart",
        dir=wrapper_directory,
        text=True,
    )
    wrapper_path = Path(raw_path)
    wrapper_target = wrapper_path.relative_to(APP_DIR).as_posix()
    if re.fullmatch(
        r"qwq_environment_smoke_[A-Za-z0-9_]+_test\.dart",
        wrapper_path.name,
    ) is None:
        os.close(descriptor)
        wrapper_path.unlink(missing_ok=True)
        raise RuntimeError("Patrol wrapper filename cannot form a Dart identifier")
    encoded = (
        "// Ephemeral runner-owned Patrol wrapper; never commit this file.\n"
        + "\n".join(imports)
        + "\n\nvoid main() {\n"
        + actor_install
        + "  canonical_target.main();\n}\n"
    ).encode("utf-8")
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        wrapper_path.unlink(missing_ok=True)
        if actor_module_path is not None:
            actor_module_path.unlink(missing_ok=True)
        raise

    def cleanup() -> None:
        wrapper_path.unlink(missing_ok=True)
        if actor_module_path is not None:
            actor_module_path.unlink(missing_ok=True)
        if bundle_path.is_symlink():
            bundle_path.unlink()
        if bundle_preimage is None:
            bundle_path.unlink(missing_ok=True)
            return
        descriptor, raw_restore_path = tempfile.mkstemp(
            prefix=".qwq_patrol_bundle_restore_",
            suffix=".dart",
            dir=wrapper_directory,
        )
        restore_path = Path(raw_restore_path)
        try:
            with os.fdopen(descriptor, "wb", closefd=True) as handle:
                handle.write(bundle_preimage)
                handle.flush()
                os.fsync(handle.fileno())
            if bundle_mode is not None:
                restore_path.chmod(bundle_mode)
            os.replace(restore_path, bundle_path)
        finally:
            restore_path.unlink(missing_ok=True)

    atexit.register(cleanup)
    return wrapper_path, wrapper_target, cleanup


def _cleanup_patrol_target_wrapper(cleanup: Callable[[], None] | None) -> None:
    if cleanup is None:
        return
    try:
        cleanup()
    finally:
        atexit.unregister(cleanup)


def _stream_contains_any(
    handle: Any,
    needles: tuple[bytes, ...],
) -> bool:
    overlap = max(len(value) for value in needles) - 1
    tail = b""
    while True:
        chunk = handle.read(1024 * 1024)
        if not chunk:
            return False
        data = tail + chunk
        if any(value in data for value in needles):
            return True
        tail = data[-overlap:] if overlap else b""


def _generated_artifact_contains_any(
    path: Path,
    needles: tuple[bytes, ...],
) -> bool:
    try:
        with path.open("rb") as handle:
            if _stream_contains_any(handle, needles):
                return True
        if path.suffix.lower() in {".aab", ".apk", ".ipa", ".zip"}:
            with zipfile.ZipFile(path) as archive:
                for info in archive.infolist():
                    if info.is_dir():
                        continue
                    with archive.open(info) as handle:
                        if _stream_contains_any(handle, needles):
                            return True
    except FileNotFoundError:
        return False
    except (EOFError, OSError, RuntimeError, zipfile.BadZipFile) as exc:
        raise RuntimeError(
            "cannot verify a generated Patrol artifact for credential residue"
        ) from exc
    return False


def _generated_patrol_artifact_candidates(root: Path) -> tuple[Path, ...]:
    """Return bounded compiler/package outputs that can retain a test target."""

    candidates: set[Path] = set()
    build_root = root / "build"
    if build_root.is_dir() and not build_root.is_symlink():
        for path in build_root.rglob("*"):
            if path.is_symlink() or not path.is_file():
                continue
            relative_parts = path.relative_to(build_root).parts
            if any(part in {"incremental", "zip-cache"} for part in relative_parts):
                continue
            if path.name == "kernel_blob.bin" or path.suffix.lower() in {
                ".aab",
                ".apk",
                ".dill",
                ".ipa",
                ".snapshot",
                ".zip",
            }:
                candidates.add(path)
    flutter_build_root = root / ".dart_tool" / "flutter_build"
    if flutter_build_root.is_dir() and not flutter_build_root.is_symlink():
        for path in flutter_build_root.rglob("*"):
            if path.is_symlink() or not path.is_file():
                continue
            if path.name in {"app.dill", "kernel_blob.bin"} or path.suffix.lower() in {
                ".dill",
                ".snapshot",
            }:
                candidates.add(path)
    return tuple(sorted(candidates))


def _purge_typed_actor_credential_artifacts(
    secret_values: tuple[str, ...],
    *,
    app_dir: Path | None = None,
) -> int:
    """Remove only generated files that contain the ephemeral actor session."""

    canonical_values = tuple(
        dict.fromkeys(value.strip() for value in secret_values if value.strip())
    )
    if not canonical_values:
        return 0
    needles = tuple(value.encode("utf-8") for value in canonical_values)
    root = app_dir or APP_DIR
    removed = 0
    for path in _generated_patrol_artifact_candidates(root):
        if _generated_artifact_contains_any(path, needles):
            path.unlink()
            removed += 1
    for path in _generated_patrol_artifact_candidates(root):
        if _generated_artifact_contains_any(path, needles):
            raise RuntimeError(
                "generated Patrol credential artifact cleanup did not converge"
            )
    return removed


def patrol_command(
    device: dict[str, Any],
    args: argparse.Namespace,
    patrol_executable: str,
    *,
    dart_define_file: Path | None,
    launcher_handoff: dict[str, Any] | None = None,
    patrol_target: str | None = None,
    typed_test_data_session_handoff: bool = False,
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
    canonical_runtime_defines: dict[str, str] | None = None
    if launcher_handoff is not None:
        canonical_runtime_defines, _ = _canonical_handoff_projection(
            launcher_handoff
        )
        expected_target = _local_target_for_environment_alias(args.env_name)
        if launcher_handoff.get("environment") != runtime_env:
            raise ValueError("launcher handoff environment does not match Patrol")
        if launcher_handoff.get("target") != expected_target:
            raise ValueError("launcher handoff target does not match Patrol")
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
        patrol_target or _patrol_bundler_target(args.target),
        "-d",
        str(device["id"]),
        "--dart-define=RUN_PATROL_ACCEPTANCE=true",
        "--dart-define=REQUIRE_NATIVE_VIDEO_PLAYBACK_SIGNALS="
        + (
            "true"
            if _requires_native_video_playback_signals(device)
            else "false"
        ),
        f"--dart-define=API_CONTRACT_ENV={api_contract_env}",
        f"--dart-define=API_CONTRACT_BASE_URL={gateway_base_url}",
        f"--dart-define=API_CONTRACT_PRODUCT_OPS_BASE_URL={product_ops_base_url}",
        f"--dart-define=VIDEO_PLAYBACK_CANARY_WORK_ID={video_playback_canary_work_id}",
    ]
    if canonical_runtime_defines is None:
        command.extend(
            (
                f"--dart-define=APP_RUNTIME_ENV={runtime_env}",
                f"--dart-define=CLOUD_GATEWAY_BASE_URL={gateway_base_url}",
                f"--dart-define=APP_LEGAL_BASE_URL={legal_base_url}",
                "--dart-define=RTC_MEDIA_CONNECTION_URL="
                f"{rtc_media_connection_url}",
            )
        )
    else:
        command.extend(
            f"--dart-define={key}={value}"
            for key, value in sorted(canonical_runtime_defines.items())
        )
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
    elif bool(getattr(args, "unauthenticated_auth_entry", False)):
        command.append(
            "--dart-define=QWQ_PATROL_SESSION_MODE=unauthenticated_auth_entry"
        )
        if dart_define_file is None:
            raise ValueError(
                "unauthenticated auth-entry Patrol requires a private Provider define file"
            )
        command.append(f"--dart-define-from-file={dart_define_file}")
    elif _uses_persisted_device_session(args):
        pass
    elif typed_test_data_session_handoff:
        command.append(
            "--dart-define=QWQ_PATROL_SESSION_MODE="
            "test_data_protected_authenticated_session"
        )
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
    if canonical_runtime_defines is None and (
        media_avatar_base_url
        or media_image_base_url
        or media_video_base_url
        or media_upload_base_url
    ):
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
        credential_artifact_cleanup: dict[str, Any] = {
            "status": "not-required",
            "removedFiles": 0,
        }
        secret_define_path: Path | None = None
        typed_actor = getattr(args, "_typed_test_data_actor", None)
        if typed_actor is not None and not isinstance(
            typed_actor,
            TypedTestDataActor,
        ):
            raise TypeError("typed test-data actor handoff is invalid")
        if args.dry_run:
            secret_define_path = run_dir / "dry-run-patrol-secrets.json"
        elif not (
            _uses_runtime_anonymous_session(args)
            or _uses_persisted_device_session(args)
            or typed_actor is not None
        ):
            secret_define_path = _create_patrol_secret_define_file(args)
        consumer_lease: tuple[str, str, str, str] | None = None
        patrol_wrapper_cleanup: Callable[[], None] | None = None
        try:
            command_env = _device_command_env(args, device)
            provider_runtime_identity = (
                _validated_provider_patrol_runtime_identity(
                    args,
                    command_env,
                )
            )
            launcher_handoff: dict[str, Any] | None = None
            if not args.dry_run:
                consumer_lease = _acquire_patrol_consumer_lease(
                    args,
                    device,
                    android_port_reverse,
                    command_env,
                )
                if runtime_env in {"alpha", "beta", "gamma"}:
                    launcher_handoff = _provider_patrol_launcher_handoff(
                        args,
                        device,
                        command_env,
                        runtime_identity=provider_runtime_identity,
                    )
                    if launcher_handoff is not None:
                        _apply_launcher_handoff_to_command_env(
                            command_env,
                            launcher_handoff,
                        )
                        if consumer_lease is not None:
                            _bind_patrol_consumer_lease_to_handoff(
                                args,
                                device,
                                consumer_lease,
                                command_env,
                                launcher_handoff,
                            )
            patrol_target = _patrol_bundler_target(args.target)
            if not args.dry_run:
                _, patrol_target, patrol_wrapper_cleanup = (
                    _create_patrol_target_wrapper(
                        args.target,
                        typed_actor=typed_actor,
                    )
                )
            command = patrol_command(
                device,
                args,
                patrol_executable,
                dart_define_file=secret_define_path,
                launcher_handoff=launcher_handoff,
                patrol_target=patrol_target,
                typed_test_data_session_handoff=typed_actor is not None,
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
        except BaseException:
            _cleanup_patrol_target_wrapper(patrol_wrapper_cleanup)
            if consumer_lease is not None:
                release_consumer_lease(
                    target=consumer_lease[0],
                    device=consumer_lease[1],
                    consumer=consumer_lease[2],
                )
            if secret_define_path is not None and not args.dry_run:
                secret_define_path.unlink(missing_ok=True)
            raise
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
            device_evidence_error = ""
            device_evidence_capture: dict[str, Any] = {
                "status": "not-required",
            }
            device_evidence_stream: _IosDeviceEvidenceStream | None = None
            credential_cleanup_error = ""

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
                    if _is_ios_device(device):
                        device_evidence_stream = _IosDeviceEvidenceStream(
                            device_id=str(device.get("id") or ""),
                            log_path=run_dir / "device-evidence.log",
                            output_line_handler=(
                                handle_controlled_edge_output
                                if controlled_fault is not None
                                else None
                            ),
                        )
                        device_evidence_stream.start()
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
                            and device_evidence_stream is None
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
                if device_evidence_stream is not None:
                    try:
                        device_evidence_capture = device_evidence_stream.stop()
                    except Exception as error:  # noqa: BLE001
                        device_evidence_error = str(error)
                        device_evidence_capture = {
                            "status": "failed",
                            "deviceId": str(device.get("id") or ""),
                            "logPath": repo_relative(
                                run_dir / "device-evidence.log"
                            ),
                            "reason": device_evidence_error,
                        }
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
                _cleanup_patrol_target_wrapper(patrol_wrapper_cleanup)
                generated_secret_values = tuple(
                    dict.fromkeys(
                        (
                            *(
                                typed_actor.secret_values()
                                if typed_actor is not None
                                else ()
                            ),
                            *(
                                base64.b64encode(value.encode("utf-8")).decode(
                                    "ascii"
                                )
                                for value in (
                                    typed_actor.secret_values()
                                    if typed_actor is not None
                                    else ()
                                )
                            ),
                            *_provider_uat_secret_values(),
                        )
                    )
                )
                if generated_secret_values:
                    try:
                        credential_artifact_cleanup = {
                            "status": "passed",
                            "removedFiles": (
                                _purge_typed_actor_credential_artifacts(
                                    generated_secret_values
                                )
                            ),
                        }
                    except RuntimeError as error:
                        credential_cleanup_error = str(error)
                        credential_artifact_cleanup = {
                            "status": "failed",
                            "removedFiles": 0,
                        }
            if restore_error:
                result["exitCode"] = 2
                result["outputSummary"] = (
                    str(result.get("outputSummary") or "")
                    + "\ncontrolled edge fail-safe restore failed: "
                    + restore_error
                ).strip()
            if device_evidence_error:
                result["exitCode"] = 2
                result["outputSummary"] = (
                    str(result.get("outputSummary") or "")
                    + "\nexact-device iOS evidence stream failed: "
                    + device_evidence_error
                ).strip()
            if controlled_fault is not None and restore_request_count != 1:
                result["exitCode"] = 1
                result["outputSummary"] = (
                    str(result.get("outputSummary") or "")
                    + "\ncontrolled edge UAT did not emit exactly one restore request"
                ).strip()
            if credential_cleanup_error:
                result["exitCode"] = 2
                result["outputSummary"] = (
                    str(result.get("outputSummary") or "")
                    + "\nPatrol credential artifact cleanup failed: "
                    + credential_cleanup_error
                ).strip()
        raw_log_path = run_dir / "patrol.log"
        device_evidence_log_path = run_dir / "device-evidence.log"
        structured_evidence_log_path = (
            device_evidence_log_path
            if _is_ios_device(device) and device_evidence_log_path.is_file()
            else raw_log_path
        )
        raw_log = (
            raw_log_path.read_text(encoding="utf-8")
            if raw_log_path.is_file()
            else ""
        )
        apply_patrol_test_execution_summary(
            result,
            raw_log,
            dry_run=args.dry_run,
        )
        typed_blocker = (
            _first_typed_patrol_blocker(raw_log)
            if result["exitCode"] != 0 and not args.dry_run
            else {}
        )
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
        runtime_recovery_evidence = _read_runtime_recovery_evidence(
            structured_evidence_log_path,
        )
        feed_content_evidence = _read_feed_content_evidence(
            structured_evidence_log_path
        )
        controlled_edge_fault_evidence = _read_controlled_edge_fault_evidence(
            structured_evidence_log_path
        )
        controlled_edge_log = (
            structured_evidence_log_path.read_text(encoding="utf-8")
            if structured_evidence_log_path.is_file()
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
            structured_evidence_log_path,
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
            "structuredEvidenceLogPath": repo_relative(
                structured_evidence_log_path
            ),
            "deviceEvidenceCapture": (
                device_evidence_capture
                if not args.dry_run
                else {"status": "skipped", "reason": "dry-run"}
            ),
            "videoPlayback": _read_video_playback_evidence(
                structured_evidence_log_path,
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
            "credentialArtifactCleanup": credential_artifact_cleanup,
            "typedBlocker": typed_blocker,
        }
        report["runs"].append(result)
        report["caseResults"].append(
            {
                "caseId": (
                    f"patrol:{args.target}:{sanitize_device_id(str(device.get('id', '')))}"
                ),
                "status": (
                    "not_executed"
                    if args.dry_run
                    else ("passed" if result["exitCode"] == 0 else "failed")
                ),
                "deviceId": device.get("id", ""),
                "testExecution": result["testExecution"],
                **typed_blocker,
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

    report["status"] = (
        "gate_block"
        if gate_blocked
        else ("failed" if failed else ("dry_run" if args.dry_run else "passed"))
    )
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
