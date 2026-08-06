import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:quwoquan_app/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/runtime/transport/http/cloud_http_client.dart';
import 'package:quwoquan_app/runtime/transport/cloud_json_transport.dart';

final class _MutableTokenProvider implements CloudAuthTokenProvider {
  String? token;

  @override
  Future<String?> getAccessToken() async => token;
}

final class _BlockingTokenProvider implements CloudAuthTokenProvider {
  final Completer<String?> completer = Completer<String?>();

  @override
  Future<String?> getAccessToken() => completer.future;
}

void main() {
  group('generated Cloud transport auth contract', () {
    test('required operation 缺 token 时在发网前失败关闭', () async {
      var requestCount = 0;
      final httpClient = CloudHttpClient(
        client: MockClient((request) async {
          requestCount += 1;
          return http.Response('{}', 200);
        }),
        authTokenProvider: _MutableTokenProvider(),
      );
      addTearDown(httpClient.close);
      final transport = HttpCloudJsonTransport(httpClient);

      await expectLater(
        transport.send(_request(authMode: 'required')),
        throwsA(
          isA<CloudException>().having(
            (error) => error.statusCode,
            'statusCode',
            401,
          ),
        ),
      );
      expect(requestCount, 0);
    });

    test('required operation 可先刷新再注入 Bearer', () async {
      final tokenProvider = _MutableTokenProvider();
      String? authorization;
      final httpClient = CloudHttpClient(
        client: MockClient((request) async {
          authorization = request.headers['authorization'];
          return http.Response('{}', 200);
        }),
        authTokenProvider: tokenProvider,
        onUnauthorizedRefresh: (_) async {
          tokenProvider.token = 'refreshed-token';
          return true;
        },
      );
      addTearDown(httpClient.close);

      await HttpCloudJsonTransport(
        httpClient,
      ).send(_request(authMode: 'required'));

      expect(authorization, 'Bearer refreshed-token');
    });

    test('optional operation 无 token 时仍可匿名请求', () async {
      var requestCount = 0;
      final httpClient = CloudHttpClient(
        client: MockClient((request) async {
          requestCount += 1;
          expect(request.headers, isNot(contains('authorization')));
          return http.Response('{}', 200);
        }),
        authTokenProvider: _MutableTokenProvider(),
      );
      addTearDown(httpClient.close);

      await HttpCloudJsonTransport(
        httpClient,
      ).send(_request(authMode: 'optional'));

      expect(requestCount, 1);
    });

    test('未知 auth mode 不得降级为 public', () async {
      var requestCount = 0;
      final httpClient = CloudHttpClient(
        client: MockClient((request) async {
          requestCount += 1;
          return http.Response('{}', 200);
        }),
        authTokenProvider: _MutableTokenProvider(),
      );
      addTearDown(httpClient.close);

      expect(
        () => HttpCloudJsonTransport(
          httpClient,
        ).send(_request(authMode: 'unsupported')),
        throwsA(isA<CloudException>()),
      );
      expect(requestCount, 0);
    });

    test('Bearer 仅可发送到精确 Gateway origin，调用方 Authorization 被剥离', () async {
      var requestCount = 0;
      Map<String, String>? observedHeaders;
      final httpClient = CloudHttpClient(
        client: MockClient((request) async {
          requestCount += 1;
          observedHeaders = request.headers;
          return http.Response('{}', 200);
        }),
        authTokenProvider: _MutableTokenProvider(),
      );
      addTearDown(httpClient.close);
      final transport = HttpCloudJsonTransport(httpClient);

      await transport.send(
        _request(
          authMode: 'optional',
          headers: const <String, String>{
            'Authorization': 'Bearer caller-controlled',
          },
        ),
      );
      expect(observedHeaders, isNot(contains('authorization')));

      await expectLater(
        transport.send(
          _request(
            authMode: 'optional',
            uri: Uri.parse('https://evil.example.test/resource'),
          ),
        ),
        throwsA(isA<CloudException>()),
      );
      expect(requestCount, 1);
    });

    test('读取 token 必须服从 operation abort trigger', () async {
      var requestCount = 0;
      final tokenProvider = _BlockingTokenProvider();
      final httpClient = CloudHttpClient(
        client: MockClient((request) async {
          requestCount += 1;
          return http.Response('{}', 200);
        }),
        authTokenProvider: tokenProvider,
      );
      addTearDown(httpClient.close);

      await expectLater(
        HttpCloudJsonTransport(httpClient).send(
          CloudJsonTransportRequest(
            method: 'GET',
            authMode: 'required',
            uri: Uri.parse('https://gateway.example.test/resource'),
            gatewayOrigin: Uri.parse('https://gateway.example.test'),
            headers: const <String, String>{'X-Request-Id': 'request-id'},
            abortTrigger: Future<void>.value(),
          ),
        ),
        throwsA(isA<http.RequestAbortedException>()),
      );
      expect(requestCount, 0);
    });

    test('refresh 回调必须接收并服从 operation abort trigger', () async {
      final refreshStarted = Completer<void>();
      final finishRefresh = Completer<bool>();
      final cancellation = Completer<void>();
      var observedAbort = false;
      final httpClient = CloudHttpClient(
        client: MockClient((_) async => http.Response('{}', 200)),
        authTokenProvider: _MutableTokenProvider(),
        onUnauthorizedRefresh: (abortTrigger) async {
          refreshStarted.complete();
          await abortTrigger;
          observedAbort = true;
          return finishRefresh.future;
        },
      );
      addTearDown(httpClient.close);

      final refresh = httpClient.refreshOperationAuthorization(
        abortTrigger: cancellation.future,
      );
      await refreshStarted.future;
      cancellation.complete();
      await expectLater(refresh, throwsA(isA<http.RequestAbortedException>()));
      await Future<void>.delayed(Duration.zero);

      expect(observedAbort, isTrue);
      finishRefresh.complete(false);
    });
  });
}

CloudJsonTransportRequest _request({
  required String authMode,
  Uri? uri,
  Map<String, String> headers = const <String, String>{
    'X-Request-Id': 'request-id',
  },
}) {
  return CloudJsonTransportRequest(
    method: 'GET',
    authMode: authMode,
    uri: uri ?? Uri.parse('https://gateway.example.test/resource'),
    gatewayOrigin: Uri.parse('https://gateway.example.test'),
    headers: headers,
    abortTrigger: Future<void>.delayed(const Duration(seconds: 30)),
  );
}
