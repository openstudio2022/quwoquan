import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:web_socket_channel/web_socket_channel.dart';
import 'package:quwoquan_app/cloud/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/cloud/runtime/auth/realtime_connection_credential.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/generated/realtime/realtime_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/rtc/rtc_signal_payloads.g.dart';
import 'package:quwoquan_app/cloud/rtc/rtc_signaling_wire.dart';
import 'package:quwoquan_app/cloud/rtc/rtc_signaling_wire_frame.dart';

class RtcSignalEvent {
  final String type;
  final String callId;
  final String? actorId;

  /// 已按 `events.yaml` / [parseRtcWsPayload] 解析；未知 `type` 为 [RtcWsUnknownPayload]。
  final RtcWsPayload payload;

  const RtcSignalEvent({
    required this.type,
    required this.callId,
    this.actorId,
    required this.payload,
  });

  factory RtcSignalEvent.fromJson(Map<String, dynamic> json) {
    final p = json['payload'];
    final payloadMap = p is Map<String, dynamic>
        ? p
        : p is Map
        ? Map<String, dynamic>.from(p)
        : <String, dynamic>{};
    final type = json['type'] as String? ?? '';
    return RtcSignalEvent(
      type: type,
      callId: json['callId'] as String? ?? '',
      actorId: json['actorId'] as String?,
      payload: parseRtcWsPayload(wireType: type, payload: payloadMap),
    );
  }
}

class RtcSignalingClient {
  RtcSignalingClient({required this.authTokenProvider});

  final CloudAuthTokenProvider authTokenProvider;
  WebSocketChannel? _channel;
  Timer? _heartbeatTimer;
  Timer? _reconnectTimer;
  Completer<void>? _authAck;
  int _reconnectAttempt = 0;
  static const _maxReconnectAttempt = 10;
  static const _heartbeatInterval = Duration(seconds: 15);
  static const _authAckTimeout = Duration(seconds: 5);

  bool _disposed = false;
  bool _authenticated = false;

  final _events = StreamController<RtcSignalEvent>.broadcast();
  Stream<RtcSignalEvent> get events => _events.stream;

  final _connectionState = ValueNotifier(false);
  ValueListenable<bool> get isConnected => _connectionState;

  Stream<RtcSignalEvent> get incomingCalls =>
      events.where((e) => e.payload is RtcCallRingingWsPayload);

  Stream<RtcSignalEvent> get callEnded =>
      events.where((e) => e.payload is RtcCallEndedWsPayload);

  Stream<RtcSignalEvent> get callAnswered =>
      events.where((e) => e.payload is RtcCallAnsweredWsPayload);

  Future<void> connect() async {
    _disposed = false;
    await _doConnect();
  }

  Future<void> _doConnect() async {
    if (_disposed) return;
    WebSocketChannel? pendingChannel;

    try {
      final credential = await RealtimeConnectionCredential.resolveWebSocket(
        authTokenProvider,
      );
      if (credential == null) {
        _connectionState.value = false;
        return;
      }
      final wsUrl = CloudRuntimeConfig.gatewayBaseUrl
          .replaceFirst('https://', 'wss://')
          .replaceFirst('http://', 'ws://');
      final uri = credential.authorizeWebSocket(
        Uri.parse('$wsUrl${RealtimeApiMetadata.webSocketUpgradePath}'),
      );
      pendingChannel = WebSocketChannel.connect(uri, protocols: null);
      await pendingChannel.ready;
      if (_disposed) {
        await pendingChannel.sink.close();
        return;
      }
      _channel = pendingChannel;
      _authAck = Completer<void>();

      _channel!.stream.listen(
        (data) =>
            _handleInboundFrame(RtcSignalingWireFrame.fromChannelData(data)),
        onError: (Object error) {
          _completeAuthFailure();
          if (kDebugMode) {
            debugPrint('RtcSignaling: connection error');
          }
          _connectionState.value = false;
          _scheduleReconnect();
        },
        onDone: _onDone,
      );

      await _authAck!.future.timeout(_authAckTimeout);
      if (_disposed || !_authenticated) {
        await pendingChannel.sink.close();
        return;
      }
      _connectionState.value = true;
      _reconnectAttempt = 0;
      _startHeartbeat();
    } catch (_) {
      try {
        await pendingChannel?.sink.close();
      } catch (_) {
        /* best-effort: 连接失败后清理半开的 channel，close 二次报错无副作用可忽略 */
      }
      if (kDebugMode) {
        debugPrint('RtcSignaling: connect failed');
      }
      _connectionState.value = false;
      _scheduleReconnect();
    }
  }

  void _handleInboundFrame(RtcSignalingWireFrame frame) {
    try {
      final json = decodeRtcSignalingJsonMessage(frame);
      if (json == null) return;

      final type = json['type'] as String? ?? '';

      if (type == 'auth_ack') {
        if (json['authenticated'] == true) {
          _authenticated = true;
          if (!(_authAck?.isCompleted ?? true)) {
            _authAck!.complete();
          }
        } else {
          _completeAuthFailure();
          _onDone();
        }
        return;
      }
      if (!_authenticated) return;
      if (type == 'pong') return;

      _events.add(RtcSignalEvent.fromJson(json));
    } catch (_) {
      if (kDebugMode) {
        debugPrint('RtcSignaling: dropped malformed frame');
      }
    }
  }

  void _onDone() {
    _completeAuthFailure();
    _authenticated = false;
    _connectionState.value = false;
    _stopHeartbeat();
    if (!_disposed) _scheduleReconnect();
  }

  void _completeAuthFailure() {
    final authAck = _authAck;
    if (authAck != null && !authAck.isCompleted) {
      authAck.complete();
    }
  }

  void _startHeartbeat() {
    _stopHeartbeat();
    _heartbeatTimer = Timer.periodic(_heartbeatInterval, (_) {
      _sendOutbound(const <String, dynamic>{'type': 'ping'});
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

  void _sendOutbound(Map<String, dynamic> message) {
    try {
      _channel?.sink.add(jsonEncode(message));
    } catch (_) {
      /* best-effort: 连接已断开时发送会抛错，丢失的帧由重连与重协商流程恢复 */
    }
  }

  Future<void> disconnect() async {
    _disposed = true;
    _stopHeartbeat();
    _reconnectTimer?.cancel();
    _reconnectTimer = null;
    await _channel?.sink.close();
    _channel = null;
    _authAck = null;
    _authenticated = false;
    _connectionState.value = false;
  }

  void dispose() {
    disconnect();
    _events.close();
    _connectionState.dispose();
  }
}
