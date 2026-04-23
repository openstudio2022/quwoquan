import 'dart:collection';

import 'package:flutter/foundation.dart';

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

  Map<String, dynamic>? get(String id) {
    final bucket = _activeBucket;
    if (bucket.memory.containsKey(id)) {
      final entry = bucket.memory.remove(id)!;
      bucket.memory[id] = entry;
      return entry.data;
    }
    if (bucket.disk.containsKey(id)) {
      final entry = bucket.disk[id]!;
      _putMemory(bucket, id, entry);
      return entry.data;
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

  List<Map<String, dynamic>> getAll() {
    final bucket = _activeBucket;
    final seen = <String>{};
    final result = <Map<String, dynamic>>[];
    for (final entry in bucket.memory.entries) {
      seen.add(entry.key);
      result.add(entry.value.data);
    }
    for (final entry in bucket.disk.entries) {
      if (!seen.contains(entry.key)) {
        result.add(entry.value.data);
      }
    }
    return result;
  }

  void put(String id, Map<String, dynamic> data, {String? updatedAt}) {
    if (id.trim().isEmpty) {
      return;
    }
    final bucket = _activeBucket;
    final entry = _entryFromMap(data, updatedAt: updatedAt);
    _putMemory(bucket, id, entry);
    bucket.disk[id] = entry;
    notifyListeners();
  }

  void putAll(List<Map<String, dynamic>> items) {
    final bucket = _activeBucket;
    var changed = false;
    for (final item in items) {
      final id = item['_id'] as String? ?? item['id'] as String? ?? '';
      if (id.isEmpty) {
        continue;
      }
      final entry = _entryFromMap(item);
      _putMemory(bucket, id, entry);
      bucket.disk[id] = entry;
      changed = true;
    }
    if (changed) {
      notifyListeners();
    }
  }

  void updateListFields(
    String id, {
    String? lastMessagePreview,
    String? lastMessageAt,
    int? unreadCount,
    int? mentionUnreadCount,
  }) {
    final bucket = _activeBucket;
    final entry = bucket.memory[id] ?? bucket.disk[id];
    if (entry == null) {
      return;
    }
    final updated = Map<String, dynamic>.from(entry.data);
    if (lastMessagePreview != null) {
      updated['lastMessagePreview'] = lastMessagePreview;
    }
    if (lastMessageAt != null) {
      updated['lastMessageAt'] = lastMessageAt;
      updated['lastMessageTime'] = lastMessageAt;
    }
    if (unreadCount != null) {
      updated['unreadCount'] = unreadCount;
    }
    if (mentionUnreadCount != null) {
      updated['mentionUnreadCount'] = mentionUnreadCount;
    }
    final newEntry = _CacheEntry(
      data: updated,
      updatedAt: entry.updatedAt,
      settingsUpdatedAt: entry.settingsUpdatedAt,
      lastMessageAt: lastMessageAt ?? entry.lastMessageAt,
    );
    _putMemory(bucket, id, newEntry);
    bucket.disk[id] = newEntry;
    notifyListeners();
  }

  void updateConversationAvatar(
    String id, {
    required String avatarUrl,
    int? groupAvatarVersion,
    String? groupAvatarSourceHash,
  }) {
    final bucket = _activeBucket;
    final entry = bucket.memory[id] ?? bucket.disk[id];
    if (entry == null) {
      return;
    }
    final updated = Map<String, dynamic>.from(entry.data);
    updated['avatarUrl'] = avatarUrl;
    updated['groupAvatarUrl'] = avatarUrl;
    if (groupAvatarVersion != null) {
      updated['groupAvatarVersion'] = groupAvatarVersion;
    }
    if (groupAvatarSourceHash != null) {
      updated['groupAvatarSourceHash'] = groupAvatarSourceHash;
    }
    final newEntry = _CacheEntry(
      data: updated,
      updatedAt: entry.updatedAt,
      settingsUpdatedAt: entry.settingsUpdatedAt,
      lastMessageAt: entry.lastMessageAt,
    );
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

  _CacheEntry _entryFromMap(Map<String, dynamic> data, {String? updatedAt}) {
    return _CacheEntry(
      data: Map<String, dynamic>.from(data),
      updatedAt: updatedAt ?? _asIsoString(data['updatedAt']) ?? '',
      settingsUpdatedAt: _asIsoString(data['settingsUpdatedAt']) ?? '',
      lastMessageAt:
          _asIsoString(data['lastMessageAt']) ??
          _asIsoString(data['lastMessageTime']) ??
          '',
    );
  }

  String? _asIsoString(dynamic value) {
    if (value is String) {
      return value;
    }
    if (value is DateTime) {
      return value.toIso8601String();
    }
    return null;
  }
}

class _CacheEntry {
  _CacheEntry({
    required this.data,
    required this.updatedAt,
    this.settingsUpdatedAt = '',
    this.lastMessageAt = '',
  });

  final Map<String, dynamic> data;
  final String updatedAt;
  final String settingsUpdatedAt;
  final String lastMessageAt;
}

class _NamespaceBucket {
  final LinkedHashMap<String, _CacheEntry> memory = LinkedHashMap();
  final Map<String, _CacheEntry> disk = <String, _CacheEntry>{};
}
