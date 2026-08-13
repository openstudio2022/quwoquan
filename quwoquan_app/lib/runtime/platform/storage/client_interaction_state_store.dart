import 'dart:async';
import 'dart:convert';

import 'package:hive_flutter/hive_flutter.dart';
import 'package:quwoquan_app/runtime/observability/app_exception_telemetry_service.dart';
import 'package:quwoquan_app/runtime/platform/storage/hive_runtime.dart';

const String _clientInteractionStateBoxName = 'client_interaction_state';
int _clientInteractionStateEpoch = 0;

Future<Box<String>> _ensureClientInteractionStateBox() async {
  final box = await HiveRuntime.openStringBoxOrNull(
    _clientInteractionStateBoxName,
  );
  if (box == null) {
    throw StateError('client interaction state storage is unavailable');
  }
  return box;
}

Future<Map<String, dynamic>?> readPersistedInteractionMap(String key) async {
  final epoch = _clientInteractionStateEpoch;
  try {
    final box = await _ensureClientInteractionStateBox();
    if (epoch != _clientInteractionStateEpoch) {
      return null;
    }
    final raw = box.get(key);
    if (raw == null || raw.isEmpty) {
      return null;
    }
    final decoded = jsonDecode(raw);
    if (decoded is Map<String, dynamic>) {
      return decoded;
    }
    if (decoded is Map) {
      return decoded.cast<String, dynamic>();
    }
  } catch (error, stackTrace) {
    // 回退到 null（调用方按未持久化态初始化），但投影损坏意味着用户点赞/
    // 关注离线态丢失，事实必须结构化上报（自带指纹去重）。
    unawaited(
      AppExceptionTelemetryService.instance.recordHandledException(
        source: 'platform.interaction_state_store.read',
        error: error,
        stackTrace: stackTrace,
      ),
    );
  }
  return null;
}

Future<void> writePersistedInteractionMap(
  String key,
  Map<String, dynamic> value,
) async {
  final epoch = _clientInteractionStateEpoch;
  try {
    final box = await _ensureClientInteractionStateBox();
    if (epoch != _clientInteractionStateEpoch) {
      return;
    }
    await box.put(key, jsonEncode(value));
  } catch (error, stackTrace) {
    // 云端同步仍为真相源，但持久化持续失败会让冷启动丢互动态；上报观测。
    unawaited(
      AppExceptionTelemetryService.instance.recordHandledException(
        source: 'platform.interaction_state_store.write',
        error: error,
        stackTrace: stackTrace,
      ),
    );
  }
}

/// 云侧账号 closed 后清除关系、内容交互投影及其待同步 outbox。
Future<void> clearClientInteractionStateForTerminalAccountClosure() async {
  _clientInteractionStateEpoch += 1;
  final box = await _ensureClientInteractionStateBox();
  await box.clear();
  if (box.isNotEmpty) {
    throw StateError('client interaction state cleanup verification failed');
  }
}
