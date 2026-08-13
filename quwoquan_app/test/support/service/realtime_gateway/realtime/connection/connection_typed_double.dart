import 'dart:async';

import 'package:quwoquan_app/service/realtime_gateway/realtime/connection/application/public/realtime_connection_delegate.dart';
import 'package:quwoquan_app/runtime/di/realtime_message_handler.dart';

/// Test-only catalog with the one realtime event shape exercised by this suite.
final class FixtureRealtimeEventCatalog {
  FixtureRealtimeEventCatalog._();

  static List<Map<String, dynamic>> eventsForConversation(
    String conversationId,
  ) {
    // 群 roster 事件：ConversationMemberAdded 只携带会话锚点，handler
    // 按事件类型触发成员 Provider 重载（不伪造未持久化 Message）。
    if (conversationId == 'fixture_conv_group') {
      return <Map<String, dynamic>>[
        <String, dynamic>{
          'type': 'ConversationMemberAdded',
          'conversationId': conversationId,
          'payload': <String, dynamic>{
            'conversationId': conversationId,
            'userId': 'fixture_user_new_member',
          },
        },
      ];
    }
    if (conversationId != 'conv_001') {
      return const <Map<String, dynamic>>[];
    }
    // payload 必须保持 canonical MessageSent wire 形状（messageId、
    // senderDisplayNameSnapshot 快照字段、无 status），与
    // RealtimeMessageHandler._decodeMessageSentEvent 的白名单同源；
    // 有辨识度的 fixture 文案与 messageId 是三个 realtime 旅程测试共同的
    // 断言真相源，修改必须同步全部消费者。
    return <Map<String, dynamic>>[
      <String, dynamic>{
        'type': 'MessageSent',
        'conversationId': conversationId,
        'payload': <String, dynamic>{
          'messageId': 'fixture_rt_conv_001_msg_13',
          'conversationId': conversationId,
          'seq': 13,
          'clientMsgId': 'fixture_msg_realtime_13_client',
          'senderId': 'fixture_user_friend',
          'senderDisplayNameSnapshot': '契约好友',
          'content': 'Fixture Realtime 新消息：咖啡馆门口见。',
          'type': 'text',
          'timestamp': '2026-06-10T00:12:00Z',
        },
      },
    ];
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
