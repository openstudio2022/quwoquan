import 'dart:async';

import 'package:quwoquan_app/service/realtime_gateway/realtime/connection/domain/realtime_connection_delegate.dart';
import 'package:quwoquan_app/runtime/di/realtime_message_handler.dart';

import '../../../../runtime/fixtures/object_contract_example_reader.dart';

/// Test-only catalog backed by the canonical Chat contract scenario.
final class FixtureRealtimeEventCatalog {
  FixtureRealtimeEventCatalog._();

  static List<Map<String, dynamic>> eventsForConversation(
    String conversationId,
  ) {
    final contractSeed = objectContractExampleReader.example(
      'chat',
      'chat_realtime_fixture_core',
    );
    final realtimeEvents = contractSeed?['realtimeEvents'];
    if (realtimeEvents is! Map) {
      return const <Map<String, dynamic>>[];
    }
    final rows = realtimeEvents[conversationId];
    if (rows is! List) {
      return const <Map<String, dynamic>>[];
    }
    return rows
        .whereType<Map>()
        .map((row) => row.cast<String, dynamic>())
        .toList(growable: false);
  }
}

/// Test-only delegate. Production cannot import files below `test/support`.
final class FixtureRealtimeConnectionDelegate
    implements RealtimeConnectionDelegate {
  FixtureRealtimeConnectionDelegate({
    required ChatProviderRead read,
    ChatProviderInvalidate? invalidate,
    this.onStateChanged,
    this.eventPushDelay = const Duration(milliseconds: 300),
  }) : _handler = RealtimeMessageHandler(read, invalidate: invalidate);

  final RealtimeConnectionStateListener? onStateChanged;
  final Duration eventPushDelay;
  final RealtimeMessageHandler _handler;

  TransportState _state = TransportState.disconnected;
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
    _cancelEventPush();
    _setState(TransportState.disconnected);
  }

  @override
  void onEnterConversation(String conversationId) {
    _cancelEventPush();
    _setState(TransportState.active);
    final events = FixtureRealtimeEventCatalog.eventsForConversation(
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

  @override
  void onLeaveConversation() {
    _cancelEventPush();
    if (_state == TransportState.active) {
      _setState(TransportState.idle);
    }
  }

  @override
  void dispose() {
    _cancelEventPush();
  }

  void _setState(TransportState next) {
    if (_state == next) {
      return;
    }
    _state = next;
    onStateChanged?.call();
  }

  void _cancelEventPush() {
    _eventPushTimer?.cancel();
    _eventPushTimer = null;
  }
}
