import 'package:quwoquan_app/cloud/runtime/contract_fixture_runtime_loader.dart';
import 'package:quwoquan_app/cloud/services/chat/mock/chat_mock_data.dart';

/// Alpha mock 模式下可推送的 realtime 事件目录（与 MockChat 同源）。
class MockRealtimeEventCatalog {
  MockRealtimeEventCatalog._();

  /// 进入会话详情后模拟推送 realtime 事件（优先 contract fixture，fallback 到本地 mock）。
  static List<Map<String, dynamic>> eventsForConversation(
    String conversationId,
  ) {
    final fixtureEvents = _fixtureRealtimeEventsForConversation(conversationId);
    if (fixtureEvents.isNotEmpty) {
      return fixtureEvents;
    }
    return _fallbackMessageSentEvents(conversationId);
  }

  static List<Map<String, dynamic>> _fixtureRealtimeEventsForConversation(
    String conversationId,
  ) {
    final contractSeed = ContractFixtureRuntimeLoader.chatSeedSet(
      'chat_realtime_mock_core',
    );
    final realtimeEvents = contractSeed?['realtimeEvents'];
    if (realtimeEvents is! Map) {
      return const [];
    }
    final rows = realtimeEvents[conversationId];
    if (rows is! List) {
      return const [];
    }
    return rows
        .whereType<Map>()
        .map((row) => row.cast<String, dynamic>())
        .toList(growable: false);
  }

  static List<Map<String, dynamic>> _fallbackMessageSentEvents(
    String conversationId,
  ) {
    final now = DateTime.now().toUtc();
    if (conversationId == 'conv_001') {
      return [
        {
          'type': 'MessageSent',
          'conversationId': conversationId,
          'payload': <String, dynamic>{
            'id': 'fixture_rt_conv_001_msg_13',
            '_id': 'fixture_rt_conv_001_msg_13',
            'messageId': 'fixture_rt_conv_001_msg_13',
            'conversationId': conversationId,
            'seq': 13,
            'clientMsgId': 'fixture_rt_conv_001_msg_13_client',
            'senderId': 'fixture_user_friend',
            'senderDisplayNameSnapshot': '契约联系人',
            'senderAvatarUrlSnapshot':
                'media/avatar/s/archived-avatar/user/fixture_user_friend/v1/avatar.png',
            'senderAvatar':
                'media/avatar/s/archived-avatar/user/fixture_user_friend/v1/avatar.png',
            'type': 'text',
            'content': 'Fixture Realtime 新消息：咖啡馆门口见。',
            'status': 'sent',
            'timestamp': now.toIso8601String(),
          },
        },
      ];
    }
    final eventId = 'mock_rt_${conversationId}_${now.millisecondsSinceEpoch}';
    return [
      {
        'type': 'MessageSent',
        'conversationId': conversationId,
        'payload': <String, dynamic>{
          'id': eventId,
          '_id': eventId,
          'messageId': eventId,
          'conversationId': conversationId,
          'seq': now.millisecondsSinceEpoch,
          'clientMsgId': 'mock-rt-$eventId',
          'senderId': 'user_002',
          'senderName': '李明',
          'senderAvatar': ChatMockData.avatarFor('user_002'),
          'senderDisplayNameSnapshot': '李明',
          'senderAvatarUrlSnapshot': ChatMockData.avatarFor('user_002'),
          'type': 'text',
          'content': 'Mock Realtime 新消息：请到咖啡馆门口集合。',
          'status': 'sent',
          'timestamp': now.toIso8601String(),
        },
      },
    ];
  }
}
