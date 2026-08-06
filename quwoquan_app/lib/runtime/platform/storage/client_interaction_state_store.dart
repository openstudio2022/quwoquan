import 'dart:convert';

import 'package:hive_flutter/hive_flutter.dart';
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
  } catch (_) {
    /* best-effort: 本地交互状态损坏时回退到 null，由调用方按未持久化态初始化 */
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
  } catch (_) {
    /* best-effort: 本地交互状态持久化失败仅丢失离线缓存，云端同步仍为真相源 */
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
