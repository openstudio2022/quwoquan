// spec_ref: specs/feature-tree/travel-journey/collaborative-trip-lifecycle/trip-placement-collaboration/spec.md#gwt-001
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/travel/travel/trip_plan_placement/application/trip_plan_placement_coordinator.dart';
import 'package:quwoquan_app/travel/travel/trip_plan_placement/application/trip_plan_placement_facet.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test('placement removal requires active CAS state', () {
    final coordinator = TripPlanPlacementCoordinator(
      _RecordingPlacementFacet(),
      (scope) => '$scope-intent-1',
    );
    final removal = coordinator.preparePlacementRemoval(
      current: _placement(),
      sourceVersion: 8,
    );

    expect(removal.request.expectedVersion, 3);
    expect(removal.request.surfaceKind, TripPlacementSurfaceKind.conversation);
  });

  test(
    'placement put freezes surface authority version and retry key',
    () async {
      final facet = _RecordingPlacementFacet();
      final coordinator = TripPlanPlacementCoordinator(
        facet,
        (scope) => '$scope-intent-1',
      );
      final intent = coordinator.preparePlacement(
        tripId: 'trip-1',
        surfaceKind: TripPlacementSurfaceKind.circle,
        surfaceId: 'circle-1',
        sourceVersion: 5,
      );

      await coordinator.putPlacement(intent);
      await coordinator.putPlacement(intent);

      expect(intent.request.expectedVersion, 0);
      expect(facet.keys, <String>[
        'placement-put-intent-1',
        'placement-put-intent-1',
      ]);
    },
  );
}

final class _RecordingPlacementFacet implements TripPlanPlacementFacet {
  final List<String> keys = <String>[];

  @override
  Future<TripPlanPlacementListSlice> listSurfacePlacements(
    ListSurfaceTripPlacementsQuery query,
  ) async => TripPlanPlacementListSlice(
    surfaceKind: query.surfaceKind,
    surfaceId: query.surfaceId,
    placements: <TripPlanPlacementSlice>[_placement()],
  );

  @override
  Future<TripPlanPlacementSlice> putPlacement(
    PutTripPlanPlacementRequest request, {
    required String idempotencyKey,
  }) async {
    keys.add(idempotencyKey);
    return _placement();
  }

  @override
  Future<TripPlanPlacementSlice> removePlacement(
    RemoveTripPlanPlacementRequest request, {
    required String idempotencyKey,
  }) {
    throw UnimplementedError();
  }
}

TripPlanPlacementSlice _placement() {
  final now = DateTime.utc(2026, 8, 2, 10);
  return TripPlanPlacementSlice(
    placementId: 'placement-1',
    version: 3,
    tripId: 'trip-1',
    surfaceKind: TripPlacementSurfaceKind.conversation,
    surfaceId: 'conversation-1',
    sourceVersion: 7,
    status: TripPlanPlacementStatus.active,
    createdByPersonaId: 'persona-1',
    createdAt: now,
    updatedAt: now,
  );
}
