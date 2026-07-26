import '../operation_request_payload.dart';
import 'conversation_contracts.dart' show ChatCommandAck;

export 'conversation_contracts.dart' show ChatCommandAck;

final class ChatConversationMember {
  const ChatConversationMember({
    required this.userId,
    required this.displayName,
    required this.avatarUrl,
    required this.role,
    required this.memberType,
    required this.assistantSkillId,
    required this.joinedAt,
    required this.isCurrentUser,
  });

  final String userId;
  final String displayName;
  final String avatarUrl;
  final String role;
  final String memberType;
  final String? assistantSkillId;
  final DateTime? joinedAt;
  final bool isCurrentUser;
}

final class ChatConversationMemberPageSlice {
  const ChatConversationMemberPageSlice({required this.items, this.nextCursor});

  final List<ChatConversationMember> items;
  final String? nextCursor;
}

abstract interface class ChatConversationMembershipQuery {
  Future<ChatConversationMemberPageSlice> listMembers(
    ChatListConversationMembersQuery query,
  );
}

abstract interface class ChatConversationMembershipCommandWriter {
  Future<ChatCommandAck> addMembers(ChatAddConversationMembersCommand command);

  Future<ChatCommandAck> removeMember(
    ChatRemoveConversationMemberCommand command,
  );

  Future<ChatCommandAck> leaveConversation(
    ChatLeaveConversationCommand command,
  );

  Future<ChatCommandAck> inviteAssistant(
    ChatInviteConversationAssistantCommand command,
  );

  Future<ChatCommandAck> removeAssistant(
    ChatRemoveConversationAssistantCommand command,
  );

  Future<ChatCommandAck> transferOwnership(
    ChatTransferConversationOwnershipCommand command,
  );

  Future<ChatCommandAck> updateAdmins(
    ChatUpdateConversationAdminsCommand command,
  );
}

final class ChatListConversationMembersQuery {
  ChatListConversationMembersQuery({
    required String conversationId,
    this.cursor,
    this.limit = 20,
    this.role,
    this.sort = 'joined_asc',
    this.query,
  }) : conversationId = _requiredNonBlankText(
         conversationId,
         'conversationId',
       ) {
    if (limit < 1 || limit > 100) {
      throw ArgumentError.value(limit, 'limit', 'must be in 1..100');
    }
    if (sort != 'joined_asc' && sort != 'display_name_asc') {
      throw ArgumentError.value(
        sort,
        'sort',
        'must be joined_asc or display_name_asc',
      );
    }
  }

  final String conversationId;
  final String? cursor;
  final int limit;
  final String? role;
  final String sort;
  final String? query;
}

CloudOperationRequestPayload encodeChatListConversationMembersQuery(
  ChatListConversationMembersQuery query,
) {
  final cursor = _optionalNonBlankText(query.cursor);
  final role = _optionalNonBlankText(query.role);
  final search = _optionalNonBlankText(query.query);
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{'conversationId': query.conversationId},
    queryParameters: <String, String>{
      if (cursor case final value?) 'cursor': value,
      'limit': '${query.limit}',
      if (role case final value?) 'role': value,
      'sort': query.sort,
      if (search case final value?) 'query': value,
    },
  );
}

ChatConversationMemberPageSlice decodeChatConversationMemberPageSlice(
  Object? response,
) {
  final root = _expectObject(response, 'ListMembers response');
  _expectOnlyKeys(root, const <String>{
    'items',
    'nextCursor',
  }, 'ListMembers response');
  final rawItems = root['items'];
  if (rawItems is! List) {
    throw const FormatException('ListMembers response.items must be a list');
  }
  return ChatConversationMemberPageSlice(
    items: List<ChatConversationMember>.unmodifiable(
      rawItems.map((value) {
        final item = _expectObject(value, 'Conversation member item');
        _expectOnlyKeys(item, _memberWireKeys, 'Conversation member item');
        return ChatConversationMember(
          userId: _requiredText(item['userId'], 'userId'),
          displayName: _requiredText(item['displayName'], 'displayName'),
          avatarUrl: _requiredText(item['avatarUrl'], 'avatarUrl'),
          role: _requiredText(item['role'], 'role'),
          memberType: _requiredText(item['memberType'], 'memberType'),
          assistantSkillId: _optionalText(
            item['assistantSkillId'],
            'assistantSkillId',
          ),
          joinedAt: _optionalTimestamp(item['joinedAt'], 'joinedAt'),
          isCurrentUser: _requiredBool(item['isCurrentUser'], 'isCurrentUser'),
        );
      }),
    ),
    nextCursor: _optionalText(root['nextCursor'], 'nextCursor'),
  );
}

final class ChatAddConversationMembersCommand {
  ChatAddConversationMembersCommand({
    required String conversationId,
    required String idempotencyKey,
    required Iterable<String> userIds,
  }) : conversationId = _requiredNonBlankText(conversationId, 'conversationId'),
       idempotencyKey = _requiredNonBlankText(idempotencyKey, 'idempotencyKey'),
       userIds = List<String>.unmodifiable(
         userIds.map((userId) => _requiredNonBlankText(userId, 'userId')),
       ) {
    if (this.userIds.isEmpty) {
      throw ArgumentError.value(userIds, 'userIds', 'must not be empty');
    }
  }

  final String conversationId;
  final String idempotencyKey;
  final List<String> userIds;
}

CloudOperationRequestPayload encodeChatAddConversationMembersCommand(
  ChatAddConversationMembersCommand command,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{'conversationId': command.conversationId},
    body: <String, Object?>{'userIds': command.userIds},
  );
}

final class ChatRemoveConversationMemberCommand {
  ChatRemoveConversationMemberCommand({
    required String conversationId,
    required String idempotencyKey,
    required String userId,
  }) : conversationId = _requiredNonBlankText(conversationId, 'conversationId'),
       idempotencyKey = _requiredNonBlankText(idempotencyKey, 'idempotencyKey'),
       userId = _requiredNonBlankText(userId, 'userId');

  final String conversationId;
  final String idempotencyKey;
  final String userId;
}

CloudOperationRequestPayload encodeChatRemoveConversationMemberCommand(
  ChatRemoveConversationMemberCommand command,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      'conversationId': command.conversationId,
      'userId': command.userId,
    },
  );
}

final class ChatLeaveConversationCommand {
  ChatLeaveConversationCommand({
    required String conversationId,
    required String idempotencyKey,
  }) : conversationId = _requiredNonBlankText(conversationId, 'conversationId'),
       idempotencyKey = _requiredNonBlankText(idempotencyKey, 'idempotencyKey');

  final String conversationId;
  final String idempotencyKey;
}

CloudOperationRequestPayload encodeChatLeaveConversationCommand(
  ChatLeaveConversationCommand command,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{'conversationId': command.conversationId},
  );
}

final class ChatInviteConversationAssistantCommand {
  ChatInviteConversationAssistantCommand({
    required String conversationId,
    required String idempotencyKey,
    String? skillId,
  }) : conversationId = _requiredNonBlankText(conversationId, 'conversationId'),
       idempotencyKey = _requiredNonBlankText(idempotencyKey, 'idempotencyKey'),
       skillId = _optionalNonBlankText(skillId);

  final String conversationId;
  final String idempotencyKey;
  final String? skillId;
}

CloudOperationRequestPayload encodeChatInviteConversationAssistantCommand(
  ChatInviteConversationAssistantCommand command,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{'conversationId': command.conversationId},
    body: <String, Object?>{
      if (command.skillId case final value?) 'skillId': value,
    },
  );
}

final class ChatRemoveConversationAssistantCommand {
  ChatRemoveConversationAssistantCommand({
    required String conversationId,
    required String idempotencyKey,
  }) : conversationId = _requiredNonBlankText(conversationId, 'conversationId'),
       idempotencyKey = _requiredNonBlankText(idempotencyKey, 'idempotencyKey');

  final String conversationId;
  final String idempotencyKey;
}

CloudOperationRequestPayload encodeChatRemoveConversationAssistantCommand(
  ChatRemoveConversationAssistantCommand command,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{'conversationId': command.conversationId},
  );
}

final class ChatTransferConversationOwnershipCommand {
  ChatTransferConversationOwnershipCommand({
    required String conversationId,
    required String idempotencyKey,
    required String newOwnerId,
  }) : conversationId = _requiredNonBlankText(conversationId, 'conversationId'),
       idempotencyKey = _requiredNonBlankText(idempotencyKey, 'idempotencyKey'),
       newOwnerId = _requiredNonBlankText(newOwnerId, 'newOwnerId');

  final String conversationId;
  final String idempotencyKey;
  final String newOwnerId;
}

CloudOperationRequestPayload encodeChatTransferConversationOwnershipCommand(
  ChatTransferConversationOwnershipCommand command,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{'conversationId': command.conversationId},
    body: <String, Object?>{'newOwnerId': command.newOwnerId},
  );
}

final class ChatUpdateConversationAdminsCommand {
  ChatUpdateConversationAdminsCommand({
    required String conversationId,
    required String idempotencyKey,
    required Iterable<String> adminIds,
  }) : conversationId = _requiredNonBlankText(conversationId, 'conversationId'),
       idempotencyKey = _requiredNonBlankText(idempotencyKey, 'idempotencyKey'),
       adminIds = List<String>.unmodifiable(
         adminIds.map((userId) => _requiredNonBlankText(userId, 'adminId')),
       );

  final String conversationId;
  final String idempotencyKey;
  final List<String> adminIds;
}

CloudOperationRequestPayload encodeChatUpdateConversationAdminsCommand(
  ChatUpdateConversationAdminsCommand command,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{'conversationId': command.conversationId},
    body: <String, Object?>{'adminIds': command.adminIds},
  );
}

const Set<String> _memberWireKeys = <String>{
  'userId',
  'displayName',
  'avatarUrl',
  'role',
  'memberType',
  'assistantSkillId',
  'joinedAt',
  'isCurrentUser',
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

String _requiredNonBlankText(String value, String field) {
  final normalized = value.trim();
  if (normalized.isEmpty) {
    throw ArgumentError.value(value, field, 'must not be blank');
  }
  return normalized;
}

String _requiredText(Object? value, String field) {
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
  return value.isEmpty ? null : value;
}

String? _optionalNonBlankText(String? value) {
  final normalized = value?.trim();
  return normalized == null || normalized.isEmpty ? null : normalized;
}

bool _requiredBool(Object? value, String field) {
  if (value is! bool) {
    throw FormatException('$field must be a boolean');
  }
  return value;
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
