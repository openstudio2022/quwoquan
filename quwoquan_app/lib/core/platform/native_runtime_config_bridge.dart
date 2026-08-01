import 'dart:async';

import 'package:flutter/services.dart';

/// 读取平台构建阶段已经验证并写入 App 制品的 runtime package。
final class NativeRuntimeConfigBridge {
  const NativeRuntimeConfigBridge._();

  static const MethodChannel _channel = MethodChannel(
    'quwoquan/runtime/config',
  );

  static Future<Map<String, String>> readRuntimePackage() async {
    try {
      final values = await _channel
          .invokeMapMethod<String, dynamic>('readRuntimeConfig')
          .timeout(const Duration(seconds: 2));
      if (values == null) {
        return const <String, String>{};
      }
      return <String, String>{
        for (final entry in values.entries)
          if (entry.value is String && (entry.value as String).isNotEmpty)
            entry.key: entry.value as String,
      };
    } on MissingPluginException {
      return const <String, String>{};
    } on PlatformException {
      return const <String, String>{};
    } on TimeoutException {
      return const <String, String>{};
    }
  }
}
