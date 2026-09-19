import 'package:quwoquan_app/runtime/transport/models/cursor_page.dart';
import 'package:quwoquan_app/service/user_service/relationship/persona_relationship/application/persona_relationship_view_data.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

final class PersonaRelationshipMutationEvidence {
  const PersonaRelationshipMutationEvidence({
    required this.idempotencyKey,
    required this.mutationBasis,
    required this.expectedVersion,
  });
  final String idempotencyKey;
  final String mutationBasis;
  final int expectedVersion;
}

/// Convenience command surface. Production UI actions use the shared state
/// coordinator; this interface remains narrow for legacy composition/test doubles.
abstract interface class PersonaRelationshipCommandWriter {
  Future<void> follow(
    String targetPersonaId, {
    required String sourceSurfaceId,
  });
  Future<void> unfollow(String targetPersonaId);
}

/// Durable command protocol consumed only by ClientStateSyncOutbox.
abstract interface class PersonaRelationshipDurableCommandWriter {
  Future<PersonaRelationshipMutationBasisSlice> getMutationBasis(
    String targetPersonaId,
  );
  Future<FollowCommandResult> followWithEvidence(
    String targetPersonaId, {
    required String sourceSurfaceId,
    required PersonaRelationshipMutationEvidence evidence,
  });
  Future<FollowCommandResult> unfollowWithEvidence(
    String targetPersonaId, {
    required PersonaRelationshipMutationEvidence evidence,
  });
  Future<PersonaRelationshipCommandRecoverySlice> recover(
    String targetPersonaId, {
    required PersonaRelationshipMutationAction operation,
    required String idempotencyKey,
  });
  Future<PersonaRelationshipCommandRecoverySlice> finalizeExpired(
    String targetPersonaId, {
    required PersonaRelationshipMutationAction operation,
    required PersonaRelationshipMutationEvidence evidence,
  });
}

abstract interface class PersonaRelationshipQuery {
  Future<CursorPage<ProfileSocialRelationRowViewData>> listFollowing({
    required String personaId,
    String? query,
    String? cursor,
    int limit = PersonaRelationshipListQuery.defaultLimit,
  });
  Future<CursorPage<ProfileSocialRelationRowViewData>> listFollowers({
    required String personaId,
    String? query,
    String? cursor,
    int limit = PersonaRelationshipListQuery.defaultLimit,
  });
}
