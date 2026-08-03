import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef TripGuideInvocationContextFactory =
    CloudOperationInvocationContext Function(
      AppUiSurface surface,
      String clientPageId, {
      String? idempotencyKey,
    });

abstract interface class TripGuideAssignmentFacet {
  Future<TripGuideAssignment> put(
    PutTripGuideAssignmentRequest request, {
    required String idempotencyKey,
  });

  Future<TripGuideAssignment> transition(
    TransitionTripGuideAssignmentRequest request, {
    required String idempotencyKey,
  });
}
