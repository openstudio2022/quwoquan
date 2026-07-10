import 'dart:collection';
import 'dart:async';
import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

/// 用户头像/资料本地缓存 — LRU 内存(200) + 磁盘持久化（无 TTL）
///
/// 使用云端 `userProfileUpdatedAt` 时间戳判断是否需要刷新。
class UserProfileCacheService {
  UserProfileCacheService({
    int maxMemoryEntries = 200,
    this._persistToPreferences = false,
  }) : _maxMemory = maxMemoryEntries {
    if (_persistToPreferences) {
      unawaited(_hydrateFromPreferences());
    }
  }

  static const String _prefsKey = 'qwq.user_profile_cache.v1';

  final int _maxMemory;
  final bool _persistToPreferences;
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
    _schedulePersist();
  }

  void putAuthorSnapshot({
    required String userId,
    String? displayName,
    String? avatarUrl,
    String? backgroundUrl,
    String? updatedAt,
  }) {
    final id = userId.trim();
    if (id.isEmpty) {
      return;
    }
    final existing = get(id) ?? const <String, dynamic>{};
    put(id, <String, dynamic>{
      ...existing,
      'userId': id,
      if ((displayName ?? '').trim().isNotEmpty)
        'displayName': displayName!.trim(),
      if ((avatarUrl ?? '').trim().isNotEmpty) 'avatarUrl': avatarUrl!.trim(),
      if ((backgroundUrl ?? '').trim().isNotEmpty)
        'backgroundUrl': backgroundUrl!.trim(),
      'updatedAt': (updatedAt ?? '').trim().isNotEmpty
          ? updatedAt!.trim()
          : existing['updatedAt'] as String? ?? '',
    });
  }

  void putAll(List<Map<String, dynamic>> profiles) {
    for (final p in profiles) {
      final id = p['userId'] as String? ?? p['_id'] as String? ?? '';
      if (id.isNotEmpty) put(id, p);
    }
  }

  int clearRebuildable({Set<String> protectedUserIds = const <String>{}}) {
    final ids = _disk.keys
        .where((id) => !protectedUserIds.contains(id))
        .toList(growable: false);
    for (final id in ids) {
      _disk.remove(id);
      _memory.remove(id);
    }
    _schedulePersist();
    return ids.length;
  }

  int get diskCount => _disk.length;

  int get memoryCount => _memory.length;

  void _putMemory(String userId, _ProfileEntry entry) {
    _memory.remove(userId);
    _memory[userId] = entry;
    while (_memory.length > _maxMemory) {
      _memory.remove(_memory.keys.first);
    }
  }

  Future<void> _hydrateFromPreferences() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final raw = prefs.getString(_prefsKey);
      if (raw == null || raw.isEmpty) {
        return;
      }
      final decoded = jsonDecode(raw);
      if (decoded is! Map<String, dynamic>) {
        return;
      }
      for (final entry in decoded.entries) {
        final value = entry.value;
        if (value is! Map<String, dynamic>) {
          continue;
        }
        final data = value['data'];
        if (data is! Map<String, dynamic>) {
          continue;
        }
        final profileEntry = _ProfileEntry(
          data: Map<String, dynamic>.from(data),
          updatedAt: value['updatedAt']?.toString() ?? '',
        );
        _disk[entry.key] = profileEntry;
        _putMemory(entry.key, profileEntry);
      }
    } catch (_) {
      return;
    }
  }

  void _schedulePersist() {
    if (!_persistToPreferences) {
      return;
    }
    unawaited(_persistToPreferencesStore());
  }

  Future<void> _persistToPreferencesStore() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final payload = _disk.map(
        (id, entry) => MapEntry(id, <String, dynamic>{
          'data': entry.data,
          'updatedAt': entry.updatedAt,
        }),
      );
      await prefs.setString(_prefsKey, jsonEncode(payload));
    } catch (_) {
      return;
    }
  }
}

class _ProfileEntry {
  _ProfileEntry({required this.data, required this.updatedAt});
  final Map<String, dynamic> data;
  final String updatedAt;
}
