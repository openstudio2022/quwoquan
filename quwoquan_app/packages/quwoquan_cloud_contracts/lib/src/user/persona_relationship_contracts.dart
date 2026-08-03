import 'user_operation_contracts.g.dart';

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
  Future<RelationshipCapabilityView> getRelationshipCapability(
    GetRelationshipCapabilityQuery query,
  );
}

abstract interface class ProfileRelationshipListQuery {
  Future<FollowingRelationshipPageSlice> listFollowing(
    PersonaRelationshipListQuery query,
  );
  Future<FollowerRelationshipPageSlice> listFollowers(
    PersonaRelationshipListQuery query,
  );
}
