import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// 旅行与 Content Post 采用关系的唯一 App 写边界。
abstract interface class TripContentLinkFacet {
  Future<TripPlanContentLinkSlice> put(
    PutTripPlanContentLinkRequest request, {
    required String idempotencyKey,
  });

  Future<TripPlanContentLinkSlice> remove(
    RemoveTripPlanContentLinkRequest request, {
    required String idempotencyKey,
  });
}
