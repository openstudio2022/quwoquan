import 'dart:async';

import 'package:riverpod/misc.dart' show ProviderListenable;
import 'package:quwoquan_app/cloud/services/realtime/mock/mock_realtime_event_catalog.dart';
import 'package:quwoquan_app/cloud/services/realtime/realtime_connection_delegate.dart';
import 'package:quwoquan_app/cloud/services/realtime/realtime_message_handler.dart';

/// Mock 实现：零 HTTP/WS，按 contract catalog 推送 realtime 事件。
class MockRealtimeConnectionDelegate implements RealtimeConnectionDelegate {
  MockRealtimeConnectionDelegate({
    required this.read,
    ChatProviderInvalidate? invalidate,
    this.onStateChanged,
    this.eventPushDelay = const Duration(milliseconds: 300),
  }) {
    _handler = RealtimeMessageHandler(read, invalidate: invalidate);
  }

  final T Function<T>(ProviderListenable<T> provider) read;
  final RealtimeConnectionStateListener? onStateChanged;
  final Duration eventPushDelay;

  late final RealtimeMessageHandler _handler;

  TransportState _state = TransportState.disconnected;
  Timer? _idleTimer;
  Timer? _eventPushTimer;

  @override
  TransportState get state => _state;

  @override
  void onAppForeground() {
    if (_state == TransportState.disconnected) {
      _setState(TransportState.idle);
    }
  }

  @override
  void onAppBackground() {
    _cancelTimers();
    _setState(TransportState.disconnected);
  }

  @override
  void onEnterChatDetail(String conversationId) {
    _cancelTimers();
    _setState(TransportState.active);
    _scheduleCatalogEvents(conversationId);
  }

  @override
  void onLeaveChatDetail() {
    _eventPushTimer?.cancel();
    _eventPushTimer = null;
    _idleTimer?.cancel();
    _idleTimer = null;
    if (_state == TransportState.active) {
      _setState(TransportState.idle);
    }
  }

  @override
  void dispose() {
    _cancelTimers();
  }

  void _setState(TransportState next) {
    if (_state == next) return;
    _state = next;
    onStateChanged?.call();
  }

  void _scheduleCatalogEvents(String conversationId) {
    final events = MockRealtimeEventCatalog.eventsForConversation(
      conversationId,
    );
    if (events.isEmpty) {
      return;
    }

    _eventPushTimer = Timer(eventPushDelay, () {
      if (_state != TransportState.active) {
        return;
      }
      for (final event in events) {
        _handler.handle(event);
      }
    });
  }

  void _cancelTimers() {
    _idleTimer?.cancel();
    _idleTimer = null;
    _eventPushTimer?.cancel();
    _eventPushTimer = null;
  }
}
