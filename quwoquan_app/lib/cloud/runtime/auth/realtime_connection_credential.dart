import 'package:quwoquan_app/cloud/runtime/auth/cloud_auth_token_provider.dart';

/// 由可信 AuthSession 提供的实时连接凭据。
///
/// LongPoll 使用 Bearer header。WebSocket/RTC 尚无短期 ticket operation，因此仅在
/// alpha/beta/gamma 允许现有 access-token query 联调；prod 与未知环境失败关闭。
/// 客户端身份和订阅主题不得再由 URL `userId/topics` 决定。
final class RealtimeConnectionCredential {
  RealtimeConnectionCredential._(this._accessToken);

  final String _accessToken;

  static Future<RealtimeConnectionCredential?> resolveHttp(
    CloudAuthTokenProvider provider,
  ) async {
    return _resolveAccessToken(provider);
  }

  static Future<RealtimeConnectionCredential?> resolveWebSocket(
    CloudAuthTokenProvider provider, {
    String runtimeEnvironment = const String.fromEnvironment(
      'APP_RUNTIME_ENV',
      defaultValue: 'alpha',
    ),
  }) async {
    if (runtimeEnvironment != 'alpha' &&
        runtimeEnvironment != 'beta' &&
        runtimeEnvironment != 'gamma') {
      return null;
    }
    return _resolveAccessToken(provider);
  }

  static Future<RealtimeConnectionCredential?> _resolveAccessToken(
    CloudAuthTokenProvider provider,
  ) async {
    final token = (await provider.getAccessToken())?.trim() ?? '';
    return token.isEmpty ? null : RealtimeConnectionCredential._(token);
  }

  Uri authorizeWebSocket(Uri endpoint) {
    return endpoint.replace(
      queryParameters: <String, String>{
        ...endpoint.queryParameters,
        'access_token': _accessToken,
      },
    );
  }

  Map<String, String> authorizeHttp(Map<String, String> headers) {
    return <String, String>{
      ...headers,
      'Authorization': 'Bearer $_accessToken',
    };
  }
}
