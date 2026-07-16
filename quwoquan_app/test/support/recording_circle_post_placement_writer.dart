import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

final class RecordingCirclePostPlacementWriter
    implements CirclePostPlacementCommandWriter {
  final List<PlaceCirclePostCommand> commands = <PlaceCirclePostCommand>[];

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
}
