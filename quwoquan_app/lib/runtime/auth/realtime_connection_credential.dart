import 'dart:async';
import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:quwoquan_app/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/runtime/observability/app_exception_telemetry_service.dart';

/// 由可信 AuthSession 提供的实时连接凭据。
///
/// LongPoll 使用 Bearer header；WebSocket 使用短期一次性 ticket：
/// 先经 `IssueConnectionTicket`（Bearer 鉴权）换取 ticket，升级 query 只携带
/// ticket，长期 access token 不进入任何 URL。客户端身份和订阅主题由服务端
/// 从可信身份派生，不再由 URL `userId/topics` 决定。
final class RealtimeConnectionCredential {
  RealtimeConnectionCredential._bearer(this._accessToken) : _ticket = null;

  RealtimeConnectionCredential._ticket(this._ticket) : _accessToken = null;

  final String? _accessToken;
  final String? _ticket;

  /// Stable only for the lifetime of the current bearer token and never
  /// exposes that credential to local storage. Token rotation safely starts a
  /// new cursor partition and may replay retained events; event/message/seq
  /// idempotency absorbs that replay.
  String get cursorPartition {
    final accessToken = _accessToken;
    if (accessToken == null) {
      throw StateError('cursor partition requires a bearer credential');
    }
    return sha256.convert(utf8.encode(accessToken)).toString();
  }

  static Future<RealtimeConnectionCredential?> resolveHttp(
    CloudAuthTokenProvider provider,
  ) async {
    final token = (await provider.getAccessToken())?.trim() ?? '';
    return token.isEmpty ? null : RealtimeConnectionCredential._bearer(token);
  }

  /// 经 IssueConnectionTicket 换取一次性 ticket；无登录态或签发失败返回 null，
  /// 由传输层按断线重连语义处理。
  static Future<RealtimeConnectionCredential?> resolveWebSocket(
    CloudAuthTokenProvider provider, {
    required Future<String> Function() issueTicket,
  }) async {
    final token = (await provider.getAccessToken())?.trim() ?? '';
    if (token.isEmpty) {
      return null;
    }
    final String ticket;
    try {
      ticket = (await issueTicket()).trim();
    } catch (error, stackTrace) {
      // 签发失败按无凭证处理，交给传输层重连；但这是真实故障，必须留证据。
      unawaited(
        AppExceptionTelemetryService.instance.recordHandledException(
          source: 'runtime.auth.issue_connection_ticket',
          error: error,
          stackTrace: stackTrace,
        ),
      );
      return null;
    }
    if (ticket.isEmpty) {
      return null;
    }
    return RealtimeConnectionCredential._ticket(ticket);
  }

  Uri authorizeWebSocket(Uri endpoint) {
    final ticket = _ticket;
    if (ticket == null) {
      throw StateError('websocket credential requires a connection ticket');
    }
    return endpoint.replace(
      queryParameters: <String, String>{
        ...endpoint.queryParameters,
        'ticket': ticket,
      },
    );
  }
}
