import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

final class AlphaCirclePostPlacementWriter
    implements CirclePostPlacementCommandWriter {
  final Map<String, CirclePostPlacementCommandResult> _placements =
      <String, CirclePostPlacementCommandResult>{};

  @override
  Future<CirclePostPlacementCommandResult> placePost(
    PlaceCirclePostCommand command,
  ) async {
    final key = '${command.circleId}:${command.postId}';
    final existing = _placements[key];
    if (existing != null) {
      return CirclePostPlacementCommandResult(
        placementId: existing.placementId,
        version: existing.version,
        state: existing.state,
        idempotentReplay: true,
      );
    }
    final result = CirclePostPlacementCommandResult(
      placementId: 'alpha_circle_placement_${_placements.length + 1}',
      version: 1,
      state: 'active',
      idempotentReplay: false,
    );
    _placements[key] = result;
    return result;
  }
}
