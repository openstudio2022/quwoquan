// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/streaming-feed-performance/spec.md#gwt-004
// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/streaming-feed-performance/spec.md#gwt-005
import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_app/realtime/realtime/connection/adapters/remote_realtime_connection_delegate.dart';
import 'package:quwoquan_app/realtime/realtime/connection/adapters/realtime_config.dart';
import 'package:quwoquan_app/realtime/realtime/connection/domain/realtime_connection_delegate.dart';
import 'package:quwoquan_app/realtime/realtime/connection/adapters/longpoll_transport.dart';
import 'package:quwoquan_app/realtime/realtime/connection/adapters/websocket_transport.dart';

void main() {
  test('remote foreground enters idle and starts long poll', () {
    final log = <String>[];
    final delegate = RemoteRealtimeConnectionDelegate(
      read: _unsupportedRead,
      currentUserIdResolver: () => 'user-42',
      authTokenProvider: const _TokenProvider(),
      config: const RealtimeConfig(
        wsUrl: 'ws://127.0.0.1:18080/realtime/ws',
        gatewayBaseUrl: 'http://127.0.0.1:17000',
        longPollHoldSec: 1,
      ),
      longPollFactory:
          ({required config, required authTokenProvider, required onEvents}) {
            return _RecordingLongPollTransport(
              config: config,
              authTokenProvider: authTokenProvider,
              onEvents: onEvents,
              log: log,
            );
          },
      webSocketFactory:
          ({
            required config,
            required authTokenProvider,
            required onEvent,
            required onDisconnect,
          }) {
            return _RecordingWebSocketTransport(
              config: config,
              authTokenProvider: authTokenProvider,
              onEvent: onEvent,
              onDisconnect: onDisconnect,
              log: log,
            );
          },
    );

    delegate.onAppForeground();

    expect(delegate.state, TransportState.idle);
    expect(log, ['longpoll:start']);
  });

  test(
    'transport lifecycle records catalog-compatible connect result',
    () async {
      final telemetry = <Map<String, Object?>>[];
      final delegate = RemoteRealtimeConnectionDelegate(
        read: _unsupportedRead,
        currentUserIdResolver: () => 'user-42',
        authTokenProvider: const _TokenProvider(),
        config: const RealtimeConfig(
          wsUrl: 'ws://127.0.0.1:18080/realtime/ws',
          gatewayBaseUrl: 'http://127.0.0.1:17000',
          longPollHoldSec: 1,
        ),
        telemetryRecorder:
            ({
              required transport,
              required result,
              required durationMs,
              failReasonCode,
            }) async {
              telemetry.add(<String, Object?>{
                'transport': transport,
                'result': result,
                'durationMs': durationMs,
                'failReasonCode': failReasonCode,
              });
            },
        longPollFactory:
            ({
              required config,
              required authTokenProvider,
              required onEvents,
            }) => _RecordingLongPollTransport(
              config: config,
              authTokenProvider: authTokenProvider,
              onEvents: onEvents,
              log: <String>[],
            ),
      );

      delegate.onAppForeground();
      await Future<void>.delayed(Duration.zero);

      expect(telemetry, hasLength(1));
      expect(telemetry.single['transport'], 'long_poll');
      expect(telemetry.single['result'], 'started');
    },
  );

  test('remote active switches from long poll to websocket', () async {
    final log = <String>[];
    final delegate = RemoteRealtimeConnectionDelegate(
      read: _unsupportedRead,
      currentUserIdResolver: () => 'user-42',
      authTokenProvider: const _TokenProvider(),
      config: const RealtimeConfig(
        wsUrl: 'ws://127.0.0.1:18080/realtime/ws',
        gatewayBaseUrl: 'http://127.0.0.1:17000',
        longPollHoldSec: 1,
      ),
      longPollFactory:
          ({required config, required authTokenProvider, required onEvents}) {
            return _RecordingLongPollTransport(
              config: config,
              authTokenProvider: authTokenProvider,
              onEvents: onEvents,
              log: log,
            );
          },
      webSocketFactory:
          ({
            required config,
            required authTokenProvider,
            required onEvent,
            required onDisconnect,
          }) {
            return _RecordingWebSocketTransport(
              config: config,
              authTokenProvider: authTokenProvider,
              onEvent: onEvent,
              onDisconnect: onDisconnect,
              log: log,
            );
          },
    );

    delegate.onAppForeground();
    delegate.onEnterConversation('conv_001');
    await Future<void>.delayed(Duration.zero);

    expect(delegate.state, TransportState.active);
    expect(log, [
      'longpoll:start',
      'longpoll:dispose',
      'ws:connect:inbox,conversation/conv_001,'
          '${feedRealtimePatchChannelFor('user-42')}',
    ]);
  });

  test('remote background tears down active transports', () async {
    final log = <String>[];
    final delegate = RemoteRealtimeConnectionDelegate(
      read: _unsupportedRead,
      currentUserIdResolver: () => 'user-42',
      authTokenProvider: const _TokenProvider(),
      config: const RealtimeConfig(
        wsUrl: 'ws://127.0.0.1:18080/realtime/ws',
        gatewayBaseUrl: 'http://127.0.0.1:17000',
        longPollHoldSec: 1,
      ),
      longPollFactory:
          ({required config, required authTokenProvider, required onEvents}) {
            return _RecordingLongPollTransport(
              config: config,
              authTokenProvider: authTokenProvider,
              onEvents: onEvents,
              log: log,
            );
          },
      webSocketFactory:
          ({
            required config,
            required authTokenProvider,
            required onEvent,
            required onDisconnect,
          }) {
            return _RecordingWebSocketTransport(
              config: config,
              authTokenProvider: authTokenProvider,
              onEvent: onEvent,
              onDisconnect: onDisconnect,
              log: log,
            );
          },
    );

    delegate.onAppForeground();
    delegate.onEnterConversation('conv_001');
    await Future<void>.delayed(Duration.zero);

    delegate.onAppBackground();

    expect(delegate.state, TransportState.disconnected);
    expect(log, [
      'longpoll:start',
      'longpoll:dispose',
      'ws:connect:inbox,conversation/conv_001,'
          '${feedRealtimePatchChannelFor('user-42')}',
      'ws:dispose',
    ]);
  });

  test(
    'foreground restores websocket when a conversation is still active',
    () async {
      final log = <String>[];
      final delegate = RemoteRealtimeConnectionDelegate(
        read: _unsupportedRead,
        currentUserIdResolver: () => 'user-42',
        authTokenProvider: const _TokenProvider(),
        config: const RealtimeConfig(
          wsUrl: 'ws://127.0.0.1:18080/realtime/ws',
          gatewayBaseUrl: 'http://127.0.0.1:17000',
          longPollHoldSec: 1,
        ),
        longPollFactory:
            ({
              required config,
              required authTokenProvider,
              required onEvents,
            }) => _RecordingLongPollTransport(
              config: config,
              authTokenProvider: authTokenProvider,
              onEvents: onEvents,
              log: log,
            ),
        webSocketFactory:
            ({
              required config,
              required authTokenProvider,
              required onEvent,
              required onDisconnect,
            }) => _RecordingWebSocketTransport(
              config: config,
              authTokenProvider: authTokenProvider,
              onEvent: onEvent,
              onDisconnect: onDisconnect,
              log: log,
            ),
      );

      delegate.onEnterConversation('conv_001');
      await Future<void>.delayed(Duration.zero);
      delegate.onAppBackground();
      delegate.onAppForeground();
      await Future<void>.delayed(Duration.zero);

      expect(delegate.state, TransportState.active);
      expect(
        log.where((entry) => entry.startsWith('ws:connect:')),
        hasLength(2),
      );
      expect(log.where((entry) => entry == 'longpoll:start'), isEmpty);
    },
  );

  test(
    'failed reconnects exhaust the budget and fall back to long poll',
    () async {
      final log = <String>[];
      final delegate = RemoteRealtimeConnectionDelegate(
        read: _unsupportedRead,
        currentUserIdResolver: () => 'user-42',
        authTokenProvider: const _TokenProvider(),
        config: const RealtimeConfig(
          wsUrl: 'ws://127.0.0.1:18080/realtime/ws',
          gatewayBaseUrl: 'http://127.0.0.1:17000',
          longPollHoldSec: 1,
          maxReconnectAttempts: 2,
          reconnectBaseDelayMs: 1,
          reconnectMaxDelayMs: 4,
        ),
        reconnectDelayResolver: ({required attempt, required config}) =>
            Duration.zero,
        longPollFactory:
            ({
              required config,
              required authTokenProvider,
              required onEvents,
            }) => _RecordingLongPollTransport(
              config: config,
              authTokenProvider: authTokenProvider,
              onEvents: onEvents,
              log: log,
            ),
        webSocketFactory:
            ({
              required config,
              required authTokenProvider,
              required onEvent,
              required onDisconnect,
            }) => _FailingWebSocketTransport(
              config: config,
              authTokenProvider: authTokenProvider,
              onEvent: onEvent,
              onDisconnect: onDisconnect,
              log: log,
            ),
      );

      delegate.onEnterConversation('conv_001');
      for (var index = 0; index < 8; index += 1) {
        await Future<void>.delayed(Duration.zero);
      }

      expect(delegate.state, TransportState.idle);
      expect(
        log.where((entry) => entry.startsWith('ws:connect:')),
        hasLength(3),
      );
      expect(log.last, 'longpoll:start');
    },
  );

  test(
    'guest (empty resolver) does not subscribe to feed patch channel',
    () async {
      final log = <String>[];
      final delegate = RemoteRealtimeConnectionDelegate(
        read: _unsupportedRead,
        currentUserIdResolver: () => '',
        authTokenProvider: const _TokenProvider(),
        config: const RealtimeConfig(
          wsUrl: 'ws://127.0.0.1:18080/realtime/ws',
          gatewayBaseUrl: 'http://127.0.0.1:17000',
          longPollHoldSec: 1,
        ),
        longPollFactory:
            ({required config, required authTokenProvider, required onEvents}) {
              return _RecordingLongPollTransport(
                config: config,
                authTokenProvider: authTokenProvider,
                onEvents: onEvents,
                log: log,
              );
            },
        webSocketFactory:
            ({
              required config,
              required authTokenProvider,
              required onEvent,
              required onDisconnect,
            }) {
              return _RecordingWebSocketTransport(
                config: config,
                authTokenProvider: authTokenProvider,
                onEvent: onEvent,
                onDisconnect: onDisconnect,
                log: log,
              );
            },
      );

      delegate.onAppForeground();
      delegate.onEnterConversation('conv_001');
      await Future<void>.delayed(Duration.zero);

      // 游客 resolver 返回空 → WS 仅订阅会话相关 topic，无 feed patch 通道。
      expect(log.any((entry) => entry.contains('rt:rec:feed:user:')), isFalse);
      expect(
        log.any(
          (entry) =>
              entry.startsWith('ws:connect:') &&
              entry.endsWith('inbox,conversation/conv_001'),
        ),
        isTrue,
      );
    },
  );
}

Never _unsupportedRead<Never>(Object _) {
  throw UnimplementedError('remote lifecycle test should not read providers');
}

class _RecordingLongPollTransport extends LongPollTransport {
  _RecordingLongPollTransport({
    required super.config,
    required super.authTokenProvider,
    required super.onEvents,
    required this.log,
  });

  final List<String> log;

  @override
  void start() {
    log.add('longpoll:start');
  }

  @override
  void stop() {
    log.add('longpoll:stop');
  }

  @override
  void dispose() {
    log.add('longpoll:dispose');
  }
}

class _RecordingWebSocketTransport extends WebSocketTransport {
  _RecordingWebSocketTransport({
    required super.config,
    required super.authTokenProvider,
    required super.onEvent,
    required super.onDisconnect,
    required this.log,
  });

  final List<String> log;

  @override
  Future<void> connect({List<String> topics = const []}) async {
    log.add('ws:connect:${topics.join(",")}');
  }

  @override
  void dispose() {
    log.add('ws:dispose');
  }
}

class _FailingWebSocketTransport extends _RecordingWebSocketTransport {
  _FailingWebSocketTransport({
    required super.config,
    required super.authTokenProvider,
    required super.onEvent,
    required super.onDisconnect,
    required super.log,
  });

  final ValueNotifier<bool> _connected = ValueNotifier<bool>(false);

  @override
  ValueListenable<bool> get isConnected => _connected;

  @override
  Future<void> connect({List<String> topics = const []}) async {
    await super.connect(topics: topics);
    scheduleMicrotask(onDisconnect);
  }

  @override
  void dispose() {
    super.dispose();
    _connected.dispose();
  }
}

class _TokenProvider implements CloudAuthTokenProvider {
  const _TokenProvider();

  @override
  Future<String?> getAccessToken() async => 'jwt-token';
}
