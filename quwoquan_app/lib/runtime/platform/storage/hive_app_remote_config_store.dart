import 'dart:async';
import 'dart:convert';

import 'package:quwoquan_app/runtime/config/cloud_runtime_config.dart';

import 'package:hive_flutter/hive_flutter.dart';
import 'package:quwoquan_app/runtime/observability/app_exception_telemetry_service.dart';
import 'package:quwoquan_app/runtime/config/app_remote_config_snapshot.dart';
import 'package:quwoquan_app/runtime/config/app_remote_config_store.dart';
import 'package:quwoquan_app/runtime/platform/storage/hive_runtime.dart';

/// Hive-backed App remote-config LKG adapter.
final class HiveAppRemoteConfigStore implements AppRemoteConfigStore {
  const HiveAppRemoteConfigStore({this.storageNamespace, this.now});

  final DateTime Function()? now;

  /// production 环境在冷启动后不可变；测试显式注入稳定 namespace。
  final String? storageNamespace;

  String get scopedBoxName {
    final namespace =
        storageNamespace ??
        '${CloudRuntimeConfig.launchTarget}|${CloudRuntimeConfig.appEnvironment}';
    if (namespace.trim().isEmpty) {
      throw ArgumentError.value(namespace, 'storageNamespace');
    }
    return '${boxName}_${Uri.encodeComponent(namespace)}';
  }

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
      final snapshot = AppRemoteConfigSnapshot.fromPersistedMap(
        persisted,
        source: AppRemoteConfigSource.diskCache,
      );
      // 运营 LKG 的 maxAgeSec 独立于内容缓存 TTL，过期不能放行展示。
      final readAt = (now ?? DateTime.now)().toUtc();
      if (snapshot.maxAge <= Duration.zero ||
          readAt.isBefore(snapshot.fetchedAt.toUtc()) ||
          !readAt.isBefore(snapshot.expiresAt)) {
        return null;
      }
      return snapshot;
    } catch (error, stackTrace) {
      // 缓存损坏时按「无本地配置」继续拉远端，但损坏本身必须留证据。
      unawaited(
        AppExceptionTelemetryService.instance.recordHandledException(
          source: 'runtime.remote_config.read_active_snapshot',
          error: error,
          stackTrace: stackTrace,
        ),
      );
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
    return HiveRuntime.openStringBoxOrNull(scopedBoxName);
  }
}
