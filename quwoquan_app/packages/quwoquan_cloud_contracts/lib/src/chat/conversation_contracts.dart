import '../operation_request_payload.dart';

/// The wire representation emitted by Chat's Conversation query and command
/// handlers. This pure contract intentionally owns the server response shape;
/// UI DTOs and Remote adapters map from it rather than decoding dynamic JSON.
final class ChatConversation {
  const ChatConversation({
    required this.id,
    required this.conversationId,
    required this.type,
    required this.title,
    required this.avatarUrl,
    required this.groupAvatarVersion,
    required this.creatorId,
    required this.circleId,
    required this.circleGroupId,
    required this.entityId,
    required this.originType,
    required this.bindingType,
    required this.lifecyclePolicy,
    required this.maxSeq,
    required this.memberCount,
    required this.membersRosterRevision,
    required this.maxGroupSize,
    required this.receiptEnabled,
    required this.announcement,
    required this.announcementUpdatedBy,
    required this.announcementUpdatedAt,
    required this.nameEditableByAdminOnly,
    required this.lastMessageId,
    required this.lastMessagePreview,
    required this.lastMessageTime,
    required this.messageCount,
    required this.status,
    required this.createdAt,
    required this.updatedAt,
  });

  final String id;
  final String conversationId;
  final String type;
  final String title;
  final String avatarUrl;
  final int groupAvatarVersion;
  final String creatorId;
  final String circleId;
  final String circleGroupId;
  final String entityId;
  final String originType;
  final String bindingType;
  final String lifecyclePolicy;
  final int maxSeq;
  final int memberCount;
  final int membersRosterRevision;
  final int maxGroupSize;
  final bool receiptEnabled;
  final String announcement;
  final String announcementUpdatedBy;
  final DateTime? announcementUpdatedAt;
  final bool nameEditableByAdminOnly;
  final String lastMessageId;
  final String lastMessagePreview;
  final DateTime lastMessageTime;
  final int messageCount;
  final String status;
  final DateTime createdAt;
  final DateTime updatedAt;
}

final class ChatConversationPageSlice {
  const ChatConversationPageSlice({required this.items, this.nextCursor});

  final List<ChatConversation> items;
  final String? nextCursor;
}

final class ChatConversationBatchSlice {
  const ChatConversationBatchSlice({required this.items});

  final List<ChatConversation> items;
}

abstract interface class ChatConversationQuery {
  Future<ChatConversationBatchSlice> batchGetConversations(
    ChatBatchGetConversationsQuery query,
  );

  Future<ChatConversationPageSlice> listConversations(
    ChatListConversationsQuery query,
  );

  Future<ChatConversation> getConversation(ChatGetConversationQuery query);

  Future<ChatConversationTimestampPageSlice> listConversationTimestamps(
    ChatListConversationTimestampsQuery query,
  );

  Future<ChatGroupHome> getGroupHome(ChatGetGroupHomeQuery query);

  Future<ChatMessageReceiptPageSlice> getMessageReceipts(
    ChatGetMessageReceiptsQuery query,
  );
}

abstract interface class ChatConversationCommandWriter {
  Future<ChatConversation> createConversation(
    ChatCreateConversationCommand command,
  );

  Future<ChatConversation> updateConversationTitle(
    ChatUpdateConversationTitleCommand command,
  );

  Future<ChatCommandAck> dissolveConversation(
    ChatDissolveConversationCommand command,
  );

  Future<ChatConversation> updateAnnouncement(
    ChatUpdateAnnouncementCommand command,
  );

  Future<ChatConversation> updateGroupGovernanceSettings(
    ChatUpdateGroupGovernanceSettingsCommand command,
  );
}

final class ChatBatchGetConversationsQuery {
  ChatBatchGetConversationsQuery({required Iterable<String> conversationIds})
    : conversationIds = List<String>.unmodifiable(
        conversationIds.map(
          (id) => _requiredNonBlankText(id, 'conversationId'),
        ),
      ) {
    if (this.conversationIds.isEmpty || this.conversationIds.length > 100) {
      throw ArgumentError.value(
        conversationIds,
        'conversationIds',
        'must contain 1..100 identifiers',
      );
    }
  }

  final List<String> conversationIds;
}

CloudOperationRequestPayload encodeChatBatchGetConversationsQuery(
  ChatBatchGetConversationsQuery query,
) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{'ids': query.conversationIds},
  );
}

final class ChatListConversationsQuery {
  ChatListConversationsQuery({this.cursor, this.limit = 20}) {
    if (limit < 1 || limit > 100) {
      throw ArgumentError.value(limit, 'limit', 'must be in 1..100');
    }
  }

  final String? cursor;
  final int limit;
}

CloudOperationRequestPayload encodeChatListConversationsQuery(
  ChatListConversationsQuery query,
) {
  final cursor = query.cursor?.trim();
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      if (cursor != null && cursor.isNotEmpty) 'cursor': cursor,
      'limit': '${query.limit}',
    },
  );
}

ChatConversationPageSlice decodeChatConversationPageSlice(Object? response) {
  final root = _expectObject(response, 'ListConversations response');
  _expectOnlyKeys(root, const <String>{
    'items',
    'nextCursor',
  }, 'ListConversations response');
  final rawItems = root['items'];
  if (rawItems is! List) {
    throw const FormatException(
      'ListConversations response.items must be a list',
    );
  }
  final items = List<ChatConversation>.unmodifiable(
    rawItems.map(_decodeChatConversation),
  );
  final nextCursor = _optionalText(root['nextCursor'], 'nextCursor');
  return ChatConversationPageSlice(items: items, nextCursor: nextCursor);
}

ChatConversationBatchSlice decodeChatConversationBatchSlice(Object? response) {
  final root = _expectObject(response, 'BatchGetConversations response');
  _expectOnlyKeys(root, const <String>{
    'items',
  }, 'BatchGetConversations response');
  final rawItems = root['items'];
  if (rawItems is! List) {
    throw const FormatException(
      'BatchGetConversations response.items must be a list',
    );
  }
  return ChatConversationBatchSlice(
    items: List<ChatConversation>.unmodifiable(
      rawItems.map(decodeChatConversation),
    ),
  );
}

ChatConversation decodeChatConversation(Object? response) {
  return _decodeChatConversation(response);
}

ChatConversation _decodeChatConversation(Object? response) {
  final root = _expectObject(response, 'Conversation response');
  _expectOnlyKeys(root, _conversationWireKeys, 'Conversation response');
  return ChatConversation(
    id: _requiredText(root['id'], 'id'),
    conversationId: _requiredText(root['conversationId'], 'conversationId'),
    type: _requiredText(root['type'], 'type'),
    title: _requiredText(root['title'], 'title'),
    avatarUrl: _requiredText(root['avatarUrl'], 'avatarUrl'),
    groupAvatarVersion: _requiredInt(
      root['groupAvatarVersion'],
      'groupAvatarVersion',
    ),
    creatorId: _requiredText(root['creatorId'], 'creatorId'),
    circleId: _requiredText(root['circleId'], 'circleId'),
    circleGroupId: _requiredText(root['circleGroupId'], 'circleGroupId'),
    entityId: _requiredText(root['entityId'], 'entityId'),
    originType: _requiredText(root['originType'], 'originType'),
    bindingType: _requiredText(root['bindingType'], 'bindingType'),
    lifecyclePolicy: _requiredText(root['lifecyclePolicy'], 'lifecyclePolicy'),
    maxSeq: _requiredInt(root['maxSeq'], 'maxSeq'),
    memberCount: _requiredInt(root['memberCount'], 'memberCount'),
    membersRosterRevision: _requiredInt(
      root['membersRosterRevision'],
      'membersRosterRevision',
    ),
    maxGroupSize: _requiredInt(root['maxGroupSize'], 'maxGroupSize'),
    receiptEnabled: _requiredBool(root['receiptEnabled'], 'receiptEnabled'),
    announcement: _requiredText(root['announcement'], 'announcement'),
    announcementUpdatedBy: _requiredText(
      root['announcementUpdatedBy'],
      'announcementUpdatedBy',
    ),
    announcementUpdatedAt: _optionalTimestamp(
      root['announcementUpdatedAt'],
      'announcementUpdatedAt',
    ),
    nameEditableByAdminOnly: _requiredBool(
      root['nameEditableByAdminOnly'],
      'nameEditableByAdminOnly',
    ),
    lastMessageId: _requiredText(root['lastMessageId'], 'lastMessageId'),
    lastMessagePreview: _requiredText(
      root['lastMessagePreview'],
      'lastMessagePreview',
    ),
    lastMessageTime: _requiredTimestamp(
      root['lastMessageTime'],
      'lastMessageTime',
    ),
    messageCount: _requiredInt(root['messageCount'], 'messageCount'),
    status: _requiredText(root['status'], 'status'),
    createdAt: _requiredTimestamp(root['createdAt'], 'createdAt'),
    updatedAt: _requiredTimestamp(root['updatedAt'], 'updatedAt'),
  );
}

final class ChatCommandAck {
  const ChatCommandAck({required this.status});

  final String status;
}

ChatCommandAck decodeChatCommandAck(Object? response) {
  final root = _expectObject(response, 'Chat command acknowledgement');
  _expectOnlyKeys(root, const <String>{
    'status',
  }, 'Chat command acknowledgement');
  return ChatCommandAck(status: _requiredText(root['status'], 'status'));
}

final class ChatCreateConversationCommand {
  ChatCreateConversationCommand({
    required String type,
    required String idempotencyKey,
    String? title,
    this.maxGroupSize,
    Iterable<String> initialMemberIds = const <String>[],
  }) : type = _requiredNonBlankText(type, 'type'),
       idempotencyKey = _requiredNonBlankText(idempotencyKey, 'idempotencyKey'),
       title = _optionalNonBlankText(title),
       initialMemberIds = List<String>.unmodifiable(
         initialMemberIds.map(
           (memberId) => _requiredNonBlankText(memberId, 'initialMemberId'),
         ),
       ) {
    if (maxGroupSize != null && (maxGroupSize! < 2 || maxGroupSize! > 1000)) {
      throw ArgumentError.value(
        maxGroupSize,
        'maxGroupSize',
        'must be in 2..1000 when present',
      );
    }
  }

  final String type;
  final String idempotencyKey;
  final String? title;
  final int? maxGroupSize;
  final List<String> initialMemberIds;
}

CloudOperationRequestPayload encodeChatCreateConversationCommand(
  ChatCreateConversationCommand command,
) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      'type': command.type,
      if (command.title case final value?) 'title': value,
      if (command.maxGroupSize case final value?) 'maxGroupSize': value,
      if (command.initialMemberIds.isNotEmpty)
        'initialMemberIds': command.initialMemberIds,
    },
  );
}

final class ChatGetConversationQuery {
  ChatGetConversationQuery({required String conversationId})
    : conversationId = _requiredNonBlankText(conversationId, 'conversationId');

  final String conversationId;
}

CloudOperationRequestPayload encodeChatGetConversationQuery(
  ChatGetConversationQuery query,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{'conversationId': query.conversationId},
  );
}

final class ChatUpdateConversationTitleCommand {
  ChatUpdateConversationTitleCommand({
    required String conversationId,
    required String idempotencyKey,
    required String title,
  }) : conversationId = _requiredNonBlankText(conversationId, 'conversationId'),
       idempotencyKey = _requiredNonBlankText(idempotencyKey, 'idempotencyKey'),
       title = _requiredNonBlankText(title, 'title');

  final String conversationId;
  final String idempotencyKey;
  final String title;
}

CloudOperationRequestPayload encodeChatUpdateConversationTitleCommand(
  ChatUpdateConversationTitleCommand command,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{'conversationId': command.conversationId},
    body: <String, Object?>{'title': command.title},
  );
}

final class ChatDissolveConversationCommand {
  ChatDissolveConversationCommand({
    required String conversationId,
    required String idempotencyKey,
  }) : conversationId = _requiredNonBlankText(conversationId, 'conversationId'),
       idempotencyKey = _requiredNonBlankText(idempotencyKey, 'idempotencyKey');

  final String conversationId;
  final String idempotencyKey;
}

CloudOperationRequestPayload encodeChatDissolveConversationCommand(
  ChatDissolveConversationCommand command,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{'conversationId': command.conversationId},
  );
}

final class ChatUpdateAnnouncementCommand {
  ChatUpdateAnnouncementCommand({
    required String conversationId,
    required String idempotencyKey,
    required this.announcement,
  }) : conversationId = _requiredNonBlankText(conversationId, 'conversationId'),
       idempotencyKey = _requiredNonBlankText(idempotencyKey, 'idempotencyKey');

  final String conversationId;
  final String idempotencyKey;
  final String announcement;
}

CloudOperationRequestPayload encodeChatUpdateAnnouncementCommand(
  ChatUpdateAnnouncementCommand command,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{'conversationId': command.conversationId},
    body: <String, Object?>{'announcement': command.announcement},
  );
}

final class ChatUpdateGroupGovernanceSettingsCommand {
  ChatUpdateGroupGovernanceSettingsCommand({
    required String conversationId,
    required String idempotencyKey,
    required this.nameEditableByAdminOnly,
  }) : conversationId = _requiredNonBlankText(conversationId, 'conversationId'),
       idempotencyKey = _requiredNonBlankText(idempotencyKey, 'idempotencyKey');

  final String conversationId;
  final String idempotencyKey;
  final bool nameEditableByAdminOnly;
}

CloudOperationRequestPayload encodeChatUpdateGroupGovernanceSettingsCommand(
  ChatUpdateGroupGovernanceSettingsCommand command,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{'conversationId': command.conversationId},
    body: <String, Object?>{
      'nameEditableByAdminOnly': command.nameEditableByAdminOnly,
    },
  );
}

final class ChatGetGroupHomeQuery {
  ChatGetGroupHomeQuery({required String conversationId})
    : conversationId = _requiredNonBlankText(conversationId, 'conversationId');

  final String conversationId;
}

CloudOperationRequestPayload encodeChatGetGroupHomeQuery(
  ChatGetGroupHomeQuery query,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{'conversationId': query.conversationId},
  );
}

final class ChatGroupHome {
  const ChatGroupHome({
    required this.conversationId,
    required this.title,
    required this.avatarUrl,
    required this.groupAvatarVersion,
    required this.circleId,
    required this.circleGroupId,
    required this.entityId,
    required this.sourceEntityTitle,
    required this.sourceCircleTitle,
    required this.memberCount,
    required this.announcement,
    required this.capabilities,
    required this.originType,
    required this.bindingType,
    required this.lifecyclePolicy,
    required this.canManageMembers,
    required this.canDissolve,
  });

  final String conversationId;
  final String title;
  final String avatarUrl;
  final int groupAvatarVersion;
  final String circleId;
  final String circleGroupId;
  final String entityId;
  final String sourceEntityTitle;
  final String sourceCircleTitle;
  final int memberCount;
  final String announcement;
  final List<String> capabilities;
  final String originType;
  final String bindingType;
  final String lifecyclePolicy;
  final bool canManageMembers;
  final bool canDissolve;
}

ChatGroupHome decodeChatGroupHome(Object? response) {
  final root = _expectObject(response, 'GetGroupHome response');
  _expectOnlyKeys(root, _groupHomeWireKeys, 'GetGroupHome response');
  return ChatGroupHome(
    conversationId: _requiredText(root['conversationId'], 'conversationId'),
    title: _requiredText(root['title'], 'title'),
    avatarUrl: _requiredText(root['avatarUrl'], 'avatarUrl'),
    groupAvatarVersion: _requiredInt(
      root['groupAvatarVersion'],
      'groupAvatarVersion',
    ),
    circleId: _requiredText(root['circleId'], 'circleId'),
    circleGroupId: _requiredText(root['circleGroupId'], 'circleGroupId'),
    entityId: _requiredText(root['entityId'], 'entityId'),
    sourceEntityTitle: _requiredText(
      root['sourceEntityTitle'],
      'sourceEntityTitle',
    ),
    sourceCircleTitle: _requiredText(
      root['sourceCircleTitle'],
      'sourceCircleTitle',
    ),
    memberCount: _requiredInt(root['memberCount'], 'memberCount'),
    announcement: _requiredText(root['announcement'], 'announcement'),
    capabilities: _requiredStringList(root['capabilities'], 'capabilities'),
    originType: _requiredText(root['originType'], 'originType'),
    bindingType: _requiredText(root['bindingType'], 'bindingType'),
    lifecyclePolicy: _requiredText(root['lifecyclePolicy'], 'lifecyclePolicy'),
    canManageMembers: _requiredBool(
      root['canManageMembers'],
      'canManageMembers',
    ),
    canDissolve: _requiredBool(root['canDissolve'], 'canDissolve'),
  );
}

final class ChatConversationTimestamp {
  const ChatConversationTimestamp({
    required this.conversationId,
    required this.type,
    required this.updatedAt,
    required this.settingsUpdatedAt,
    required this.lastMessageAt,
    required this.lastMessageTime,
    required this.lastMessagePreview,
    required this.unreadCount,
  });

  final String conversationId;
  final String type;
  final DateTime updatedAt;
  final DateTime settingsUpdatedAt;
  final DateTime? lastMessageAt;
  final DateTime? lastMessageTime;
  final String lastMessagePreview;
  final int unreadCount;
}

final class ChatConversationTimestampPageSlice {
  const ChatConversationTimestampPageSlice({required this.items});

  final List<ChatConversationTimestamp> items;
}

final class ChatListConversationTimestampsQuery {
  const ChatListConversationTimestampsQuery();
}

CloudOperationRequestPayload encodeChatListConversationTimestampsQuery(
  ChatListConversationTimestampsQuery query,
) {
  return const CloudOperationRequestPayload();
}

ChatConversationTimestampPageSlice decodeChatConversationTimestampPageSlice(
  Object? response,
) {
  final root = _expectObject(response, 'ListConversationTimestamps response');
  _expectOnlyKeys(root, const <String>{
    'items',
  }, 'ListConversationTimestamps response');
  final rawItems = root['items'];
  if (rawItems is! List) {
    throw const FormatException(
      'ListConversationTimestamps response.items must be a list',
    );
  }
  return ChatConversationTimestampPageSlice(
    items: List<ChatConversationTimestamp>.unmodifiable(
      rawItems.map((value) {
        final item = _expectObject(value, 'Conversation timestamp item');
        _expectOnlyKeys(
          item,
          _conversationTimestampWireKeys,
          'Conversation timestamp item',
        );
        return ChatConversationTimestamp(
          conversationId: _requiredText(
            item['conversationId'],
            'conversationId',
          ),
          type: _requiredText(item['type'], 'type'),
          updatedAt: _requiredTimestamp(item['updatedAt'], 'updatedAt'),
          settingsUpdatedAt: _requiredTimestamp(
            item['settingsUpdatedAt'],
            'settingsUpdatedAt',
          ),
          lastMessageAt: _optionalTimestamp(
            item['lastMessageAt'],
            'lastMessageAt',
          ),
          lastMessageTime: _optionalTimestamp(
            item['lastMessageTime'],
            'lastMessageTime',
          ),
          lastMessagePreview: _requiredText(
            item['lastMessagePreview'],
            'lastMessagePreview',
          ),
          unreadCount: _requiredInt(item['unreadCount'], 'unreadCount'),
        );
      }),
    ),
  );
}

final class ChatGetMessageReceiptsQuery {
  ChatGetMessageReceiptsQuery({
    required String conversationId,
    required String messageId,
  }) : conversationId = _requiredNonBlankText(conversationId, 'conversationId'),
       messageId = _requiredNonBlankText(messageId, 'messageId');

  final String conversationId;
  final String messageId;
}

CloudOperationRequestPayload encodeChatGetMessageReceiptsQuery(
  ChatGetMessageReceiptsQuery query,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      'conversationId': query.conversationId,
      'messageId': query.messageId,
    },
  );
}

final class ChatMessageReceipt {
  const ChatMessageReceipt({
    required this.id,
    required this.messageId,
    required this.conversationId,
    required this.userId,
    required this.readAt,
  });

  final String id;
  final String messageId;
  final String conversationId;
  final String userId;
  final DateTime readAt;
}

final class ChatMessageReceiptPageSlice {
  const ChatMessageReceiptPageSlice({required this.items});

  final List<ChatMessageReceipt> items;
}

ChatMessageReceiptPageSlice decodeChatMessageReceiptPageSlice(
  Object? response,
) {
  final root = _expectObject(response, 'GetReceipts response');
  _expectOnlyKeys(root, const <String>{'items'}, 'GetReceipts response');
  final rawItems = root['items'];
  if (rawItems is! List) {
    throw const FormatException('GetReceipts response.items must be a list');
  }
  return ChatMessageReceiptPageSlice(
    items: List<ChatMessageReceipt>.unmodifiable(
      rawItems.map((value) {
        final item = _expectObject(value, 'Message receipt item');
        _expectOnlyKeys(item, _messageReceiptWireKeys, 'Message receipt item');
        return ChatMessageReceipt(
          id: _requiredText(item['id'], 'id'),
          messageId: _requiredText(item['messageId'], 'messageId'),
          conversationId: _requiredText(
            item['conversationId'],
            'conversationId',
          ),
          userId: _requiredText(item['userId'], 'userId'),
          readAt: _requiredTimestamp(item['readAt'], 'readAt'),
        );
      }),
    ),
  );
}

const Set<String> _conversationWireKeys = <String>{
  'id',
  'conversationId',
  'type',
  'title',
  'avatarUrl',
  'groupAvatarVersion',
  'creatorId',
  'circleId',
  'circleGroupId',
  'entityId',
  'originType',
  'bindingType',
  'lifecyclePolicy',
  'maxSeq',
  'memberCount',
  'membersRosterRevision',
  'maxGroupSize',
  'receiptEnabled',
  'announcement',
  'announcementUpdatedBy',
  'announcementUpdatedAt',
  'nameEditableByAdminOnly',
  'lastMessageId',
  'lastMessagePreview',
  'lastMessageTime',
  'messageCount',
  'status',
  'createdAt',
  'updatedAt',
};

const Set<String> _groupHomeWireKeys = <String>{
  'conversationId',
  'title',
  'avatarUrl',
  'groupAvatarVersion',
  'circleId',
  'circleGroupId',
  'entityId',
  'sourceEntityTitle',
  'sourceCircleTitle',
  'memberCount',
  'announcement',
  'capabilities',
  'originType',
  'bindingType',
  'lifecyclePolicy',
  'canManageMembers',
  'canDissolve',
};

const Set<String> _conversationTimestampWireKeys = <String>{
  'conversationId',
  'type',
  'updatedAt',
  'settingsUpdatedAt',
  'lastMessageAt',
  'lastMessageTime',
  'lastMessagePreview',
  'unreadCount',
};

const Set<String> _messageReceiptWireKeys = <String>{
  'id',
  'messageId',
  'conversationId',
  'userId',
  'readAt',
};

Map<String, Object?> _expectObject(Object? value, String context) {
  if (value is! Map) {
    throw FormatException('$context must be an object');
  }
  return value.map<String, Object?>(
    (key, item) => MapEntry(key.toString(), item),
  );
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

String _requiredText(Object? value, String field) {
  if (value is! String) {
    throw FormatException('$field must be a string');
  }
  return value;
}

String _requiredNonBlankText(String value, String field) {
  final normalized = value.trim();
  if (normalized.isEmpty) {
    throw ArgumentError.value(value, field, 'must not be blank');
  }
  return normalized;
}

String? _optionalNonBlankText(String? value) {
  final normalized = value?.trim();
  return normalized == null || normalized.isEmpty ? null : normalized;
}

String? _optionalText(Object? value, String field) {
  if (value == null) {
    return null;
  }
  if (value is! String) {
    throw FormatException('$field must be a string when present');
  }
  return value.isEmpty ? null : value;
}

List<String> _requiredStringList(Object? value, String field) {
  if (value is! List || value.any((item) => item is! String)) {
    throw FormatException('$field must be a list of strings');
  }
  return List<String>.unmodifiable(value.cast<String>());
}

int _requiredInt(Object? value, String field) {
  if (value is! num || value.toInt() != value) {
    throw FormatException('$field must be an integer');
  }
  return value.toInt();
}

bool _requiredBool(Object? value, String field) {
  if (value is! bool) {
    throw FormatException('$field must be a boolean');
  }
  return value;
}

DateTime _requiredTimestamp(Object? value, String field) {
  final parsed = _optionalTimestamp(value, field);
  if (parsed == null) {
    throw FormatException('$field must be an ISO-8601 timestamp');
  }
  return parsed;
}

DateTime? _optionalTimestamp(Object? value, String field) {
  if (value == null) {
    return null;
  }
  if (value is DateTime) {
    return value.toUtc();
  }
  if (value is! String) {
    throw FormatException('$field must be an ISO-8601 timestamp');
  }
  final parsed = DateTime.tryParse(value);
  if (parsed == null) {
    throw FormatException('$field must be an ISO-8601 timestamp');
  }
  return parsed.toUtc();
}
