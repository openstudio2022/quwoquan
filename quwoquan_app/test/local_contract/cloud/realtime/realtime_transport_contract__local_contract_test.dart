import 'dart:async';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:quwoquan_app/cloud/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/cloud/runtime/auth/realtime_connection_credential.dart';
import 'package:quwoquan_app/cloud/runtime/generated/realtime/realtime_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/realtime/realtime_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/services/realtime/realtime_config.dart';
import 'package:quwoquan_app/cloud/services/realtime/transport/longpoll_transport.dart';

void main() {
  group('Realtime transport contract', () {
    test('fromGateway derives websocket url from generated metadata', () {
      final config = RealtimeConfig.fromGateway();

      expect(config.wsUrl, endsWith(RealtimeApiMetadata.webSocketUpgradePath));
      expect(
        config.wsUrl.startsWith('ws://') || config.wsUrl.startsWith('wss://'),
        isTrue,
      );
    });

    test('websocket credential carries only trusted token identity', () async {
      final credential = await RealtimeConnectionCredential.resolveWebSocket(
        const _TokenProvider('jwt-token'),
        runtimeEnvironment: 'gamma',
      );
      final uri = credential!.authorizeWebSocket(
        Uri.parse('wss://gateway.example/realtime/ws'),
      );

      expect(uri.queryParameters['access_token'], 'jwt-token');
      expect(uri.queryParameters.containsKey('userId'), isFalse);
      expect(uri.queryParameters.containsKey('topics'), isFalse);
    });

    test('prod websocket 无短期 ticket contract 时失败关闭', () async {
      final credential = await RealtimeConnectionCredential.resolveWebSocket(
        const _TokenProvider('jwt-token'),
        runtimeEnvironment: 'prod',
      );

      expect(credential, isNull);
    });

    test('prod long poll 仍使用可信 Bearer credential', () async {
      final credential = await RealtimeConnectionCredential.resolveHttp(
        const _TokenProvider('jwt-token'),
      );

      expect(
        credential!.authorizeHttp(const <String, String>{})['Authorization'],
        'Bearer jwt-token',
      );
    });

    test('long poll uses generated path and request page id headers', () async {
      final requests = <http.Request>[];
      late LongPollTransport transport;
      final completed = Completer<void>();

      final client = MockClient((request) async {
        requests.add(request);
        if (!completed.isCompleted) {
          completed.complete();
        }
        return http.Response(
          jsonEncode({'events': []}),
          200,
          headers: {'content-type': 'application/json'},
        );
      });

      transport = LongPollTransport(
        config: const RealtimeConfig(
          wsUrl: 'ws://127.0.0.1:18080/realtime/ws',
          longPollHoldSec: 1,
        ),
        authTokenProvider: const _TokenProvider('jwt-token'),
        onEvents: (_) {},
        client: client,
      );

      transport.start();
      await completed.future.timeout(const Duration(seconds: 2));
      transport.stop();
      transport.dispose();

      expect(requests, isNotEmpty);
      expect(requests.first.method, 'GET');
      expect(requests.first.url.path, RealtimeApiMetadata.longPollPath);
      expect(requests.first.url.queryParameters.containsKey('userId'), isFalse);
      expect(requests.first.url.queryParameters['timeout'], '1');
      expect(requests.first.headers['Authorization'], 'Bearer jwt-token');
      expect(
        requests.first.headers['X-Client-Page-Id'],
        RealtimeRequestPageIds.longPoll,
      );
    });

    test(
      'long poll tolerates transient failures and eventually delivers events',
      () async {
        late LongPollTransport transport;
        final delivered = <Map<String, dynamic>>[];
        final completed = Completer<void>();
        var attempts = 0;

        final client = MockClient((request) async {
          attempts++;
          if (attempts < 3) {
            throw http.ClientException(
              'temporary network failure',
              request.url,
            );
          }
          return http.Response(
            jsonEncode({
              'events': [
                {'type': 'message', 'conversationId': 'c1'},
              ],
            }),
            200,
            headers: {'content-type': 'application/json'},
          );
        });

        transport = LongPollTransport(
          config: const RealtimeConfig(
            wsUrl: 'ws://127.0.0.1:18080/realtime/ws',
            longPollHoldSec: 1,
          ),
          authTokenProvider: const _TokenProvider('jwt-token'),
          onEvents: (events) {
            delivered.addAll(events);
            transport.stop();
            if (!completed.isCompleted) {
              completed.complete();
            }
          },
          client: client,
        );

        transport.start();
        await completed.future.timeout(const Duration(seconds: 2));
        transport.dispose();

        expect(attempts, greaterThanOrEqualTo(3));
        expect(delivered, hasLength(1));
        expect(delivered.single['type'], 'message');
      },
    );

    test(
      'long poll fails closed before network when access token is absent',
      () async {
        var requestCount = 0;
        final transport = LongPollTransport(
          config: const RealtimeConfig(
            wsUrl: 'ws://127.0.0.1:18080/realtime/ws',
            longPollHoldSec: 1,
          ),
          authTokenProvider: const _TokenProvider(null),
          onEvents: (_) {},
          client: MockClient((_) async {
            requestCount++;
            return http.Response('', 204);
          }),
        );

        transport.start();
        await Future<void>.delayed(const Duration(milliseconds: 20));
        transport.dispose();

        expect(requestCount, 0);
      },
    );
  });
}

class _TokenProvider implements CloudAuthTokenProvider {
  const _TokenProvider(this.token);

  final String? token;

  @override
  Future<String?> getAccessToken() async => token;
}
