import 'package:quwoquan_app/service/user_service/relationship/persona_relationship/application/persona_relationship_facets.dart';
import 'package:quwoquan_app/runtime/transport/generated/user/user_request_page_ids.g.dart';
import 'package:quwoquan_app/runtime/transport/models/cursor_page.dart';
import 'package:quwoquan_app/service/user_service/relationship/persona_relationship/application/persona_relationship_view_data.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:uuid/uuid.dart';

typedef PersonaRelationshipInvocationContextFactory =
    CloudOperationInvocationContext Function(
      String clientPageId,
      String canonicalOperationId,
    );

/// PersonaRelationship 关注命令与列表查询的 production Remote adapter。
/// path/auth/retry/idempotency/decoder 全部由 generated client 承担。
final class RemotePersonaRelationshipFollowAdapter
    implements
        PersonaRelationshipQuery,
        PersonaRelationshipCommandWriter,
        PersonaRelationshipDurableCommandWriter {
  const RemotePersonaRelationshipFollowAdapter({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final PersonaRelationshipInvocationContextFactory invocationContext;

  @override
  Future<void> follow(
    String targetPersonaId, {
    required String sourceSurfaceId,
  }) async {
    final b = await getMutationBasis(targetPersonaId);
    await followWithEvidence(
      b.targetPersonaId,
      sourceSurfaceId: sourceSurfaceId,
      evidence: PersonaRelationshipMutationEvidence(
        idempotencyKey: const Uuid().v4(),
        mutationBasis: b.mutationBasis,
        expectedVersion: b.expectedVersion,
      ),
    );
  }

  @override
  Future<void> unfollow(String targetPersonaId) async {
    final b = await getMutationBasis(targetPersonaId);
    await unfollowWithEvidence(
      b.targetPersonaId,
      evidence: PersonaRelationshipMutationEvidence(
        idempotencyKey: const Uuid().v4(),
        mutationBasis: b.mutationBasis,
        expectedVersion: b.expectedVersion,
      ),
    );
  }

  @override
  Future<PersonaRelationshipMutationBasisSlice> getMutationBasis(
    String targetPersonaId,
  ) {
    return client.userPersonaRelationshipGetRelationshipMutationBasis(
      GetRelationshipCapabilityQuery(targetPersonaId: targetPersonaId),
      context: invocationContext(
        UserRequestPageIds.getRelationshipMutationBasis,
        AppCloudOperationIds
            .userPersonaRelationshipGetRelationshipMutationBasis,
      ),
    );
  }

  @override
  Future<FollowCommandResult> followWithEvidence(
    String targetPersonaId, {
    required String sourceSurfaceId,
    required PersonaRelationshipMutationEvidence evidence,
  }) {
    return client.userPersonaRelationshipFollowUser(
      FollowUserCommand(
        targetPersonaId: targetPersonaId,
        source: sourceSurfaceId,
        mutationBasis: evidence.mutationBasis,
        expectedVersion: evidence.expectedVersion,
      ),
      context: _withIdempotency(
        invocationContext(
          UserRequestPageIds.followUser,
          AppCloudOperationIds.userPersonaRelationshipFollowUser,
        ),
        evidence.idempotencyKey,
      ),
    );
  }

  @override
  Future<FollowCommandResult> unfollowWithEvidence(
    String targetPersonaId, {
    required PersonaRelationshipMutationEvidence evidence,
  }) {
    return client.userPersonaRelationshipUnfollowUser(
      UnfollowUserCommand(
        targetPersonaId: targetPersonaId,
        mutationBasis: evidence.mutationBasis,
        expectedVersion: evidence.expectedVersion,
      ),
      context: _withIdempotency(
        invocationContext(
          UserRequestPageIds.unfollowUser,
          AppCloudOperationIds.userPersonaRelationshipUnfollowUser,
        ),
        evidence.idempotencyKey,
      ),
    );
  }

  @override
  Future<PersonaRelationshipCommandRecoverySlice> recover(
    String targetPersonaId, {
    required PersonaRelationshipMutationAction operation,
    required String idempotencyKey,
  }) {
    return client.userPersonaRelationshipRecoverRelationshipCommand(
      RecoverRelationshipCommandQuery(
        targetPersonaId: targetPersonaId,
        operation: operation,
      ),
      context: _withIdempotency(
        invocationContext(
          UserRequestPageIds.recoverRelationshipCommand,
          AppCloudOperationIds
              .userPersonaRelationshipRecoverRelationshipCommand,
        ),
        idempotencyKey,
      ),
    );
  }

  @override
  Future<PersonaRelationshipCommandRecoverySlice> finalizeExpired(
    String targetPersonaId, {
    required PersonaRelationshipMutationAction operation,
    required PersonaRelationshipMutationEvidence evidence,
  }) {
    return client.userPersonaRelationshipFinalizeExpiredRelationshipCommand(
      FinalizeExpiredRelationshipCommand(
        targetPersonaId: targetPersonaId,
        operation: operation,
        mutationBasis: evidence.mutationBasis,
        expectedVersion: evidence.expectedVersion,
      ),
      context: _withIdempotency(
        invocationContext(
          UserRequestPageIds.finalizeExpiredRelationshipCommand,
          AppCloudOperationIds
              .userPersonaRelationshipFinalizeExpiredRelationshipCommand,
        ),
        evidence.idempotencyKey,
      ),
    );
  }

  @override
  Future<CursorPage<ProfileSocialRelationRowViewData>> listFollowing({
    required String personaId,
    String? query,
    String? cursor,
    int limit = PersonaRelationshipListQuery.defaultLimit,
  }) async {
    final page = await client.userPersonaRelationshipListFollowing(
      PersonaRelationshipListQuery(
        personaId: personaId,
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
          .map(ProfileSocialRelationRowViewData.fromFollowingWire)
          .toList(growable: false),
      nextCursor: page.nextCursor,
    );
  }

  @override
  Future<CursorPage<ProfileSocialRelationRowViewData>> listFollowers({
    required String personaId,
    String? query,
    String? cursor,
    int limit = PersonaRelationshipListQuery.defaultLimit,
  }) async {
    final page = await client.userPersonaRelationshipListFollowers(
      PersonaRelationshipListQuery(
        personaId: personaId,
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
          .map(ProfileSocialRelationRowViewData.fromFollowerWire)
          .toList(growable: false),
      nextCursor: page.nextCursor,
    );
  }

  CloudOperationInvocationContext _withIdempotency(
    CloudOperationInvocationContext base,
    String key,
  ) => CloudOperationInvocationContext(
    surfaceId: base.surfaceId,
    clientPageId: base.clientPageId,
    routeId: base.routeId,
    actor: base.actor,
    referralSource: base.referralSource,
    feedRequestId: base.feedRequestId,
    shareId: base.shareId,
    modelId: base.modelId,
    experimentBucket: base.experimentBucket,
    idempotencyKey: key,
    deadlineAt: base.deadlineAt,
    cancellation: base.cancellation,
  );
}
