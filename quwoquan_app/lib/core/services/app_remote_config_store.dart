import 'dart:convert';

import 'package:hive_flutter/hive_flutter.dart';
import 'package:quwoquan_app/cloud/runtime/models/app_remote_config_snapshot.dart';
import 'package:quwoquan_app/core/services/hive_runtime.dart';

class AppRemoteConfigStore {
  const AppRemoteConfigStore();

  static const String boxName = 'app_remote_config';
  static const String activeSnapshotKey = 'active_snapshot_v1';
  static const String previousSnapshotKey = 'previous_snapshot_v1';

  Future<AppRemoteConfigSnapshot?> readActiveSnapshot() async {
    try {
      final box = await _boxOrNull();
      if (box == null) return null;
      final raw = box.get(activeSnapshotKey);
      if (raw == null || raw.isEmpty) return null;
      final decoded = jsonDecode(raw);
      if (decoded is! Map) return null;
      final source =
          AppRemoteConfigSnapshot.fromPersistedMap(
            decoded.cast<String, dynamic>(),
          ).isExpired
          ? AppRemoteConfigSource.staleDiskCache
          : AppRemoteConfigSource.diskCache;
      return AppRemoteConfigSnapshot.fromPersistedMap(
        decoded.cast<String, dynamic>(),
        source: source,
      );
    } catch (_) {
      return null;
    }
  }

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

  Future<Box<String>?> _boxOrNull() async {
    return HiveRuntime.openStringBoxOrNull(boxName);
  }
}
