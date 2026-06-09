import 'package:flutter_test/flutter_test.dart';
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
      config: const RealtimeConfig(
        wsUrl: 'ws://127.0.0.1:18080/v1/realtime/ws',
        gatewayBaseUrl: 'http://127.0.0.1:17000',
        longPollHoldSec: 1,
      ),
      longPollFactory: ({required config, required userId, required onEvents}) {
        return _RecordingLongPollTransport(
          config: config,
          userId: userId,
          onEvents: onEvents,
          log: log,
        );
      },
      webSocketFactory: ({
        required config,
        required userId,
        required onEvent,
        required onDisconnect,
      }) {
        return _RecordingWebSocketTransport(
          config: config,
          userId: userId,
          onEvent: onEvent,
          onDisconnect: onDisconnect,
          log: log,
        );
      },
    );

    delegate.onAppForeground();

    expect(delegate.state, TransportState.idle);
    expect(log, ['longpoll:start:user-42']);
  });

  test('remote active switches from long poll to websocket', () async {
    final log = <String>[];
    final delegate = RemoteRealtimeConnectionDelegate(
      read: _unsupportedRead,
      currentUserIdResolver: () => 'user-42',
      config: const RealtimeConfig(
        wsUrl: 'ws://127.0.0.1:18080/v1/realtime/ws',
        gatewayBaseUrl: 'http://127.0.0.1:17000',
        longPollHoldSec: 1,
      ),
      longPollFactory: ({required config, required userId, required onEvents}) {
        return _RecordingLongPollTransport(
          config: config,
          userId: userId,
          onEvents: onEvents,
          log: log,
        );
      },
      webSocketFactory: ({
        required config,
        required userId,
        required onEvent,
        required onDisconnect,
      }) {
        return _RecordingWebSocketTransport(
          config: config,
          userId: userId,
          onEvent: onEvent,
          onDisconnect: onDisconnect,
          log: log,
        );
      },
    );

    delegate.onAppForeground();
    delegate.onEnterChatDetail('conv_001');
    await Future<void>.delayed(Duration.zero);

    expect(delegate.state, TransportState.active);
    expect(
      log,
      [
        'longpoll:start:user-42',
        'longpoll:dispose:user-42',
        'ws:connect:user-42:inbox,conversation/conv_001',
      ],
    );
  });

  test('remote background tears down active transports', () async {
    final log = <String>[];
    final delegate = RemoteRealtimeConnectionDelegate(
      read: _unsupportedRead,
      currentUserIdResolver: () => 'user-42',
      config: const RealtimeConfig(
        wsUrl: 'ws://127.0.0.1:18080/v1/realtime/ws',
        gatewayBaseUrl: 'http://127.0.0.1:17000',
        longPollHoldSec: 1,
      ),
      longPollFactory: ({required config, required userId, required onEvents}) {
        return _RecordingLongPollTransport(
          config: config,
          userId: userId,
          onEvents: onEvents,
          log: log,
        );
      },
      webSocketFactory: ({
        required config,
        required userId,
        required onEvent,
        required onDisconnect,
      }) {
        return _RecordingWebSocketTransport(
          config: config,
          userId: userId,
          onEvent: onEvent,
          onDisconnect: onDisconnect,
          log: log,
        );
      },
    );

    delegate.onAppForeground();
    delegate.onEnterChatDetail('conv_001');
    await Future<void>.delayed(Duration.zero);

    delegate.onAppBackground();

    expect(delegate.state, TransportState.disconnected);
    expect(
      log,
      [
        'longpoll:start:user-42',
        'longpoll:dispose:user-42',
        'ws:connect:user-42:inbox,conversation/conv_001',
        'ws:dispose:user-42',
      ],
    );
  });
}

Never _unsupportedRead<Never>(Object _) {
  throw UnimplementedError('remote lifecycle test should not read providers');
}

class _RecordingLongPollTransport extends LongPollTransport {
  _RecordingLongPollTransport({
    required super.config,
    required super.userId,
    required super.onEvents,
    required this.log,
  });

  final List<String> log;

  @override
  void start() {
    log.add('longpoll:start:$userId');
  }

  @override
  void stop() {
    log.add('longpoll:stop:$userId');
  }

  @override
  void dispose() {
    log.add('longpoll:dispose:$userId');
  }
}

class _RecordingWebSocketTransport extends WebSocketTransport {
  _RecordingWebSocketTransport({
    required super.config,
    required super.userId,
    required super.onEvent,
    required super.onDisconnect,
    required this.log,
  });

  final List<String> log;

  @override
  Future<void> connect({List<String> topics = const []}) async {
    log.add('ws:connect:$userId:${topics.join(",")}');
  }

  @override
  void dispose() {
    log.add('ws:dispose:$userId');
  }
}
