import 'dart:async';
import 'dart:math';

import 'package:flutter/foundation.dart';
import 'package:riverpod/misc.dart' show ProviderListenable;
import 'package:quwoquan_app/cloud/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/feed_realtime_patch.g.dart';
import 'package:quwoquan_app/cloud/services/realtime/realtime_config.dart';
import 'package:quwoquan_app/cloud/services/realtime/realtime_connection_delegate.dart';
import 'package:quwoquan_app/cloud/services/realtime/realtime_message_handler.dart';
import 'package:quwoquan_app/cloud/services/realtime/transport/longpoll_transport.dart';
import 'package:quwoquan_app/cloud/services/realtime/transport/websocket_transport.dart';

typedef RemoteRealtimeLongPollFactory =
    LongPollTransport Function({
      required RealtimeConfig config,
      required CloudAuthTokenProvider authTokenProvider,
      required LongPollEventCallback onEvents,
    });

typedef RemoteRealtimeWebSocketFactory =
    WebSocketTransport Function({
      required RealtimeConfig config,
      required CloudAuthTokenProvider authTokenProvider,
      required RealtimeEventCallback onEvent,
      required VoidCallback onDisconnect,
    });

typedef RealtimeConnectTelemetryRecorder =
    Future<void> Function({
      required String transport,
      required String result,
      required int durationMs,
      String? failReasonCode,
    });

typedef RealtimeReconnectDelayResolver =
    Duration Function({required int attempt, required RealtimeConfig config});

/// Remote 实现：WebSocket + LongPoll，行为与 refactor 前 [RealtimeConnectionManager] 一致。
class RemoteRealtimeConnectionDelegate implements RealtimeConnectionDelegate {
  RemoteRealtimeConnectionDelegate({
    required this.read,
    ChatProviderInvalidate? invalidate,
    required this.currentUserIdResolver,
    required this.authTokenProvider,
    this.onStateChanged,
    this.telemetryRecorder,
    RealtimeReconnectDelayResolver? reconnectDelayResolver,
    RealtimeConfig? config,
    RemoteRealtimeLongPollFactory? longPollFactory,
    RemoteRealtimeWebSocketFactory? webSocketFactory,
  }) : _config = config ?? RealtimeConfig.fromRuntime(),
       _reconnectDelayResolver =
           reconnectDelayResolver ?? _defaultReconnectDelay,
       _longPollFactory = longPollFactory ?? _defaultLongPollFactory,
       _webSocketFactory = webSocketFactory ?? _defaultWebSocketFactory {
    _handler = RealtimeMessageHandler(
      read,
      invalidate: invalidate,
      currentUserIdResolver: currentUserIdResolver,
    );
  }

  static LongPollTransport _defaultLongPollFactory({
    required RealtimeConfig config,
    required CloudAuthTokenProvider authTokenProvider,
    required LongPollEventCallback onEvents,
  }) {
    return LongPollTransport(
      config: config,
      authTokenProvider: authTokenProvider,
      onEvents: onEvents,
    );
  }

  static WebSocketTransport _defaultWebSocketFactory({
    required RealtimeConfig config,
    required CloudAuthTokenProvider authTokenProvider,
    required RealtimeEventCallback onEvent,
    required VoidCallback onDisconnect,
  }) {
    return WebSocketTransport(
      config: config,
      authTokenProvider: authTokenProvider,
      onEvent: onEvent,
      onDisconnect: onDisconnect,
    );
  }

  static final Random _reconnectRandom = Random.secure();

  static Duration _defaultReconnectDelay({
    required int attempt,
    required RealtimeConfig config,
  }) {
    final exponent = attempt.clamp(0, 20);
    final capMilliseconds = (config.reconnectBaseDelayMs * (1 << exponent))
        .clamp(0, config.reconnectMaxDelayMs);
    if (capMilliseconds <= 0) {
      return Duration.zero;
    }
    // Full jitter prevents all clients that lost the same edge from reconnecting together.
    return Duration(
      milliseconds: _reconnectRandom.nextInt(capMilliseconds + 1),
    );
  }

  final T Function<T>(ProviderListenable<T> provider) read;
  final String Function() currentUserIdResolver;
  final CloudAuthTokenProvider authTokenProvider;
  final RealtimeConnectionStateListener? onStateChanged;
  final RealtimeConnectTelemetryRecorder? telemetryRecorder;
  final RealtimeConfig _config;
  final RemoteRealtimeLongPollFactory _longPollFactory;
  final RemoteRealtimeWebSocketFactory _webSocketFactory;
  final RealtimeReconnectDelayResolver _reconnectDelayResolver;

  late final RealtimeMessageHandler _handler;

  TransportState _state = TransportState.disconnected;

  @override
  TransportState get state => _state;

  WebSocketTransport? _ws;
  LongPollTransport? _longPoll;
  Timer? _idleTimer;
  int _reconnectAttempt = 0;
  Timer? _reconnectTimer;
  String? _activeConversationId;

  @override
  void onAppForeground() {
    if (_state == TransportState.disconnected) {
      _transitionTo(
        _activeConversationId == null
            ? TransportState.idle
            : TransportState.active,
      );
    }
  }

  @override
  void onAppBackground() {
    _transitionTo(TransportState.disconnected);
  }

  @override
  void onEnterConversation(String conversationId) {
    _activeConversationId = conversationId;
    _cancelIdleTimer();
    _transitionTo(TransportState.active);
  }

  @override
  void onLeaveConversation() {
    _activeConversationId = null;
    if (_state != TransportState.active) {
      _cancelIdleTimer();
      return;
    }
    _startIdleTimer();
  }

  @override
  void dispose() {
    _teardownAll();
  }

  void _setState(TransportState next) {
    if (_state == next) return;
    _state = next;
    onStateChanged?.call();
  }

  void _transitionTo(TransportState target) {
    if (_state == target) return;

    switch (target) {
      case TransportState.disconnected:
        _teardownAll();
        _reconnectAttempt = 0;
        _setState(TransportState.disconnected);

      case TransportState.idle:
        _teardownWebSocket();
        _startLongPoll();
        _setState(TransportState.idle);

      case TransportState.active:
        _teardownLongPoll();
        _reconnectAttempt = 0;
        unawaited(_connectWebSocket());
        _setState(TransportState.active);
    }
  }

  Future<void> _connectWebSocket() async {
    final startedAt = DateTime.now();
    _teardownWebSocket();

    final topics = <String>['inbox'];
    final conversationId = _activeConversationId;
    if (conversationId != null) {
      topics.add('conversation/$conversationId');
    }
    // 登录用户额外订阅个人推荐实时 patch 通道（游客 resolver 返回空 → 不订阅）。
    final feedPatchUserId = currentUserIdResolver().trim();
    if (feedPatchUserId.isNotEmpty) {
      topics.add(feedRealtimePatchChannelFor(feedPatchUserId));
    }

    _ws = _webSocketFactory(
      config: _config,
      authTokenProvider: authTokenProvider,
      onEvent: _onRealtimeEvent,
      onDisconnect: _onWebSocketDisconnect,
    );
    await _ws!.connect(topics: topics);
    final connected = _ws?.isConnected.value ?? false;
    if (connected) {
      // A completed authenticated connection, not a reconnect invocation,
      // starts a new retry budget.
      _reconnectAttempt = 0;
    }
    unawaited(
      _recordConnectResult(
        transport: 'websocket',
        result: connected ? 'success' : 'failed',
        durationMs: DateTime.now().difference(startedAt).inMilliseconds,
        failReasonCode: connected ? null : 'connection_not_established',
      ),
    );
  }

  void _onWebSocketDisconnect() {
    if (_state != TransportState.active) return;
    _scheduleReconnect();
  }

  void _scheduleReconnect() {
    if (_reconnectAttempt >= _config.maxReconnectAttempts) {
      debugPrint(
        'RemoteRealtimeConnectionDelegate: max reconnect attempts, falling back to long-poll',
      );
      _transitionTo(TransportState.idle);
      return;
    }

    _reconnectTimer?.cancel();
    final delay = _reconnectDelayResolver(
      attempt: _reconnectAttempt,
      config: _config,
    );
    _reconnectAttempt++;

    _reconnectTimer = Timer(delay, () {
      if (_state == TransportState.active) {
        unawaited(_connectWebSocket());
      }
    });
  }

  void _teardownWebSocket() {
    _reconnectTimer?.cancel();
    _reconnectTimer = null;
    _ws?.dispose();
    _ws = null;
  }

  void _startLongPoll() {
    _teardownLongPoll();
    _longPoll = _longPollFactory(
      config: _config,
      authTokenProvider: authTokenProvider,
      onEvents: _onLongPollEvents,
    );
    _longPoll!.onFirstTransportFailure = (reasonCode) {
      unawaited(
        _recordConnectResult(
          transport: 'long_poll',
          result: 'failed',
          durationMs: 0,
          failReasonCode: reasonCode,
        ),
      );
    };
    _longPoll!.start();
    unawaited(
      _recordConnectResult(
        transport: 'long_poll',
        result: 'started',
        durationMs: 0,
      ),
    );
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

  void _onRealtimeEvent(Map<String, dynamic> event) {
    _handler.handle(event);
  }

  void _startIdleTimer() {
    _cancelIdleTimer();
    _idleTimer = Timer(Duration(seconds: _config.wsIdleTimeoutSec), () {
      if (_state == TransportState.active) {
        _transitionTo(TransportState.idle);
      }
    });
  }

  void _cancelIdleTimer() {
    _idleTimer?.cancel();
    _idleTimer = null;
  }

  void _teardownAll() {
    _cancelIdleTimer();
    _teardownWebSocket();
    _teardownLongPoll();
  }

  Future<void> _recordConnectResult({
    required String transport,
    required String result,
    required int durationMs,
    String? failReasonCode,
  }) async {
    final recorder = telemetryRecorder;
    if (recorder == null) return;
    await recorder(
      transport: transport,
      result: result,
      durationMs: durationMs,
      failReasonCode: failReasonCode,
    );
  }
}
