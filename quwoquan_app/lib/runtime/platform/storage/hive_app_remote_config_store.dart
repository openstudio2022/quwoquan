import 'dart:convert';

import 'package:hive_flutter/hive_flutter.dart';
import 'package:quwoquan_app/runtime/config/app_remote_config_snapshot.dart';
import 'package:quwoquan_app/runtime/config/app_remote_config_store.dart';
import 'package:quwoquan_app/runtime/platform/storage/hive_runtime.dart';

/// Hive-backed App remote-config LKG adapter.
final class HiveAppRemoteConfigStore implements AppRemoteConfigStore {
  const HiveAppRemoteConfigStore();

  static const String boxName = 'app_remote_config';
  static const String activeSnapshotKey = 'active_snapshot';
  static const String previousSnapshotKey = 'previous_snapshot';

  @override
  Future<AppRemoteConfigSnapshot?> readActiveSnapshot() async {
    try {
      final box = await _boxOrNull();
      if (box == null) return null;
      final raw = box.get(activeSnapshotKey);
      if (raw == null || raw.isEmpty) return null;
      final decoded = jsonDecode(raw);
      if (decoded is! Map) return null;
      final persisted = decoded.cast<String, dynamic>();
      final source =
          AppRemoteConfigSnapshot.fromPersistedMap(persisted).isExpired
          ? AppRemoteConfigSource.staleDiskCache
          : AppRemoteConfigSource.diskCache;
      return AppRemoteConfigSnapshot.fromPersistedMap(
        persisted,
        source: source,
      );
    } catch (_) {
      return null;
    }
  }

  @override
  Future<void> writeActiveSnapshot(AppRemoteConfigSnapshot snapshot) async {
    try {
      final box = await _boxOrNull();
      if (box == null) return;
      final current = box.get(activeSnapshotKey);
      if (current != null && current.isNotEmpty) {
        await box.put(previousSnapshotKey, current);
      }
      await box.put(activeSnapshotKey, jsonEncode(snapshot.toPersistedMap()));
    } catch (_) {
      // 远程配置缓存是启动优化，写入失败不应影响当前会话可用性。
    }
  }

  Future<Box<String>?> _boxOrNull() {
    return HiveRuntime.openStringBoxOrNull(boxName);
  }
}
