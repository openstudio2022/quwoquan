import 'circle_operation_contracts.g.dart';

abstract interface class CirclePostPlacementCommandWriter {
  Future<CirclePostPlacementCommandResult> placePost(
    PlaceCirclePostCommand command,
  );

  Future<CirclePostPlacementCommandResult> removePost(
    RemoveCirclePostCommand command,
  );

  Future<CirclePostPlacementCommandResult> setPinned(
    PinCirclePostCommand command,
  );

  Future<CirclePostPlacementCommandResult> setFeatured(
    FeatureCirclePostCommand command,
  );
}
