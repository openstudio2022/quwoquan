import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:hive_flutter/hive_flutter.dart';
import 'package:quwoquan_app/core/platform/platform_target.dart';

/// 统一收口 Hive 初始化与 String Box 打开逻辑。
///
/// 启动期若 path_provider / Hive 尚不可用，调用方应拿到 `null` 并降级，
/// 不能继续 `openBox()` 把初始化问题放大成未捕获异常。
class HiveRuntime {
  HiveRuntime._();

  static Future<bool>? _initializationFuture;

  @visibleForTesting
  static Future<bool> Function()? debugEnsureInitializedHook;

  @visibleForTesting
  static void resetForTest() {
    _initializationFuture = null;
    debugEnsureInitializedHook = null;
  }

  static Future<bool> ensureInitialized() {
    final hook = debugEnsureInitializedHook;
    if (hook != null) {
      return hook();
    }
    if (currentAppPlatform == AppPlatform.web || _hasHomePath) {
      return Future<bool>.value(true);
    }
    final inFlight = _initializationFuture;
    if (inFlight != null) {
      return inFlight;
    }
    final future = _initialize();
    _initializationFuture = future;
    return future;
  }

  static Future<Box<String>?> openStringBoxOrNull(String boxName) async {
    if (Hive.isBoxOpen(boxName)) {
      return Hive.box<String>(boxName);
    }
    final ready = await ensureInitialized();
    if (!ready) {
      return null;
    }
    try {
      return await Hive.openBox<String>(boxName);
    } catch (_) {
      return null;
    }
  }

  static Future<Box<String>?> openEncryptedStringBoxOrNull(
    String boxName, {
    required List<int> encryptionKey,
  }) async {
    if (encryptionKey.length != 32) {
      throw ArgumentError.value(
        encryptionKey.length,
        'encryptionKey',
        'Hive AES key must contain 32 bytes',
      );
    }
    if (Hive.isBoxOpen(boxName)) {
      return Hive.box<String>(boxName);
    }
    final ready = await ensureInitialized();
    if (!ready) return null;
    try {
      return await Hive.openBox<String>(
        boxName,
        encryptionCipher: HiveAesCipher(encryptionKey),
      );
    } catch (_) {
      return null;
    }
  }

  static Future<bool> _initialize() async {
    try {
      await Hive.initFlutter();
      return currentAppPlatform == AppPlatform.web || _hasHomePath;
    } catch (_) {
      _initializationFuture = null;
      return currentAppPlatform == AppPlatform.web || _hasHomePath;
    }
  }

  static bool get _hasHomePath {
    try {
      final dynamic hive = Hive;
      final Object? homePath = hive.homePath;
      return homePath is String && homePath.isNotEmpty;
    } catch (_) {
      return false;
    }
  }
}
