import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

abstract interface class CirclePostPlacementCommands {
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
