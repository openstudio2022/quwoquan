import 'package:quwoquan_app/cloud/runtime/generated/user/user_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef PersonaRelationshipInvocationContextFactory =
    CloudOperationInvocationContext Function(String clientPageId);

/// PersonaRelationship 拉黑命令与列表查询的 production Remote adapter。
/// path/auth/retry/idempotency/decoder 全部由 generated client 承担。
final class RemotePersonaRelationshipFacet
    implements
        BlockCommandWriter,
        BlockedListQuery,
        RelationshipCapabilityQuery {
  const RemotePersonaRelationshipFacet({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final PersonaRelationshipInvocationContextFactory invocationContext;

  @override
  Future<BlockCommandResult> blockUser(BlockUserCommand command) {
    return client.userPersonaRelationshipBlockUser(
      command,
      context: invocationContext(UserRequestPageIds.blockUser),
    );
  }

  @override
  Future<BlockCommandResult> unblockUser(UnblockUserCommand command) {
    return client.userPersonaRelationshipUnblockUser(
      command,
      context: invocationContext(UserRequestPageIds.unblockUser),
    );
  }

  @override
  Future<BlockedUserSlice> listBlockedUsers(ListBlockedUsersQuery query) {
    return client.userPersonaRelationshipListBlockedUsers(
      query,
      context: invocationContext(UserRequestPageIds.listBlockedUsers),
    );
  }

  @override
  Future<RelationshipCapabilityResult> getRelationshipCapability(
    GetRelationshipCapabilityQuery query,
  ) {
    return client.userPersonaRelationshipGetRelationshipCapability(
      query,
      context: invocationContext(UserRequestPageIds.getRelationshipCapability),
    );
  }
}
