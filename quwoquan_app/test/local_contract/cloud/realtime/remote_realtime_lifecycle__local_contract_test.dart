import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/feed_realtime_patch.g.dart';
import 'package:quwoquan_app/cloud/services/realtime/remote_realtime_connection_delegate.dart';
import 'package:quwoquan_app/cloud/services/realtime/realtime_config.dart';
import 'package:quwoquan_app/cloud/services/realtime/realtime_connection_delegate.dart';
import 'package:quwoquan_app/cloud/services/realtime/transport/longpoll_transport.dart';
import 'package:quwoquan_app/cloud/services/realtime/transport/websocket_transport.dart';

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

class _TokenProvider implements CloudAuthTokenProvider {
  const _TokenProvider();

  @override
  Future<String?> getAccessToken() async => 'jwt-token';
}
