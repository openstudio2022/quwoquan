#!/usr/bin/env python3
"""Run page-level Patrol smoke tests for one environment target.

实现单轨落在同名子包 ``environment_patrol_smoke/``（constants / session /
evidence / handoff / device_runtime / cli_args / execution / devices /
wrapper / entry）；本文件是稳定 CLI 入口，全部被外部消费的符号由这里 re-export。

契约文本锚点（供只读门禁逐字扫描本入口文件，勿删）：

- 默认 Patrol target 是 video_playback_canary__user_acceptance_test.dart，
  core readback target 是 app_core_readback__user_acceptance_test.dart。
- 设备命令环境按 topology 逐字段显式注入 MEDIA_AVATAR_CDN_BASE_URL、
  MEDIA_IMAGE_CDN_BASE_URL、MEDIA_VIDEO_CDN_BASE_URL、MEDIA_UPLOAD_BASE_URL，
  不存在单一 media base fallback。
- "local-gamma" 等环境别名走 runtime_anonymous_session 设备端匿名登录。
"""

from __future__ import annotations

import argparse  # noqa: F401
import atexit  # noqa: F401
import base64  # noqa: F401
import datetime as dt  # noqa: F401
import hashlib  # noqa: F401
import json  # noqa: F401
import os  # noqa: F401
import queue  # noqa: F401
import re  # noqa: F401
import signal  # noqa: F401
import shutil  # noqa: F401
import subprocess  # noqa: F401
import sys
import tempfile  # noqa: F401
import threading  # noqa: F401
import time  # noqa: F401
import urllib.parse  # noqa: F401
import zipfile  # noqa: F401
from dataclasses import dataclass  # noqa: F401
from pathlib import Path
from typing import Any, Callable  # noqa: F401

sys.dont_write_bytecode = True

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from quwoquan_ops.ci.device_matrix.evidence import (  # noqa: E402,F401
    capture_device_screenshot,
    repo_relative,
    sanitize_device_id,
    write_device_manifest,
    write_discovered_devices_snapshot,
    write_json,
)
from quwoquan_ops.ci.device_matrix.android import resolve_android_debug_bridge  # noqa: E402,F401
from quwoquan_ops.cli.lib.local_runtime_reservation import (  # noqa: E402,F401
    acquire_local_runtime_use_lock,
)
from quwoquan_ops.cli.lib.patrol_execution_lock import (  # noqa: E402,F401
    PATROL_EXECUTION_LOCK,
    acquire_patrol_execution_lock as _acquire_patrol_execution_lock,
)
from quwoquan_ops.cli.lib.local_runtime_consumer_lease import (  # noqa: E402,F401
    acquire_consumer_lease,
    release_consumer_lease,
)
from quwoquan_ops.cli.lib.local_controlled_edge_fault import (  # noqa: E402,F401
    CONTROLLED_EDGE_SERVICES,
    ControlledEdgeFault,
    begin_controlled_edge_fault,
)
from quwoquan_ops.cli.lib.test_live_content_binding import (  # noqa: E402,F401
    load_test_live_content_binding,
)
from quwoquan_ops.cli.lib.test_live_startup_attempt_receipt import (  # noqa: E402,F401
    load_test_live_startup_attempt,
)
from quwoquan_ops.cli.lib.patrol_cli import resolve_patrol_cli  # noqa: E402,F401
from quwoquan_ops.cli.lib.environment_topology import (  # noqa: E402,F401
    get_target,
    load_environment_topology,
)
from quwoquan_ops.cli.lib.flutter_android_device_proxy import (  # noqa: E402,F401
    ANDROID_DEVICE_INVENTORY_ENV,
    REAL_FLUTTER_ENV,
)
from quwoquan_ops.cli.lib.video_playback_evidence import (  # noqa: E402,F401
    VIDEO_PLAYBACK_EVIDENCE_MARKER,
    read_native_video_playback_evidence,
)

from quwoquan_ops.cli.smoke.environment_patrol_smoke import (  # noqa: E402,F401
    ACCOUNT_CLOSURE_TARGET,
    ACCOUNT_ENFORCEMENT_CANDIDATE_DIGEST_PATTERN,
    ACCOUNT_ENFORCEMENT_EVIDENCE_PREFIX,
    ACCOUNT_ENFORCEMENT_EXPECTED_EVIDENCE,
    ACCOUNT_ENFORCEMENT_TARGETS,
    ALPHA_APP_CONTENT_TYPED_SESSION_TARGETS,
    ANDROID_DEVICE_EVIDENCE_LOG_TAG,
    ANDROID_DEVICE_EVIDENCE_TOKENS,
    ANDROID_DEVICE_PROXY,
    APP_DIR,
    APP_CONTENT_VIDEO_PAGE_COUNT_ENV,
    APP_UAT_PAGE_EVIDENCE_READY_PREFIX,
    APP_UAT_CASE_EVIDENCE_PREFIX,
    APP_UAT_CASE_EVIDENCE_MISSING,
    APP_UAT_CASE_EVIDENCE_SCHEMA,
    APP_LAUNCHER_HANDOFF_BUILDER,
    BASIC_VIABILITY_TARGET,
    CANONICAL_DIGEST_PATTERN,
    CANONICAL_TEST_LIVE_DART_DEFINE_KEYS,
    CONTROLLED_EDGE_FAULT_COPY_KEYS,
    CONTROLLED_EDGE_FAULT_EVIDENCE_PREFIX,
    CONTROLLED_EDGE_FAULT_TARGET,
    CONTROLLED_EDGE_RESTORE_REQUEST_PREFIX,
    CORE_READBACK_TARGET,
    DEFAULT_REPORT,
    DEFAULT_TARGET,
    FEED_CONTENT_EVIDENCE_PREFIX,
    FEED_LOAD_TARGET,
    FORBIDDEN_PROD_PLAYBACK_CANARY_TOKENS,
    HOME_VIDEO_PLAYBACK_TARGET,
    IOS_DEVICE_EVIDENCE_TOKENS,
    IOS_RUNNER_UITESTS_XCTRUNNER_BUNDLE_ID,
    IOS_RUNTIME_VERSION_PATTERN,
    IOS_SDK_VERSION_PATTERN,
    LOCAL_ENVIRONMENT_ALIAS_TARGETS,
    LOCAL_TARGETS,
    MESSAGE_HOME_TARGET,
    PATROL_EXECUTION_SUMMARY_PATTERN,
    PATROL_FLUTTER_COMMAND_ENV,
    PATROL_IOS_PRODUCTS_DIR,
    PATROL_TEST_DIRECTORY,
    PROFILE_JOURNEY_TARGET,
    PROVIDER_CONFORMANCE_RUNTIME_IDENTITY_COMMON_FIELDS,
    PROVIDER_CONFORMANCE_RUNTIME_IDENTITY_ENV,
    PROVIDER_CONFORMANCE_RUNTIME_IDENTITY_IMMUTABLE_FIELDS,
    PROVIDER_CONFORMANCE_RUNTIME_IDENTITY_MUTABLE_FIELDS,
    PROVIDER_CONFORMANCE_RUNTIME_IDENTITY_SCHEMA,
    RELEASE_APP_UAT_DEFINES,
    RELEASE_SAMPLE_MATRIX_TARGET,
    RUNTIME_ANONYMOUS_SESSION_MODES,
    RUNTIME_RECOVERY_EVIDENCE_FIELDS,
    RUNTIME_RECOVERY_EVIDENCE_PREFIX,
    RUNTIME_RECOVERY_TARGET,
    TYPED_AUTHENTICATED_SESSION_TARGETS,
    TYPED_TEST_DATA_ACTOR_ENV,
    TYPED_TEST_DATA_CONVERSATION_ENV,
    TYPED_TEST_DATA_CONVERSATION_TARGETS,
    TypedTestDataActor,
    TypedTestDataConversation,
    XCODE_GLOBAL_PRODUCTS_DIR,
    XCODE_IOS_SIMULATOR_SDK_PATTERN,
    XCTEST_EXECUTION_SUMMARY_PATTERN,
    android_release_uat_package,
    ios_release_uat_bundle_ids,
    _AndroidDeviceEvidenceStream,
    _IosDeviceEvidenceStream,
    _account_enforcement_phase,
    _account_enforcement_subject_digest,
    _acquire_patrol_consumer_lease,
    _android_target_platform,
    _android_device_evidence_commands,
    _apply_feed_content_evidence_gate,
    _apply_launcher_handoff_to_command_env,
    _bind_patrol_consumer_lease_to_handoff,
    _bind_typed_test_data_actor,
    _canonical_patrol_uat_targets,
    _canonical_handoff_projection,
    _test_host_dart_defines,
    _canonical_test_live_launcher_handoff,
    _cleanup_patrol_target_wrapper,
    _create_patrol_secret_define_file,
    _create_patrol_target_wrapper,
    _device_command_env,
    _device_evidence_stream,
    _effective_base_urls_for_device,
    _enrich_ios_simulator_runtime_versions,
    _evidence_class_for_runtime,
    _explicit_android_devices,
    _first_typed_patrol_blocker,
    _generated_artifact_contains_any,
    _generated_patrol_artifact_candidates,
    _ios_device_evidence_command,
    _is_account_enforcement_target,
    _is_android_device,
    _is_controlled_edge_fault_target,
    _is_feed_load_target,
    _is_ios_device,
    _is_local_target,
    _is_runtime_recovery_target,
    _load_release_uat_cases_b64,
    _local_target_for_environment_alias,
    _local_tls_trust_evidence,
    _missing_required_args,
    _output_evidence_ref,
    _patrol_bundler_target,
    _prepare_android_local_port_reverse,
    _prepare_execution_session,
    _provider_patrol_launcher_handoff,
    _provider_uat_secret_values,
    _public_video_canary_session_mode,
    _purge_typed_actor_credential_artifacts,
    _read_account_enforcement_evidence,
    _read_controlled_edge_fault_evidence,
    _read_feed_content_evidence,
    _read_runtime_recovery_evidence,
    _read_video_playback_evidence,
    _redact_command,
    _redact_text,
    _requires_account_closure,
    _requires_native_video_playback_signals,
    _requires_typed_test_data_conversation,
    _requires_typed_authenticated_session,
    _requires_video_playback_canary,
    _reset_release_uat_device_state,
    _resolved_media_base_urls,
    _resolved_owner_id,
    _resolved_persona_id,
    _runtime_anonymous_session_mode,
    _runtime_env_for_alias,
    _select_compatible_ios_devices,
    _stream_contains_any,
    _structured_evidence_log_path,
    _terminate_process_group,
    _typed_test_data_actor_from_environment,
    _typed_test_data_conversation_from_environment,
    _uses_persisted_device_session,
    _uses_public_video_canary_anonymous_session,
    _uses_runtime_anonymous_session,
    _validate_account_closure_execution,
    _validate_account_enforcement_device_matrix,
    _validate_runtime_recovery_device_matrix,
    _validate_video_playback_canary_work_id,
    _validated_provider_patrol_runtime_identity,
    apply_patrol_test_execution_summary,
    discover_devices,
    dry_run_devices,
    ensure_patrol_ios_products_bridge,
    ios_sdk_version,
    load_remote_api_evidence,
    main,
    parse_args,
    patrol_command,
    patrol_ios_runtime_argument,
    patrol_test_execution_failure_reason,
    patrol_test_execution_summary,
    run_command,
    summarize_output,
    utc_now,
    write_report,
    xcode_ios_simulator_sdk_version,
)

if __name__ == "__main__":
    raise SystemExit(main())
