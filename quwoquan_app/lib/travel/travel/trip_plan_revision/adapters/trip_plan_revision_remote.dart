import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/travel/travel/trip_plan_revision/application/trip_plan_revision_facet.dart';
import 'package:quwoquan_app/travel/travel/trip_share_snapshot/adapters/trip_share_remote.dart';
import 'package:quwoquan_app/cloud/runtime/generated/travel/travel_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

final class RemoteTripPlanRevisionFacet implements TripPlanRevisionFacet {
  const RemoteTripPlanRevisionFacet({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final TripShareInvocationContextFactory invocationContext;

  @override
  Future<TripPlanCommandResult> revise(
    ReviseTripPlanCommand command, {
    required String idempotencyKey,
  }) {
    return client.travelTripPlanReviseTripPlan(
      command,
      context: invocationContext(
        AppUiSurfaces.travelTimeline,
        TravelRequestPageIds.reviseTripPlan,
        idempotencyKey: idempotencyKey,
      ),
    );
  }

  @override
  Future<TripPlanCommandResult> transition(
    TransitionTripPlanCommand command, {
    required String idempotencyKey,
  }) {
    return client.travelTripPlanTransitionTripPlan(
      command,
      context: invocationContext(
        AppUiSurfaces.travelTimeline,
        TravelRequestPageIds.transitionTripPlan,
        idempotencyKey: idempotencyKey,
      ),
    );
  }
}
