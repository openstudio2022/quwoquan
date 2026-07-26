import 'package:flutter/services.dart';

class AppRecoveryNativeContext {
  const AppRecoveryNativeContext({
    required this.platform,
    required this.appVersion,
    required this.buildNumber,
  });

  final String platform;
  final String appVersion;
  final int buildNumber;
}

/// 启动恢复的最小原生能力；不依赖登录、业务 Router 或普通插件注册。
final class AppRecoveryNativeBridge {
  AppRecoveryNativeBridge({MethodChannel? channel})
    : _channel = channel ?? const MethodChannel('quwoquan/app_recovery');

  final MethodChannel _channel;

  Future<AppRecoveryNativeContext?> context() async {
    try {
      final raw = await _channel.invokeMapMethod<String, Object?>(
        'getRecoveryContext',
      );
      final platform = raw?['platform']?.toString().trim() ?? '';
      final appVersion = raw?['appVersion']?.toString().trim() ?? '';
      final buildNumber = int.tryParse(raw?['buildNumber']?.toString() ?? '');
      if ((platform != 'ios' && platform != 'android') ||
          appVersion.isEmpty ||
          buildNumber == null ||
          buildNumber <= 0) {
        return null;
      }
      return AppRecoveryNativeContext(
        platform: platform,
        appVersion: appVersion,
        buildNumber: buildNumber,
      );
    } on PlatformException {
      return null;
    } on MissingPluginException {
      return null;
    }
  }

  Future<bool> openTrustedExternalUrl(String rawUrl) async {
    final uri = Uri.tryParse(rawUrl.trim());
    if (uri == null ||
        uri.scheme.toLowerCase() != 'https' ||
        uri.host.isEmpty ||
        uri.userInfo.isNotEmpty) {
      return false;
    }
    try {
      return await _channel.invokeMethod<bool>(
            'openTrustedExternalUrl',
            <String, String>{'url': uri.toString()},
          ) ??
          false;
    } on PlatformException {
      return false;
    } on MissingPluginException {
      return false;
    }
  }

  Future<void> recordFatalStartup() async {
    try {
      await _channel.invokeMethod<void>('recordFatalStartup');
    } on PlatformException {
      // 状态持久化失败不得阻断恢复页。
    } on MissingPluginException {
      // 原生桥不可用时仍展示 Flutter 恢复页。
    }
  }
}
