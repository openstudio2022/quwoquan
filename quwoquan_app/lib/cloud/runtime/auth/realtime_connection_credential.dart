import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:quwoquan_app/cloud/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/cloud/runtime/generated/realtime/realtime_api_metadata.g.dart';

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
    required String gatewayBaseUrl,
    required http.Client client,
  }) async {
    final token = (await provider.getAccessToken())?.trim() ?? '';
    if (token.isEmpty) {
      return null;
    }
    final uri = Uri.parse(
      '$gatewayBaseUrl${RealtimeApiMetadata.issueConnectionTicketPath}',
    );
    final http.Response response;
    try {
      response = await client
          .post(uri, headers: <String, String>{'Authorization': 'Bearer $token'})
          .timeout(const Duration(seconds: 5));
    } catch (_) {
      return null;
    }
    if (response.statusCode != 200) {
      return null;
    }
    final body = jsonDecode(response.body);
    if (body is! Map<String, dynamic>) {
      return null;
    }
    final ticket = (body['ticket'] as String?)?.trim() ?? '';
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

  Map<String, String> authorizeHttp(Map<String, String> headers) {
    final accessToken = _accessToken;
    if (accessToken == null) {
      throw StateError('http credential requires a bearer access token');
    }
    return <String, String>{
      ...headers,
      'Authorization': 'Bearer $accessToken',
    };
  }
}
