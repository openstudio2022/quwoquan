import 'dart:async';
import 'dart:math';

import 'package:flutter/foundation.dart';
import 'package:riverpod/misc.dart' show ProviderListenable;
import 'package:quwoquan_app/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_app/service/realtime_gateway/realtime/connection/adapters/realtime_config.dart';
import 'package:quwoquan_app/service/realtime_gateway/realtime/connection/application/public/realtime_connection_delegate.dart';
import 'package:quwoquan_app/service/realtime_gateway/realtime/connection/application/realtime_connection_operation_gateway.dart';
import 'package:quwoquan_app/runtime/di/realtime_message_handler.dart';
import 'package:quwoquan_app/service/realtime_gateway/realtime/connection/adapters/longpoll_transport.dart';
import 'package:quwoquan_app/service/realtime_gateway/realtime/connection/adapters/websocket_transport.dart';

typedef RemoteRealtimeLongPollFactory = LongPollTransport Function({
  required RealtimeConfig config,
  required CloudAuthTokenProvider authTokenProvider,
  required LongPollActiveConversationIdResolver activeConversationIdResolver,
  required LongPollEventCallback onEvents,
});

typedef RemoteRealtimeWebSocketFactory = WebSocketTransport Function({
  required RealtimeConfig config,
  required CloudAuthTokenProvider authTokenProvider,
  required RealtimeEventCallback onEvent,
  required VoidCallback onDisconnect,
});

typedef RealtimeConnectTelemetryRecorder = Future<void> Function({
  required String transport,
  required String result,
  required int durationMs,
  String? failReasonCode,
});

typedef RealtimeReconnectDelayResolver = Duration Function({
  required int attempt,
  required RealtimeConfig config,
});

/// Remote 实现：WebSocket + LongPoll，行为与 refactor 前 [RealtimeConnectionManager] 一致。
class RemoteRealtimeConnectionDelegate implements RealtimeConnectionDelegate {
  RemoteRealtimeConnectionDelegate({
    required this.read,
    ChatProviderInvalidate? invalidate,
    required this.currentUserIdResolver,
    required this.authTokenProvider,
    this.operations,
    this.onStateChanged,
    this.telemetryRecorder,
    RealtimeReconnectDelayResolver? reconnectDelayResolver,
    RealtimeConfig? config,
    this._longPollFactory,
    this._webSocketFactory,
  }) : _config = config ?? RealtimeConfig.fromRuntime(),
       _reconnectDelayResolver =
           reconnectDelayResolver ?? _defaultReconnectDelay {
    _handler = RealtimeMessageHandler(
      read,
      invalidate: invalidate,
      currentUserIdResolver: currentUserIdResolver,
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
  final RealtimeConnectionOperationGateway? operations;
  final RealtimeConnectionStateListener? onStateChanged;
  final RealtimeConnectTelemetryRecorder? telemetryRecorder;
  final RealtimeConfig _config;
  final RemoteRealtimeLongPollFactory? _longPollFactory;
  final RemoteRealtimeWebSocketFactory? _webSocketFactory;
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
  bool _wsHadDisconnect = false;
  bool _disposed = false;
  int _webSocketGeneration = 0;

  @override
  void onAppForeground() {
    if (_disposed) return;
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
    if (_disposed) return;
    // 后台断开同样是断连窗口：回到前台重建传输后必须触发与 WS 断线重连
    // 同等的 Reconnected 补洞（realtime-push-and-offline-sync REQ-008），
    // 否则后台期间的消息在下一次全量刷新前不可见。
    if (_state != TransportState.disconnected) {
      _wsHadDisconnect = true;
    }
    _transitionTo(TransportState.disconnected);
  }

  @override
  void onEnterConversation(String conversationId) {
    if (_disposed) return;
    _activeConversationId = conversationId;
    _cancelIdleTimer();
    _transitionTo(TransportState.active);
  }

  @override
  void onLeaveConversation() {
    if (_disposed) return;
    _activeConversationId = null;
    if (_state != TransportState.active) {
      _cancelIdleTimer();
      return;
    }
    _startIdleTimer();
  }

  @override
  void dispose() {
    if (_disposed) return;
    _disposed = true;
    _handler.dispose();
    _teardownAll();
  }

  void _setState(TransportState next) {
    if (_state == next) return;
    _state = next;
    onStateChanged?.call();
  }

  void _transitionTo(TransportState target) {
    if (_disposed) return;
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
    if (_disposed) return;
    final startedAt = DateTime.now();
    _teardownWebSocket();
    if (_disposed) return;
    final generation = _webSocketGeneration;

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

    final factory = _webSocketFactory;
    late final WebSocketTransport transport;
    void onEvent(Map<String, dynamic> event) {
      if (_ownsWebSocket(generation, transport)) {
        _handler.handle(event);
      }
    }

    void onDisconnect() {
      _onWebSocketDisconnect(generation, transport);
    }

    transport = factory != null
        ? factory(
            config: _config,
            authTokenProvider: authTokenProvider,
            onEvent: onEvent,
            onDisconnect: onDisconnect,
          )
        : WebSocketTransport(
            config: _config,
            authTokenProvider: authTokenProvider,
            operations: _requiredOperations(),
            onEvent: onEvent,
            onDisconnect: onDisconnect,
          );
    _ws = transport;
    await transport.connect(topics: topics);
    if (!_ownsWebSocket(generation, transport)) return;
    final connected = transport.isConnected.value;
    if (connected) {
      // A completed authenticated connection, not a reconnect invocation,
      // starts a new retry budget.
      _reconnectAttempt = 0;
      if (_wsHadDisconnect) {
        // 传输恢复必须发出真实事件并驱动 seq 补洞
        //（realtime-push-and-offline-sync REQ-008）：WS 是即时广播通道，
        // 断连窗口内的消息只能由端侧按本地最大 seq 经消息同步接口补齐。
        _wsHadDisconnect = false;
        _handler.handle(<String, dynamic>{
          'type': 'Reconnected',
          'conversationId': ?_activeConversationId,
        });
      }
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

  bool _ownsWebSocket(int generation, WebSocketTransport transport) {
    return !_disposed &&
        generation == _webSocketGeneration &&
        identical(_ws, transport);
  }

  void _onWebSocketDisconnect(int generation, WebSocketTransport transport) {
    if (!_ownsWebSocket(generation, transport) ||
        _state != TransportState.active) {
      return;
    }
    _wsHadDisconnect = true;
    _scheduleReconnect();
  }

  void _scheduleReconnect() {
    if (_disposed) return;
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
      if (!_disposed && _state == TransportState.active) {
        unawaited(_connectWebSocket());
      }
    });
  }

  void _teardownWebSocket() {
    _webSocketGeneration++;
    _reconnectTimer?.cancel();
    _reconnectTimer = null;
    final transport = _ws;
    _ws = null;
    transport?.dispose();
  }

  void _startLongPoll() {
    if (_disposed) return;
    _teardownLongPoll();
    final factory = _longPollFactory;
    _longPoll = factory != null
        ? factory(
            config: _config,
            authTokenProvider: authTokenProvider,
            activeConversationIdResolver: () => _activeConversationId,
            onEvents: _onLongPollEvents,
          )
        : LongPollTransport(
            config: _config,
            authTokenProvider: authTokenProvider,
            operations: _requiredOperations(),
            activeConversationIdResolver: () => _activeConversationId,
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

  Future<void> _onLongPollEvents(List<Map<String, dynamic>> events) async {
    for (final event in events) {
      await _handler.handleAndWait(event);
      if (event['type'] == 'Reconnected') {
        _wsHadDisconnect = false;
      }
    }
  }

  void _teardownLongPoll() {
    _longPoll?.dispose();
    _longPoll = null;
  }

  RealtimeConnectionOperationGateway _requiredOperations() {
    final gateway = operations;
    if (gateway == null) {
      throw StateError(
        'production realtime transport requires generated operation gateway',
      );
    }
    return gateway;
  }

  void _startIdleTimer() {
    if (_disposed) return;
    _cancelIdleTimer();
    _idleTimer = Timer(Duration(seconds: _config.wsIdleTimeoutSec), () {
      if (!_disposed && _state == TransportState.active) {
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
    if (_disposed) return;
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
