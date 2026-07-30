import '../operation_request_payload.dart';
part '../generated/requests/user/persona_relationship_contracts.requests.g.dart';

/// PersonaRelationship 的关注/拉黑命令与私有列表 typed contracts。
/// pair/version/direction 等聚合内部状态不得穿透 App ABI。
abstract interface class FollowCommandWriter {
  Future<FollowCommandResult> followUser(FollowUserCommand command);

  Future<FollowCommandResult> unfollowUser(UnfollowUserCommand command);
}

abstract interface class BlockCommandWriter {
  Future<BlockCommandResult> blockUser(BlockUserCommand command);

  Future<BlockCommandResult> unblockUser(UnblockUserCommand command);
}

abstract interface class BlockedListQuery {
  Future<BlockedUserSlice> listBlockedUsers(ListBlockedUsersQuery query);
}

abstract interface class RelationshipCapabilityQuery {
  Future<RelationshipCapabilityResult> getRelationshipCapability(
    GetRelationshipCapabilityQuery query,
  );
}



abstract interface class ProfileRelationshipListQuery {
  Future<ProfileRelationshipSlice> listFollowing(
    ProfileRelationshipPageQuery query,
  );

  Future<ProfileRelationshipSlice> listFollowers(
    ProfileRelationshipPageQuery query,
  );
}







final class FollowCommandResult {
  const FollowCommandResult({
    required this.actorPersonaId,
    required this.targetPersonaId,
    required this.relationState,
    required this.idempotentReplay,
    required this.updatedAt,
  });

  final String actorPersonaId;
  final String targetPersonaId;
  final String relationState;
  final bool idempotentReplay;
  final DateTime updatedAt;
}







final class BlockCommandResult {
  const BlockCommandResult({
    required this.targetPersonaId,
    required this.blocked,
    required this.idempotentReplay,
    required this.updatedAt,
  });

  final String targetPersonaId;
  final bool blocked;
  final bool idempotentReplay;
  final DateTime updatedAt;
}

final class BlockedUserListItem {
  const BlockedUserListItem({
    required this.targetPersonaId,
    required this.displayName,
    required this.userHandle,
    required this.avatarUrl,
    required this.blockedAt,
  });

  final String targetPersonaId;
  final String displayName;
  final String userHandle;
  final String avatarUrl;
  final DateTime blockedAt;
}

final class BlockedUserSlice {
  const BlockedUserSlice({required this.items, this.nextCursor});

  final List<BlockedUserListItem> items;
  final String? nextCursor;
}

final class RelationshipCapabilityResult {
  const RelationshipCapabilityResult({
    required this.viewerPersonaId,
    required this.targetPersonaId,
    required this.relationState,
    required this.canFollow,
    required this.canUnfollow,
    required this.canFollowBack,
    required this.canGreet,
    required this.canOpenConversation,
    required this.canCreateDirectConversation,
    required this.canSendMessage,
    required this.hasPendingGreeting,
    required this.hasFormalConversation,
    required this.canStartVoiceCall,
    required this.canStartVideoCall,
    required this.isBlocked,
    required this.isBlockedBy,
  });

  final String viewerPersonaId;
  final String targetPersonaId;
  final String relationState;
  final bool canFollow;
  final bool canUnfollow;
  final bool canFollowBack;
  final bool canGreet;
  final bool canOpenConversation;
  final bool canCreateDirectConversation;
  final bool canSendMessage;
  final bool hasPendingGreeting;
  final bool hasFormalConversation;
  final bool canStartVoiceCall;
  final bool canStartVideoCall;
  final bool isBlocked;
  final bool isBlockedBy;
}

final class PersonaRelationshipListItem {
  const PersonaRelationshipListItem({
    required this.personaId,
    required this.username,
    required this.userHandle,
    required this.displayName,
    required this.avatarUrl,
    required this.profileVisibility,
    required this.relationState,
    required this.followedAt,
    this.relationshipCapability,
  });

  final String personaId;
  final String username;
  final String userHandle;
  final String displayName;
  final String avatarUrl;
  final String profileVisibility;
  final String relationState;
  final DateTime? followedAt;
  final RelationshipCapabilityResult? relationshipCapability;
}

final class PersonaRelationshipPage {
  const PersonaRelationshipPage({required this.items, this.nextCursor});

  final List<PersonaRelationshipListItem> items;
  final String? nextCursor;
}

final class ProfileRelationshipPageQuery {
  ProfileRelationshipPageQuery({
    required String personaId,
    this.query,
    this.cursor,
    this.limit = 20,
  }) : personaId = _required(personaId, 'personaId');

  final String personaId;
  final String? query;
  final String? cursor;
  final int limit;
}

final class ProfileRelationshipListItem {
  const ProfileRelationshipListItem({
    required this.personaId,
    required this.displayName,
    required this.relationState,
    this.username = '',
    this.userHandle = '',
    this.avatarUrl = '',
    this.profileVisibility = 'public',
    this.followedAt,
    this.relationshipCapability,
  });

  final String personaId;
  final String username;
  final String userHandle;
  final String displayName;
  final String avatarUrl;
  final String profileVisibility;
  final String relationState;
  final DateTime? followedAt;
  final RelationshipCapabilityResult? relationshipCapability;
}

final class ProfileRelationshipSlice {
  const ProfileRelationshipSlice({required this.items, this.nextCursor});

  final List<ProfileRelationshipListItem> items;
  final String? nextCursor;
}





FollowCommandResult decodeFollowCommandResult(Object? response) {
  final root = _object(response, 'FollowCommandResult');
  return FollowCommandResult(
    actorPersonaId: _requiredField(root, 'actorPersonaId'),
    targetPersonaId: _requiredField(root, 'targetPersonaId'),
    relationState: _requiredField(root, 'relationState'),
    idempotentReplay: _requiredBool(root, 'idempotentReplay'),
    updatedAt: _requiredTimestamp(root, 'updatedAt'),
  );
}











CloudOperationRequestPayload encodeProfileRelationshipPageQuery(
  ProfileRelationshipPageQuery query,
) {
  final search = query.query?.trim() ?? '';
  final cursor = query.cursor?.trim() ?? '';
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{'personaId': query.personaId},
    queryParameters: <String, String>{
      if (search.isNotEmpty) 'query': search,
      if (cursor.isNotEmpty) 'cursor': cursor,
      'limit': '${query.limit.clamp(1, 100)}',
    },
  );
}

BlockCommandResult decodeBlockCommandResult(Object? response) {
  final root = _object(response, 'BlockCommandResult');
  return BlockCommandResult(
    targetPersonaId: _requiredField(root, 'targetPersonaId'),
    blocked: _requiredBool(root, 'blocked'),
    idempotentReplay: _requiredBool(root, 'idempotentReplay'),
    updatedAt: _requiredTimestamp(root, 'updatedAt'),
  );
}

BlockedUserSlice decodeBlockedUserSlice(Object? response) {
  final root = _object(response, 'BlockedUserSlice');
  final rawItems = root['items'];
  if (rawItems is! List<Object?>) {
    throw const FormatException('BlockedUserSlice.items must be a JSON array');
  }
  final items = rawItems
      .map((raw) {
        final item = _object(raw, 'BlockedUserListItem');
        return BlockedUserListItem(
          targetPersonaId: _requiredField(item, 'targetPersonaId'),
          displayName: _requiredField(item, 'displayName'),
          userHandle: _requiredField(item, 'userHandle'),
          avatarUrl: _optionalString(item['avatarUrl']),
          blockedAt: _requiredTimestamp(item, 'blockedAt'),
        );
      })
      .toList(growable: false);
  final nextCursor = _optionalString(root['nextCursor']);
  return BlockedUserSlice(
    items: items,
    nextCursor: nextCursor.isEmpty ? null : nextCursor,
  );
}

RelationshipCapabilityResult decodeRelationshipCapabilityResult(
  Object? response,
) {
  final root = _object(response, 'RelationshipCapabilityResult');
  return RelationshipCapabilityResult(
    viewerPersonaId: _requiredField(root, 'viewerPersonaId'),
    targetPersonaId: _requiredField(root, 'targetPersonaId'),
    relationState: _requiredField(root, 'relationState'),
    canFollow: _requiredBool(root, 'canFollow'),
    canUnfollow: _requiredBool(root, 'canUnfollow'),
    canFollowBack: _requiredBool(root, 'canFollowBack'),
    canGreet: _requiredBool(root, 'canGreet'),
    canOpenConversation: _requiredBool(root, 'canOpenConversation'),
    canCreateDirectConversation: _requiredBool(
      root,
      'canCreateDirectConversation',
    ),
    canSendMessage: _requiredBool(root, 'canSendMessage'),
    hasPendingGreeting: _requiredBool(root, 'hasPendingGreeting'),
    hasFormalConversation: _requiredBool(root, 'hasFormalConversation'),
    canStartVoiceCall: _requiredBool(root, 'canStartVoiceCall'),
    canStartVideoCall: _requiredBool(root, 'canStartVideoCall'),
    isBlocked: _requiredBool(root, 'isBlocked'),
    isBlockedBy: _requiredBool(root, 'isBlockedBy'),
  );
}

PersonaRelationshipPage decodePersonaRelationshipPage(Object? response) {
  final root = _object(response, 'PersonaRelationshipPage');
  final rawItems = root['items'];
  if (rawItems is! List<Object?>) {
    throw const FormatException(
      'PersonaRelationshipPage.items must be a JSON array',
    );
  }
  final nextCursor = _optionalString(root['nextCursor']);
  final cursor = nextCursor.isEmpty
      ? _optionalString(root['cursor'])
      : nextCursor;
  return PersonaRelationshipPage(
    items: rawItems
        .map<PersonaRelationshipListItem>((raw) {
          final item = _object(raw, 'PersonaRelationshipListItem');
          final capability = item['relationshipCapability'];
          return PersonaRelationshipListItem(
            personaId: _requiredField(item, 'personaId'),
            username: _optionalString(item['username']),
            userHandle: _optionalString(item['userHandle']),
            displayName: _requiredField(item, 'displayName'),
            avatarUrl: _optionalString(item['avatarUrl']),
            profileVisibility:
                _optionalString(item['profileVisibility']).isEmpty
                ? 'public'
                : _optionalString(item['profileVisibility']),
            relationState: _requiredField(item, 'relationState'),
            followedAt: _optionalTimestamp(item['followedAt']),
            relationshipCapability: capability == null
                ? null
                : decodeRelationshipCapabilityResult(capability),
          );
        })
        .toList(growable: false),
    nextCursor: cursor.isEmpty ? null : cursor,
  );
}

ProfileRelationshipSlice decodeProfileRelationshipSlice(Object? response) {
  final root = _object(response, 'ProfileRelationshipSlice');
  final rawItems = root['items'];
  if (rawItems is! List<Object?>) {
    throw const FormatException(
      'ProfileRelationshipSlice.items must be a JSON array',
    );
  }
  return ProfileRelationshipSlice(
    items: rawItems
        .map((raw) {
          final item = _object(raw, 'ProfileRelationshipListItem');
          final rawCapability = item['relationshipCapability'];
          return ProfileRelationshipListItem(
            personaId: _requiredField(item, 'personaId'),
            username: _optionalString(item['username']),
            userHandle: _optionalString(item['userHandle']),
            displayName: _requiredField(item, 'displayName'),
            avatarUrl: _optionalString(item['avatarUrl']),
            profileVisibility:
                _optionalString(item['profileVisibility']).isEmpty
                ? 'public'
                : _optionalString(item['profileVisibility']),
            relationState: _requiredField(item, 'relationState'),
            followedAt: _optionalTimestamp(item['followedAt']),
            relationshipCapability: rawCapability is Map<Object?, Object?>
                ? decodeRelationshipCapabilityResult(rawCapability)
                : null,
          );
        })
        .toList(growable: false),
    nextCursor: _optionalString(root['nextCursor']).isEmpty
        ? null
        : _optionalString(root['nextCursor']),
  );
}

Map<Object?, Object?> _object(Object? value, String name) {
  if (value is! Map<Object?, Object?>) {
    throw FormatException('$name must be a JSON object');
  }
  return value;
}

String _requiredField(Map<Object?, Object?> root, String key) {
  final value = _optionalString(root[key]);
  if (value.isEmpty) {
    throw FormatException('missing required field "$key"');
  }
  return value;
}

bool _requiredBool(Map<Object?, Object?> root, String key) {
  final value = root[key];
  if (value is! bool) {
    throw FormatException('field "$key" must be a bool');
  }
  return value;
}

DateTime _requiredTimestamp(Map<Object?, Object?> root, String key) {
  final value = _requiredField(root, key);
  return DateTime.parse(value).toUtc();
}

DateTime? _optionalTimestamp(Object? value) {
  final text = _optionalString(value);
  return text.isEmpty ? null : DateTime.parse(text).toUtc();
}

String _optionalString(Object? value) {
  return value is String ? value.trim() : '';
}

String _required(String value, String name) {
  final text = value.trim();
  if (text.isEmpty) {
    throw ArgumentError.value(value, name, 'must not be empty');
  }
  return text;
}
