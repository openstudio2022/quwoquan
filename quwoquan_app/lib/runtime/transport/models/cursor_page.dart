class CursorPage<T> {
  const CursorPage({
    required this.items,
    this.nextCursor,
    this.totalCount,
    this.cacheFallbackError,
    this.cacheAgeMs,
  });

  final List<T> items;
  final String? nextCursor;
  final int? totalCount;
  final Object? cacheFallbackError;
  final int? cacheAgeMs;

  bool get isCacheFallback => cacheFallbackError != null;
}
