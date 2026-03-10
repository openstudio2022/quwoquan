import 'dart:collection';

/// 会话本地缓存 — LRU 内存 + Hive 持久化（无 TTL）
///
/// 内存层使用 LinkedHashMap 实现 LRU，磁盘层暂用内存 Map 模拟
/// （后续替换为 Hive box，无需改动外部接口）。
///
/// 支持分拆时间戳：settingsUpdatedAt（低频）和 lastMessageAt（高频）
class ConversationCacheService {
  ConversationCacheService({int maxMemoryEntries = 200})
      : _maxMemory = maxMemoryEntries;

  final int _maxMemory;

  final LinkedHashMap<String, _CacheEntry> _memory = LinkedHashMap();
  final Map<String, _CacheEntry> _disk = {};

  Map<String, dynamic>? get(String id) {
    if (_memory.containsKey(id)) {
      final entry = _memory.remove(id)!;
      _memory[id] = entry;
      return entry.data;
    }
    if (_disk.containsKey(id)) {
      final entry = _disk[id]!;
      _putMemory(id, entry);
      return entry.data;
    }
    return null;
  }

  /// 向后兼容：返回 settingsUpdatedAt 或旧 updatedAt
  String? getTimestamp(String id) {
    final entry = _memory[id] ?? _disk[id];
    return entry?.settingsUpdatedAt.isNotEmpty == true
        ? entry!.settingsUpdatedAt
        : entry?.updatedAt;
  }

  String? getSettingsTimestamp(String id) {
    final entry = _memory[id] ?? _disk[id];
    return entry?.settingsUpdatedAt.isNotEmpty == true
        ? entry!.settingsUpdatedAt
        : entry?.updatedAt;
  }

  String? getMessageTimestamp(String id) {
    return (_memory[id] ?? _disk[id])?.lastMessageAt;
  }

  List<Map<String, dynamic>> getAll() {
    final seen = <String>{};
    final result = <Map<String, dynamic>>[];
    for (final e in _memory.entries) {
      seen.add(e.key);
      result.add(e.value.data);
    }
    for (final e in _disk.entries) {
      if (!seen.contains(e.key)) result.add(e.value.data);
    }
    return result;
  }

  void put(String id, Map<String, dynamic> data, {String? updatedAt}) {
    final entry = _CacheEntry(
      data: Map<String, dynamic>.from(data),
      updatedAt: updatedAt ?? data['updatedAt'] as String? ?? '',
      settingsUpdatedAt: data['settingsUpdatedAt'] as String? ?? '',
      lastMessageAt: data['lastMessageAt'] as String?
          ?? data['lastMessageTime'] as String?
          ?? '',
    );
    _putMemory(id, entry);
    _disk[id] = entry;
  }

  void putAll(List<Map<String, dynamic>> items) {
    for (final item in items) {
      final id = item['_id'] as String? ?? item['id'] as String? ?? '';
      if (id.isNotEmpty) put(id, item);
    }
  }

  /// 仅更新列表展示字段（lastMessagePreview / lastMessageAt / unreadCount）
  /// 不拉取完整会话数据，避免活跃群高频消息触发全量拉取
  void updateListFields(
    String id, {
    String? lastMessagePreview,
    String? lastMessageAt,
    int? unreadCount,
  }) {
    final entry = _memory[id] ?? _disk[id];
    if (entry == null) return;

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

    final newEntry = _CacheEntry(
      data: updated,
      updatedAt: entry.updatedAt,
      settingsUpdatedAt: entry.settingsUpdatedAt,
      lastMessageAt: lastMessageAt ?? entry.lastMessageAt,
    );
    _putMemory(id, newEntry);
    _disk[id] = newEntry;
  }

  void remove(String id) {
    _memory.remove(id);
    _disk.remove(id);
  }

  void _putMemory(String id, _CacheEntry entry) {
    _memory.remove(id);
    _memory[id] = entry;
    while (_memory.length > _maxMemory) {
      _memory.remove(_memory.keys.first);
    }
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
