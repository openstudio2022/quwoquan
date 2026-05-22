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

/// 对象级 LRU 缓存。首版使用内存 + 进程内磁盘桶，后续可替换为 Hive/SQLite adapter。
class ObjectCacheStore<T> {
  ObjectCacheStore({
    this.maxMemoryEntries = 200,
    this.freshFor = const Duration(minutes: 15),
  });

  final int maxMemoryEntries;
  final Duration freshFor;
  final LinkedHashMap<String, ObjectCacheEntry<T>> _memory =
      LinkedHashMap<String, ObjectCacheEntry<T>>();
  final Map<String, ObjectCacheEntry<T>> _disk =
      <String, ObjectCacheEntry<T>>{};

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
    final diskEntry = _disk[normalized];
    if (diskEntry == null) {
      return null;
    }
    _putMemory(normalized, diskEntry);
    return _resultFor(diskEntry, CacheReadSource.disk, now);
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
    _disk[normalized] = entry;
  }

  int clearWhere(bool Function(ObjectCacheEntry<T> entry) shouldClear) {
    final ids = _disk.entries
        .where((entry) => shouldClear(entry.value))
        .map((entry) => entry.key)
        .toList(growable: false);
    for (final id in ids) {
      _disk.remove(id);
      _memory.remove(id);
    }
    return ids.length;
  }

  int clearAllRebuildable() {
    return clearWhere((entry) => entry.cacheClass != CacheClass.pinned);
  }

  int get diskCount => _disk.length;

  int get memoryCount => _memory.length;

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
