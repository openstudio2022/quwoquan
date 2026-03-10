/// Canonical mock data for the chat domain.
/// Maps to contracts/metadata/messages/conversation/fields.yaml entities.
class ChatMockData {
  ChatMockData._();

  static const assistantConversationId = 'conv_assistant_001';

  // ── Conversations ──────────────────────────────────────────────────────────

  static List<Map<String, dynamic>> get conversations => [
        {
          '_id': 'conv_001',
          'id': 'conv_001',
          'type': 'direct',
          'title': '李明',
          'avatarUrl': 'https://i.pravatar.cc/150?u=liming',
          'creatorId': 'user_001',
          'maxSeq': 42,
          'memberCount': 2,
          'maxGroupSize': 2,
          'receiptEnabled': true,
          'lastMessagePreview': '好的，明天见',
          'lastMessageTime': '2026-03-07T10:30:00Z',
          'messageCount': 42,
          'status': 'active',
          'createdAt': '2026-01-15T08:00:00Z',
          'updatedAt': '2026-03-07T10:30:00Z',
        },
        {
          '_id': 'conv_002',
          'id': 'conv_002',
          'type': 'group',
          'title': '周末登山群',
          'avatarUrl': 'https://i.pravatar.cc/150?u=hiking',
          'creatorId': 'user_002',
          'maxSeq': 256,
          'memberCount': 15,
          'maxGroupSize': 1000,
          'receiptEnabled': true,
          'lastMessagePreview': '周六早上8点出发',
          'lastMessageTime': '2026-03-07T09:15:00Z',
          'messageCount': 256,
          'status': 'active',
          'createdAt': '2026-02-01T10:00:00Z',
          'updatedAt': '2026-03-07T09:15:00Z',
        },
        {
          '_id': 'conv_003',
          'id': 'conv_003',
          'type': 'circle',
          'title': '摄影爱好者圈子',
          'avatarUrl': 'https://i.pravatar.cc/150?u=photo',
          'creatorId': 'user_003',
          'circleId': 'circle_001',
          'maxSeq': 1024,
          'memberCount': 200,
          'maxGroupSize': 1000,
          'receiptEnabled': false,
          'lastMessagePreview': '分享一组新疆风景照',
          'lastMessageTime': '2026-03-07T08:00:00Z',
          'messageCount': 1024,
          'status': 'active',
          'createdAt': '2025-12-01T10:00:00Z',
          'updatedAt': '2026-03-07T08:00:00Z',
        },
        {
          '_id': 'conv_004',
          'id': 'conv_004',
          'type': 'encrypted',
          'title': '密信 - 张华',
          'avatarUrl': 'https://i.pravatar.cc/150?u=zhanghua',
          'creatorId': 'user_001',
          'maxSeq': 8,
          'memberCount': 2,
          'maxGroupSize': 2,
          'receiptEnabled': true,
          'lastMessagePreview': '[加密消息]',
          'lastMessageTime': '2026-03-06T22:00:00Z',
          'messageCount': 8,
          'status': 'active',
          'createdAt': '2026-03-01T10:00:00Z',
          'updatedAt': '2026-03-06T22:00:00Z',
        },
      ];

  // ── Messages ───────────────────────────────────────────────────────────────

  static List<Map<String, dynamic>> messagesFor(String conversationId) {
    return _messagesByConversation[conversationId] ?? _defaultMessages;
  }

  static final Map<String, List<Map<String, dynamic>>> _messagesByConversation =
      {
    'conv_001': [
      {
        '_id': 'msg_001_01',
        'id': 'msg_001_01',
        'conversationId': 'conv_001',
        'seq': 42,
        'clientMsgId': 'client-uuid-001',
        'senderId': 'user_002',
        'type': 'text',
        'content': '好的，明天见',
        'status': 'sent',
        'timestamp': '2026-03-07T10:30:00Z',
      },
      {
        '_id': 'msg_001_02',
        'id': 'msg_001_02',
        'conversationId': 'conv_001',
        'seq': 41,
        'clientMsgId': 'client-uuid-002',
        'senderId': 'user_001',
        'type': 'text',
        'content': '那我们明天下午三点见面？',
        'status': 'read',
        'timestamp': '2026-03-07T10:29:00Z',
      },
    ],
    'conv_002': [
      {
        '_id': 'msg_002_01',
        'id': 'msg_002_01',
        'conversationId': 'conv_002',
        'seq': 256,
        'clientMsgId': 'client-uuid-003',
        'senderId': 'user_003',
        'type': 'text',
        'content': '周六早上8点出发',
        'status': 'sent',
        'timestamp': '2026-03-07T09:15:00Z',
      },
    ],
  };

  static final List<Map<String, dynamic>> _defaultMessages = [
    {
      '_id': 'msg_default_01',
      'id': 'msg_default_01',
      'conversationId': '',
      'seq': 1,
      'clientMsgId': 'client-uuid-default',
      'senderId': 'user_001',
      'type': 'text',
      'content': '你好',
      'status': 'sent',
      'timestamp': '2026-03-07T10:00:00Z',
    },
  ];

  // ── Members ────────────────────────────────────────────────────────────────

  static List<Map<String, dynamic>> membersFor(String conversationId) {
    return _membersByConversation[conversationId] ?? _defaultMembers;
  }

  static final Map<String, List<Map<String, dynamic>>>
      _membersByConversation = {
    'conv_001': [
      {
        '_id': 'cm_001_01',
        'id': 'cm_001_01',
        'conversationId': 'conv_001',
        'userId': 'user_001',
        'displayName': '我',
        'avatarUrl': 'https://i.pravatar.cc/150?u=me',
        'memberType': 'user',
        'role': 'member',
        'joinedAt': '2026-01-15T08:00:00Z',
      },
      {
        '_id': 'cm_001_02',
        'id': 'cm_001_02',
        'conversationId': 'conv_001',
        'userId': 'user_002',
        'displayName': '李明',
        'avatarUrl': 'https://i.pravatar.cc/150?u=liming',
        'memberType': 'user',
        'role': 'member',
        'joinedAt': '2026-01-15T08:00:00Z',
      },
    ],
    'conv_002': [
      {
        '_id': 'cm_002_01',
        'id': 'cm_002_01',
        'conversationId': 'conv_002',
        'userId': 'user_002',
        'displayName': '群主小王',
        'avatarUrl': 'https://i.pravatar.cc/150?u=wang',
        'memberType': 'user',
        'role': 'owner',
        'joinedAt': '2026-02-01T10:00:00Z',
      },
      {
        '_id': 'cm_002_02',
        'id': 'cm_002_02',
        'conversationId': 'conv_002',
        'userId': 'user_001',
        'displayName': '我',
        'avatarUrl': 'https://i.pravatar.cc/150?u=me',
        'memberType': 'user',
        'role': 'member',
        'invitedBy': 'user_002',
        'joinedAt': '2026-02-01T10:05:00Z',
      },
      for (int i = 3; i <= 15; i++)
        {
          '_id': 'cm_002_${i.toString().padLeft(2, '0')}',
          'id': 'cm_002_${i.toString().padLeft(2, '0')}',
          'conversationId': 'conv_002',
          'userId': 'user_${i.toString().padLeft(3, '0')}',
          'displayName': '成员$i',
          'avatarUrl': 'https://i.pravatar.cc/150?u=member$i',
          'memberType': 'user',
          'role': 'member',
          'invitedBy': 'user_002',
          'joinedAt': '2026-02-01T10:${i.toString().padLeft(2, '0')}:00Z',
        },
    ],
  };

  static final List<Map<String, dynamic>> _defaultMembers = [
    {
      '_id': 'cm_default_01',
      'id': 'cm_default_01',
      'conversationId': '',
      'userId': 'user_001',
      'displayName': '我',
      'avatarUrl': 'https://i.pravatar.cc/150?u=me',
      'memberType': 'user',
      'role': 'owner',
      'joinedAt': '2026-01-01T00:00:00Z',
    },
  ];

  // ── Contacts ───────────────────────────────────────────────────────────────

  static List<Map<String, dynamic>> get contacts => [
        {
          'userId': 'user_002',
          'displayName': '李明',
          'avatarUrl': 'https://i.pravatar.cc/150?u=liming',
        },
        {
          'userId': 'user_003',
          'displayName': '张华',
          'avatarUrl': 'https://i.pravatar.cc/150?u=zhanghua',
        },
        {
          'userId': 'user_004',
          'displayName': '王芳',
          'avatarUrl': 'https://i.pravatar.cc/150?u=wangfang',
        },
      ];
}
