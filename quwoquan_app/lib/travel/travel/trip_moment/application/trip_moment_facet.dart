import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef TripMomentInvocationContextFactory =
    CloudOperationInvocationContext Function(
      AppUiSurface surface,
      String clientPageId, {
      String? idempotencyKey,
    });

/// TripMoment 写面。重试时由调用方复用同一个 intent key，Remote
/// 不会自行生成新 key 或猜测 wire。
abstract interface class TripMomentFacet {
  Future<TripMomentSlice> create(
    CreateTripMomentRequest request, {
    required String idempotencyKey,
  });

  Future<TripMomentSlice> assign(
    AssignTripMomentRequest request, {
    required String idempotencyKey,
  });

  Future<TripMomentSlice> delete(
    DeleteTripMomentRequest request, {
    required String idempotencyKey,
  });
}
