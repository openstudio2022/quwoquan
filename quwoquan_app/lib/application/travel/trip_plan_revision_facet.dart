import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// 当前 Trip 修订与生命周期推进的唯一 App 写边界。
abstract interface class TripPlanRevisionFacet {
  Future<TripPlanCommandResult> revise(
    ReviseTripPlanCommand command, {
    required String idempotencyKey,
  });

  Future<TripPlanCommandResult> transition(
    TransitionTripPlanCommand command, {
    required String idempotencyKey,
  });
}
