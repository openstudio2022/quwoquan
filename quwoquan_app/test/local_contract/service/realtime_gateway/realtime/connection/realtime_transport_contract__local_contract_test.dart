/// spec_ref: specs/feature-tree/chat-conversation/message-reliability-foundation/realtime-push-and-offline-sync/spec.md#gwt-002.t2
library;

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
          activeConversationIdResolver: () => null,
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
          activeConversationIdResolver: () => null,
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
          activeConversationIdResolver: () => null,
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
          activeConversationIdResolver: () => null,
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

    test(
      'five consecutive handler failures enter backoff without tight loop',
      () {
        fakeAsync((clock) {
          var requestCount = 0;
          var handlerFailures = 0;
          late LongPollTransport transport;
          final operations = _RealtimeOperations(
            onLongPoll: ({timeout, cursor}) async {
              requestCount += 1;
              return _longPollResponse(
                events: <realtime.RealtimeEventEnvelope>[
                  _syncHint('failing-event-$requestCount', requestCount),
                ],
                nextCursor: '$requestCount-0',
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
            activeConversationIdResolver: () => null,
            onEvents: (_) {
              handlerFailures += 1;
              if (handlerFailures >= 6) transport.stop();
              throw StateError('downstream recovery failed');
            },
            cursorStore: _MemoryLongPollCursorStore(),
          );

          transport.start();
          clock.flushMicrotasks();

          expect(requestCount, 5, reason: '连续下游失败必须累计，不能每轮重置错误计数');
          expect(handlerFailures, 5);
          expect(clock.pendingTimers, hasLength(1), reason: '第 5 次连续失败后必须进入退避');
          clock.elapse(const Duration(seconds: 4));
          expect(requestCount, 5, reason: '退避窗口内不得继续紧循环请求');

          transport.stop();
          transport.dispose();
        });
      },
    );

    test(
      'stop while cursor store read is pending prevents gateway poll',
      () async {
        final cursorStore = _BlockingReadCursorStore();
        var requestCount = 0;
        final operations = _RealtimeOperations(
          onLongPoll: ({timeout, cursor}) async {
            requestCount += 1;
            return _longPollResponse(nextCursor: '100-0');
          },
        );
        final transport = LongPollTransport(
          config: const RealtimeConfig(
            wsUrl: 'ws://127.0.0.1:18080/realtime/ws',
            longPollHoldSec: 1,
          ),
          authTokenProvider: const _TokenProvider('jwt-token'),
          operations: operations,
          activeConversationIdResolver: () => null,
          onEvents: (_) {},
          cursorStore: cursorStore,
        );

        transport.start();
        await cursorStore.readEntered.future.timeout(
          const Duration(seconds: 2),
        );
        transport.stop();
        cursorStore.releaseRead.complete('99-0');
        await Future<void>.delayed(Duration.zero);
        await Future<void>.delayed(Duration.zero);
        transport.dispose();

        expect(
          requestCount,
          0,
          reason: '旧 generation 的 cursor read 完成后不得再发 gateway 请求',
        );
      },
    );

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
        activeConversationIdResolver: () => 'conv_active',
        onEvents: (events) {
          delivered.addAll(events);
        },
        cursorStore: cursorStore,
      );
      cursorStore.onWrite = (cursor) {
        if (cursor == '101-0') {
          transport.stop();
          if (!completed.isCompleted) completed.complete();
        }
      };

      transport.start();
      await completed.future.timeout(const Duration(seconds: 2));
      transport.dispose();

      expect(cursors, <String?>[null, '100-0']);
      expect(
        delivered.where((event) => event['type'] == 'Reconnected'),
        hasLength(1),
      );
      expect(
        delivered.singleWhere(
          (event) => event['type'] == 'Reconnected',
        )['conversationId'],
        'conv_active',
      );
      expect(cursorStore.values.values.single, '101-0');
    });

    test(
      'long poll preserves cursor when reconnect recovery dispatch fails',
      () async {
        final credential = await RealtimeConnectionCredential.resolveHttp(
          const _TokenProvider('jwt-token'),
        );
        final cursorStore = _MemoryLongPollCursorStore()
          ..values[credential!.cursorPartition] = '99-0';
        final delivered = <Map<String, dynamic>>[];
        final failed = Completer<String>();
        late LongPollTransport transport;
        final operations = _RealtimeOperations(
          onLongPoll: ({timeout, cursor}) async {
            expect(cursor, '99-0');
            return _longPollResponse(
              nextCursor: '100-0',
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
          activeConversationIdResolver: () => 'conv_active',
          onEvents: (events) async {
            delivered.addAll(events);
            await Future<void>.delayed(Duration.zero);
            throw StateError('gap recovery rejected');
          },
          cursorStore: cursorStore,
        );
        transport.onFirstTransportFailure = (reasonCode) {
          transport.stop();
          if (!failed.isCompleted) failed.complete(reasonCode);
        };

        transport.start();
        final failureReason = await failed.future.timeout(
          const Duration(seconds: 2),
        );
        await Future<void>.delayed(Duration.zero);
        transport.dispose();

        expect(failureReason, 'StateError');
        expect(delivered, <Map<String, dynamic>>[
          <String, dynamic>{
            'type': 'Reconnected',
            'conversationId': 'conv_active',
          },
        ]);
        expect(
          cursorStore.values[credential.cursorPartition],
          '99-0',
          reason: '恢复分发失败必须保留已提交游标，供下一次重试继续补洞',
        );
      },
    );

    test('stop during awaited event dispatch prevents cursor commit', () async {
      final cursorStore = _MemoryLongPollCursorStore();
      final callbackEntered = Completer<void>();
      final releaseCallback = Completer<void>();
      final operations = _RealtimeOperations(
        onLongPoll: ({timeout, cursor}) async => _longPollResponse(
          events: <realtime.RealtimeEventEnvelope>[
            _syncHint('event-before-stop', 1),
          ],
          nextCursor: '100-0',
        ),
      );
      final transport = LongPollTransport(
        config: const RealtimeConfig(
          wsUrl: 'ws://127.0.0.1:18080/realtime/ws',
          longPollHoldSec: 1,
        ),
        authTokenProvider: const _TokenProvider('jwt-token'),
        operations: operations,
        activeConversationIdResolver: () => null,
        onEvents: (_) async {
          if (!callbackEntered.isCompleted) callbackEntered.complete();
          await releaseCallback.future;
        },
        cursorStore: cursorStore,
      );

      transport.start();
      await callbackEntered.future.timeout(const Duration(seconds: 2));
      transport.stop();
      releaseCallback.complete();
      await Future<void>.delayed(Duration.zero);
      transport.dispose();

      expect(
        cursorStore.values,
        isEmpty,
        reason: 'stop/dispose 后不得提交仍在 callback 中的旧 generation cursor',
      );
    });
  });
}

final class _MemoryLongPollCursorStore implements LongPollCursorStore {
  final Map<String, String> values = <String, String>{};
  void Function(String cursor)? onWrite;

  @override
  Future<String?> read(String partition) async => values[partition];

  @override
  Future<void> write(String partition, String cursor) async {
    values[partition] = cursor;
    onWrite?.call(cursor);
  }
}

final class _BlockingReadCursorStore implements LongPollCursorStore {
  final Completer<void> readEntered = Completer<void>();
  final Completer<String?> releaseRead = Completer<String?>();

  @override
  Future<String?> read(String partition) {
    if (!readEntered.isCompleted) readEntered.complete();
    return releaseRead.future;
  }

  @override
  Future<void> write(String partition, String cursor) async {}
}

typedef _LongPollHandler = Future<realtime.LongPollResponse> Function({
  int? timeout,
  String? cursor,
});

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
