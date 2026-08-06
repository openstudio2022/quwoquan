// spec_ref: specs/feature-tree/travel-journey/collaborative-trip-lifecycle/trip-placement-collaboration/spec.md#gwt-001
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/travel/travel/trip_membership/application/trip_membership_coordinator.dart';
import 'package:quwoquan_app/travel/travel/trip_membership/application/trip_membership_facet.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test(
    'membership sourced from conversation freezes typed source and key',
    () async {
      final facet = _RecordingMembershipFacet();
      final coordinator = TripMembershipCoordinator(
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

  test('membership departure requires active CAS state', () {
    final coordinator = TripMembershipCoordinator(
      _RecordingMembershipFacet(),
      (scope) => '$scope-intent-1',
    );
    final departure = coordinator.prepareDeparture(
      current: _membership(),
      reason: ' 本次旅行结束 ',
    );

    expect(departure.request.expectedVersion, 2);
    expect(departure.request.reason, '本次旅行结束');
  });
}

final class _RecordingMembershipFacet implements TripMembershipFacet {
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
