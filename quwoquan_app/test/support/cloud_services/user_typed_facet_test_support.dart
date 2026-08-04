import 'package:quwoquan_app/cloud/services/user/greeting_repository.dart';
import 'package:quwoquan_app/cloud/services/user/relationship_capability_repository.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import 'object_doubles/user/alpha_greeting_request_facets.dart';

/// Chat/User widget contracts use an explicit authenticated identity instead
/// of relying on the production session store or an anonymous default.
final class TestAuthenticatedSessionController extends AuthSessionController {
  @override
  AuthSessionState build() => const AuthSessionState(
    status: AuthSessionStatus.authenticated,
    accessToken: 'test-access-token',
    refreshToken: 'test-refresh-token',
    ownerId: 'fixture_user_current',
    activePersonaId: 'fixture_user_current',
    accountState: 'active',
    identityOrigin: 'phone',
    installId: 'test-install-id',
  );
}

RemoteGreetingRepository alphaGreetingRepository({
  String requesterPersonaId = 'fixture_user_current',
  Iterable<GreetingRequestRecord> seedInbox = const <GreetingRequestRecord>[],
  Iterable<GreetingRequestRecord> seedOutbox = const <GreetingRequestRecord>[],
}) {
  final facet = AlphaGreetingRequestFacet(
    requesterPersonaId: requesterPersonaId,
    seedInbox: seedInbox,
    seedOutbox: seedOutbox,
  );
  return RemoteGreetingRepository(commandWriter: facet, query: facet);
}

RelationshipCapabilityRepository relationshipCapabilityRepositoryFrom(
  RelationshipCapabilityQuery query, {
  bool reconcilesWithSharedRelationshipState = false,
}) {
  if (reconcilesWithSharedRelationshipState) {
    return _ReconciledRelationshipCapabilityRepository(query);
  }
  return RemoteRelationshipCapabilityRepository(query: query);
}

RelationshipCapabilityRepository mutualRelationshipCapabilityRepository() {
  return relationshipCapabilityRepositoryFrom(
    const TestRelationshipCapabilityQuery.mutual(),
  );
}

/// 仅为 Widget/UAT 注入稳定能力位的 typed query fake。
final class TestRelationshipCapabilityQuery
    implements RelationshipCapabilityQuery {
  const TestRelationshipCapabilityQuery.mutual()
    : _preset = _RelationshipCapabilityPreset.mutual;

  const TestRelationshipCapabilityQuery.notFollowing()
    : _preset = _RelationshipCapabilityPreset.notFollowing;

  final _RelationshipCapabilityPreset _preset;

  @override
  Future<RelationshipCapabilityView> getRelationshipCapability(
    GetRelationshipCapabilityQuery query,
  ) async {
    return switch (_preset) {
      _RelationshipCapabilityPreset.mutual => RelationshipCapabilityView(
        viewerPersonaId: 'fixture_user_current',
        targetPersonaId: query.targetPersonaId,
        relationState: RelationshipState.mutual,
        canFollow: false,
        canUnfollow: true,
        canFollowBack: false,
        canGreet: false,
        canOpenConversation: true,
        canCreateDirectConversation: true,
        canSendMessage: true,
        hasPendingGreeting: false,
        hasFormalConversation: true,
        canStartVoiceCall: true,
        canStartVideoCall: true,
        isBlocked: false,
        isBlockedBy: false,
      ),
      _RelationshipCapabilityPreset.notFollowing => RelationshipCapabilityView(
        viewerPersonaId: 'fixture_user_current',
        targetPersonaId: query.targetPersonaId,
        relationState: RelationshipState.notFollowing,
        canFollow: true,
        canUnfollow: false,
        canFollowBack: false,
        canGreet: true,
        canOpenConversation: false,
        canCreateDirectConversation: false,
        canSendMessage: false,
        hasPendingGreeting: false,
        hasFormalConversation: false,
        canStartVoiceCall: false,
        canStartVideoCall: false,
        isBlocked: false,
        isBlockedBy: false,
      ),
    };
  }
}

final class _ReconciledRelationshipCapabilityRepository
    implements RelationshipCapabilityRepository {
  const _ReconciledRelationshipCapabilityRepository(this.query);

  final RelationshipCapabilityQuery query;

  @override
  bool get reconcilesCapabilityWithSharedRelationshipState => true;

  @override
  Future<RelationshipCapabilityViewData> getCapability(
    String targetUserId,
  ) async {
    final result = await query.getRelationshipCapability(
      GetRelationshipCapabilityQuery(targetPersonaId: targetUserId),
    );
    return RelationshipCapabilityViewData.fromWire(result);
  }
}

enum _RelationshipCapabilityPreset { mutual, notFollowing }
