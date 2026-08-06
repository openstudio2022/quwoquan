import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// TripPlanPlacement 的 Travel-owned 应用边界（共享场景挂载读写）。
abstract interface class TripPlanPlacementFacet {
  Future<TripPlanPlacementListSlice> listSurfacePlacements(
    ListSurfaceTripPlacementsQuery query,
  );

  Future<TripPlanPlacementSlice> putPlacement(
    PutTripPlanPlacementRequest request, {
    required String idempotencyKey,
  });

  Future<TripPlanPlacementSlice> removePlacement(
    RemoveTripPlanPlacementRequest request, {
    required String idempotencyKey,
  });
}
