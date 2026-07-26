import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart';
import 'package:quwoquan_app/core/observability/runtime_api_latency_dispatcher.dart';

/// 统一的鉴权、401 刷新与 API 延迟观测客户端。
///
/// 能力级组合根可直接依赖本文件，避免为取得 HTTP client 而编译整个
/// `app_providers.dart` 聚合图。
final cloudHttpClientProvider = Provider<CloudHttpClient>((ref) {
  final latencyDispatcher = ref.watch(runtimeApiLatencyDispatcherProvider);
  final client = CloudHttpClient(
    authTokenProvider: ProviderBackedCloudAuthTokenProvider(
      () => ref.read(authSessionControllerProvider).accessToken,
    ),
    onUnauthorizedRefresh: (abortTrigger) => ref
        .read(authSessionControllerProvider.notifier)
        .refreshSessionIfNeeded(abortTrigger: abortTrigger),
    latencyObserver: latencyDispatcher.record,
  );
  ref.onDispose(client.close);
  return client;
});

/// Public bootstrap endpoints are intentionally isolated from session state.
///
/// They carry the same trace and latency telemetry as normal API calls but
/// never read, attach, refresh, or synthesize a bearer token.
final unauthenticatedCloudHttpClientProvider = Provider<CloudHttpClient>((ref) {
  final latencyDispatcher = ref.watch(runtimeApiLatencyDispatcherProvider);
  final client = CloudHttpClient(latencyObserver: latencyDispatcher.record);
  ref.onDispose(client.close);
  return client;
});

final runtimeApiLatencyDispatcherProvider =
    Provider<RuntimeApiLatencyDispatcher>(
      (ref) => RuntimeApiLatencyDispatcher(),
    );
