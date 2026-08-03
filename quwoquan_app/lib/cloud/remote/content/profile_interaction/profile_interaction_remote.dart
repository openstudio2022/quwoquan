import 'package:quwoquan_app/cloud/runtime/generated/content/content_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef ProfileInteractionInvocationContextFactory =
    CloudOperationInvocationContext Function(String clientPageId);

final class RemoteProfileInteractionAdapter
    implements
        ContentProfileInteractionQueryFacet,
        ContentProfileInteractionReadFactAppendFacet {
  const RemoteProfileInteractionAdapter({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final ProfileInteractionInvocationContextFactory invocationContext;

  @override
  Future<ProfileInteractionActivityPageSlice> listActivities(
    ContentProfileInteractionPageQuery query, {
    required InteractionDirection direction,
  }) {
    return switch (direction) {
      InteractionDirection.received => _listReceived(query),
      InteractionDirection.sent => _listSent(query),
    };
  }

  Future<ProfileInteractionActivityPageSlice> _listReceived(
    ContentProfileInteractionPageQuery query,
  ) {
    final client = this.client;
    // dart format off
    return client.contentProfileInteractionActivityViewListProfileInteractionActivitiesReceived(
      query,
      context: invocationContext(
        ContentRequestPageIds.listProfileInteractionActivitiesReceived,
      ),
    );
    // dart format on
  }

  Future<ProfileInteractionActivityPageSlice> _listSent(
    ContentProfileInteractionPageQuery query,
  ) {
    final client = this.client;
    // dart format off
    return client.contentProfileInteractionActivityViewListProfileInteractionActivitiesSent(
      query,
      context: invocationContext(
        ContentRequestPageIds.listProfileInteractionActivitiesSent,
      ),
    );
    // dart format on
  }

  @override
  Future<ProfileInteractionReadFactAck> appendReadFact(
    AppendContentProfileInteractionReadFactCommand command,
  ) {
    final client = this.client;
    final base = invocationContext(
      ContentRequestPageIds.updateProfileInteractionState,
    );
    // dart format off
    return client.contentProfileInteractionReadFactUpdateProfileInteractionState(
      command,
      context: CloudOperationInvocationContext(
        surfaceId: base.surfaceId,
        clientPageId: base.clientPageId,
        actor: base.actor,
        routeId: base.routeId,
        referralSource: base.referralSource,
        feedRequestId: base.feedRequestId,
        shareId: base.shareId,
        modelId: base.modelId,
        experimentBucket: base.experimentBucket,
        deadlineAt: base.deadlineAt,
        cancellation: base.cancellation,
        idempotencyKey:
            'profile-read:${command.personaId}:${command.activityId}:${command.state.wireName}',
      ),
    );
    // dart format on
  }
}
