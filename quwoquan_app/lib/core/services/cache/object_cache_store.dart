import 'dart:collection';

import 'package:quwoquan_app/core/services/cache/cache_read_result.dart';

class ObjectCacheEntry<T> {
  const ObjectCacheEntry({
    required this.id,
    required this.value,
    required this.cachedAt,
    this.objectVersion,
    this.cacheClass = CacheClass.recent,
  });

  final String id;
  final T value;
  final DateTime cachedAt;
  final String? objectVersion;
  final CacheClass cacheClass;

  bool isFresh(Duration maxAge, DateTime now) {
    return now.difference(cachedAt) <= maxAge;
  }
}

/// 对象级有界 LRU 内存缓存。
///
/// 持久 feed 只由 `ContentQuerySnapshotStore` 拥有；本类不创建第二个
/// feed store，也不将进程内 Map 标记为 disk hit。
class ObjectCacheStore<T> {
  ObjectCacheStore({
    this.maxMemoryEntries = 200,
    this.freshFor = const Duration(minutes: 15),
  });

  final int maxMemoryEntries;
  final Duration freshFor;
  final LinkedHashMap<String, ObjectCacheEntry<T>> _memory =
      LinkedHashMap<String, ObjectCacheEntry<T>>();

  CacheReadResult<T>? get(String id) {
    final normalized = id.trim();
    if (normalized.isEmpty) {
      return null;
    }
    final now = DateTime.now();
    final memoryEntry = _memory.remove(normalized);
    if (memoryEntry != null) {
      _memory[normalized] = memoryEntry;
      return _resultFor(memoryEntry, CacheReadSource.memory, now);
    }
    return null;
  }

  void put(
    String id,
    T value, {
    String? objectVersion,
    CacheClass cacheClass = CacheClass.recent,
  }) {
    final normalized = id.trim();
    if (normalized.isEmpty) {
      return;
    }
    final entry = ObjectCacheEntry<T>(
      id: normalized,
      value: value,
      cachedAt: DateTime.now(),
      objectVersion: objectVersion,
      cacheClass: cacheClass,
    );
    _putMemory(normalized, entry);
  }

  int clearWhere(bool Function(ObjectCacheEntry<T> entry) shouldClear) {
    final ids = _memory.entries
        .where((entry) => shouldClear(entry.value))
        .map((entry) => entry.key)
        .toList(growable: false);
    for (final id in ids) {
      _memory.remove(id);
    }
    return ids.length;
  }

  bool remove(String id) {
    final normalized = id.trim();
    if (normalized.isEmpty) {
      return false;
    }
    return _memory.remove(normalized) != null;
  }

  int clearAllRebuildable() {
    return clearWhere((entry) => entry.cacheClass != CacheClass.pinned);
  }

  int get count => _memory.length;

  void _putMemory(String id, ObjectCacheEntry<T> entry) {
    _memory.remove(id);
    _memory[id] = entry;
    while (_memory.length > maxMemoryEntries) {
      _memory.remove(_memory.keys.first);
    }
  }

  CacheReadResult<T> _resultFor(
    ObjectCacheEntry<T> entry,
    CacheReadSource source,
    DateTime now,
  ) {
    final freshness = entry.isFresh(freshFor, now)
        ? CacheFreshness.fresh
        : CacheFreshness.stale;
    return CacheReadResult<T>(
      value: entry.value,
      source: source,
      freshness: freshness,
      syncState: freshness == CacheFreshness.fresh
          ? CacheSyncState.idle
          : CacheSyncState.refreshing,
      objectVersion: entry.objectVersion,
      cacheClass: entry.cacheClass,
      diagnostics: CacheDiagnostics(hitLayer: source.name, requestCount: 0),
    );
  }
}
