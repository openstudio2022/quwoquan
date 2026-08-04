import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/application/travel/trip_collaboration_facet.dart';
import 'package:quwoquan_app/travel/travel/trip_share_snapshot/adapters/trip_share_remote.dart';
import 'package:quwoquan_app/cloud/runtime/generated/travel/travel_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

final class RemoteTripCollaborationFacet implements TripCollaborationFacet {
  const RemoteTripCollaborationFacet({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final TripShareInvocationContextFactory invocationContext;

  @override
  Future<TripPlanPlacementListSlice> listSurfacePlacements(
    ListSurfaceTripPlacementsQuery query,
  ) => client.travelTripPlanPlacementListSurfaceTripPlacements(
    query,
    context: invocationContext(
      AppUiSurfaces.travelTrips,
      TravelRequestPageIds.listSurfaceTripPlacements,
    ),
  );

  @override
  Future<TripMembershipSlice> putMembership(
    PutTripMembershipRequest request, {
    required String idempotencyKey,
  }) => client.travelTripMembershipPutTripMembership(
    request,
    context: _context(TravelRequestPageIds.putTripMembership, idempotencyKey),
  );

  @override
  Future<TripMembershipSlice> departMembership(
    DepartTripMembershipRequest request, {
    required String idempotencyKey,
  }) => client.travelTripMembershipDepartTripMembership(
    request,
    context: _context(
      TravelRequestPageIds.departTripMembership,
      idempotencyKey,
    ),
  );

  @override
  Future<TripPlanPlacementSlice> putPlacement(
    PutTripPlanPlacementRequest request, {
    required String idempotencyKey,
  }) => client.travelTripPlanPlacementPutTripPlanPlacement(
    request,
    context: _context(
      TravelRequestPageIds.putTripPlanPlacement,
      idempotencyKey,
    ),
  );

  @override
  Future<TripPlanPlacementSlice> removePlacement(
    RemoveTripPlanPlacementRequest request, {
    required String idempotencyKey,
  }) => client.travelTripPlanPlacementRemoveTripPlanPlacement(
    request,
    context: _context(
      TravelRequestPageIds.removeTripPlanPlacement,
      idempotencyKey,
    ),
  );

  CloudOperationInvocationContext _context(
    String clientPageId,
    String idempotencyKey,
  ) => invocationContext(
    AppUiSurfaces.travelTrips,
    clientPageId,
    idempotencyKey: idempotencyKey,
  );
}
