import 'dart:async';

import 'package:fake_async/fake_async.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/runtime/auth/realtime_connection_credential.dart';
import 'package:quwoquan_app/service/realtime_gateway/realtime/connection/adapters/realtime_config.dart';
import 'package:quwoquan_app/service/realtime_gateway/realtime/connection/application/realtime_connection_operation_gateway.dart';
import 'package:quwoquan_app/service/realtime_gateway/realtime/connection/adapters/longpoll_transport.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show AppCloudOperationIds, appCloudOperationContracts;
import 'package:quwoquan_cloud_contracts/generated/realtime_contracts.dart'
    as realtime;

void main() {
  group('Realtime transport contract', () {
    test('fromRuntime combines topology authority with generated path', () {
      final upgrade =
          appCloudOperationContracts[AppCloudOperationIds
              .realtimeConnectionWebSocketUpgrade]!;
      final config = RealtimeConfig.fromRuntime(
        gatewayBaseUrl: 'https://gateway.example',
        realtimeBaseUrl: 'wss://realtime.example',
      );

      expect(config.wsUrl, 'wss://realtime.example${upgrade.pathTemplate}');
      expect(upgrade.method, 'GET');
      expect(upgrade.requestBodyKind, 'none');
      expect(upgrade.responseBodyKind, 'upgrade');
      expect(
        upgrade.requestQueryBindings.map(
          (binding) => (binding.name, binding.field, binding.required),
        ),
        <(String, String, bool)>[('ticket', 'ticket', true)],
      );
    });

    test('websocket credential 先换一次性 ticket，URL 只携带 ticket', () async {
      var issueCount = 0;

      final credential = await RealtimeConnectionCredential.resolveWebSocket(
        const _TokenProvider('jwt-token'),
        issueTicket: () async {
          issueCount++;
          return 'one-time-ticket';
        },
      );
      final upgrade =
          appCloudOperationContracts[AppCloudOperationIds
              .realtimeConnectionWebSocketUpgrade]!;
      final uri = credential!.authorizeWebSocket(
        Uri.parse('wss://gateway.example${upgrade.pathTemplate}'),
      );

      expect(issueCount, 1);
      expect(uri.queryParameters['ticket'], 'one-time-ticket');
      expect(uri.queryParameters.containsKey('access_token'), isFalse);
      expect(uri.queryParameters.containsKey('userId'), isFalse);
      expect(uri.queryParameters.containsKey('topics'), isFalse);
    });

    test('ticket 签发失败或未登录时失败关闭', () async {
      expect(
        await RealtimeConnectionCredential.resolveWebSocket(
          const _TokenProvider('jwt-token'),
          issueTicket: () async => throw StateError('unauthorized'),
        ),
        isNull,
      );
      expect(
        await RealtimeConnectionCredential.resolveWebSocket(
          const _TokenProvider(null),
          issueTicket: () async => 'must-not-be-used',
        ),
        isNull,
      );
    });

    test('long poll cursor partition 由可信 credential 派生且不泄露 token', () async {
      final credential = await RealtimeConnectionCredential.resolveHttp(
        const _TokenProvider('jwt-token'),
      );

      expect(credential!.cursorPartition, hasLength(64));
      expect(credential.cursorPartition, isNot(contains('jwt-token')));
    });

    test(
      'long poll delegates timeout/cursor to generated operation gateway',
      () async {
        final calls = <({int? timeout, String? cursor})>[];
        late LongPollTransport transport;
        final completed = Completer<void>();

        final operations = _RealtimeOperations(
          onLongPoll: ({timeout, cursor}) async {
            calls.add((timeout: timeout, cursor: cursor));
            if (!completed.isCompleted) completed.complete();
            return _longPollResponse(nextCursor: '0-0');
          },
        );

        transport = LongPollTransport(
          config: const RealtimeConfig(
            wsUrl: 'ws://127.0.0.1:18080/realtime/ws',
            longPollHoldSec: 1,
          ),
          authTokenProvider: const _TokenProvider('jwt-token'),
          operations: operations,
          onEvents: (_) {},
          cursorStore: _MemoryLongPollCursorStore(),
        );

        transport.start();
        await completed.future.timeout(const Duration(seconds: 2));
        transport.stop();
        transport.dispose();

        expect(calls, isNotEmpty);
        expect(calls.first.timeout, 1);
        expect(calls.first.cursor, isNull);
      },
    );

    test(
      'long poll tolerates transient failures and eventually delivers events',
      () async {
        late LongPollTransport transport;
        final delivered = <Map<String, dynamic>>[];
        final completed = Completer<void>();
        var attempts = 0;

        final operations = _RealtimeOperations(
          onLongPoll: ({timeout, cursor}) async {
            attempts++;
            if (attempts < 3) {
              throw StateError('temporary network failure');
            }
            return _longPollResponse(
              events: <realtime.RealtimeEventEnvelope>[
                _syncHint('sync-event-1', 1),
              ],
              nextCursor: '100-0',
            );
          },
        );

        transport = LongPollTransport(
          config: const RealtimeConfig(
            wsUrl: 'ws://127.0.0.1:18080/realtime/ws',
            longPollHoldSec: 1,
          ),
          authTokenProvider: const _TokenProvider('jwt-token'),
          operations: operations,
          onEvents: (events) {
            delivered.addAll(events);
            transport.stop();
            if (!completed.isCompleted) {
              completed.complete();
            }
          },
          cursorStore: _MemoryLongPollCursorStore(),
        );

        transport.start();
        await completed.future.timeout(const Duration(seconds: 2));
        transport.dispose();

        expect(attempts, greaterThanOrEqualTo(3));
        expect(delivered, hasLength(1));
        expect(delivered.single['type'], 'sync_hint');
      },
    );

    test(
      'long poll fails closed before network when access token is absent',
      () async {
        var requestCount = 0;
        final operations = _RealtimeOperations(
          onLongPoll: ({timeout, cursor}) async {
            requestCount++;
            return _longPollResponse(nextCursor: '0-0');
          },
        );
        final transport = LongPollTransport(
          config: const RealtimeConfig(
            wsUrl: 'ws://127.0.0.1:18080/realtime/ws',
            longPollHoldSec: 1,
          ),
          authTokenProvider: const _TokenProvider(null),
          operations: operations,
          onEvents: (_) {},
          cursorStore: _MemoryLongPollCursorStore(),
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
        final operations = _RealtimeOperations(
          onLongPoll: ({timeout, cursor}) async {
            requestCount++;
            throw StateError('offline');
          },
        );
        final transport = LongPollTransport(
          config: const RealtimeConfig(
            wsUrl: 'ws://127.0.0.1:18080/realtime/ws',
            longPollHoldSec: 1,
          ),
          authTokenProvider: const _TokenProvider('jwt-token'),
          operations: operations,
          onEvents: (_) {},
          cursorStore: _MemoryLongPollCursorStore(),
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
      final cursors = <String?>[];
      final delivered = <Map<String, dynamic>>[];
      final completed = Completer<void>();
      var attempts = 0;
      late LongPollTransport transport;
      final operations = _RealtimeOperations(
        onLongPoll: ({timeout, cursor}) async {
          cursors.add(cursor);
          attempts++;
          if (attempts == 1) {
            return _longPollResponse(nextCursor: '100-0');
          }
          return _longPollResponse(
            events: <realtime.RealtimeEventEnvelope>[_syncHint('event-2', 2)],
            nextCursor: '101-0',
            transportResumed: true,
          );
        },
      );
      transport = LongPollTransport(
        config: const RealtimeConfig(
          wsUrl: 'ws://127.0.0.1:18080/realtime/ws',
          longPollHoldSec: 1,
        ),
        authTokenProvider: const _TokenProvider('jwt-token'),
        operations: operations,
        onEvents: (events) {
          delivered.addAll(events);
          if (delivered.any((event) => event['eventId'] == 'event-2')) {
            transport.stop();
            if (!completed.isCompleted) completed.complete();
          }
        },
        cursorStore: cursorStore,
      );

      transport.start();
      await completed.future.timeout(const Duration(seconds: 2));
      transport.dispose();

      expect(cursors, <String?>[null, '100-0']);
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

typedef _LongPollHandler =
    Future<realtime.LongPollResponse> Function({int? timeout, String? cursor});

final class _RealtimeOperations implements RealtimeConnectionOperationGateway {
  const _RealtimeOperations({required this.onLongPoll});

  final _LongPollHandler onLongPoll;

  @override
  Future<realtime.ConnectionTicket> issueConnectionTicket() async =>
      realtime.ConnectionTicket(
        ticket: 'one-time-ticket',
        expiresAt: DateTime.utc(2026, 8, 4, 0, 0, 30),
      );

  @override
  Future<realtime.LongPollResponse> longPoll({int? timeout, String? cursor}) =>
      onLongPoll(timeout: timeout, cursor: cursor);
}

realtime.LongPollResponse _longPollResponse({
  List<realtime.RealtimeEventEnvelope> events =
      const <realtime.RealtimeEventEnvelope>[],
  required String nextCursor,
  bool transportResumed = false,
}) => realtime.LongPollResponse(
  events: events,
  nextCursor: nextCursor,
  transportResumed: transportResumed,
);

realtime.RealtimeEventEnvelope _syncHint(String eventId, int sequence) =>
    realtime.UserSyncHintRealtimeEventEnvelope(
      wireType: 'sync_hint',
      eventId: eventId,
      occurredAt: DateTime.utc(2026, 8, 4, 12, 0, sequence),
      payload: realtime.UserSyncHintEventPayload(
        userId: 'user-1',
        latestSyncSeq: sequence,
      ),
    );

class _TokenProvider implements CloudAuthTokenProvider {
  const _TokenProvider(this.token);

  final String? token;

  @override
  Future<String?> getAccessToken() async => token;
}
