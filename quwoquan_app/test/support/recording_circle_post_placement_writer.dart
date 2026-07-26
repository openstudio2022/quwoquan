import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

final class RecordingCirclePostPlacementWriter
    implements CirclePostPlacementCommandWriter {
  final List<PlaceCirclePostCommand> commands = <PlaceCirclePostCommand>[];
  final List<RemoveCirclePostCommand> removeCommands =
      <RemoveCirclePostCommand>[];
  final List<PinCirclePostCommand> pinCommands = <PinCirclePostCommand>[];
  final List<FeatureCirclePostCommand> featureCommands =
      <FeatureCirclePostCommand>[];

  @override
  Future<CirclePostPlacementCommandResult> placePost(
    PlaceCirclePostCommand command,
  ) async {
    commands.add(command);
    return CirclePostPlacementCommandResult(
      placementId: 'placement_${commands.length}',
      version: 1,
      state: 'active',
      idempotentReplay: false,
    );
  }

  @override
  Future<CirclePostPlacementCommandResult> removePost(
    RemoveCirclePostCommand command,
  ) async {
    removeCommands.add(command);
    return CirclePostPlacementCommandResult(
      placementId: 'placement_removed_${removeCommands.length}',
      version: 1,
      state: 'removed',
      idempotentReplay: false,
    );
  }

  @override
  Future<CirclePostPlacementCommandResult> setPinned(
    PinCirclePostCommand command,
  ) async {
    pinCommands.add(command);
    return CirclePostPlacementCommandResult(
      placementId: 'placement_pinned_${pinCommands.length}',
      version: 1,
      state: 'active',
      idempotentReplay: false,
    );
  }

  @override
  Future<CirclePostPlacementCommandResult> setFeatured(
    FeatureCirclePostCommand command,
  ) async {
    featureCommands.add(command);
    return CirclePostPlacementCommandResult(
      placementId: 'placement_featured_${featureCommands.length}',
      version: 1,
      state: 'active',
      idempotentReplay: false,
    );
  }
}
