// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-suspension-and-appeal-lifecycle/spec.md#gwt-004
import 'dart:async';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:quwoquan_app/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/runtime/errors/generated/user/user_errors.g.dart';
import 'package:quwoquan_app/runtime/transport/http/cloud_http_client.dart';

void main() {
  test('401 后自动 refresh 一次并重试原请求', () async {
    var requestCount = 0;
    var currentAccessToken = 'expired-token';
    var refreshCount = 0;
    final client = CloudHttpClient(
      client: MockClient((request) async {
        requestCount++;
        final authHeader = request.headers['Authorization'];
        if (request.url.path == '/protected') {
          if (authHeader == 'Bearer expired-token') {
            return http.Response('{"code":"USER.AUTH.token_expired"}', 401);
          }
          expect(authHeader, 'Bearer fresh-token');
          return http.Response(jsonEncode(<String, dynamic>{'ok': true}), 200);
        }
        return http.Response('{}', 404);
      }),
      authTokenProvider: _MemoryTokenProvider(() => currentAccessToken),
      onUnauthorizedRefresh: (_) async {
        refreshCount++;
        currentAccessToken = 'fresh-token';
        return true;
      },
    );

    final response = await client.getJson(
      Uri.parse('https://gateway.example.com/protected'),
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
      onUnauthorizedRefresh: (_) async {
        refreshCount++;
        return false;
      },
    );

    await expectLater(
      () => client.getJson(
        Uri.parse('https://gateway.example.com/protected'),
        headers: const <String, String>{'X-Client-Page-Id': 'test.page'},
      ),
      throwsA(isA<Exception>()),
    );
    expect(requestCount, 1);
    expect(refreshCount, 1);
  });

  test('403 账号限制也只触发一次 refresh，以便会话层安全清凭证', () async {
    var requestCount = 0;
    var refreshCount = 0;
    final client = CloudHttpClient(
      client: MockClient((request) async {
        requestCount++;
        return http.Response('{"code":"USER.AUTH.account_suspended"}', 403);
      }),
      authTokenProvider: const _StaticTokenProvider('pre-suspension-token'),
      onUnauthorizedRefresh: (_) async {
        refreshCount++;
        // 真正的 refresh 在 AuthSessionController 中将解析 account_suspended、
        // 清理本地凭证并返回 false；HTTP 客户端必须保留最初结构化 403。
        return false;
      },
    );

    await expectLater(
      () => client.getJson(
        Uri.parse('https://gateway.example.com/protected'),
        headers: const <String, String>{'X-Client-Page-Id': 'test.page'},
      ),
      throwsA(isA<Exception>()),
    );
    expect(requestCount, 1);
    expect(refreshCount, 1);
  });

  test('generated operation 的 canonical 403 立即通知实际 bearer 且不重试', () async {
    var requestCount = 0;
    var refreshCount = 0;
    CloudException? observedFailure;
    String? observedToken;
    final client = CloudHttpClient(
      client: MockClient((request) async {
        requestCount += 1;
        expect(request.headers['Authorization'], 'Bearer old-access-token');
        return http.Response(
          jsonEncode(<String, String>{
            'code': UserErrorCode.accountSuspended.code,
          }),
          403,
        );
      }),
      authTokenProvider: const _StaticTokenProvider('old-access-token'),
      onUnauthorizedRefresh: (_) async {
        refreshCount += 1;
        return false;
      },
      onAuthoritativeSessionFailure: (failure, presentedAccessToken) async {
        observedFailure = failure;
        observedToken = presentedAccessToken;
      },
    );

    await expectLater(
      () => client.sendOperationJson(
        method: 'GET',
        uri: Uri.parse('https://gateway.example.com/protected'),
        gatewayOrigin: Uri.parse('https://gateway.example.com'),
        headers: const <String, String>{},
        requireAuth: true,
        abortTrigger: Completer<void>().future,
      ),
      throwsA(
        isA<CloudException>().having(
          (error) => error.code,
          'code',
          UserErrorCode.accountSuspended.code,
        ),
      ),
    );

    expect(requestCount, 1);
    expect(refreshCount, 0);
    expect(observedFailure?.code, UserErrorCode.accountSuspended.code);
    expect(observedToken, 'old-access-token');
  });

  test('旧 bearer cleanup 挂起时新 bearer 的 canonical 403 仍独立处理', () async {
    var currentAccessToken = 'old-access-token';
    final oldCleanupStarted = Completer<void>();
    final oldCleanupGate = Completer<void>();
    final observedTokens = <String>[];
    final client = CloudHttpClient(
      client: MockClient(
        (_) async => http.Response(
          jsonEncode(<String, String>{
            'code': UserErrorCode.accountSuspended.code,
          }),
          403,
        ),
      ),
      authTokenProvider: _MemoryTokenProvider(() => currentAccessToken),
      timeout: const Duration(milliseconds: 20),
      onAuthoritativeSessionFailure: (_, presentedAccessToken) {
        observedTokens.add(presentedAccessToken);
        if (presentedAccessToken == 'old-access-token') {
          if (!oldCleanupStarted.isCompleted) oldCleanupStarted.complete();
          return oldCleanupGate.future;
        }
        return Future<void>.value();
      },
    );
    final oldAbort = Completer<void>();
    final oldRequest = client.sendOperationJson(
      method: 'GET',
      uri: Uri.parse('https://gateway.example.com/protected'),
      gatewayOrigin: Uri.parse('https://gateway.example.com'),
      headers: const <String, String>{},
      requireAuth: true,
      abortTrigger: oldAbort.future,
    );
    final oldFailure = expectLater(
      oldRequest,
      throwsA(
        isA<CloudException>().having(
          (error) => error.code,
          'code',
          UserErrorCode.accountSuspended.code,
        ),
      ),
    );

    await oldCleanupStarted.future;
    currentAccessToken = 'new-access-token';
    final stopwatch = Stopwatch()..start();
    await expectLater(
      client.sendOperationJson(
        method: 'GET',
        uri: Uri.parse('https://gateway.example.com/protected'),
        gatewayOrigin: Uri.parse('https://gateway.example.com'),
        headers: const <String, String>{},
        requireAuth: true,
        abortTrigger: Completer<void>().future,
      ),
      throwsA(
        isA<CloudException>().having(
          (error) => error.code,
          'code',
          UserErrorCode.accountSuspended.code,
        ),
      ),
    );
    stopwatch.stop();
    expect(stopwatch.elapsed, lessThan(const Duration(milliseconds: 250)));
    expect(observedTokens, <String>['old-access-token', 'new-access-token']);

    oldAbort.complete();
    await oldFailure;
    oldCleanupGate.complete();
    await Future<void>.delayed(Duration.zero);
    client.close();
  });

  test('仅 canonical account_deleted 410 触发一次 refresh 以清除本地会话', () async {
    var accountClosureRequestCount = 0;
    var ordinaryGoneRequestCount = 0;
    var refreshCount = 0;
    final client = CloudHttpClient(
      client: MockClient((request) async {
        if (request.url.path == '/account-closed') {
          accountClosureRequestCount++;
          return http.Response('{"code":"USER.AUTH.account_deleted"}', 410);
        }
        ordinaryGoneRequestCount++;
        return http.Response('{"code":"CONTENT.POST.not_found"}', 410);
      }),
      authTokenProvider: const _StaticTokenProvider('pre-closure-token'),
      onUnauthorizedRefresh: (_) async {
        refreshCount++;
        // 真正的 refresh 会因账号已注销而清除会话并返回 false。
        return false;
      },
    );

    await expectLater(
      () => client.getJson(
        Uri.parse('https://gateway.example.com/account-closed'),
        headers: const <String, String>{'X-Client-Page-Id': 'test.page'},
      ),
      throwsA(isA<Exception>()),
    );
    await expectLater(
      () => client.getJson(
        Uri.parse('https://gateway.example.com/ordinary-gone'),
        headers: const <String, String>{'X-Client-Page-Id': 'test.page'},
      ),
      throwsA(isA<Exception>()),
    );

    expect(accountClosureRequestCount, 1);
    expect(ordinaryGoneRequestCount, 1);
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
