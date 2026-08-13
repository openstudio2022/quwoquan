typedef ChatSeedObject = Map<String, Object?>;

final class ChatStateSeed {
  const ChatStateSeed({
    required this.currentUserId,
    required this.conversations,
    required this.members,
    required this.messages,
    this.userStates = const <ChatSeedObject>[],
    this.contacts = const <ChatSeedObject>[],
    this.settings = const <ChatSeedObject>[],
    this.contactCircleIds = const <String>[],
    this.contactGroupConversationIds = const <String>[],
    this.circleRows = const <ChatSeedObject>[],
  });

  final String currentUserId;
  final List<ChatSeedObject> conversations;
  final Map<String, List<ChatSeedObject>> members;
  final Map<String, List<ChatSeedObject>> messages;
  final List<ChatSeedObject> userStates;
  final List<ChatSeedObject> contacts;
  final List<ChatSeedObject> settings;
  final List<String> contactCircleIds;
  final List<String> contactGroupConversationIds;
  final List<ChatSeedObject> circleRows;
}

/// Chat timeline wire projection consumed by the runtime fixture server seed.
Map<String, Object?> chatStateSeedTimelineWire(ChatStateSeed seed) =>
    <String, Object?>{
      'currentUserId': seed.currentUserId,
      'conversations': seed.conversations,
      'messages': seed.messages,
      'members': seed.members,
      'userStates': seed.userStates,
    };

/// Chat contacts wire projection consumed by the runtime fixture server seed.
Map<String, Object?> chatStateSeedContactsWire(ChatStateSeed seed) =>
    <String, Object?>{
      'contacts': seed.contacts,
      'circleIds': seed.contactCircleIds,
      'groupConversationIds': seed.contactGroupConversationIds,
    };

/// Chat 对象级最小 seed。suite 可显式替换任一集合，不读取跨域场景文档。
ChatStateSeed minimalChatStateSeed({
  String currentUserId = 'fixture_user_current',
  List<ChatSeedObject>? conversations,
  Map<String, List<ChatSeedObject>>? members,
  Map<String, List<ChatSeedObject>>? messages,
  List<ChatSeedObject>? userStates,
  List<ChatSeedObject>? contacts,
  List<ChatSeedObject>? settings,
}) {
  final direct = _conversation(
    id: 'fixture_conv_direct',
    type: 'direct',
    title: '契约好友',
    memberIds: <String>[currentUserId, 'fixture_user_friend'],
  );
  final group = _conversation(
    id: 'fixture_conv_group',
    type: 'group',
    title: '契约周末群',
    memberIds: <String>[
      currentUserId,
      'fixture_user_weekend_1',
      'fixture_user_weekend_2',
    ],
  );
  final defaults = <ChatSeedObject>[direct, group];
  final defaultMembers = <String, List<ChatSeedObject>>{
    for (final conversation in defaults)
      conversation['id']! as String: _members(
        conversation['memberIds']! as List<String>,
        currentUserId,
      ),
  };
  final defaultMessages = <String, List<ChatSeedObject>>{
    for (final conversation in defaults)
      conversation['id']! as String: conversation['id'] == 'fixture_conv_direct'
          ? <ChatSeedObject>[
              _message(
                conversationId: conversation['id']! as String,
                senderId: 'fixture_user_friend',
              ),
              _message(
                conversationId: conversation['id']! as String,
                senderId: currentUserId,
                seq: 2,
              ),
            ]
          : <ChatSeedObject>[
              _message(
                conversationId: conversation['id']! as String,
                senderId: (conversation['memberIds']! as List<String>).last,
              ),
            ],
  };
  return ChatStateSeed(
    currentUserId: currentUserId,
    conversations: conversations ?? defaults,
    members: members ?? defaultMembers,
    messages: messages ?? defaultMessages,
    userStates:
        userStates ??
        <ChatSeedObject>[
          for (final conversation in defaults)
            <String, Object?>{
              'conversationId': conversation['id'],
              'userId': currentUserId,
              'readSeq': 0,
              'unreadCount': 1,
              'mentionUnreadCount': conversation['id'] == 'fixture_conv_direct'
                  ? 1
                  : 0,
              'muted': false,
              'pinned': false,
              'updatedAt': '2026-06-10T10:00:00Z',
            },
        ],
    contacts:
        contacts ??
        <ChatSeedObject>[
          _contact('fixture_user_friend'),
          _contact('fixture_user_weekend_1'),
          _contact('fixture_user_weekend_2'),
        ],
    settings: settings ?? const <ChatSeedObject>[],
    contactCircleIds: const <String>['fixture_circle_photo'],
    contactGroupConversationIds: const <String>['fixture_conv_group'],
    circleRows: const <ChatSeedObject>[
      <String, Object?>{
        'id': 'fixture_circle_photo',
        'name': '契约摄影社',
        'description': '对象级联系人圈子投影。',
        'avatarUrl':
            'media/avatar/s/archived-avatar/circle/fixture_circle_photo/v1/avatar.png',
        'memberCount': 3,
      },
    ],
  );
}

ChatSeedObject _conversation({
  required String id,
  required String type,
  required String title,
  required List<String> memberIds,
}) => <String, Object?>{
  'id': id,
  'type': type,
  'conversationType': type == 'group'
      ? 'interestGroupConversation'
      : 'directConversation',
  'title': title,
  'memberIds': memberIds,
  'avatarUrl': type == 'group'
      ? 'media/avatar/s/archived-avatar/group/$id/v1/composite.png'
      : _avatar(memberIds.last),
  'creatorId': memberIds.first,
  'maxSeq': 1,
  'memberCount': memberIds.length,
  'maxGroupSize': type == 'group' ? 500 : 2,
  'receiptEnabled': true,
  'lastMessagePreview': '$title 最小 seed 消息',
  'lastMessageTime': '2026-06-10T10:00:00Z',
  'messageCount': 1,
  'status': 'active',
  'createdAt': '2026-06-10T09:00:00Z',
  'updatedAt': '2026-06-10T10:00:00Z',
};

List<ChatSeedObject> _members(List<String> userIds, String currentUserId) =>
    userIds
        .map(
          (userId) => <String, Object?>{
            'userId': userId,
            'displayName': _displayName(userId),
            'avatarUrl': _avatar(userId),
            'userHandle': userId,
            'role': userId == userIds.first ? 'owner' : 'member',
            'isCurrentUser': userId == currentUserId,
          },
        )
        .toList(growable: false);

ChatSeedObject _message({
  required String conversationId,
  required String senderId,
  int seq = 1,
}) => <String, Object?>{
  'id': conversationId == 'fixture_conv_direct'
      ? 'fixture_msg_direct_$seq'
      : '${conversationId}_message_$seq',
  'conversationId': conversationId,
  'senderId': senderId,
  'senderName': '',
  'senderAvatar': '',
  'type': 'text',
  'content': '最小 seed 消息',
  'seq': seq,
  'clientMsgId': '${conversationId}_message_${seq}_client',
  'status': 'sent',
  'timestamp': '2026-06-10T10:00:00Z',
};

ChatSeedObject _contact(String userId) => <String, Object?>{
  'userId': userId,
  'displayName': _displayName(userId),
  'avatarUrl': _avatar(userId),
  'avatarObjectKey': _avatar(userId),
  'userHandle': userId,
  'relationState': 'mutual',
  'source': 'follow',
  'bio': '',
};

String _avatar(String userId) =>
    'media/avatar/s/archived-avatar/user/$userId/v1/avatar.png';

String _displayName(String userId) =>
    <String, String>{
      'fixture_user_current': '新同学_260622_6698692',
      'fixture_user_friend': '契约好友',
      'fixture_user_weekend_1': '契约同伴一',
      'fixture_user_weekend_2': '契约同伴二',
    }[userId] ??
    userId;
