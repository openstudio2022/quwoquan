import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/application/travel/trip_guide_assignment_facet.dart';
import 'package:quwoquan_app/cloud/runtime/generated/travel/travel_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

final class RemoteTripGuideAssignmentFacet implements TripGuideAssignmentFacet {
  const RemoteTripGuideAssignmentFacet({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final TripGuideInvocationContextFactory invocationContext;

  @override
  Future<TripGuideAssignment> put(
    PutTripGuideAssignmentRequest request, {
    required String idempotencyKey,
  }) {
    return client.travelTripGuideAssignmentPutTripGuideAssignment(
      request,
      context: invocationContext(
        AppUiSurfaces.travelTimeline,
        TravelRequestPageIds.putTripGuideAssignment,
        idempotencyKey: idempotencyKey,
      ),
    );
  }

  @override
  Future<TripGuideAssignment> transition(
    TransitionTripGuideAssignmentRequest request, {
    required String idempotencyKey,
  }) {
    return client.travelTripGuideAssignmentTransitionTripGuideAssignment(
      request,
      context: invocationContext(
        AppUiSurfaces.travelTimeline,
        TravelRequestPageIds.transitionTripGuideAssignment,
        idempotencyKey: idempotencyKey,
      ),
    );
  }
}
