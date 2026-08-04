// spec_ref: specs/feature-tree/travel-journey/collaborative-trip-lifecycle/trip-placement-collaboration/spec.md#gwt-001
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/cloud/remote/travel/trip_collaboration_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test(
    'surface placement query uses generated owner and typed surface path',
    () async {
      final executor = _CollaborationExecutor();
      final facet = RemoteTripCollaborationFacet(
        client: GeneratedCloudOperationClient(executor),
        invocationContext: _context,
      );

      final result = await facet.listSurfacePlacements(
        ListSurfaceTripPlacementsQuery(
          surfaceKind: TripPlacementSurfaceKind.circle,
          surfaceId: 'circle-1',
        ),
      );

      expect(
        executor.operation?.canonicalOperationId,
        AppCloudOperationIds.travelTripPlanPlacementListSurfaceTripPlacements,
      );
      expect(executor.context?.surfaceId, AppUiSurfaces.travelTrips.id);
      expect(executor.context?.idempotencyKey, isNull);
      expect(executor.pathParameters, <String, String>{
        'surfaceKind': 'circle',
        'surfaceId': 'circle-1',
      });
      expect(result.surfaceKind, TripPlacementSurfaceKind.circle);
      expect(result.surfaceId, 'circle-1');
      expect(result.placements.single.tripId, 'trip-1');
    },
  );

  test(
    'membership and placement mutations use typed travel paths and keys',
    () async {
      final executor = _CollaborationExecutor();
      final facet = RemoteTripCollaborationFacet(
        client: GeneratedCloudOperationClient(executor),
        invocationContext: _context,
      );

      await facet.putMembership(
        PutTripMembershipRequest(
          tripId: 'trip-1',
          personaId: 'persona-2',
          role: TripMembershipRole.participant,
          sourceKind: TripMembershipSourceKind.conversation,
          sourceVersion: 3,
          expectedVersion: 0,
        ),
        idempotencyKey: 'membership-intent-1',
      );
      expect(
        executor.operation?.canonicalOperationId,
        AppCloudOperationIds.travelTripMembershipPutTripMembership,
      );
      expect(executor.context?.surfaceId, AppUiSurfaces.travelTrips.id);
      expect(executor.context?.idempotencyKey, 'membership-intent-1');
      expect(executor.pathParameters, <String, String>{
        'tripId': 'trip-1',
        'personaId': 'persona-2',
      });

      await facet.putPlacement(
        PutTripPlanPlacementRequest(
          tripId: 'trip-1',
          surfaceKind: TripPlacementSurfaceKind.circle,
          surfaceId: 'circle-1',
          sourceVersion: 8,
          expectedVersion: 0,
        ),
        idempotencyKey: 'placement-intent-1',
      );
      expect(
        executor.operation?.canonicalOperationId,
        AppCloudOperationIds.travelTripPlanPlacementPutTripPlanPlacement,
      );
      expect(executor.context?.idempotencyKey, 'placement-intent-1');
      expect(executor.pathParameters, <String, String>{
        'tripId': 'trip-1',
        'surfaceKind': 'circle',
        'surfaceId': 'circle-1',
      });
    },
  );
}

CloudOperationInvocationContext _context(
  AppUiSurface surface,
  String clientPageId, {
  String? idempotencyKey,
}) => CloudOperationInvocationContext(
  surfaceId: surface.id,
  routeId: surface.routeId,
  clientPageId: clientPageId,
  idempotencyKey: idempotencyKey,
  actor: const CloudOperationActorContext(
    accountId: 'account-1',
    personaId: 'persona-1',
  ),
);

final class _CollaborationExecutor implements CloudOperationExecutor {
  CloudOperationContract? operation;
  CloudOperationInvocationContext? context;
  Map<String, String> pathParameters = const <String, String>{};

  @override
  Future<TResponse> send<TResponse>(
    CloudOperationContract operation, {
    required CloudOperationInvocationContext context,
    required CloudOperationResponseDecoder<TResponse> responseDecoder,
    required CloudOperationRequestEncoder requestEncoder,
  }) async {
    this.operation = operation;
    this.context = context;
    pathParameters = requestEncoder().pathParameters;
    return responseDecoder(switch (operation.canonicalOperationId) {
      AppCloudOperationIds.travelTripMembershipPutTripMembership =>
        _membershipWire(),
      AppCloudOperationIds.travelTripPlanPlacementListSurfaceTripPlacements =>
        <String, Object?>{
          'surfaceKind': 'circle',
          'surfaceId': 'circle-1',
          'placements': <Object?>[_placementWire()],
        },
      _ => _placementWire(),
    });
  }
}

Map<String, Object?> _membershipWire() => <String, Object?>{
  'membershipId': 'membership-1',
  'version': 1,
  'tripId': 'trip-1',
  'personaId': 'persona-2',
  'role': 'participant',
  'state': 'active',
  'sourceKind': 'conversation',
  'sourceVersion': 3,
  'joinedAt': '2026-08-02T10:00:00Z',
  'updatedAt': '2026-08-02T10:00:00Z',
};

Map<String, Object?> _placementWire() => <String, Object?>{
  'placementId': 'placement-1',
  'version': 1,
  'tripId': 'trip-1',
  'surfaceKind': 'circle',
  'surfaceId': 'circle-1',
  'sourceVersion': 8,
  'status': 'active',
  'createdByPersonaId': 'persona-1',
  'createdAt': '2026-08-02T10:00:00Z',
  'updatedAt': '2026-08-02T10:00:00Z',
};
