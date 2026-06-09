import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:quwoquan_app/cloud/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';

void main() {
  test('401 后自动 refresh 一次并重试原请求', () async {
    var requestCount = 0;
    var currentAccessToken = 'expired-token';
    var refreshCount = 0;
    final client = CloudHttpClient(
      client: MockClient((request) async {
        requestCount++;
        final authHeader = request.headers['Authorization'];
        if (request.url.path == '/v1/protected') {
          if (authHeader == 'Bearer expired-token') {
            return http.Response('{"code":"USER.AUTH.token_expired"}', 401);
          }
          expect(authHeader, 'Bearer fresh-token');
          return http.Response(jsonEncode(<String, dynamic>{'ok': true}), 200);
        }
        return http.Response('{}', 404);
      }),
      authTokenProvider: _MemoryTokenProvider(() => currentAccessToken),
      onUnauthorizedRefresh: () async {
        refreshCount++;
        currentAccessToken = 'fresh-token';
        return true;
      },
    );

    final response = await client.getJson(
      Uri.parse('https://gateway.example.com/v1/protected'),
      headers: const <String, String>{'X-Client-Page-Id': 'test.page'},
    );

    expect(response, <String, dynamic>{'ok': true});
    expect(requestCount, 2);
    expect(refreshCount, 1);
  });

  test('refresh 失败时保留原始 401，不无限重试', () async {
    var requestCount = 0;
    var refreshCount = 0;
    final client = CloudHttpClient(
      client: MockClient((request) async {
        requestCount++;
        return http.Response('{"code":"USER.AUTH.token_expired"}', 401);
      }),
      authTokenProvider: const _StaticTokenProvider('expired-token'),
      onUnauthorizedRefresh: () async {
        refreshCount++;
        return false;
      },
    );

    await expectLater(
      () => client.getJson(
        Uri.parse('https://gateway.example.com/v1/protected'),
        headers: const <String, String>{'X-Client-Page-Id': 'test.page'},
      ),
      throwsA(isA<Exception>()),
    );
    expect(requestCount, 1);
    expect(refreshCount, 1);
  });
}

class _MemoryTokenProvider implements CloudAuthTokenProvider {
  _MemoryTokenProvider(this._readToken);

  final String Function() _readToken;

  @override
  Future<String?> getAccessToken() async => _readToken();
}

class _StaticTokenProvider implements CloudAuthTokenProvider {
  const _StaticTokenProvider(this.token);

  final String token;

  @override
  Future<String?> getAccessToken() async => token;
}
