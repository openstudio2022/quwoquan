import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:web_socket_channel/web_socket_channel.dart';
import 'package:quwoquan_app/cloud/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/cloud/runtime/auth/realtime_connection_credential.dart';
import 'package:quwoquan_app/cloud/services/realtime/realtime_config.dart';

/// Callback for incoming realtime events from WebSocket.
typedef RealtimeEventCallback = void Function(Map<String, dynamic> event);

/// WebSocket transport for active (foreground chat) state.
/// Handles connection, heartbeat, auth, and raw event dispatch.
/// 鉴权：先经 IssueConnectionTicket 换取一次性 ticket，升级 query 只带 ticket。
class WebSocketTransport {
  WebSocketTransport({
    required this.config,
    required this.authTokenProvider,
    required this.onEvent,
    required this.onDisconnect,
    http.Client? ticketClient,
  }) : _ticketClient = ticketClient ?? http.Client(),
       _ownsTicketClient = ticketClient == null;

  final RealtimeConfig config;
  final CloudAuthTokenProvider authTokenProvider;
  final RealtimeEventCallback onEvent;
  final VoidCallback onDisconnect;
  final http.Client _ticketClient;
  final bool _ownsTicketClient;

  WebSocketChannel? _channel;
  Timer? _heartbeatTimer;
  Completer<void>? _authAck;
  bool _disposed = false;
  bool _authenticated = false;
  final _connected = ValueNotifier(false);
  ValueListenable<bool> get isConnected => _connected;

  Future<void> connect({List<String> topics = const []}) async {
    if (_disposed) return;
    WebSocketChannel? pendingChannel;
    try {
      final credential = await RealtimeConnectionCredential.resolveWebSocket(
        authTokenProvider,
        gatewayBaseUrl: config.gatewayBaseUrl,
        client: _ticketClient,
      );
      if (credential == null) {
        _handleDisconnect();
        return;
      }
      final uri = credential.authorizeWebSocket(Uri.parse(config.wsUrl));
      pendingChannel = WebSocketChannel.connect(uri);
      await pendingChannel.ready;
      if (_disposed) {
        await pendingChannel.sink.close();
        return;
      }
      _channel = pendingChannel;
      _authAck = Completer<void>();

      _channel!.stream.listen(
        _onMessage,
        onError: (_) {
          _completeAuthFailure();
          _handleDisconnect();
        },
        onDone: _handleDisconnect,
      );

      await _authAck!.future.timeout(
        Duration(seconds: config.authAckTimeoutSec),
      );
      if (_disposed || !_authenticated) {
        await pendingChannel.sink.close();
        return;
      }
      _connected.value = true;
      for (final topic in topics) {
        subscribeTopic(topic);
      }
      _startHeartbeat();
    } catch (_) {
      try {
        await pendingChannel?.sink.close();
      } catch (_) {
        /* best-effort: 连接失败后清理半开的 channel，close 二次报错无副作用可忽略 */
      }
      _connected.value = false;
      onDisconnect();
    }
  }

  void subscribeTopic(String topic) {
    if (!_authenticated || topic.trim().isEmpty) return;
    _send({'type': 'subscribe', 'topic': topic});
  }

  void unsubscribeTopic(String topic) {
    if (!_authenticated || topic.trim().isEmpty) return;
    _send({'type': 'unsubscribe', 'topic': topic});
  }

  void _onMessage(dynamic data) {
    try {
      final json = jsonDecode(data as String) as Map<String, dynamic>;
      final type = json['type'] as String? ?? '';
      if (type == 'auth_ack') {
        if (json['authenticated'] == true) {
          _authenticated = true;
          if (!(_authAck?.isCompleted ?? true)) {
            _authAck!.complete();
          }
        } else {
          _completeAuthFailure();
          _handleDisconnect();
        }
        return;
      }
      if (!_authenticated) return;
      if (type == 'pong') return;
      onEvent(json);
    } catch (_) {
      if (kDebugMode) {
        debugPrint('WebSocketTransport: dropped malformed frame');
      }
    }
  }

  void _handleDisconnect() {
    _completeAuthFailure();
    _authenticated = false;
    _connected.value = false;
    _stopHeartbeat();
    if (!_disposed) onDisconnect();
  }

  void _completeAuthFailure() {
    final authAck = _authAck;
    if (authAck != null && !authAck.isCompleted) {
      authAck.complete();
    }
  }

  void _startHeartbeat() {
    _stopHeartbeat();
    _heartbeatTimer = Timer.periodic(
      Duration(seconds: config.heartbeatIntervalSec),
      (_) => _send({'type': 'ping'}),
    );
  }

  void _stopHeartbeat() {
    _heartbeatTimer?.cancel();
    _heartbeatTimer = null;
  }

  void _send(Map<String, dynamic> message) {
    try {
      _channel?.sink.add(jsonEncode(message));
    } catch (_) {
      /* best-effort: 连接已断开时发送会抛错，心跳/订阅丢帧由重连与补偿机制恢复 */
    }
  }

  Future<void> disconnect() async {
    _stopHeartbeat();
    await _channel?.sink.close();
    _channel = null;
    _authAck = null;
    _authenticated = false;
    _connected.value = false;
  }

  void dispose() {
    _disposed = true;
    disconnect();
    _connected.dispose();
    if (_ownsTicketClient) {
      _ticketClient.close();
    }
  }
}
