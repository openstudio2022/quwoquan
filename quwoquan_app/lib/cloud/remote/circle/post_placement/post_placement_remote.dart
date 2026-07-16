import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef CirclePostPlacementInvocationContextFactory =
    CloudOperationInvocationContext Function(String clientPageId);

final class RemoteCirclePostPlacementCommandWriter
    implements CirclePostPlacementCommandWriter {
  const RemoteCirclePostPlacementCommandWriter({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final CirclePostPlacementInvocationContextFactory invocationContext;

  @override
  Future<CirclePostPlacementCommandResult> placePost(
    PlaceCirclePostCommand command,
  ) => client.circleCirclePostPlacementPlacePostInCircle(
    command,
    context: invocationContext(CircleRequestPageIds.placePostInCircle),
  );
}
