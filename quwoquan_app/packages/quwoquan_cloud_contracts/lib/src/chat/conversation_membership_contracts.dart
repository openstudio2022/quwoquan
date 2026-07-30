import '../operation_request_payload.dart';
import 'conversation_contracts.dart' show ChatCommandAck;

export 'conversation_contracts.dart' show ChatCommandAck;
part '../generated/requests/chat/conversation_membership_contracts.requests.g.dart';

final class ChatConversationMember {
  const ChatConversationMember({
    required this.userId,
    required this.userHandle,
    required this.displayName,
    required this.avatarUrl,
    required this.role,
    required this.memberType,
    required this.assistantSkillId,
    required this.joinedAt,
    required this.isCurrentUser,
  });

  final String userId;
  final String userHandle;
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
  Future<ChatCommandAck> addMembers(
    ChatAddConversationMembersCommand command, {
    required String idempotencyKey,
  });

  Future<ChatCommandAck> removeMember(
    ChatRemoveConversationMemberCommand command, {
    required String idempotencyKey,
  });

  Future<ChatCommandAck> leaveConversation(
    ChatLeaveConversationCommand command, {
    required String idempotencyKey,
  });

  Future<ChatCommandAck> inviteAssistant(
    ChatInviteConversationAssistantCommand command, {
    required String idempotencyKey,
  });

  Future<ChatCommandAck> removeAssistant(
    ChatRemoveConversationAssistantCommand command, {
    required String idempotencyKey,
  });

  Future<ChatCommandAck> transferOwnership(
    ChatTransferConversationOwnershipCommand command, {
    required String idempotencyKey,
  });

  Future<ChatCommandAck> updateAdmins(
    ChatUpdateConversationAdminsCommand command, {
    required String idempotencyKey,
  });
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
          userHandle: _requiredText(item['userHandle'], 'userHandle'),
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

const Set<String> _memberWireKeys = <String>{
  'userId',
  'userHandle',
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
