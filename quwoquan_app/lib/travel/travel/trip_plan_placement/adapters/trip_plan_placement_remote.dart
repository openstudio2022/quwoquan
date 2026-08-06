import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/travel/travel_request_page_ids.g.dart';
import 'package:quwoquan_app/travel/travel/trip_plan_placement/application/trip_plan_placement_facet.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// TripPlanPlacement 对象的 invocation context 工厂。
typedef TripPlanPlacementInvocationContextFactory =
    CloudOperationInvocationContext Function(
      AppUiSurface surface,
      String clientPageId, {
      String? idempotencyKey,
    });

final class RemoteTripPlanPlacementFacet implements TripPlanPlacementFacet {
  const RemoteTripPlanPlacementFacet({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final TripPlanPlacementInvocationContextFactory invocationContext;

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
