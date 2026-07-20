import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef CirclePostPlacementInvocationContextFactory =
    CloudOperationInvocationContext Function(
      String clientPageId,
      String idempotencyKey,
    );

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
    context: invocationContext(
      CircleRequestPageIds.placePostInCircle,
      _placementIdempotencyKey(command),
    ),
  );

  @override
  Future<CirclePostPlacementCommandResult> removePost(
    RemoveCirclePostCommand command,
  ) => client.circleCirclePostPlacementRemovePostFromCircle(
    command,
    context: invocationContext(
      CircleRequestPageIds.removePostFromCircle,
      _removeIdempotencyKey(command),
    ),
  );

  @override
  Future<CirclePostPlacementCommandResult> setPinned(
    PinCirclePostCommand command,
  ) => client.circleCirclePostPlacementPinCirclePost(
    command,
    context: invocationContext(
      CircleRequestPageIds.pinCirclePost,
      _pinIdempotencyKey(command),
    ),
  );

  @override
  Future<CirclePostPlacementCommandResult> setFeatured(
    FeatureCirclePostCommand command,
  ) => client.circleCirclePostPlacementFeatureCirclePost(
    command,
    context: invocationContext(
      CircleRequestPageIds.featureCirclePost,
      _featureIdempotencyKey(command),
    ),
  );
}

String _placementIdempotencyKey(PlaceCirclePostCommand command) {
  return 'circle-placement:${command.circleId}:${command.groupId ?? '-'}:${command.postId}';
}

String _removeIdempotencyKey(RemoveCirclePostCommand command) =>
    'circle-placement-remove:${command.circleId}:${command.placementId}';

String _pinIdempotencyKey(PinCirclePostCommand command) =>
    'circle-placement-pin:${command.circleId}:${command.placementId}:${command.enabled}';

String _featureIdempotencyKey(FeatureCirclePostCommand command) =>
    'circle-placement-feature:${command.circleId}:${command.placementId}:${command.enabled}';
