import 'dart:math';

import 'package:quwoquan_app/cloud/runtime/context/cloud_client_context.dart';

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

  static CloudClientContextSnapshot get _clientContext =>
      CloudClientContextRegistry.provider.snapshot();

  /// Canonical session ID is injected by the application composition root.
  static String get sessionId => _clientContext.sessionId;

  /// 隐私安全的派生设备标识（installId hash 派生）。游客设备态点赞/分享以此作为
  /// 设备维度计数键；登录用户也携带（用于同设备识别），但云侧账号维度优先、不并账。
  static String? get deviceActorId => _clientContext.deviceActorId;
  static final Random _rng = Random();

  static String get appVersion => _clientContext.appVersion;

  static String platform() => _clientContext.platform;

  static Map<String, String> forPage(String pageId) {
    final ts = _toBase36(DateTime.now().microsecondsSinceEpoch);
    final rand = _toBase36(_rng.nextInt(36 * 36 * 36 * 36)); // 4 chars base36
    final nowIso = DateTime.now().toIso8601String();
    final traceId = 'APP.$sessionId.$pageId.$ts.$rand';
    final requestId = 'APP.$pageId.$ts.$rand';
    return <String, String>{
      'X-Client-Page-Id': pageId,
      'X-Client-Session-Id': sessionId,
      if (deviceActorId != null && deviceActorId!.isNotEmpty)
        'X-Client-Device-Actor-Id': deviceActorId!,
      'X-Client-Sent-At': nowIso,
      'X-Client-Device-Platform': platform(),
      'X-Client-App-Version': appVersion,
      'X-Client-Locale': _clientContext.locale,
      // 追踪：分段可读，可从 ID 直接看出源头/页面/会话/时间
      'X-Trace-Id': traceId,
      'X-Request-Id': requestId,
    };
  }

  static Map<String, String> withOwnerSubAccountContext(
    Map<String, String> headers, {
    String? ownerUserId,
    String? subAccountId,
    String? subAccountContextVersion,
  }) {
    final next = Map<String, String>.from(headers);
    final resolvedOwnerUserId = (ownerUserId ?? '').trim();
    final resolvedSubAccountId = (subAccountId ?? '').trim();
    final resolvedContextVersion = (subAccountContextVersion ?? '').trim();
    if (resolvedOwnerUserId.isNotEmpty) {
      next['X-Client-User-Id'] = resolvedOwnerUserId;
    }
    if (resolvedSubAccountId.isNotEmpty) {
      next['X-Client-Sub-Account-Id'] = resolvedSubAccountId;
    }
    if (resolvedContextVersion.isNotEmpty) {
      next['X-Client-Sub-Account-Context-Version'] = resolvedContextVersion;
    }
    return next;
  }

  static Map<String, String> forSurfaceOperation({
    required String surfaceId,
    required String operationId,
    required String clientPageId,
    String? routeId,
    String? referralSource,
    String? feedRequestId,
  }) {
    if (surfaceId.trim().isEmpty ||
        operationId.trim().isEmpty ||
        clientPageId.trim().isEmpty) {
      throw ArgumentError.value(
        operationId,
        'operationId',
        'surface operation context is incomplete',
      );
    }
    final ts = _toBase36(DateTime.now().microsecondsSinceEpoch);
    final rand = _toBase36(_rng.nextInt(36 * 36 * 36 * 36));
    final nowIso = DateTime.now().toIso8601String();
    final traceId = 'APP.$sessionId.$surfaceId.$operationId.$ts.$rand';
    final requestId = 'APP.$surfaceId.$operationId.$ts.$rand';
    final resolvedDeviceActorId = deviceActorId?.trim() ?? '';
    return <String, String>{
      'X-Client-Page-Id': clientPageId,
      'X-Client-Surface-Id': surfaceId,
      'X-Client-Operation-Id': operationId,
      if ((routeId ?? '').trim().isNotEmpty)
        'X-Client-Route-Id': routeId!.trim(),
      'X-Client-Session-Id': sessionId,
      if (resolvedDeviceActorId.isNotEmpty)
        'X-Client-Device-Actor-Id': resolvedDeviceActorId,
      if ((referralSource ?? '').trim().isNotEmpty)
        'X-Referral-Source': referralSource!.trim(),
      if ((feedRequestId ?? '').trim().isNotEmpty)
        'X-Feed-Request-Id': feedRequestId!.trim(),
      'X-Client-Sent-At': nowIso,
      'X-Client-Device-Platform': platform(),
      'X-Client-App-Version': appVersion,
      'X-Client-Locale': _clientContext.locale,
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
