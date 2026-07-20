import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../alpha_fixture_seed_reader.dart';

/// Alpha-only PersonaRelationship 拉黑 Facet。
/// production 依赖图不可达本文件；命令与列表共享一份有状态集合。
final class AlphaPersonaRelationshipFacet
    implements
        BlockCommandWriter,
        BlockedListQuery,
        RelationshipCapabilityQuery {
  AlphaPersonaRelationshipFacet({
    this.viewerSubAccountId = 'fixture_user_current',
    AlphaFixtureSeedReader? fixtures,
  }) : _relationshipRows = _loadRelationships(
         fixtures ?? alphaFixtureSeedReader,
       );

  final String viewerSubAccountId;
  final Map<String, Map<String, Object?>> _relationshipRows;
  final Map<String, BlockedUserListItem> _blocked =
      <String, BlockedUserListItem>{};

  static Map<String, Map<String, Object?>> _loadRelationships(
    AlphaFixtureSeedReader fixtures,
  ) {
    final seed = fixtures.requireSeedSet('user', 'relationship_core');
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
    final replayed = _blocked.containsKey(command.targetSubAccountId);
    _blocked.putIfAbsent(
      command.targetSubAccountId,
      () => BlockedUserListItem(
        targetSubAccountId: command.targetSubAccountId,
        displayName: command.targetSubAccountId,
        userHandle: '',
        avatarUrl: '',
        blockedAt: now,
      ),
    );
    return BlockCommandResult(
      targetSubAccountId: command.targetSubAccountId,
      blocked: true,
      idempotentReplay: replayed,
      updatedAt: now,
    );
  }

  @override
  Future<BlockCommandResult> unblockUser(UnblockUserCommand command) async {
    final now = DateTime.now().toUtc();
    final removed = _blocked.remove(command.targetSubAccountId) != null;
    return BlockCommandResult(
      targetSubAccountId: command.targetSubAccountId,
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
  Future<RelationshipCapabilityResult> getRelationshipCapability(
    GetRelationshipCapabilityQuery query,
  ) async {
    final target = query.targetSubAccountId;
    final row = _relationshipRows[target];
    final isSelf = target == viewerSubAccountId;
    final isBlocked = _blocked.containsKey(target) || row?['blocked'] == true;
    final isFollowing = row?['following'] == true;
    final isFollowedBy = row?['mutualFollow'] == true;
    final isMutual = isFollowing && isFollowedBy;
    final relationState = isSelf
        ? 'self'
        : isMutual
        ? 'mutual'
        : isFollowing
        ? 'following'
        : isFollowedBy
        ? 'followed_by'
        : 'not_following';
    final hasFormalConversation = row?['canChat'] == true && !isMutual;
    final canCreateDirectConversation = !isBlocked && isMutual;
    final canSendMessage =
        !isBlocked && (isMutual || hasFormalConversation);
    final hasPendingGreeting = row?['hasPendingGreeting'] == true;
    return RelationshipCapabilityResult(
      viewerSubAccountId: viewerSubAccountId,
      targetSubAccountId: target,
      relationState: relationState,
      canFollow:
          !isBlocked &&
          !isSelf &&
          (relationState == 'not_following' ||
              relationState == 'followed_by'),
      canUnfollow:
          !isBlocked &&
          (relationState == 'following' || relationState == 'mutual'),
      canFollowBack: !isBlocked && relationState == 'followed_by',
      canGreet:
          !isBlocked &&
          !isSelf &&
          !isMutual &&
          !hasPendingGreeting &&
          !hasFormalConversation,
      canOpenConversation:
          canCreateDirectConversation || hasFormalConversation,
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
