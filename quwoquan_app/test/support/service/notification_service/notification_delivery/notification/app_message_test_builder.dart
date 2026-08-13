/// Notification/AppMessage 对象级 local_contract wire 样本。
List<Map<String, Object?>> appMessageWireExamples() => <Map<String, Object?>>[
  <String, Object?>{
    'messageId': 'fixture_app_message_assistant_stock',
    'userId': 'fixture_user_current',
    'messageType': 'assistant',
    'source': 'assistant_turn',
    'sourceId': 'fixture_turn_stock',
    'destination': <String, Object?>{
      'type': 'user',
      'id': 'fixture_user_current',
    },
    'title': '股票哨兵提醒',
    'summary': '契约股票哨兵触发了一条消息。',
    'target': <String, Object?>{
      'targetType': 'assistant_turn',
      'targetId': 'fixture_turn_stock',
      'routeId': 'assistantPersonal',
      'routePath': '/assistant/personal',
      'query': <String, Object?>{},
    },
    'read': false,
    'createdAt': '2026-04-29T08:00:00Z',
  },
  <String, Object?>{
    'messageId': 'fixture_app_message_chat',
    'userId': 'fixture_user_current',
    'messageType': 'chat',
    'source': 'chat_message',
    'sourceId': 'fixture_chat_message',
    'destination': <String, Object?>{
      'type': 'user',
      'id': 'fixture_user_current',
    },
    'title': '契约好友发来消息',
    'summary': '契约消息已送达',
    'target': <String, Object?>{
      'targetType': 'chat_message',
      'targetId': 'fixture_chat_message',
      'routeId': 'chatDetail',
      'routePath': '/chat/fixture_conversation',
      'query': <String, Object?>{},
    },
    'read': false,
    'createdAt': '2026-04-29T08:01:00Z',
  },
];
