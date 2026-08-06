import 'package:quwoquan_app/runtime/transport/generated/content/content_request_page_ids.g.dart';
import 'package:quwoquan_app/service/content_service/content/profile_interaction_activity_view/application/profile_interaction_activity_query.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef ProfileInteractionActivityInvocationContextFactory =
    CloudOperationInvocationContext Function(String clientPageId);

/// ProfileInteractionActivityView 对象拥有的 generated query adapter。
final class RemoteProfileInteractionActivityQuery
    implements ProfileInteractionActivityQuery {
  const RemoteProfileInteractionActivityQuery({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final ProfileInteractionActivityInvocationContextFactory invocationContext;

  @override
  Future<ProfileInteractionActivityPageSlice> listActivities(
    ContentProfileInteractionPageQuery query, {
    required InteractionDirection direction,
  }) {
    return switch (direction) {
      InteractionDirection.received =>
        client
            .contentProfileInteractionActivityViewListProfileInteractionActivitiesReceived(
              query,
              context: invocationContext(
                ContentRequestPageIds.listProfileInteractionActivitiesReceived,
              ),
            ),
      InteractionDirection.sent =>
        client
            .contentProfileInteractionActivityViewListProfileInteractionActivitiesSent(
              query,
              context: invocationContext(
                ContentRequestPageIds.listProfileInteractionActivitiesSent,
              ),
            ),
    };
  }
}
