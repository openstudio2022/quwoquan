import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// Alpha-only PersonaRelationship 拉黑 Facet。
/// production 依赖图不可达本文件；命令与列表共享一份有状态集合。
final class InMemoryPersonaRelationshipFacet
    implements
        BlockCommandWriter,
        BlockedListQuery,
        RelationshipCapabilityQuery {
  InMemoryPersonaRelationshipFacet({
    this.viewerPersonaId = 'fixture_user_current',
    Map<String, Object?>? relationshipWireExample,
  }) : _relationshipRows = _loadRelationships(
         relationshipWireExample ?? _relationshipWireExample(),
       );

  final String viewerPersonaId;
  final Map<String, Map<String, Object?>> _relationshipRows;
  final Map<String, BlockedListItemView> _blocked =
      <String, BlockedListItemView>{};

  static Map<String, Map<String, Object?>> _loadRelationships(
    Map<String, Object?> seed,
  ) {
    final rows = seed['relationships'];
    if (rows is! List<Object?>) {
      throw const FormatException(
        'user/relationship_core.relationships must be an array',
      );
    }
    return <String, Map<String, Object?>>{
      for (final raw in rows.whereType<Map<Object?, Object?>>())
        if ((raw['targetUserId']?.toString().trim() ?? '').isNotEmpty)
          raw['targetUserId'].toString(): raw.map(
            (key, value) => MapEntry(key.toString(), value),
          ),
    };
  }

  @override
  Future<BlockCommandResult> blockUser(BlockUserCommand command) async {
    final now = DateTime.now().toUtc();
    final replayed = _blocked.containsKey(command.targetPersonaId);
    _blocked.putIfAbsent(
      command.targetPersonaId,
      () => BlockedListItemView(
        targetPersonaId: command.targetPersonaId,
        displayName: command.targetPersonaId,
        userHandle: '',
        avatarUrl: '',
        blockedAt: now,
      ),
    );
    return BlockCommandResult(
      targetPersonaId: command.targetPersonaId,
      blocked: true,
      idempotentReplay: replayed,
      updatedAt: now,
    );
  }

  @override
  Future<BlockCommandResult> unblockUser(UnblockUserCommand command) async {
    final now = DateTime.now().toUtc();
    final removed = _blocked.remove(command.targetPersonaId) != null;
    return BlockCommandResult(
      targetPersonaId: command.targetPersonaId,
      blocked: false,
      idempotentReplay: !removed,
      updatedAt: now,
    );
  }

  @override
  Future<BlockedUserSlice> listBlockedUsers(ListBlockedUsersQuery query) async {
    final items = _blocked.values.toList(growable: false)
      ..sort((left, right) => right.blockedAt.compareTo(left.blockedAt));
    return BlockedUserSlice(
      items: items.take(query.limit.clamp(1, 100)).toList(growable: false),
    );
  }

  @override
  Future<RelationshipCapabilityView> getRelationshipCapability(
    GetRelationshipCapabilityQuery query,
  ) async {
    final target = query.targetPersonaId;
    final row = _relationshipRows[target];
    final isSelf = target == viewerPersonaId;
    final isBlocked = _blocked.containsKey(target) || row?['blocked'] == true;
    final isFollowing = row?['following'] == true;
    final isFollowedBy = row?['mutualFollow'] == true;
    final isMutual = isFollowing && isFollowedBy;
    final relationState = isSelf
        ? RelationshipState.self
        : isMutual
        ? RelationshipState.mutual
        : isFollowing
        ? RelationshipState.following
        : isFollowedBy
        ? RelationshipState.followedBy
        : RelationshipState.notFollowing;
    final hasFormalConversation = row?['canChat'] == true && !isMutual;
    final canCreateDirectConversation = !isBlocked && isMutual;
    final canSendMessage = !isBlocked && (isMutual || hasFormalConversation);
    final hasPendingGreeting = row?['hasPendingGreeting'] == true;
    return RelationshipCapabilityView(
      viewerPersonaId: viewerPersonaId,
      targetPersonaId: target,
      relationState: relationState,
      canFollow:
          !isBlocked &&
          !isSelf &&
          (relationState == RelationshipState.notFollowing ||
              relationState == RelationshipState.followedBy),
      canUnfollow:
          !isBlocked &&
          (relationState == RelationshipState.following ||
              relationState == RelationshipState.mutual),
      canFollowBack:
          !isBlocked && relationState == RelationshipState.followedBy,
      canGreet:
          !isBlocked &&
          !isSelf &&
          !isMutual &&
          !hasPendingGreeting &&
          !hasFormalConversation,
      canOpenConversation: canCreateDirectConversation || hasFormalConversation,
      canCreateDirectConversation: canCreateDirectConversation,
      canSendMessage: canSendMessage,
      hasPendingGreeting: hasPendingGreeting,
      hasFormalConversation: hasFormalConversation,
      canStartVoiceCall: !isBlocked && isMutual,
      canStartVideoCall: !isBlocked && isMutual,
      isBlocked: isBlocked,
      isBlockedBy: row?['blockedBy'] == true,
    );
  }
}

Map<String, Object?> _relationshipWireExample() => <String, Object?>{
  'relationships':
      const <String>[
            'fixture_user_photo',
            'fixture_user_friend',
            'fixture_user_weekend_1',
          ]
          .map(
            (target) => <String, Object?>{
              'sourceUserId': 'fixture_user_current',
              'targetUserId': target,
              'following': true,
              'mutualFollow': true,
              'blocked': false,
              'canChat': true,
              'canCall': true,
            },
          )
          .toList(growable: false),
};
