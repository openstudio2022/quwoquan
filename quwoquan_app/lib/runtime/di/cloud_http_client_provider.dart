import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/runtime/transport/http/cloud_http_client.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/observability/runtime_api_latency_dispatcher.dart';
import 'package:quwoquan_app/runtime/platform/cloud_transport_failure_classifier.dart';

/// 统一的鉴权、401 刷新与 API 延迟观测客户端。
///
/// 能力级组合根可直接依赖本文件，避免为取得 HTTP client 而编译整个
/// `app_providers.dart` 聚合图。
final cloudHttpClientProvider = Provider<CloudHttpClient>((ref) {
  final latencyDispatcher = ref.watch(runtimeApiLatencyDispatcherProvider);
  final client = CloudHttpClient(
    authTokenProvider: ProviderBackedCloudAuthTokenProvider(
      () => ref
          .read(authSessionControllerProvider.notifier)
          .accessTokenForRequest(),
    ),
    onUnauthorizedRefresh: (abortTrigger) => ref
        .read(authSessionControllerProvider.notifier)
        .refreshSessionIfNeeded(abortTrigger: abortTrigger),
    onAuthoritativeSessionFailure: (failure, presentedAccessToken) => ref
        .read(authSessionControllerProvider.notifier)
        .handleAuthoritativeSessionFailure(
          failure,
          presentedAccessToken: presentedAccessToken,
        ),
    latencyObserver: latencyDispatcher.record,
    transportFailureClassifier: classifyCloudTransportFailure,
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
  final client = CloudHttpClient(
    latencyObserver: latencyDispatcher.record,
    transportFailureClassifier: classifyCloudTransportFailure,
  );
  ref.onDispose(client.close);
  return client;
});

/// 媒体数据面（对象存储上传 / 媒体 CDN 下载）的统一客户端。
///
/// 与 Gateway 客户端共享超时、单次尝试、`CloudErrorMapper` 错误映射、传输失败
/// 分类与 API 延迟观测，但**永不附带 bearer**：数据面授权只由服务端签发的 URL
/// 承载。这里也是媒体数据面唯一被认可的超时声明点——adapter 不得自建
/// `http.Client()` 或各写一套 `.timeout(...)`。
final mediaDataPlaneHttpClientProvider = Provider<CloudHttpClient>((ref) {
  final latencyDispatcher = ref.watch(runtimeApiLatencyDispatcherProvider);
  final client = CloudHttpClient(
    // 媒体字节流远大于 Gateway JSON：单次尝试的挂钟预算按分钟计，
    // 否则大视频上传/下载会在传输中途被 Gateway 级 12s 预算掐断。
    timeout: const Duration(minutes: 5),
    latencyObserver: latencyDispatcher.record,
    transportFailureClassifier: classifyCloudTransportFailure,
  );
  ref.onDispose(client.close);
  return client;
});

final runtimeApiLatencyDispatcherProvider =
    Provider<RuntimeApiLatencyDispatcher>(
      (ref) => RuntimeApiLatencyDispatcher(),
    );
