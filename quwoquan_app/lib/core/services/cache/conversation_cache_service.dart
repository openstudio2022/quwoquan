import 'dart:collection';

/// 会话本地缓存 — LRU 内存 + Hive 持久化（无 TTL）
///
/// 内存层使用 LinkedHashMap 实现 LRU，磁盘层暂用内存 Map 模拟
/// （后续替换为 Hive box，无需改动外部接口）。
class ConversationCacheService {
  ConversationCacheService({int maxMemoryEntries = 200})
      : _maxMemory = maxMemoryEntries;

  final int _maxMemory;

  /// LRU 内存缓存：key = conversationId
  final LinkedHashMap<String, _CacheEntry> _memory = LinkedHashMap();

  /// 模拟持久化层（替换为 Hive 后签名不变）
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

  String? getTimestamp(String id) {
    final entry = _memory[id] ?? _disk[id];
    return entry?.updatedAt;
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
      data: data,
      updatedAt: updatedAt ?? data['updatedAt'] as String? ?? '',
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
  _CacheEntry({required this.data, required this.updatedAt});
  final Map<String, dynamic> data;
  final String updatedAt;
}
