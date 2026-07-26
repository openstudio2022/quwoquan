#!/usr/bin/env python3
"""验证 App Cloud P0 安全切换保持失败关闭且无身份串线。"""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "quwoquan_app"


def read(relative: str) -> str:
    path = ROOT / relative
    if not path.is_file():
        raise AssertionError(f"缺少文件: {relative}")
    return path.read_text(encoding="utf-8")


def require(relative: str, *tokens: str) -> None:
    text = read(relative)
    missing = [token for token in tokens if token not in text]
    if missing:
        raise AssertionError(f"{relative} 缺少安全契约: {missing}")


def require_package(relative_dir: str, *tokens: str) -> None:
    package_dir = ROOT / relative_dir
    if not package_dir.is_dir():
        raise AssertionError(f"缺少目录: {relative_dir}")
    sources = sorted(
        path for path in package_dir.glob("*.go") if not path.name.endswith("_test.go")
    )
    text = "\n".join(path.read_text(encoding="utf-8") for path in sources)
    missing = [token for token in tokens if token not in text]
    if missing:
        raise AssertionError(f"{relative_dir} package 缺少安全契约: {missing}")


def require_glob(relative_dir: str, pattern: str, *tokens: str) -> None:
    source_dir = ROOT / relative_dir
    if not source_dir.is_dir():
        raise AssertionError(f"缺少目录: {relative_dir}")
    sources = sorted(source_dir.glob(pattern))
    if not sources:
        raise AssertionError(f"{relative_dir} 缺少匹配文件: {pattern}")
    text = "\n".join(path.read_text(encoding="utf-8") for path in sources)
    missing = [token for token in tokens if token not in text]
    if missing:
        raise AssertionError(
            f"{relative_dir}/{pattern} 聚合源码缺少安全契约: {missing}"
        )


def forbid(relative: str, *tokens: str) -> None:
    text = read(relative)
    found = [token for token in tokens if token in text]
    if found:
        raise AssertionError(f"{relative} 命中禁用实现: {found}")


def verify_sensitive_logs() -> None:
    cloud_root = APP / "lib" / "cloud"
    logging_secret = re.compile(
        r"(?:debugPrint|print|logger\.\w+)\s*\("
        r"[^)]{0,500}"
        r"(?:accessToken|refreshToken|access_token|Authorization|"
        r"presignUrl|actorScope|personaId|accountId)",
        re.IGNORECASE | re.DOTALL,
    )
    violations: list[str] = []
    for path in sorted(cloud_root.rglob("*.dart")):
        text = path.read_text(encoding="utf-8")
        if logging_secret.search(text):
            violations.append(str(path.relative_to(ROOT)))
    if violations:
        raise AssertionError(f"Cloud 日志可能泄露身份或凭据: {violations}")


def main() -> int:
    require(
        "quwoquan_app/lib/cloud/runtime/auth/realtime_connection_credential.dart",
        "resolveWebSocket",
        "RealtimeApiMetadata.issueConnectionTicketPath",
        "'Authorization': 'Bearer $token'",
        "'ticket': ticket",
        "websocket credential requires a connection ticket",
        "return null;",
    )
    forbid(
        "quwoquan_app/lib/cloud/runtime/auth/realtime_connection_credential.dart",
        "'access_token': _accessToken",
        "runtimeEnvironment != 'gamma'",
    )
    require(
        "quwoquan_app/lib/cloud/services/realtime/transport/websocket_transport.dart",
        "RealtimeConnectionCredential.resolveWebSocket",
        "'auth_ack'",
    )
    forbid(
        "quwoquan_app/lib/cloud/services/realtime/transport/websocket_transport.dart",
        "'userId':",
        "'topics':",
    )
    require(
        "quwoquan_app/lib/cloud/rtc/rtc_signal_events.dart",
        "realtime 单通道",
        "RtcSignalEventBus",
        "parseRtcWsPayload",
    )
    require(
        "quwoquan_app/lib/cloud/rtc/incoming_call_coordinator.dart",
        "rtcSignalEventBusProvider",
        "不再维护独立信令 WebSocket",
    )
    require(
        "quwoquan_app/lib/cloud/services/realtime/transport/longpoll_transport.dart",
        "RealtimeConnectionCredential.resolveHttp",
        "credential.authorizeHttp",
        "statusCode == 401",
        "statusCode == 403",
    )
    forbid(
        "quwoquan_app/lib/cloud/services/realtime/transport/longpoll_transport.dart",
        "'userId':",
    )

    require(
        "quwoquan_app/lib/cloud/services/assistant/assistant_facets.dart",
        "json['granted'] == true && revokedAt.isEmpty",
    )
    forbid(
        "quwoquan_app/lib/cloud/services/assistant/assistant_facets.dart",
        "json['granted'] == true || revokedAt.isEmpty",
    )
    require(
        "quwoquan_app/lib/cloud/services/assistant/assistant_consent_store.dart",
        "AssistantConsentStore({",
        "required String actorScope",
        "sha256.convert",
    )
    forbid(
        "quwoquan_app/lib/cloud/services/assistant/assistant_consent_store.dart",
        "assistant_skill_consents_v1')",
    )
    forbid(
        "quwoquan_app/lib/cloud/services/assistant/assistant_repository.dart",
        "json['granted'] == true || revokedAt.isEmpty",
        "assistant_skill_consents_v1')",
        "return local;",
        "upsert(fallback)",
    )
    require_package(
        "quwoquan_service/services/assistant-service/internal/assistant/skill_consent/application",
        "assistant consent store is not configured",
        "return nil, StoreUnavailable()",
        "return assistant.SkillConsent{}, StoreUnavailable()",
        "return StoreUnavailable()",
        "return rterr.NewUnavailable(",
    )
    require(
        "quwoquan_service/services/assistant-service/tests/local_contract/assistant/assistant_conversation/consent_fail_closed__security__local_contract_test.go",
        "TestAssistantConsentFailsClosedWithoutStore",
        "TestAssistantConsentLifecycleUsesAuthoritativeStore",
    )

    require(
        "quwoquan_app/lib/cloud/services/behavior/behavior_repository.dart",
        "ActorQueuePartition",
        "ActorQueueStorage",
        "actorPartitionKey",
        ".acceptsEnvelope(",
        ".moveToDlq(",
        "clearPendingForLogout",
    )
    forbid(
        "quwoquan_app/lib/cloud/services/behavior/behavior_repository.dart",
        "queuePartition ??",
        "httpClient ?? CloudHttpClient()",
    )
    require(
        "quwoquan_app/lib/core/telemetry/app_telemetry_outbox.dart",
        "ActorQueuePartition",
        "ActorQueueStorage",
        "actorPartitionKey",
        ".acceptsEnvelope(",
        ".moveToDlq(",
        "ActorQueueSignalKind.overflowMoved",
        "idempotencyKey: sealed.digest",
    )
    require(
        "quwoquan_app/lib/core/telemetry/app_telemetry_transport.dart",
        "OpsApiMetadata.reportEventBatchPath",
        "required CloudHttpClient httpClient",
        "'Idempotency-Key': idempotencyKey",
        "CloudErrorMapper.fromStatusCode",
    )
    retired_ops_repository = (
        ROOT / "quwoquan_app/lib/cloud/services/ops/ops_event_repository.dart"
    )
    if retired_ops_repository.exists():
        raise AssertionError(
            "退休的 OpsEventRepository 不得恢复；产品遥测唯一出口是 "
            "AppTelemetryOutbox + CloudAppTelemetryTransport"
        )
    require(
        "quwoquan_app/lib/infrastructure/local/actor_queue/actor_queue_storage.dart",
        "SecureActorQueueEncryptionKeyStore",
        "ActorQueueSessionBoundary",
        "openEncryptedStringBoxOrNull",
        "moveToDlq",
        "overflowMoved",
        "Future<void> purge(",
    )
    for relative in (
        "quwoquan_app/lib/cloud/services/behavior/behavior_repository.dart",
        "quwoquan_app/lib/core/telemetry/app_telemetry_outbox.dart",
    ):
        require(relative, "ActorQueueSignalKind.overflowMoved")
    require(
        "quwoquan_app/lib/core/services/hive_runtime.dart",
        "openEncryptedStringBoxOrNull",
        "HiveAesCipher(encryptionKey)",
    )
    require(
        "quwoquan_app/lib/ui/settings/pages/settings_page.dart",
        "behaviorRepositoryProvider).clearPendingForLogout()",
        "appTelemetryReporterProvider).clearPendingForLogout()",
    )
    require(
        "quwoquan_app/lib/core/di/ops_event_dependencies.dart",
        "accountId: session.isAuthenticated ? session.ownerId : ''",
        "actorQueueSessionBoundaryProvider",
        "previous: _partitionFor(previous)",
        "current: _partitionFor(next)",
        "AppExceptionTelemetryService.instance.bind",
    )
    require_glob(
        "quwoquan_app/lib/core/providers",
        "app_providers*.dart",
        "accountId: accountId",
        "consentActorScope = '$accountId/$personaId'",
    )
    require(
        "quwoquan_app/lib/assistant/observability/logging/app_exception_telemetry_service.dart",
        "RuntimeLogger",
        "RuntimeLogCatalog.failureCodes['app_uncaught_flutter']!",
        "RuntimeLogCorrelation(",
        "await logger.exception(",
        "await logger.flush()",
    )
    forbid(
        "quwoquan_app/lib/assistant/observability/logging/app_exception_telemetry_service.dart",
        "AppTelemetryRecorder",
        "AppTelemetryPayload.runtimeException",
        "ActorQueueStorage",
        "actorPartitionKey",
        ".moveToDlq(",
        "package:hive",
    )

    content_object_uploader = (
        "quwoquan_app/lib/cloud/remote/content/media/"
        "content_media_object_uploader.dart"
    )
    require(
        content_object_uploader,
        "http.AbortableStreamedRequest",
        "abortTrigger: abortTrigger",
        "response.stream.drain<void>()",
    )
    forbid(content_object_uploader, "readAsBytes(")

    profile_object_uploader = (
        "quwoquan_app/lib/cloud/services/user/profile_media_upload_gateway.dart"
    )
    require(
        profile_object_uploader,
        "ContentMediaUploadCoordinator",
        "ContentMediaSourceReader",
        "ContentMediaStreamObjectUpload",
        "uploadPreparedSource",
        "ContentMediaAccessPolicy.ownerOnly",
    )
    forbid(
        profile_object_uploader,
        "readAsBytes(",
        "package:http/http.dart",
    )
    require(
        "quwoquan_app/lib/cloud/remote/content/media/local_media_upload_source.dart",
        "prepareLocalFileByteSource",
    )
    forbid(
        "quwoquan_app/lib/cloud/remote/content/media/local_media_upload_source.dart",
        "dart:io",
    )
    require(
        "quwoquan_app/lib/core/platform/local_file_byte_source_io.dart",
        "sha256.bind(file.openRead()).first",
        "openRead: file.openRead",
    )
    require(
        "quwoquan_app/lib/cloud/media/media_upload_manager.dart",
        "coordinator.uploadPreparedSource",
        "required this.sourceReader",
        "required this.uploadStream",
    )
    forbid(
        "quwoquan_app/lib/cloud/media/media_upload_manager.dart",
        "CloudHttpClient",
        "CloudRequestHeaders",
        "ContentApiMetadata",
        "readAsBytes(",
    )
    require(
        "quwoquan_app/lib/cloud/remote/content/media/content_media_remote.dart",
        "contentMediaUploadSessionInitMediaUpload",
        "contentMediaUploadSessionCompleteMediaUpload",
        "contentMediaUploadSessionAbortMediaUpload",
    )

    require(
        "quwoquan_service/tools/codegen_app_metadata/metadata_types.go",
        'return "required"',
        "禁止 fail-open",
    )
    require(
        "quwoquan_service/tools/codegen_app_metadata/api_metadata_codegen.go",
        "duplicate short operation id",
    )
    require(
        "quwoquan_app/scripts/auth/verify_auth_policy_contract.py",
        "canonicalOperationId",
        "accepted ContractGraph",
        "generated != op_to_mode",
    )

    verify_sensitive_logs()
    print("PASS: App Cloud 安全切换契约")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"FAIL: {exc}")
        raise SystemExit(1)
