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
  Future<ContentProfileInteractionPage> listActivities(
    ContentProfileInteractionPageQuery query, {
    required ContentProfileInteractionDirection direction,
  }) {
    return switch (direction) {
      ContentProfileInteractionDirection.received => _listReceived(query),
      ContentProfileInteractionDirection.sent => _listSent(query),
    };
  }

  Future<ContentProfileInteractionPage> _listReceived(
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

  Future<ContentProfileInteractionPage> _listSent(
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
  Future<ContentProfileInteractionReadFactAck> appendReadFact(
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
            'profile-read:${command.subAccountId}:${command.activityId}:${command.state.wireValue}',
      ),
    );
    // dart format on
  }
}
