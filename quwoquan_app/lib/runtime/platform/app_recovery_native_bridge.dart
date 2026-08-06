import 'package:flutter/services.dart';
import 'package:quwoquan_app/runtime/shell/recovery/recovery_runtime_binding.dart';
import 'package:quwoquan_app/runtime/transport/links/trusted_endpoint_policy.dart';

class AppRecoveryNativeContext {
  const AppRecoveryNativeContext({
    required this.platform,
    required this.appVersion,
    required this.buildNumber,
    required this.osVersion,
    required this.deviceModel,
    required this.runtimeBinding,
    required this.publicWebUrl,
    required this.appDownloadBaseUrl,
  });

  final String platform;
  final String appVersion;
  final int buildNumber;
  final String osVersion;
  final String deviceModel;
  final RecoveryRuntimeBinding runtimeBinding;
  final String publicWebUrl;
  final String appDownloadBaseUrl;

  String get recoveryBaseUrl => runtimeBinding.recoveryOrigin.toString();
}

/// 启动恢复的最小原生能力；不依赖登录、业务 Router 或普通插件注册。
final class AppRecoveryNativeBridge {
  AppRecoveryNativeBridge({MethodChannel? channel})
    : _channel = channel ?? const MethodChannel('quwoquan/app_recovery');

  final MethodChannel _channel;
  final List<String> _trustedBaseUrls = <String>[];

  Future<AppRecoveryNativeContext?> context() async {
    try {
      final raw = await _channel.invokeMapMethod<String, Object?>(
        'getRecoveryContext',
      );
      final platform = raw?['platform']?.toString().trim() ?? '';
      final appVersion = raw?['appVersion']?.toString().trim() ?? '';
      final buildNumber = int.tryParse(raw?['buildNumber']?.toString() ?? '');
      final osVersion = raw?['osVersion']?.toString().trim() ?? '';
      final deviceModel = raw?['deviceModel']?.toString().trim() ?? '';
      final environment = raw?['environment']?.toString().trim() ?? '';
      final recoveryBaseUrl = raw?['recoveryBaseUrl']?.toString().trim() ?? '';
      final runtimeConfigDigest =
          raw?['runtimeConfigDigest']?.toString().trim() ?? '';
      final effectiveLaunchManifestDigest =
          raw?['effectiveLaunchManifestDigest']?.toString().trim() ?? '';
      final publicWebUrl = raw?['publicWebUrl']?.toString().trim() ?? '';
      final appDownloadBaseUrl =
          raw?['appDownloadBaseUrl']?.toString().trim() ?? '';
      if ((platform != 'ios' && platform != 'android') ||
          appVersion.isEmpty ||
          buildNumber == null ||
          buildNumber <= 0 ||
          osVersion.isEmpty ||
          deviceModel.isEmpty ||
          !_isTrustedHttps(publicWebUrl) ||
          !_isTrustedHttps(appDownloadBaseUrl)) {
        return null;
      }
      final runtimeBinding = RecoveryRuntimeBinding.fromLaunchManifest(
        environment: environment,
        recoveryBaseUrl: recoveryBaseUrl,
        runtimeConfigDigest: runtimeConfigDigest,
        effectiveLaunchManifestDigest: effectiveLaunchManifestDigest,
      );
      _trustedBaseUrls
        ..clear()
        ..addAll(<String>[recoveryBaseUrl, publicWebUrl, appDownloadBaseUrl]);
      return AppRecoveryNativeContext(
        platform: platform,
        appVersion: appVersion,
        buildNumber: buildNumber,
        osVersion: osVersion,
        deviceModel: deviceModel,
        runtimeBinding: runtimeBinding,
        publicWebUrl: publicWebUrl,
        appDownloadBaseUrl: appDownloadBaseUrl,
      );
    } on FormatException {
      return null;
    } on PlatformException {
      return null;
    } on MissingPluginException {
      return null;
    }
  }

  Future<bool> openTrustedExternalUrl(String rawUrl) async {
    final uri = Uri.tryParse(rawUrl.trim());
    if (uri == null || !isTrustedHttpsUrl(rawUrl, _trustedBaseUrls)) {
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

  Future<bool> recordFatalStartup({
    required String attemptId,
    required String failureCode,
  }) async {
    final normalizedAttemptId = attemptId.trim();
    final normalizedFailureCode = failureCode.trim();
    if (normalizedAttemptId.isEmpty || normalizedFailureCode.isEmpty) {
      return false;
    }
    try {
      return await _channel.invokeMethod<bool>(
            'recordFatalStartup',
            <String, String>{
              'attemptId': normalizedAttemptId,
              'failureCode': normalizedFailureCode,
            },
          ) ??
          false;
    } on PlatformException {
      // 状态持久化失败不得阻断恢复页。
      return false;
    } on MissingPluginException {
      // 原生桥不可用时仍展示 Flutter 恢复页。
      return false;
    }
  }

  Future<Map<String, Object?>?> readPendingNativeStartupFatal() async {
    try {
      return await _channel.invokeMapMethod<String, Object?>(
        'readPendingNativeStartupFatal',
      );
    } on PlatformException {
      return null;
    } on MissingPluginException {
      return null;
    }
  }

  Future<void> acknowledgePendingNativeStartupFatal() async {
    try {
      await _channel.invokeMethod<void>('ackPendingNativeStartupFatal');
    } on PlatformException {
      // ACK 失败保留原生 marker，下一次仍可补报。
    } on MissingPluginException {
      // 原生桥不可用时不清理 marker。
    }
  }

  Future<String?> readRecoveryFailureQueue() async {
    try {
      return await _channel.invokeMethod<String>('readRecoveryFailureQueue');
    } on PlatformException {
      return null;
    } on MissingPluginException {
      return null;
    }
  }

  Future<bool> writeRecoveryFailureQueue(String value) async {
    try {
      return await _channel.invokeMethod<bool>(
            'writeRecoveryFailureQueue',
            <String, String>{'value': value},
          ) ??
          false;
    } on PlatformException {
      return false;
    } on MissingPluginException {
      return false;
    }
  }

  Future<bool> clearRecoveryFailureQueue() async {
    try {
      return await _channel.invokeMethod<bool>('clearRecoveryFailureQueue') ??
          false;
    } on PlatformException {
      return false;
    } on MissingPluginException {
      return false;
    }
  }

  static bool _isTrustedHttps(String rawUrl) {
    final uri = Uri.tryParse(rawUrl.trim());
    if (uri == null ||
        uri.scheme.toLowerCase() != 'https' ||
        uri.host.isEmpty ||
        uri.userInfo.isNotEmpty ||
        uri.hasQuery ||
        uri.hasFragment) {
      return false;
    }
    return true;
  }
}
