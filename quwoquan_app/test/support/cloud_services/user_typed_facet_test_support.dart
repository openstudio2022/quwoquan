import 'package:quwoquan_app/cloud/services/user/greeting_repository.dart';
import 'package:quwoquan_app/cloud/services/user/relationship_capability_repository.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_cloud_mock/quwoquan_cloud_mock.dart';

RemoteGreetingRepository alphaGreetingRepository({
  String requesterSubAccountId = 'fixture_user_current',
  Iterable<GreetingRequestRecord> seedInbox = const <GreetingRequestRecord>[],
  Iterable<GreetingRequestRecord> seedOutbox = const <GreetingRequestRecord>[],
}) {
  final facet = AlphaGreetingRequestFacet(
    requesterSubAccountId: requesterSubAccountId,
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
  Future<RelationshipCapabilityResult> getRelationshipCapability(
    GetRelationshipCapabilityQuery query,
  ) async {
    return switch (_preset) {
      _RelationshipCapabilityPreset.mutual => RelationshipCapabilityResult(
        viewerSubAccountId: 'fixture_user_current',
        targetSubAccountId: query.targetSubAccountId,
        relationState: 'mutual',
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
      _RelationshipCapabilityPreset.notFollowing =>
        RelationshipCapabilityResult(
          viewerSubAccountId: 'fixture_user_current',
          targetSubAccountId: query.targetSubAccountId,
          relationState: 'not_following',
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
  Future<RelationshipCapabilityDto> getCapability(String targetUserId) async {
    final result = await query.getRelationshipCapability(
      GetRelationshipCapabilityQuery(targetSubAccountId: targetUserId),
    );
    return RelationshipCapabilityDto.fromContract(result);
  }
}

enum _RelationshipCapabilityPreset { mutual, notFollowing }
