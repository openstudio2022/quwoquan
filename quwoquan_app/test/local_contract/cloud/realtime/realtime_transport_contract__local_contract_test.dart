import 'dart:async';
import 'dart:convert';

import 'package:fake_async/fake_async.dart';
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
    test('fromRuntime combines topology authority with generated path', () {
      final config = RealtimeConfig.fromRuntime(
        gatewayBaseUrl: 'https://gateway.example',
        realtimeBaseUrl: 'wss://realtime.example',
      );

      expect(
        config.wsUrl,
        'wss://realtime.example${RealtimeApiMetadata.webSocketUpgradePath}',
      );
    });

    test('websocket credential 先换一次性 ticket，URL 只携带 ticket', () async {
      http.Request? ticketRequest;
      final client = MockClient((request) async {
        ticketRequest = request;
        return http.Response(
          jsonEncode({
            'ticket': 'one-time-ticket',
            'expiresAt': '2026-07-19T00:00:30Z',
          }),
          200,
          headers: {'content-type': 'application/json'},
        );
      });

      final credential = await RealtimeConnectionCredential.resolveWebSocket(
        const _TokenProvider('jwt-token'),
        gatewayBaseUrl: 'https://gateway.example',
        client: client,
      );
      final uri = credential!.authorizeWebSocket(
        Uri.parse('wss://gateway.example/realtime/ws'),
      );

      expect(
        ticketRequest!.url.path,
        RealtimeApiMetadata.issueConnectionTicketPath,
      );
      expect(ticketRequest!.headers['Authorization'], 'Bearer jwt-token');
      expect(uri.queryParameters['ticket'], 'one-time-ticket');
      expect(uri.queryParameters.containsKey('access_token'), isFalse);
      expect(uri.queryParameters.containsKey('userId'), isFalse);
      expect(uri.queryParameters.containsKey('topics'), isFalse);
    });

    test('ticket 签发失败或未登录时失败关闭', () async {
      final rejectingClient = MockClient(
        (_) async =>
            http.Response('{"code":"REALTIME.USER.unauthorized"}', 401),
      );
      expect(
        await RealtimeConnectionCredential.resolveWebSocket(
          const _TokenProvider('jwt-token'),
          gatewayBaseUrl: 'https://gateway.example',
          client: rejectingClient,
        ),
        isNull,
      );
      expect(
        await RealtimeConnectionCredential.resolveWebSocket(
          const _TokenProvider(null),
          gatewayBaseUrl: 'https://gateway.example',
          client: rejectingClient,
        ),
        isNull,
      );
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
          jsonEncode({
            'events': [],
            'nextCursor': '0-0',
            'transportResumed': false,
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
        onEvents: (_) {},
        cursorStore: _MemoryLongPollCursorStore(),
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
              'nextCursor': '100-0',
              'transportResumed': false,
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
          cursorStore: _MemoryLongPollCursorStore(),
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
          cursorStore: _MemoryLongPollCursorStore(),
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

    test('stop cancels a pending long poll backoff timer', () {
      fakeAsync((clock) {
        var requestCount = 0;
        final transport = LongPollTransport(
          config: const RealtimeConfig(
            wsUrl: 'ws://127.0.0.1:18080/realtime/ws',
            longPollHoldSec: 1,
          ),
          authTokenProvider: const _TokenProvider('jwt-token'),
          onEvents: (_) {},
          cursorStore: _MemoryLongPollCursorStore(),
          client: MockClient((request) async {
            requestCount++;
            throw http.ClientException('offline', request.url);
          }),
        );

        transport.start();
        clock.flushMicrotasks();

        expect(requestCount, 5);
        expect(clock.pendingTimers, hasLength(1));

        transport.stop();
        expect(clock.pendingTimers, isEmpty);
        transport.dispose();
      });
    });

    test('long poll persists cursor and emits one resume recovery', () async {
      final cursorStore = _MemoryLongPollCursorStore();
      final requests = <http.Request>[];
      final delivered = <Map<String, dynamic>>[];
      final completed = Completer<void>();
      var attempts = 0;
      late LongPollTransport transport;
      final client = MockClient((request) async {
        requests.add(request);
        attempts++;
        if (attempts == 1) {
          return http.Response(
            jsonEncode({
              'events': [],
              'nextCursor': '100-0',
              'transportResumed': false,
            }),
            200,
          );
        }
        return http.Response(
          jsonEncode({
            'events': [
              {'eventId': 'event-2', 'type': 'MessageSent'},
            ],
            'nextCursor': '101-0',
            'transportResumed': true,
          }),
          200,
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
          if (delivered.any((event) => event['eventId'] == 'event-2')) {
            transport.stop();
            if (!completed.isCompleted) completed.complete();
          }
        },
        cursorStore: cursorStore,
        client: client,
      );

      transport.start();
      await completed.future.timeout(const Duration(seconds: 2));
      transport.dispose();

      expect(requests, hasLength(2));
      expect(requests.first.url.queryParameters.containsKey('cursor'), isFalse);
      expect(requests.last.url.queryParameters['cursor'], '100-0');
      expect(
        delivered.where((event) => event['type'] == 'Reconnected'),
        hasLength(1),
      );
      expect(cursorStore.values.values.single, '101-0');
    });
  });
}

final class _MemoryLongPollCursorStore implements LongPollCursorStore {
  final Map<String, String> values = <String, String>{};

  @override
  Future<String?> read(String partition) async => values[partition];

  @override
  Future<void> write(String partition, String cursor) async {
    values[partition] = cursor;
  }
}

class _TokenProvider implements CloudAuthTokenProvider {
  const _TokenProvider(this.token);

  final String? token;

  @override
  Future<String?> getAccessToken() async => token;
}
