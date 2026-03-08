import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:web_socket_channel/web_socket_channel.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';

class RtcSignalEvent {
  final String type;
  final String callId;
  final String? actorId;
  final Map<String, dynamic> payload;

  const RtcSignalEvent({
    required this.type,
    required this.callId,
    this.actorId,
    this.payload = const {},
  });

  factory RtcSignalEvent.fromJson(Map<String, dynamic> json) {
    return RtcSignalEvent(
      type: json['type'] as String? ?? '',
      callId: json['callId'] as String? ?? '',
      actorId: json['actorId'] as String?,
      payload: json['payload'] as Map<String, dynamic>? ?? {},
    );
  }
}

class RtcSignalingClient {
  WebSocketChannel? _channel;
  Timer? _heartbeatTimer;
  Timer? _reconnectTimer;
  int _reconnectAttempt = 0;
  static const _maxReconnectAttempt = 10;
  static const _heartbeatInterval = Duration(seconds: 15);

  bool _disposed = false;
  String? _userId;

  final _events = StreamController<RtcSignalEvent>.broadcast();
  Stream<RtcSignalEvent> get events => _events.stream;

  final _connectionState = ValueNotifier(false);
  ValueListenable<bool> get isConnected => _connectionState;

  Stream<RtcSignalEvent> get incomingCalls =>
      events.where((e) => e.type == 'call.ringing');

  Stream<RtcSignalEvent> get callEnded =>
      events.where((e) => e.type == 'call.ended');

  Stream<RtcSignalEvent> get callAnswered =>
      events.where((e) => e.type == 'call.answered');

  Future<void> connect(String userId) async {
    _userId = userId;
    _disposed = false;
    await _doConnect();
  }

  Future<void> _doConnect() async {
    if (_disposed) return;

    try {
      final wsUrl = CloudRuntimeConfig.gatewayBaseUrl
          .replaceFirst('https://', 'wss://')
          .replaceFirst('http://', 'ws://');
      final headers = CloudRequestHeaders.forPage('rtc.signal');

      final uri = Uri.parse('$wsUrl/v1/rtc/signal?userId=$_userId');
      _channel = WebSocketChannel.connect(uri, protocols: null);

      _channel!.stream.listen(
        _onMessage,
        onError: _onError,
        onDone: _onDone,
      );

      _connectionState.value = true;
      _reconnectAttempt = 0;
      _startHeartbeat();

      // Authenticate after connection
      _send({'type': 'auth', 'userId': _userId, ...headers});
    } catch (e) {
      _connectionState.value = false;
      _scheduleReconnect();
    }
  }

  void _onMessage(dynamic data) {
    try {
      final json = jsonDecode(data as String) as Map<String, dynamic>;
      final type = json['type'] as String? ?? '';

      if (type == 'pong') return;

      _events.add(RtcSignalEvent.fromJson(json));
    } catch (e) {
      debugPrint('RtcSignaling: failed to parse message: $e');
    }
  }

  void _onError(Object error) {
    debugPrint('RtcSignaling: connection error: $error');
    _connectionState.value = false;
    _scheduleReconnect();
  }

  void _onDone() {
    _connectionState.value = false;
    _stopHeartbeat();
    if (!_disposed) _scheduleReconnect();
  }

  void _startHeartbeat() {
    _stopHeartbeat();
    _heartbeatTimer = Timer.periodic(_heartbeatInterval, (_) {
      _send({'type': 'ping'});
    });
  }

  void _stopHeartbeat() {
    _heartbeatTimer?.cancel();
    _heartbeatTimer = null;
  }

  void _scheduleReconnect() {
    if (_disposed || _reconnectAttempt >= _maxReconnectAttempt) return;

    _reconnectTimer?.cancel();
    final delay = Duration(
      milliseconds: 1000 * (1 << _reconnectAttempt).clamp(1, 30),
    );
    _reconnectAttempt++;

    _reconnectTimer = Timer(delay, () {
      if (!_disposed) _doConnect();
    });
  }

  void _send(Map<String, dynamic> message) {
    try {
      _channel?.sink.add(jsonEncode(message));
    } catch (_) {}
  }

  Future<void> disconnect() async {
    _disposed = true;
    _stopHeartbeat();
    _reconnectTimer?.cancel();
    _reconnectTimer = null;
    await _channel?.sink.close();
    _channel = null;
    _connectionState.value = false;
  }

  void dispose() {
    disconnect();
    _events.close();
    _connectionState.dispose();
  }
}
