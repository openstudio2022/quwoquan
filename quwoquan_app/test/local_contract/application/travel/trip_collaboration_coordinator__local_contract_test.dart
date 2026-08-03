// spec_ref: specs/feature-tree/travel-journey/collaborative-trip-lifecycle/trip-placement-collaboration/spec.md#gwt-001
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/application/travel/trip_collaboration_coordinator.dart';
import 'package:quwoquan_app/application/travel/trip_collaboration_facet.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test(
    'membership sourced from conversation freezes typed source and key',
    () async {
      final facet = _RecordingCollaborationFacet();
      final coordinator = TripCollaborationCoordinator(
        facet,
        (scope) => '$scope-intent-1',
      );
      final intent = coordinator.prepareMembership(
        tripId: ' trip-1 ',
        personaId: ' persona-2 ',
        role: TripMembershipRole.participant,
        sourceKind: TripMembershipSourceKind.conversation,
        sourceObjectRef: const TripMembershipSourceRef(
          objectTypeRef: 'chat.Conversation',
          objectId: 'conversation-1',
        ),
        sourceVersion: 4,
      );

      await coordinator.putMembership(intent);
      await coordinator.putMembership(intent);

      expect(intent.request.tripId, 'trip-1');
      expect(intent.request.personaId, 'persona-2');
      expect(intent.request.expectedVersion, 0);
      expect(facet.keys, <String>[
        'membership-put-intent-1',
        'membership-put-intent-1',
      ]);
      expect(
        () => coordinator.prepareMembership(
          tripId: 'trip-1',
          personaId: 'persona-2',
          role: TripMembershipRole.participant,
          sourceKind: TripMembershipSourceKind.circle,
          sourceVersion: 1,
        ),
        throwsArgumentError,
      );
    },
  );

  test(
    'membership departure and placement removal require active CAS state',
    () {
      final coordinator = TripCollaborationCoordinator(
        _RecordingCollaborationFacet(),
        (scope) => '$scope-intent-1',
      );
      final membership = _membership();
      final departure = coordinator.prepareDeparture(
        current: membership,
        reason: ' 本次旅行结束 ',
      );
      expect(departure.request.expectedVersion, 2);
      expect(departure.request.reason, '本次旅行结束');

      final placement = _placement();
      final removal = coordinator.preparePlacementRemoval(
        current: placement,
        sourceVersion: 8,
      );
      expect(removal.request.expectedVersion, 3);
      expect(
        removal.request.surfaceKind,
        TripPlacementSurfaceKind.conversation,
      );
    },
  );

  test(
    'placement put freezes surface authority version and retry key',
    () async {
      final facet = _RecordingCollaborationFacet();
      final coordinator = TripCollaborationCoordinator(
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

final class _RecordingCollaborationFacet implements TripCollaborationFacet {
  final List<String> keys = <String>[];

  @override
  Future<TripMembershipSlice> putMembership(
    PutTripMembershipRequest request, {
    required String idempotencyKey,
  }) async {
    keys.add(idempotencyKey);
    return _membership();
  }

  @override
  Future<TripMembershipSlice> departMembership(
    DepartTripMembershipRequest request, {
    required String idempotencyKey,
  }) {
    throw UnimplementedError();
  }

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

TripMembershipSlice _membership() {
  final now = DateTime.utc(2026, 8, 2, 10);
  return TripMembershipSlice(
    membershipId: 'membership-1',
    version: 2,
    tripId: 'trip-1',
    personaId: 'persona-2',
    role: TripMembershipRole.participant,
    state: TripMembershipState.active,
    sourceKind: TripMembershipSourceKind.conversation,
    sourceVersion: 4,
    joinedAt: now,
    updatedAt: now,
  );
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
