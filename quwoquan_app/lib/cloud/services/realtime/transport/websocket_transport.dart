import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:web_socket_channel/web_socket_channel.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/generated/realtime/realtime_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/services/realtime/realtime_config.dart';

/// Callback for incoming realtime events from WebSocket.
typedef RealtimeEventCallback = void Function(Map<String, dynamic> event);

/// WebSocket transport for active (foreground chat) state.
/// Handles connection, heartbeat, auth, and raw event dispatch.
class WebSocketTransport {
  WebSocketTransport({
    required this.config,
    required this.userId,
    required this.onEvent,
    required this.onDisconnect,
  });

  final RealtimeConfig config;
  final String userId;
  final RealtimeEventCallback onEvent;
  final VoidCallback onDisconnect;

  WebSocketChannel? _channel;
  Timer? _heartbeatTimer;
  bool _disposed = false;
  final _connected = ValueNotifier(false);
  ValueListenable<bool> get isConnected => _connected;

  Future<void> connect({List<String> topics = const []}) async {
    if (_disposed) return;
    try {
      final topicParam = topics.isNotEmpty ? '&topics=${topics.join(",")}' : '';
      final uri = Uri.parse('${config.wsUrl}?userId=$userId$topicParam');
      _channel = WebSocketChannel.connect(uri);

      _channel!.stream.listen(
        _onMessage,
        onError: (_) => _handleDisconnect(),
        onDone: _handleDisconnect,
      );

      _connected.value = true;

      final headers = CloudRequestHeaders.forPage(
        RealtimeRequestPageIds.webSocketUpgrade,
      );
      _send({'type': 'auth', 'userId': userId, ...headers});

      _startHeartbeat();
    } catch (e) {
      debugPrint('WebSocketTransport: connect failed: $e');
      _connected.value = false;
      onDisconnect();
    }
  }

  void subscribeTopic(String topic) {
    _send({'type': 'subscribe', 'topic': topic});
  }

  void unsubscribeTopic(String topic) {
    _send({'type': 'unsubscribe', 'topic': topic});
  }

  void _onMessage(dynamic data) {
    try {
      final json = jsonDecode(data as String) as Map<String, dynamic>;
      final type = json['type'] as String? ?? '';
      if (type == 'pong') return;
      onEvent(json);
    } catch (e) {
      debugPrint('WebSocketTransport: parse error: $e');
    }
  }

  void _handleDisconnect() {
    _connected.value = false;
    _stopHeartbeat();
    if (!_disposed) onDisconnect();
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
    } catch (_) {}
  }

  Future<void> disconnect() async {
    _stopHeartbeat();
    await _channel?.sink.close();
    _channel = null;
    _connected.value = false;
  }

  void dispose() {
    _disposed = true;
    disconnect();
    _connected.dispose();
  }
}
