import 'dart:math';

import 'package:flutter/foundation.dart';

/// 端侧请求上下文 header 注入（用于网关访问日志/异常日志/过程日志关联）。
///
/// 约定字段（与云侧 contracts/openapi/common.yaml 对齐）：
/// - X-Client-Page-Id：来源标识（推荐三段式：模块.业务对象.页面名/动作）
/// - X-Client-Session-Id：端侧一次启动会话 ID（稳定）
/// - X-Client-Sent-At：端侧发送时间（用于端云时延/对齐）
/// - X-Client-Device-Platform：android/ios/web/desktop
/// - X-Client-App-Version：端侧版本（可用 dart-define 注入）
/// - X-Trace-Id / X-Request-Id：分段可读的追踪 ID（见云侧 error_codes.md）
class CloudRequestHeaders {
  CloudRequestHeaders._();

  static final String sessionId = _toBase36(
    DateTime.now().microsecondsSinceEpoch,
  );
  static final Random _rng = Random();

  static const String appVersion = String.fromEnvironment(
    'APP_VERSION',
    defaultValue: 'dev',
  );

  static String platform() {
    if (kIsWeb) return 'web';
    switch (defaultTargetPlatform) {
      case TargetPlatform.android:
        return 'android';
      case TargetPlatform.iOS:
        return 'ios';
      case TargetPlatform.macOS:
        return 'macos';
      case TargetPlatform.windows:
        return 'windows';
      case TargetPlatform.linux:
        return 'linux';
      case TargetPlatform.fuchsia:
        return 'fuchsia';
    }
  }

  static Map<String, String> forPage(String pageId) {
    final ts = _toBase36(DateTime.now().microsecondsSinceEpoch);
    final rand = _toBase36(_rng.nextInt(36 * 36 * 36 * 36)); // 4 chars base36
    final nowIso = DateTime.now().toIso8601String();
    final traceId = 'APP.$sessionId.$pageId.$ts.$rand';
    final requestId = 'APP.$pageId.$ts.$rand';
    return <String, String>{
      'X-Client-Page-Id': pageId,
      'X-Client-Session-Id': sessionId,
      'X-Client-Sent-At': nowIso,
      'X-Client-Device-Platform': platform(),
      'X-Client-App-Version': appVersion,
      // 追踪：分段可读，可从 ID 直接看出源头/页面/会话/时间
      'X-Trace-Id': traceId,
      'X-Request-Id': requestId,
    };
  }

  static Map<String, String> forSurfaceOperation({
    required String surfaceId,
    required String operationId,
    required String legacyPageId,
    String? routeId,
  }) {
    final ts = _toBase36(DateTime.now().microsecondsSinceEpoch);
    final rand = _toBase36(_rng.nextInt(36 * 36 * 36 * 36));
    final nowIso = DateTime.now().toIso8601String();
    final traceId = 'APP.$sessionId.$surfaceId.$operationId.$ts.$rand';
    final requestId = 'APP.$surfaceId.$operationId.$ts.$rand';
    return <String, String>{
      'X-Client-Page-Id': legacyPageId,
      'X-Client-Surface-Id': surfaceId,
      'X-Client-Operation-Id': operationId,
      if (routeId != null && routeId.isNotEmpty) 'X-Client-Route-Id': routeId,
      'X-Client-Session-Id': sessionId,
      'X-Client-Sent-At': nowIso,
      'X-Client-Device-Platform': platform(),
      'X-Client-App-Version': appVersion,
      'X-Trace-Id': traceId,
      'X-Request-Id': requestId,
    };
  }

  static String contextForSurfaceOperation({
    required String surfaceId,
    required String operationId,
  }) {
    return '$surfaceId.$operationId';
  }

  static String _toBase36(int value) => value.toRadixString(36);
}

