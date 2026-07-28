import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

final class AlphaCirclePostPlacementSnapshot {
  const AlphaCirclePostPlacementSnapshot({
    this.pinned = false,
    this.featured = false,
    this.removed = false,
  });

  final bool pinned;
  final bool featured;
  final bool removed;

  AlphaCirclePostPlacementSnapshot copyWith({
    bool? pinned,
    bool? featured,
    bool? removed,
  }) => AlphaCirclePostPlacementSnapshot(
    pinned: pinned ?? this.pinned,
    featured: featured ?? this.featured,
    removed: removed ?? this.removed,
  );
}

final class AlphaCirclePostPlacementStore {
  final Map<String, AlphaCirclePostPlacementSnapshot> _presentations =
      <String, AlphaCirclePostPlacementSnapshot>{};

  AlphaCirclePostPlacementSnapshot presentation(String placementId) =>
      _presentations[placementId] ?? const AlphaCirclePostPlacementSnapshot();

  void setPinned(String placementId, bool enabled) {
    _presentations[placementId] = presentation(
      placementId,
    ).copyWith(pinned: enabled, removed: false);
  }

  void setFeatured(String placementId, bool enabled) {
    _presentations[placementId] = presentation(
      placementId,
    ).copyWith(featured: enabled, removed: false);
  }

  void remove(String placementId) {
    _presentations[placementId] = presentation(
      placementId,
    ).copyWith(removed: true);
  }
}

final class AlphaCirclePostPlacementWriter
    implements CirclePostPlacementCommandWriter {
  AlphaCirclePostPlacementWriter({AlphaCirclePostPlacementStore? store})
    : store = store ?? AlphaCirclePostPlacementStore();

  final AlphaCirclePostPlacementStore store;
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
    store.setPinned(result.placementId, false);
    return result;
  }

  @override
  Future<CirclePostPlacementCommandResult> removePost(
    RemoveCirclePostCommand command,
  ) async {
    _placements.removeWhere(
      (_, placement) => placement.placementId == command.placementId,
    );
    store.remove(command.placementId);
    return CirclePostPlacementCommandResult(
      placementId: command.placementId,
      version: 1,
      state: 'removed',
      idempotentReplay: false,
    );
  }

  @override
  Future<CirclePostPlacementCommandResult> setPinned(
    PinCirclePostCommand command,
  ) async {
    store.setPinned(command.placementId, command.enabled);
    return _mutatePlacementState(command.placementId);
  }

  @override
  Future<CirclePostPlacementCommandResult> setFeatured(
    FeatureCirclePostCommand command,
  ) async {
    store.setFeatured(command.placementId, command.enabled);
    return _mutatePlacementState(command.placementId);
  }

  CirclePostPlacementCommandResult _mutatePlacementState(String placementId) {
    for (final entry in _placements.entries) {
      if (entry.value.placementId != placementId) continue;
      final updated = CirclePostPlacementCommandResult(
        placementId: placementId,
        version: entry.value.version + 1,
        state: 'active',
        idempotentReplay: false,
      );
      _placements[entry.key] = updated;
      return updated;
    }
    final created = CirclePostPlacementCommandResult(
      placementId: placementId,
      version: 1,
      state: 'active',
      idempotentReplay: false,
    );
    _placements[placementId] = created;
    return created;
  }
}
