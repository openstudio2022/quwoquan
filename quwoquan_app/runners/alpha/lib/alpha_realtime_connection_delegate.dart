import 'dart:async';
import 'dart:convert';

import 'package:quwoquan_app/cloud/services/realtime/realtime_connection_delegate.dart';
import 'package:quwoquan_app/cloud/services/realtime/realtime_message_handler.dart';
import 'package:quwoquan_cloud_mock/quwoquan_cloud_mock.dart';

/// Alpha-only realtime fixture adapter.
///
/// The adapter is owned by the independent alpha runner and consumes the
/// generated immutable fixture bundle. It is therefore unreachable from the
/// production application kernel and never reads repository files at runtime.
final class AlphaRealtimeConnectionDelegate
    implements RealtimeConnectionDelegate {
  AlphaRealtimeConnectionDelegate({
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
  bool _didPushIncomingCall = false;

  @override
  TransportState get state => _state;

  @override
  void onAppForeground() {
    if (_state == TransportState.disconnected) {
      _setState(TransportState.idle);
    }
    if (_didPushIncomingCall) return;
    _didPushIncomingCall = true;
    final event = _AlphaRealtimeEventCatalog.incomingCallEvent();
    if (event == null) return;
    _eventPushTimer = Timer(eventPushDelay, () => _handler.handle(event));
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
    final events = _AlphaRealtimeEventCatalog.eventsForConversation(
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

final class _AlphaRealtimeEventCatalog {
  _AlphaRealtimeEventCatalog._();

  static List<Map<String, dynamic>> eventsForConversation(
    String conversationId,
  ) {
    final asset = alphaFixtureBundle.assets['chat'];
    if (asset == null) {
      return const <Map<String, dynamic>>[];
    }
    final decoded = jsonDecode(asset.sourceJson);
    if (decoded is! Map) {
      return const <Map<String, dynamic>>[];
    }
    final seedSets = decoded['seedSets'];
    if (seedSets is! Map) {
      return const <Map<String, dynamic>>[];
    }
    final seed = seedSets['chat_realtime_fixture_core'];
    if (seed is! Map) {
      return const <Map<String, dynamic>>[];
    }
    final realtimeEvents = seed['realtimeEvents'];
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

  static Map<String, dynamic>? incomingCallEvent() {
    final asset = alphaFixtureBundle.assets['rtc'];
    if (asset == null) return null;
    final decoded = jsonDecode(asset.sourceJson);
    if (decoded is! Map) return null;
    final seedSets = decoded['seedSets'];
    if (seedSets is! Map) return null;
    final core = seedSets['rtc_core'];
    if (core is! Map) return null;
    final sessions = core['sessions'];
    final participants = core['participants'];
    if (sessions is! List || participants is! List) return null;
    Map? incoming;
    for (final row in sessions.whereType<Map>()) {
      if (row['state'] == 'incoming') {
        incoming = row;
        break;
      }
    }
    if (incoming == null) return null;
    final callerId = incoming['callerUserId']?.toString() ?? '';
    String? callerName;
    String? avatarUrl;
    for (final row in participants.whereType<Map>()) {
      if (row['userId'] == callerId) {
        callerName = row['displayName']?.toString();
        avatarUrl = row['avatarUrl']?.toString();
        break;
      }
    }
    return <String, dynamic>{
      'type': 'call.ringing',
      'callId': incoming['sessionId']?.toString() ?? '',
      'actorId': callerId,
      'payload': <String, dynamic>{
        'callType': incoming['type'] == 'video' ? 'video' : 'audio',
        'initiatorId': callerId,
        if (callerName != null) 'callerName': callerName,
        if (avatarUrl != null) 'callerAvatarUrl': avatarUrl,
        'trustRelation': 'known',
        'expiresAt': DateTime.now()
            .add(const Duration(seconds: 30))
            .toUtc()
            .toIso8601String(),
      },
    };
  }
}
