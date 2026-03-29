import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/legacy.dart';
import 'package:quwoquan_app/cloud/services/realtime/realtime_config.dart';
import 'package:quwoquan_app/cloud/services/realtime/realtime_message_handler.dart';
import 'package:quwoquan_app/cloud/services/realtime/transport/longpoll_transport.dart';
import 'package:quwoquan_app/cloud/services/realtime/transport/websocket_transport.dart';

/// Transport-level connection state.
enum TransportState {
  /// App is foreground but no active chat → long-polling for inbox updates.
  idle,

  /// User is viewing a chat detail → WebSocket for real-time messaging.
  active,

  /// App is in background → no connection (relies on FCM/APNs).
  disconnected,
}

/// Manages the lifecycle of the realtime transport:
///   disconnected ←→ idle ←→ active
///
/// State transitions:
///   - [onAppForeground] → idle (starts long-polling + gap fill)
///   - [onEnterChatDetail] → active (opens WebSocket, subscribes conversation topic)
///   - [onLeaveChatDetail] → idle (after ws_idle_timeout, closes WS → long-poll)
///   - [onAppBackground] → disconnected (closes everything)
class RealtimeConnectionManager extends StateNotifier<TransportState> {
  RealtimeConnectionManager({
    required RealtimeConfig config,
    required String userId,
    required RealtimeMessageHandler messageHandler,
  })  : _config = config,
        _userId = userId,
        _handler = messageHandler,
        super(TransportState.disconnected);

  final RealtimeConfig _config;
  final String _userId;
  final RealtimeMessageHandler _handler;

  WebSocketTransport? _ws;
  LongPollTransport? _longPoll;
  Timer? _idleTimer;
  int _reconnectAttempt = 0;
  Timer? _reconnectTimer;
  String? _activeConversationId;

  // ── Public API ─────────────────────────────────────────────

  void onAppForeground() {
    if (state == TransportState.disconnected) {
      _transitionTo(TransportState.idle);
    }
  }

  void onAppBackground() {
    _transitionTo(TransportState.disconnected);
  }

  void onEnterChatDetail(String conversationId) {
    _activeConversationId = conversationId;
    _cancelIdleTimer();
    _transitionTo(TransportState.active);
  }

  void onLeaveChatDetail() {
    _activeConversationId = null;
    _startIdleTimer();
  }

  // ── State transitions ─────────────────────────────────────

  void _transitionTo(TransportState target) {
    if (state == target) return;

    switch (target) {
      case TransportState.disconnected:
        _teardownAll();
        state = TransportState.disconnected;

      case TransportState.idle:
        _teardownWebSocket();
        _startLongPoll();
        state = TransportState.idle;

      case TransportState.active:
        _teardownLongPoll();
        _connectWebSocket();
        state = TransportState.active;
    }
  }

  // ── WebSocket ─────────────────────────────────────────────

  Future<void> _connectWebSocket() async {
    _teardownWebSocket();
    _reconnectAttempt = 0;

    final topics = <String>['inbox'];
    if (_activeConversationId != null) {
      topics.add('conversation/$_activeConversationId');
    }

    _ws = WebSocketTransport(
      config: _config,
      userId: _userId,
      onEvent: _onRealtimeEvent,
      onDisconnect: _onWebSocketDisconnect,
    );
    await _ws!.connect(topics: topics);
  }

  void _onWebSocketDisconnect() {
    if (state != TransportState.active) return;
    _scheduleReconnect();
  }

  void _scheduleReconnect() {
    if (_reconnectAttempt >= _config.maxReconnectAttempts) {
      debugPrint('RealtimeConnectionManager: max reconnect attempts, falling back to long-poll');
      _transitionTo(TransportState.idle);
      return;
    }

    _reconnectTimer?.cancel();
    final delay = Duration(
      milliseconds: (_config.reconnectBaseDelayMs * (1 << _reconnectAttempt))
          .clamp(0, _config.reconnectMaxDelayMs),
    );
    _reconnectAttempt++;

    _reconnectTimer = Timer(delay, () {
      if (state == TransportState.active) _connectWebSocket();
    });
  }

  void _teardownWebSocket() {
    _reconnectTimer?.cancel();
    _reconnectTimer = null;
    _ws?.dispose();
    _ws = null;
  }

  // ── Long-polling ──────────────────────────────────────────

  void _startLongPoll() {
    _teardownLongPoll();
    _longPoll = LongPollTransport(
      config: _config,
      userId: _userId,
      onEvents: _onLongPollEvents,
    );
    _longPoll!.start();
  }

  void _onLongPollEvents(List<Map<String, dynamic>> events) {
    for (final event in events) {
      _onRealtimeEvent(event);
    }
  }

  void _teardownLongPoll() {
    _longPoll?.dispose();
    _longPoll = null;
  }

  // ── Event dispatch ────────────────────────────────────────

  void _onRealtimeEvent(Map<String, dynamic> event) {
    _handler.handle(event);
  }

  // ── Idle timer ────────────────────────────────────────────

  void _startIdleTimer() {
    _cancelIdleTimer();
    _idleTimer = Timer(
      Duration(seconds: _config.wsIdleTimeoutSec),
      () {
        if (state == TransportState.active) {
          _transitionTo(TransportState.idle);
        }
      },
    );
  }

  void _cancelIdleTimer() {
    _idleTimer?.cancel();
    _idleTimer = null;
  }

  // ── Cleanup ───────────────────────────────────────────────

  void _teardownAll() {
    _cancelIdleTimer();
    _teardownWebSocket();
    _teardownLongPoll();
  }

  @override
  void dispose() {
    _teardownAll();
    super.dispose();
  }
}

/// Riverpod provider for [RealtimeConnectionManager].
/// Requires userId to be set before use.
final realtimeConnectionManagerProvider =
    StateNotifierProvider<RealtimeConnectionManager, TransportState>((ref) {
  final config = RealtimeConfig.fromGateway();
  final handler = RealtimeMessageHandler(ref.read);
  return RealtimeConnectionManager(
    config: config,
    userId: 'current_user',
    messageHandler: handler,
  );
});
