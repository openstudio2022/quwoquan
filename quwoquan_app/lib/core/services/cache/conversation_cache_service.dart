import 'dart:collection';

import 'package:flutter/foundation.dart';
import 'package:quwoquan_app/core/services/cache/conversation_cache_record.dart';

/// 会话本地缓存，按 namespace 隔离，避免 persona 切换时相互污染。
class ConversationCacheService extends ChangeNotifier {
  ConversationCacheService({int maxMemoryEntries = 200})
    : _maxMemory = maxMemoryEntries;

  static const _defaultNamespaceKey = '__default__';

  final int _maxMemory;
  final Map<String, _NamespaceBucket> _buckets = <String, _NamespaceBucket>{};
  String _activeNamespaceKey = _defaultNamespaceKey;

  void activateNamespace(String namespaceKey) {
    final normalized = namespaceKey.trim().isEmpty
        ? _defaultNamespaceKey
        : namespaceKey.trim();
    if (_activeNamespaceKey == normalized) {
      return;
    }
    if (_activeNamespaceKey == _defaultNamespaceKey &&
        normalized != _defaultNamespaceKey) {
      final defaultBucket = _bucketFor(_defaultNamespaceKey);
      final targetBucket = _buckets[normalized];
      final targetIsEmpty =
          targetBucket == null ||
          (targetBucket.memory.isEmpty && targetBucket.disk.isEmpty);
      final defaultHasData =
          defaultBucket.memory.isNotEmpty || defaultBucket.disk.isNotEmpty;
      if (targetIsEmpty && defaultHasData) {
        _buckets[normalized] = defaultBucket;
        _buckets[_defaultNamespaceKey] = _NamespaceBucket();
      }
    }
    _activeNamespaceKey = normalized;
    _bucketFor(normalized);
    notifyListeners();
  }

  ConversationCacheRecord? get(String id) {
    final bucket = _activeBucket;
    if (bucket.memory.containsKey(id)) {
      final entry = bucket.memory.remove(id)!;
      bucket.memory[id] = entry;
      return entry.record;
    }
    if (bucket.disk.containsKey(id)) {
      final entry = bucket.disk[id]!;
      _putMemory(bucket, id, entry);
      return entry.record;
    }
    return null;
  }

  String? getTimestamp(String id) {
    final entry = _activeBucket.memory[id] ?? _activeBucket.disk[id];
    return entry?.settingsUpdatedAt.isNotEmpty == true
        ? entry!.settingsUpdatedAt
        : entry?.updatedAt;
  }

  String? getSettingsTimestamp(String id) {
    final entry = _activeBucket.memory[id] ?? _activeBucket.disk[id];
    return entry?.settingsUpdatedAt.isNotEmpty == true
        ? entry!.settingsUpdatedAt
        : entry?.updatedAt;
  }

  String? getMessageTimestamp(String id) {
    return (_activeBucket.memory[id] ?? _activeBucket.disk[id])?.lastMessageAt;
  }

  List<ConversationCacheRecord> getAll() {
    final bucket = _activeBucket;
    final seen = <String>{};
    final result = <ConversationCacheRecord>[];
    for (final entry in bucket.memory.entries) {
      seen.add(entry.key);
      result.add(entry.value.record);
    }
    for (final entry in bucket.disk.entries) {
      if (!seen.contains(entry.key)) {
        result.add(entry.value.record);
      }
    }
    return result;
  }

  void put(ConversationCacheRecord record) {
    if (record.id.trim().isEmpty) {
      return;
    }
    final bucket = _activeBucket;
    final entry = _entryFromRecord(record);
    _putMemory(bucket, record.id, entry);
    bucket.disk[record.id] = entry;
    notifyListeners();
  }

  void putAll(Iterable<ConversationCacheRecord> records) {
    final bucket = _activeBucket;
    var changed = false;
    for (final record in records) {
      if (record.id.isEmpty) {
        continue;
      }
      final entry = _entryFromRecord(record);
      _putMemory(bucket, record.id, entry);
      bucket.disk[record.id] = entry;
      changed = true;
    }
    if (changed) {
      notifyListeners();
    }
  }

  void replaceAll(Iterable<ConversationCacheRecord> records) {
    final bucket = _activeBucket;
    bucket.memory.clear();
    bucket.disk.clear();
    for (final record in records) {
      if (record.id.isEmpty) {
        continue;
      }
      final entry = _entryFromRecord(record);
      _putMemory(bucket, record.id, entry);
      bucket.disk[record.id] = entry;
    }
    notifyListeners();
  }

  void applyListPatch(String id, ConversationListPatch patch) {
    final bucket = _activeBucket;
    final entry = bucket.memory[id] ?? bucket.disk[id];
    if (entry == null) {
      return;
    }
    final nextRecord = entry.record.copyWith(
      lastMessagePreview: patch.lastMessagePreview,
      lastMessageAt: patch.lastMessageAt,
      unreadCount: patch.unreadCount,
      mentionUnreadCount: patch.mentionUnreadCount,
    );
    final newEntry = _entryFromRecord(nextRecord);
    _putMemory(bucket, id, newEntry);
    bucket.disk[id] = newEntry;
    notifyListeners();
  }

  void applyAvatarPatch(String id, ConversationAvatarPatch patch) {
    final bucket = _activeBucket;
    final entry = bucket.memory[id] ?? bucket.disk[id];
    if (entry == null) {
      return;
    }
    final nextRecord = entry.record.copyWith(
      avatarUrl: patch.avatarUrl,
      groupAvatarVersion: patch.groupAvatarVersion,
      groupAvatarSourceHash: patch.groupAvatarSourceHash,
    );
    final newEntry = _entryFromRecord(nextRecord);
    _putMemory(bucket, id, newEntry);
    bucket.disk[id] = newEntry;
    notifyListeners();
  }

  void remove(String id) {
    final bucket = _activeBucket;
    final removedFromMemory = bucket.memory.remove(id);
    final removedFromDisk = bucket.disk.remove(id);
    if (removedFromMemory != null || removedFromDisk != null) {
      notifyListeners();
    }
  }

  void clear() {
    final bucket = _activeBucket;
    if (bucket.memory.isEmpty && bucket.disk.isEmpty) {
      return;
    }
    bucket.memory.clear();
    bucket.disk.clear();
    notifyListeners();
  }

  _NamespaceBucket get _activeBucket => _bucketFor(_activeNamespaceKey);

  _NamespaceBucket _bucketFor(String namespaceKey) {
    return _buckets.putIfAbsent(namespaceKey, _NamespaceBucket.new);
  }

  void _putMemory(_NamespaceBucket bucket, String id, _CacheEntry entry) {
    bucket.memory.remove(id);
    bucket.memory[id] = entry;
    while (bucket.memory.length > _maxMemory) {
      bucket.memory.remove(bucket.memory.keys.first);
    }
  }

  _CacheEntry _entryFromRecord(ConversationCacheRecord record) {
    return _CacheEntry(
      record: record,
      updatedAt: record.updatedAt,
      settingsUpdatedAt: record.settingsTimestamp,
      lastMessageAt: record.messageTimestamp,
    );
  }
}

class _CacheEntry {
  _CacheEntry({
    required this.record,
    required this.updatedAt,
    this.settingsUpdatedAt = '',
    this.lastMessageAt = '',
  });

  final ConversationCacheRecord record;
  final String updatedAt;
  final String settingsUpdatedAt;
  final String lastMessageAt;
}

class _NamespaceBucket {
  final LinkedHashMap<String, _CacheEntry> memory = LinkedHashMap();
  final Map<String, _CacheEntry> disk = <String, _CacheEntry>{};
}
