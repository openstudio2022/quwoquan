"""run_environment_patrol_smoke 的实现包。

唯一稳定入口是 ``quwoquan_ops/cli/smoke/run_environment_patrol_smoke.py``（薄壳
re-export）；本包按职责切分：

- ``constants``：target 路径、证据前缀、正则与目录常量。
- ``session``：target 谓词、环境别名解析、typed test-data actor 与会话准备。
- ``evidence``：运行证据读取、设备矩阵校验与 iOS 证据流。
- ``handoff``：test-live launcher handoff 构建/投影与 provider runtime 身份校验。
- ``device_runtime``：设备命令 env、端口反转、consumer lease 与 release UAT 状态复位。
- ``cli_args``：CLI 参数解析与输出脱敏。
- ``execution``：命令运行、进程组终止与执行摘要归因。
- ``devices``：iOS/Android 设备发现与 dry-run。
- ``wrapper``：Patrol target wrapper、secret define 与 patrol_command 组装。
- ``entry``：CLI main 与报告落盘。
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from .constants import (  # noqa: E402,F401
    ACCOUNT_CLOSURE_TARGET,
    ACCOUNT_ENFORCEMENT_CANDIDATE_DIGEST_PATTERN,
    ACCOUNT_ENFORCEMENT_EVIDENCE_PREFIX,
    ACCOUNT_ENFORCEMENT_EXPECTED_EVIDENCE,
    ACCOUNT_ENFORCEMENT_TARGETS,
    ALPHA_APP_CONTENT_TYPED_SESSION_TARGETS,
    ANDROID_DEVICE_PROXY,
    ANDROID_RELEASE_UAT_PACKAGE,
    APP_DIR,
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
    IOS_RELEASE_UAT_BUNDLE_IDS,
    IOS_RUNTIME_VERSION_PATTERN,
    IOS_SDK_VERSION_PATTERN,
    LOCAL_ENVIRONMENT_ALIAS_TARGETS,
    LOCAL_TARGETS,
    PATROL_EXECUTION_SUMMARY_PATTERN,
    PATROL_FLUTTER_COMMAND_ENV,
    PATROL_IOS_PRODUCTS_DIR,
    PATROL_TEST_DIRECTORY,
    PROVIDER_CONFORMANCE_RUNTIME_IDENTITY_COMMON_FIELDS,
    PROVIDER_CONFORMANCE_RUNTIME_IDENTITY_ENV,
    PROVIDER_CONFORMANCE_RUNTIME_IDENTITY_IMMUTABLE_FIELDS,
    PROVIDER_CONFORMANCE_RUNTIME_IDENTITY_MUTABLE_FIELDS,
    PROVIDER_CONFORMANCE_RUNTIME_IDENTITY_SCHEMA,
    RELEASE_APP_UAT_DEFINES,
    REPO_ROOT,
    RUNTIME_ANONYMOUS_SESSION_MODES,
    RUNTIME_RECOVERY_EVIDENCE_FIELDS,
    RUNTIME_RECOVERY_EVIDENCE_PREFIX,
    RUNTIME_RECOVERY_TARGET,
    TYPED_AUTHENTICATED_SESSION_TARGETS,
    TYPED_TEST_DATA_ACTOR_ENV,
    XCODE_GLOBAL_PRODUCTS_DIR,
    XCODE_IOS_SIMULATOR_SDK_PATTERN,
    XCTEST_EXECUTION_SUMMARY_PATTERN,
    utc_now,
)
from .session import (  # noqa: E402,F401
    TypedTestDataActor,
    _account_enforcement_phase,
    _account_enforcement_subject_digest,
    _bind_typed_test_data_actor,
    _evidence_class_for_runtime,
    _is_account_enforcement_target,
    _is_controlled_edge_fault_target,
    _is_feed_load_target,
    _is_local_target,
    _is_runtime_recovery_target,
    _local_target_for_environment_alias,
    _missing_required_args,
    _prepare_execution_session,
    _public_video_canary_session_mode,
    _requires_account_closure,
    _requires_native_video_playback_signals,
    _requires_typed_authenticated_session,
    _requires_video_playback_canary,
    _resolved_media_base_urls,
    _resolved_owner_id,
    _resolved_persona_id,
    _runtime_anonymous_session_mode,
    _runtime_env_for_alias,
    _typed_test_data_actor_from_environment,
    _uses_persisted_device_session,
    _uses_public_video_canary_anonymous_session,
    _uses_runtime_anonymous_session,
    _validate_account_closure_execution,
    _validate_video_playback_canary_work_id,
)
from .evidence import (  # noqa: E402,F401
    _IosDeviceEvidenceStream,
    _ios_device_evidence_command,
    _is_ios_device,
    _output_evidence_ref,
    _read_account_enforcement_evidence,
    _read_controlled_edge_fault_evidence,
    _read_feed_content_evidence,
    _read_runtime_recovery_evidence,
    _read_video_playback_evidence,
    _validate_account_enforcement_device_matrix,
    _validate_runtime_recovery_device_matrix,
    load_remote_api_evidence,
)
from .handoff import (  # noqa: E402,F401
    _apply_launcher_handoff_to_command_env,
    _canonical_handoff_projection,
    _canonical_test_live_launcher_handoff,
    _effective_base_urls_for_device,
    _provider_patrol_launcher_handoff,
    _validated_provider_patrol_runtime_identity,
)
from .device_runtime import (  # noqa: E402,F401
    _acquire_patrol_consumer_lease,
    _bind_patrol_consumer_lease_to_handoff,
    _device_command_env,
    _local_tls_trust_evidence,
    _prepare_android_local_port_reverse,
    _reset_release_uat_device_state,
)
from .cli_args import (  # noqa: E402,F401
    _load_release_uat_cases_b64,
    _redact_command,
    _redact_text,
    parse_args,
    summarize_output,
)
from .execution import (  # noqa: E402,F401
    _first_typed_patrol_blocker,
    _terminate_process_group,
    apply_patrol_test_execution_summary,
    patrol_test_execution_failure_reason,
    patrol_test_execution_summary,
    run_command,
)
from .devices import (  # noqa: E402,F401
    _android_target_platform,
    _enrich_ios_simulator_runtime_versions,
    _explicit_android_devices,
    _select_compatible_ios_devices,
    discover_devices,
    dry_run_devices,
    ensure_patrol_ios_products_bridge,
    ios_sdk_version,
    patrol_ios_runtime_argument,
    xcode_ios_simulator_sdk_version,
)
from .wrapper import (  # noqa: E402,F401
    _cleanup_patrol_target_wrapper,
    _create_patrol_secret_define_file,
    _create_patrol_target_wrapper,
    _generated_artifact_contains_any,
    _generated_patrol_artifact_candidates,
    _patrol_bundler_target,
    _provider_uat_secret_values,
    _purge_typed_actor_credential_artifacts,
    _stream_contains_any,
    patrol_command,
)
from .entry import main, write_report  # noqa: E402,F401
