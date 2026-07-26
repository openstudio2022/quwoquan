import 'package:quwoquan_app/application/user/persona_relationship/persona_relationship_facets.dart';
import 'package:quwoquan_app/cloud/runtime/generated/cloud_api_defaults.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/models/cursor_page.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef PersonaRelationshipInvocationContextFactory =
    CloudOperationInvocationContext Function(
      String clientPageId,
      String canonicalOperationId,
    );

/// PersonaRelationship 关注命令与列表查询的 production Remote adapter。
/// path/auth/retry/idempotency/decoder 全部由 generated client 承担。
final class RemotePersonaRelationshipFollowAdapter
    implements PersonaRelationshipQuery, PersonaRelationshipCommandWriter {
  const RemotePersonaRelationshipFollowAdapter({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final PersonaRelationshipInvocationContextFactory invocationContext;

  @override
  Future<void> follow(
    String targetSubAccountId, {
    required String sourceSurfaceId,
  }) async {
    await client.userPersonaRelationshipFollowUser(
      FollowUserCommand(
        targetSubAccountId: targetSubAccountId,
        source: sourceSurfaceId,
      ),
      context: invocationContext(
        UserRequestPageIds.followUser,
        AppCloudOperationIds.userPersonaRelationshipFollowUser,
      ),
    );
  }

  @override
  Future<void> unfollow(String targetSubAccountId) async {
    await client.userPersonaRelationshipUnfollowUser(
      UnfollowUserCommand(targetSubAccountId: targetSubAccountId),
      context: invocationContext(
        UserRequestPageIds.unfollowUser,
        AppCloudOperationIds.userPersonaRelationshipUnfollowUser,
      ),
    );
  }

  @override
  Future<CursorPage<ProfileSocialRelationRowViewData>> listFollowing({
    required String subAccountId,
    String? query,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final page = await client.userPersonaRelationshipListFollowing(
      PersonaRelationshipListQuery(
        subAccountId: subAccountId,
        query: query,
        cursor: cursor,
        limit: limit,
      ),
      context: invocationContext(
        UserRequestPageIds.listFollowing,
        AppCloudOperationIds.userPersonaRelationshipListFollowing,
      ),
    );
    return CursorPage<ProfileSocialRelationRowViewData>(
      items: page.items
          .map(ProfileSocialRelationRowViewData.fromPersonaRelationshipListItem)
          .toList(growable: false),
      nextCursor: page.nextCursor,
    );
  }

  @override
  Future<CursorPage<ProfileSocialRelationRowViewData>> listFollowers({
    required String subAccountId,
    String? query,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final page = await client.userPersonaRelationshipListFollowers(
      PersonaRelationshipListQuery(
        subAccountId: subAccountId,
        query: query,
        cursor: cursor,
        limit: limit,
      ),
      context: invocationContext(
        UserRequestPageIds.listFollowers,
        AppCloudOperationIds.userPersonaRelationshipListFollowers,
      ),
    );
    return CursorPage<ProfileSocialRelationRowViewData>(
      items: page.items
          .map(ProfileSocialRelationRowViewData.fromPersonaRelationshipListItem)
          .toList(growable: false),
      nextCursor: page.nextCursor,
    );
  }
}
