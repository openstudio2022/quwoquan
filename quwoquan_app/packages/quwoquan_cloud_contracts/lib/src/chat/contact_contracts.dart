import '../generated/chat_contract_enums.g.dart';
import '../operation_request_payload.dart';

export 'conversation_contracts.dart'
    show ChatConversationBatchSlice, decodeChatConversationBatchSlice;
part '../generated/requests/chat/contact_contracts.requests.g.dart';

final class ChatContact {
  const ChatContact({
    required this.userId,
    required this.userHandle,
    required this.displayName,
    required this.avatarUrl,
    required this.bio,
    required this.metFrom,
    required this.lastInteraction,
    required this.relationState,
    required this.conversationId,
    required this.conversationType,
    required this.subtitle,
    required this.highlightText,
    required this.matchedField,
    required this.source,
    required this.isStarred,
  });

  final String userId;
  final String userHandle;
  final String displayName;
  final String avatarUrl;
  final String lastInteraction;
  final String relationState;
  final String bio;
  final String metFrom;
  final String conversationId;
  final String conversationType;
  final String subtitle;
  final String highlightText;
  final String matchedField;
  final String source;
  final bool isStarred;
}

final class ChatContactPageSlice {
  const ChatContactPageSlice({required this.items, this.nextCursor});

  final List<ChatContact> items;
  final String? nextCursor;
}

abstract interface class ChatContactQuery {
  Future<ChatContactPageSlice> listContacts(ChatListContactsQuery query);

  Future<ChatContactHomePageSlice> listContactHome(
    ChatListContactHomeQuery query,
  );

  Future<ChatContactPageSlice> listGroupCandidates(
    ChatListGroupCandidatesQuery query,
  );

  Future<ChatSelectableGroupConversationPageSlice>
  listSelectableGroupConversations(
    ChatListSelectableGroupConversationsQuery query,
  );

  Future<ChatContactPageSlice> listSelectableGroupContactMembers(
    ChatListSelectableGroupContactMembersQuery query,
  );
}

abstract interface class ChatInboxQuery {
  Future<ChatInboxPageSlice> listInbox(ChatListInboxQuery query);
}

ChatContactPageSlice decodeChatContactPageSlice(Object? response) {
  final root = _expectObject(response, 'ListContacts response');
  _expectOnlyKeys(root, const <String>{
    'items',
    'nextCursor',
  }, 'ListContacts response');
  return ChatContactPageSlice(
    items: _requiredList(
      root['items'],
      'ListContacts response.items',
    ).map(_decodeContact).toList(growable: false),
    nextCursor: _optionalText(root['nextCursor'], 'nextCursor'),
  );
}

ChatContactPageSlice decodeChatGroupCandidatePageSlice(Object? response) {
  final root = _expectObject(response, 'ListGroupCandidates response');
  _expectOnlyKeys(root, const <String>{
    'items',
    'nextCursor',
  }, 'ListGroupCandidates response');
  return ChatContactPageSlice(
    items: _requiredList(
      root['items'],
      'ListGroupCandidates response.items',
    ).map(_decodeContact).toList(growable: false),
    nextCursor: _optionalText(root['nextCursor'], 'nextCursor'),
  );
}

final class ChatInboxItem {
  const ChatInboxItem({
    required this.id,
    required this.type,
    required this.title,
    required this.avatarUrl,
    required this.groupAvatarVersion,
    required this.lastMessagePreview,
    required this.lastMessageType,
    required this.lastMessageTime,
    required this.lastSeq,
    required this.unreadCount,
    required this.mentionUnreadCount,
    required this.muted,
    required this.pinned,
    required this.circleId,
  });

  final String id;
  final String type;
  final String title;
  final String avatarUrl;
  final int groupAvatarVersion;
  final String lastMessagePreview;
  final MessageType lastMessageType;
  final DateTime? lastMessageTime;
  final int lastSeq;
  final int unreadCount;
  final int mentionUnreadCount;
  final bool muted;
  final bool pinned;
  final String? circleId;
}

final class ChatInboxPageSlice {
  const ChatInboxPageSlice({required this.items, this.nextCursor});

  final List<ChatInboxItem> items;
  final String? nextCursor;
}

ChatInboxPageSlice decodeChatInboxPageSlice(Object? response) {
  final root = _expectObject(response, 'ListInbox response');
  _expectOnlyKeys(root, const <String>{
    'items',
    'nextCursor',
  }, 'ListInbox response');
  return ChatInboxPageSlice(
    items: _requiredList(
      root['items'],
      'ListInbox response.items',
    ).map(_decodeInboxItem).toList(growable: false),
    nextCursor: _optionalText(root['nextCursor'], 'nextCursor'),
  );
}

final class ChatContactHomeItem {
  const ChatContactHomeItem({
    required this.id,
    required this.kind,
    required this.objectId,
    required this.userHandle,
    required this.title,
    required this.subtitle,
    required this.avatarUrl,
    required this.summaryIntersections,
    required this.sortKey,
    required this.contactCount,
    this.userId,
    this.conversationId,
    this.circleId,
    this.circleGroupId,
    this.entityId,
    this.relationState,
    this.lastActiveAt,
    this.isStarred,
    this.memberCount,
    this.sourceEntityTitle,
    this.sourceCircleTitle,
  });

  final String id;
  final String kind;
  final String objectId;
  final String userHandle;
  final String title;
  final String subtitle;
  final String avatarUrl;
  final List<String> summaryIntersections;
  final String sortKey;
  final int contactCount;
  final String? userId;
  final String? conversationId;
  final String? circleId;
  final String? circleGroupId;
  final String? entityId;
  final String? relationState;
  final DateTime? lastActiveAt;
  final bool? isStarred;
  final int? memberCount;
  final String? sourceEntityTitle;
  final String? sourceCircleTitle;
}

final class ChatContactHomePageSlice {
  const ChatContactHomePageSlice({required this.items});

  final List<ChatContactHomeItem> items;
}

ChatContactHomePageSlice decodeChatContactHomePageSlice(Object? response) {
  final root = _expectObject(response, 'ListContactHome response');
  _expectOnlyKeys(root, const <String>{'items'}, 'ListContactHome response');
  return ChatContactHomePageSlice(
    items: _requiredList(
      root['items'],
      'ListContactHome response.items',
    ).map(_decodeContactHomeItem).toList(growable: false),
  );
}

final class ChatSelectableGroupConversation {
  const ChatSelectableGroupConversation({
    required this.conversationId,
    required this.title,
    required this.avatarUrl,
    required this.circleId,
    required this.friendMemberCount,
    required this.memberCount,
  });

  final String conversationId;
  final String title;
  final String avatarUrl;
  final String circleId;
  final int friendMemberCount;
  final int memberCount;
}

final class ChatSelectableGroupConversationPageSlice {
  const ChatSelectableGroupConversationPageSlice({
    required this.items,
    this.nextCursor,
  });

  final List<ChatSelectableGroupConversation> items;
  final String? nextCursor;
}

ChatSelectableGroupConversationPageSlice
decodeChatSelectableGroupConversationPageSlice(Object? response) {
  final root = _expectObject(
    response,
    'ListSelectableGroupConversations response',
  );
  _expectOnlyKeys(root, const <String>{
    'items',
    'nextCursor',
  }, 'ListSelectableGroupConversations response');
  return ChatSelectableGroupConversationPageSlice(
    items:
        _requiredList(
              root['items'],
              'ListSelectableGroupConversations response.items',
            )
            .map((value) {
              final item = _expectObject(
                value,
                'Selectable group conversation',
              );
              _expectOnlyKeys(
                item,
                _selectableGroupConversationKeys,
                'Selectable group conversation',
              );
              return ChatSelectableGroupConversation(
                conversationId: _requiredText(
                  item['conversationId'],
                  'conversationId',
                ),
                title: _requiredString(item['title'], 'title'),
                avatarUrl: _requiredString(item['avatarUrl'], 'avatarUrl'),
                circleId: _requiredString(item['circleId'], 'circleId'),
                friendMemberCount: _requiredNonNegativeInt(
                  item['friendMemberCount'],
                  'friendMemberCount',
                ),
                memberCount: _requiredNonNegativeInt(
                  item['memberCount'],
                  'memberCount',
                ),
              );
            })
            .toList(growable: false),
    nextCursor: _optionalText(root['nextCursor'], 'nextCursor'),
  );
}

ChatContactPageSlice decodeChatSelectableGroupContactMemberPageSlice(
  Object? response,
) {
  final root = _expectObject(
    response,
    'ListSelectableGroupContactMembers response',
  );
  _expectOnlyKeys(root, const <String>{
    'items',
    'nextCursor',
  }, 'ListSelectableGroupContactMembers response');
  return ChatContactPageSlice(
    items:
        _requiredList(
              root['items'],
              'ListSelectableGroupContactMembers response.items',
            )
            .map((value) {
              final item = _expectObject(
                value,
                'Selectable group contact member',
              );
              _expectOnlyKeys(
                item,
                _selectableGroupContactMemberKeys,
                'Selectable group contact member',
              );
              return ChatContact(
                userId: _requiredText(item['userId'], 'userId'),
                userHandle: _requiredString(item['userHandle'], 'userHandle'),
                displayName: _requiredString(
                  item['displayName'],
                  'displayName',
                ),
                avatarUrl: _requiredString(item['avatarUrl'], 'avatarUrl'),
                relationState: _requiredText(
                  item['relationState'],
                  'relationState',
                ),
                source: _requiredText(item['source'], 'source'),
                bio: '',
                metFrom: '',
                lastInteraction: '',
                conversationId: '',
                conversationType: '',
                subtitle: '',
                highlightText: '',
                matchedField: '',
                isStarred: false,
              );
            })
            .toList(growable: false),
    nextCursor: _optionalText(root['nextCursor'], 'nextCursor'),
  );
}

Map<String, Object?> _expectObject(Object? value, String context) {
  if (value is! Map) {
    throw FormatException('$context must be an object');
  }
  return value.map<String, Object?>((key, item) => MapEntry('$key', item));
}

List<Object?> _requiredList(Object? value, String field) {
  if (value is! List) {
    throw FormatException('$field must be a list');
  }
  return List<Object?>.unmodifiable(value);
}

void _expectOnlyKeys(
  Map<String, Object?> value,
  Set<String> allowed,
  String context,
) {
  final unknown = value.keys.where((key) => !allowed.contains(key)).toList();
  if (unknown.isNotEmpty) {
    throw FormatException(
      '$context contains unknown fields: ${unknown.join(', ')}',
    );
  }
}

ChatContact _decodeContact(Object? value) {
  final item = _expectObject(value, 'Chat contact');
  _expectOnlyKeys(item, _contactKeys, 'Chat contact');
  final userId = _requiredText(item['userId'], 'userId');
  return ChatContact(
    userId: userId,
    userHandle: _requiredString(item['userHandle'], 'userHandle'),
    displayName: _requiredString(item['displayName'], 'displayName'),
    avatarUrl: _requiredString(item['avatarUrl'], 'avatarUrl'),
    bio: _requiredString(item['bio'], 'bio'),
    metFrom: _requiredString(item['metFrom'], 'metFrom'),
    lastInteraction: _requiredString(
      item['lastInteraction'],
      'lastInteraction',
    ),
    relationState: _requiredString(item['relationState'], 'relationState'),
    conversationId: '',
    conversationType: '',
    subtitle: '',
    highlightText: '',
    matchedField: '',
    source: _requiredString(item['source'], 'source'),
    isStarred: _requiredBool(item['isStarred'], 'isStarred'),
  );
}

ChatInboxItem _decodeInboxItem(Object? value) {
  final item = _expectObject(value, 'Chat inbox item');
  _expectOnlyKeys(item, _inboxKeys, 'Chat inbox item');
  return ChatInboxItem(
    id: _requiredText(item['id'], 'id'),
    type: _requiredText(item['type'], 'type'),
    title: _requiredString(item['title'], 'title'),
    avatarUrl: _requiredString(item['avatarUrl'], 'avatarUrl'),
    groupAvatarVersion: _requiredNonNegativeInt(
      item['groupAvatarVersion'],
      'groupAvatarVersion',
    ),
    lastMessagePreview: _requiredString(
      item['lastMessagePreview'],
      'lastMessagePreview',
    ),
    lastMessageType: MessageType.fromWire(item['lastMessageType']),
    lastMessageTime: _optionalTimestamp(
      item['lastMessageTime'],
      'lastMessageTime',
    ),
    lastSeq: _requiredNonNegativeInt(item['lastSeq'], 'lastSeq'),
    unreadCount: _requiredNonNegativeInt(item['unreadCount'], 'unreadCount'),
    mentionUnreadCount: _requiredNonNegativeInt(
      item['mentionUnreadCount'],
      'mentionUnreadCount',
    ),
    muted: _requiredBool(item['muted'], 'muted'),
    pinned: _requiredBool(item['pinned'], 'pinned'),
    circleId: _optionalText(item['circleId'], 'circleId'),
  );
}

ChatContactHomeItem _decodeContactHomeItem(Object? value) {
  final item = _expectObject(value, 'Chat contact-home item');
  _expectOnlyKeys(item, _contactHomeKeys, 'Chat contact-home item');
  return ChatContactHomeItem(
    id: _requiredText(item['id'], 'id'),
    kind: _requiredText(item['kind'], 'kind'),
    objectId: _requiredText(item['objectId'], 'objectId'),
    userHandle: _requiredString(item['userHandle'], 'userHandle'),
    title: _requiredString(item['title'], 'title'),
    subtitle: _requiredString(item['subtitle'], 'subtitle'),
    avatarUrl: _requiredString(item['avatarUrl'], 'avatarUrl'),
    summaryIntersections: item['summaryIntersections'] == null
        ? const <String>[]
        : _requiredStringList(
            item['summaryIntersections'],
            'summaryIntersections',
          ),
    sortKey: item['sortKey'] == null
        ? ''
        : _requiredString(item['sortKey'], 'sortKey'),
    contactCount:
        _optionalNonNegativeInt(item['contactCount'], 'contactCount') ?? 0,
    userId: _optionalText(item['userId'], 'userId'),
    conversationId: _optionalText(item['conversationId'], 'conversationId'),
    circleId: _optionalText(item['circleId'], 'circleId'),
    circleGroupId: _optionalText(item['circleGroupId'], 'circleGroupId'),
    entityId: _optionalText(item['entityId'], 'entityId'),
    relationState: _optionalText(item['relationState'], 'relationState'),
    lastActiveAt: _optionalTimestamp(item['lastActiveAt'], 'lastActiveAt'),
    isStarred: _optionalBool(item['isStarred'], 'isStarred'),
    memberCount: _optionalNonNegativeInt(item['memberCount'], 'memberCount'),
    sourceEntityTitle: _optionalText(
      item['sourceEntityTitle'],
      'sourceEntityTitle',
    ),
    sourceCircleTitle: _optionalText(
      item['sourceCircleTitle'],
      'sourceCircleTitle',
    ),
  );
}

String _requiredText(Object? value, String field) {
  if (value is! String || value.trim().isEmpty) {
    throw FormatException('$field must be a non-blank string');
  }
  return value.trim();
}

String _requiredString(Object? value, String field) {
  if (value is! String) {
    throw FormatException('$field must be a string');
  }
  return value;
}

String? _optionalText(Object? value, String field) {
  if (value == null) {
    return null;
  }
  if (value is! String) {
    throw FormatException('$field must be a string when present');
  }
  final normalized = value.trim();
  return normalized.isEmpty ? null : normalized;
}

bool _requiredBool(Object? value, String field) {
  if (value is! bool) {
    throw FormatException('$field must be a boolean');
  }
  return value;
}

bool? _optionalBool(Object? value, String field) {
  if (value == null) {
    return null;
  }
  return _requiredBool(value, field);
}

int _requiredNonNegativeInt(Object? value, String field) {
  if (value is! num || value.toInt() < 0 || value.toDouble() != value.toInt()) {
    throw FormatException('$field must be a non-negative integer');
  }
  return value.toInt();
}

int? _optionalNonNegativeInt(Object? value, String field) {
  if (value == null) {
    return null;
  }
  return _requiredNonNegativeInt(value, field);
}

DateTime? _optionalTimestamp(Object? value, String field) {
  if (value == null) {
    return null;
  }
  if (value is! String) {
    throw FormatException('$field must be an ISO-8601 timestamp');
  }
  final timestamp = DateTime.tryParse(value);
  if (timestamp == null) {
    throw FormatException('$field must be an ISO-8601 timestamp');
  }
  return timestamp.toUtc();
}

List<String> _requiredStringList(Object? value, String field) {
  if (value is! List || value.any((item) => item is! String)) {
    throw FormatException('$field must be a list of strings');
  }
  return List<String>.unmodifiable(value.cast<String>());
}

const Set<String> _contactKeys = <String>{
  'userId',
  'userHandle',
  'displayName',
  'avatarUrl',
  'bio',
  'metFrom',
  'lastInteraction',
  'relationState',
  'source',
  'isStarred',
};

const Set<String> _inboxKeys = <String>{
  'id',
  'type',
  'title',
  'avatarUrl',
  'groupAvatarVersion',
  'lastMessagePreview',
  'lastMessageType',
  'lastMessageTime',
  'lastSeq',
  'unreadCount',
  'mentionUnreadCount',
  'muted',
  'pinned',
  'circleId',
};

const Set<String> _contactHomeKeys = <String>{
  'id',
  'kind',
  'objectId',
  'userId',
  'userHandle',
  'conversationId',
  'circleId',
  'circleGroupId',
  'entityId',
  'title',
  'subtitle',
  'avatarUrl',
  'relationState',
  'summaryIntersections',
  'lastActiveAt',
  'sortKey',
  'isStarred',
  'memberCount',
  'contactCount',
  'sourceEntityTitle',
  'sourceCircleTitle',
};

const Set<String> _selectableGroupConversationKeys = <String>{
  'conversationId',
  'title',
  'avatarUrl',
  'circleId',
  'friendMemberCount',
  'memberCount',
};

const Set<String> _selectableGroupContactMemberKeys = <String>{
  'userId',
  'userHandle',
  'displayName',
  'avatarUrl',
  'relationState',
  'source',
};
