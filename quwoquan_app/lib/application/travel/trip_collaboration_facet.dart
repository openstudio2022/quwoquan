import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// Trip 成员与共享场景 Placement 的 Travel-owned 写边界。
abstract interface class TripCollaborationFacet {
  Future<TripMembershipSlice> putMembership(
    PutTripMembershipRequest request, {
    required String idempotencyKey,
  });

  Future<TripMembershipSlice> departMembership(
    DepartTripMembershipRequest request, {
    required String idempotencyKey,
  });

  Future<TripPlanPlacementSlice> putPlacement(
    PutTripPlanPlacementRequest request, {
    required String idempotencyKey,
  });

  Future<TripPlanPlacementSlice> removePlacement(
    RemoveTripPlanPlacementRequest request, {
    required String idempotencyKey,
  });
}
