import 'dart:async';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:quwoquan_app/cloud/runtime/generated/realtime/realtime_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/realtime/realtime_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/services/realtime/realtime_config.dart';
import 'package:quwoquan_app/cloud/services/realtime/transport/longpoll_transport.dart';

void main() {
  group('Realtime transport contract', () {
    test('fromGateway derives websocket url from generated metadata', () {
      final config = RealtimeConfig.fromGateway();

      expect(config.wsUrl, endsWith(RealtimeApiMetadata.webSocketUpgradePath));
      expect(config.wsUrl.startsWith('ws://') || config.wsUrl.startsWith('wss://'), isTrue);
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
        return http.Response(jsonEncode({'events': []}), 200, headers: {'content-type': 'application/json'});
      });

      transport = LongPollTransport(
        config: const RealtimeConfig(wsUrl: 'ws://127.0.0.1:18080/v1/realtime/ws', longPollHoldSec: 1),
        userId: 'user-1',
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
      expect(requests.first.headers['X-Client-Page-Id'], RealtimeRequestPageIds.longPoll);
    });

    test('long poll tolerates transient failures and eventually delivers events', () async {
      late LongPollTransport transport;
      final delivered = <Map<String, dynamic>>[];
      final completed = Completer<void>();
      var attempts = 0;

      final client = MockClient((request) async {
        attempts++;
        if (attempts < 3) {
          throw http.ClientException('temporary network failure', request.url);
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
        config: const RealtimeConfig(wsUrl: 'ws://127.0.0.1:18080/v1/realtime/ws', longPollHoldSec: 1),
        userId: 'user-1',
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
    });
  });
}
