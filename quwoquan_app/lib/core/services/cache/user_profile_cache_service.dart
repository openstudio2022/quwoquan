import 'dart:collection';

/// 用户头像/资料本地缓存 — LRU 内存(200) + 磁盘持久化（无 TTL）
///
/// 使用云端 `userProfileUpdatedAt` 时间戳判断是否需要刷新。
class UserProfileCacheService {
  UserProfileCacheService({int maxMemoryEntries = 200})
      : _maxMemory = maxMemoryEntries;

  final int _maxMemory;
  final LinkedHashMap<String, _ProfileEntry> _memory = LinkedHashMap();
  final Map<String, _ProfileEntry> _disk = {};

  Map<String, dynamic>? get(String userId) {
    if (_memory.containsKey(userId)) {
      final entry = _memory.remove(userId)!;
      _memory[userId] = entry;
      return entry.data;
    }
    if (_disk.containsKey(userId)) {
      final entry = _disk[userId]!;
      _putMemory(userId, entry);
      return entry.data;
    }
    return null;
  }

  String? getTimestamp(String userId) {
    return (_memory[userId] ?? _disk[userId])?.updatedAt;
  }

  void put(String userId, Map<String, dynamic> data, {String? updatedAt}) {
    final entry = _ProfileEntry(
      data: data,
      updatedAt: updatedAt ?? data['updatedAt'] as String? ?? '',
    );
    _putMemory(userId, entry);
    _disk[userId] = entry;
  }

  void putAll(List<Map<String, dynamic>> profiles) {
    for (final p in profiles) {
      final id = p['userId'] as String? ?? p['_id'] as String? ?? '';
      if (id.isNotEmpty) put(id, p);
    }
  }

  void _putMemory(String userId, _ProfileEntry entry) {
    _memory.remove(userId);
    _memory[userId] = entry;
    while (_memory.length > _maxMemory) {
      _memory.remove(_memory.keys.first);
    }
  }
}

class _ProfileEntry {
  _ProfileEntry({required this.data, required this.updatedAt});
  final Map<String, dynamic> data;
  final String updatedAt;
}
