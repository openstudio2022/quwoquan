import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// TripMembership 的 Travel-owned 应用边界（成员写侧）。
abstract interface class TripMembershipFacet {
  Future<TripMembershipSlice> putMembership(
    PutTripMembershipRequest request, {
    required String idempotencyKey,
  });

  Future<TripMembershipSlice> departMembership(
    DepartTripMembershipRequest request, {
    required String idempotencyKey,
  });
}
