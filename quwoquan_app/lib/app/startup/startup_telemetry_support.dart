import 'dart:convert';
import 'dart:math';

/// 启动遥测的输入归一化与匿名标识工具。
///
/// 这些规则必须在新事件与本地 journal 回放时保持一致。
final class StartupTelemetrySupport {
  const StartupTelemetrySupport._();

  static int asInt(Object? value) {
    if (value is int) {
      return value;
    }
    if (value is num) {
      return value.round();
    }
    return int.tryParse(value?.toString() ?? '') ?? 0;
  }

  static bool isValidProof(String value) =>
      RegExp(r'^[A-Za-z0-9_-]{24,192}$').hasMatch(value);

  static bool isValidAttemptId(String value) =>
      RegExp(r'^[A-Za-z0-9_-]{16,128}$').hasMatch(value);

  static String randomUrlSafeToken(int bytes) {
    final random = Random.secure();
    final values = List<int>.generate(bytes, (_) => random.nextInt(256));
    return base64UrlEncode(values).replaceAll('=', '');
  }

  static String sanitizeAppVersion(String value) {
    final normalized = value.trim();
    if (normalized.isEmpty) {
      return '';
    }
    return RegExp(
          r'^v?[0-9]+(?:\.[0-9]+){1,3}(?:[-.][A-Za-z0-9]+)*$',
        ).hasMatch(normalized)
        ? normalized
        : '';
  }

  static String sanitizeEnum(
    String value,
    Set<String> allowed, {
    required String fallback,
  }) {
    final normalized = value.trim();
    return allowed.contains(normalized) ? normalized : fallback;
  }

  static const Set<String> outcomes = <String>{
    'observed',
    'started',
    'validated',
    'skipped',
    'painted',
    'ready',
    'retry',
    'failed',
    'entered',
    'degraded',
    'usable',
    'success',
    'recovery',
    'shown',
    'bootstrap_failure',
    'native_first_frame_timeout',
    'bootstrap_error',
    'unhandled_rejection',
    'pagehide_before_first_frame',
    'journal_drop',
    'unknown',
  };

  static const Set<String> platforms = <String>{
    'android',
    'ios',
    'ohos',
    'web',
    'desktop',
    'unknown',
  };

  static const Set<String> runtimeEnvs = <String>{
    'alpha',
    'beta',
    'gamma',
    'prod',
    'unknown',
  };

  static const Set<String> networkClasses = <String>{
    '',
    'offline',
    'wifi',
    'cellular',
    'ethernet',
    'unknown',
  };

  static const Set<String> recoverySurfaces = <String>{
    '',
    'flutter_recovery',
    'safe_recovery',
    'native_recovery',
  };

  static const Set<String> failureCodes = <String>{
    '',
    'OPS.SYSTEM.startup_configuration_invalid',
    'OPS.SYSTEM.startup_initialization_failed',
    'OPS.SYSTEM.startup_router_unavailable',
    'OPS.SYSTEM.startup_native_first_frame_timeout',
  };

  static const Set<String> failureSources = <String>{
    '',
    'bootstrap',
    'router',
    'startup_deadline',
    'native_watchdog',
    'web_error',
    'web_unhandled_rejection',
    'web_pagehide',
  };

  static const Set<String> deadlineOrigins = <String>{
    '',
    'fallbackDart',
    'android_process',
    'ios_process',
    'web_bootstrap',
  };
}
