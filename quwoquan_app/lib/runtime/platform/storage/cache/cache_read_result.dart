/// 缓存读结果来源。
enum CacheReadSource { memory, disk, remote, seed, optimisticOverlay }

/// 缓存对象的新鲜度。
enum CacheFreshness { fresh, stale, expired, unknown }

/// 缓存对象与端云同步的当前状态。
enum CacheSyncState { idle, refreshing, offline, pendingWrite, conflict, error }

/// 对象保留等级。
enum CacheClass { pinned, recent, ephemeral }

/// 资源引用只保存业务可验证的元信息，不保存大资源字节。
class CacheResourceRef {
  const CacheResourceRef({
    required this.url,
    this.objectKey,
    this.version,
    this.variant,
  });

  final String url;
  final String? objectKey;
  final String? version;
  final String? variant;
}

/// 测试与观测读取的缓存诊断信息。
class CacheDiagnostics {
  const CacheDiagnostics({
    this.hitLayer,
    this.requestCount = 0,
    this.refreshElapsedMs,
    this.errorReason,
  });

  final String? hitLayer;
  final int requestCount;
  final int? refreshElapsedMs;
  final String? errorReason;
}

/// 面向 UI / Provider 的统一缓存输出合同。
class CacheReadResult<T> {
  const CacheReadResult({
    required this.value,
    required this.source,
    required this.freshness,
    required this.syncState,
    required this.cacheClass,
    this.objectVersion,
    this.resourceRefs = const <CacheResourceRef>[],
    this.overlay,
    this.diagnostics = const CacheDiagnostics(),
  });

  factory CacheReadResult.remote(
    T value, {
    String? objectVersion,
    CacheClass cacheClass = CacheClass.recent,
  }) {
    return CacheReadResult<T>(
      value: value,
      source: CacheReadSource.remote,
      freshness: CacheFreshness.fresh,
      syncState: CacheSyncState.idle,
      cacheClass: cacheClass,
      objectVersion: objectVersion,
      diagnostics: const CacheDiagnostics(hitLayer: 'remote', requestCount: 1),
    );
  }

  final T value;
  final CacheReadSource source;
  final CacheFreshness freshness;
  final CacheSyncState syncState;
  final String? objectVersion;
  final CacheClass cacheClass;
  final List<CacheResourceRef> resourceRefs;
  final Object? overlay;
  final CacheDiagnostics diagnostics;
}
