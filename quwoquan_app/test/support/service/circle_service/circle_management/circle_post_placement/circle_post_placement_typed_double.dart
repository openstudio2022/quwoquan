import 'package:quwoquan_app/service/circle_service/circle_management/circle_post_placement/application/public/circle_post_placement_commands.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

final class InMemoryCirclePostPlacementSnapshot {
  const InMemoryCirclePostPlacementSnapshot({
    this.pinned = false,
    this.featured = false,
    this.removed = false,
  });

  final bool pinned;
  final bool featured;
  final bool removed;

  InMemoryCirclePostPlacementSnapshot copyWith({
    bool? pinned,
    bool? featured,
    bool? removed,
  }) => InMemoryCirclePostPlacementSnapshot(
    pinned: pinned ?? this.pinned,
    featured: featured ?? this.featured,
    removed: removed ?? this.removed,
  );
}

final class InMemoryCirclePostPlacementStore {
  final Map<String, InMemoryCirclePostPlacementSnapshot> _presentations =
      <String, InMemoryCirclePostPlacementSnapshot>{};

  InMemoryCirclePostPlacementSnapshot presentation(String placementId) =>
      _presentations[placementId] ??
      const InMemoryCirclePostPlacementSnapshot();

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

final class InMemoryCirclePostPlacementWriter
    implements CirclePostPlacementCommands {
  InMemoryCirclePostPlacementWriter({InMemoryCirclePostPlacementStore? store})
    : store = store ?? InMemoryCirclePostPlacementStore();

  final InMemoryCirclePostPlacementStore store;
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
      placementId: 'fixture_circle_placement_${_placements.length + 1}',
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
