import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_log_models.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_log_service.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_trace_context_store.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart';

/// 统一的鉴权、401 刷新与 API 延迟观测客户端。
///
/// 能力级组合根可直接依赖本文件，避免为取得 HTTP client 而编译整个
/// `app_providers.dart` 聚合图。
final cloudHttpClientProvider = Provider<CloudHttpClient>((ref) {
  final client = CloudHttpClient(
    authTokenProvider: ProviderBackedCloudAuthTokenProvider(
      () => ref.read(authSessionControllerProvider).accessToken,
    ),
    onUnauthorizedRefresh: (abortTrigger) => ref
        .read(authSessionControllerProvider.notifier)
        .refreshSessionIfNeeded(abortTrigger: abortTrigger),
    latencyObserver: _recordCloudApiLatency,
  );
  ref.onDispose(client.close);
  return client;
});

/// Public bootstrap endpoints are intentionally isolated from session state.
///
/// They carry the same trace and latency telemetry as normal API calls but
/// never read, attach, refresh, or synthesize a bearer token.
final unauthenticatedCloudHttpClientProvider = Provider<CloudHttpClient>((ref) {
  final client = CloudHttpClient(latencyObserver: _recordCloudApiLatency);
  ref.onDispose(client.close);
  return client;
});

void _recordCloudApiLatency(
  String method,
  String path,
  int elapsedMs,
  int statusCode,
) {
  AppLogService.instance.writeEvent(
    logType: AppLogType.perf,
    level: statusCode >= 0 && statusCode < 400
        ? AppLogLevel.info
        : AppLogLevel.warn,
    context: AppLogContext(
      sessionId: AppTraceContextStore.instance.sessionId,
      requestId: AppTraceContextStore.instance.newRequestId(),
      target: 'cloud_api',
      action: '$method $path',
    ),
    payload: <String, dynamic>{
      'kind': 'api_latency',
      'method': method,
      'path': path,
      'elapsedMs': elapsedMs,
      'statusCode': statusCode,
    },
  );
}
