import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/travel/travel/trip_plan/application/trip_plan_creation_facet.dart';
import 'package:quwoquan_app/travel/travel/trip_share_snapshot/adapters/trip_share_remote.dart';
import 'package:quwoquan_app/cloud/runtime/generated/travel/travel_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

final class RemoteTripPlanCreationFacet implements TripPlanCreationFacet {
  const RemoteTripPlanCreationFacet({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final TripShareInvocationContextFactory invocationContext;

  @override
  Future<TripPlanCommandResult> create(
    CreateTripPlanCommand command, {
    required String idempotencyKey,
  }) {
    return client.travelTripPlanCreateTripPlan(
      command,
      context: invocationContext(
        AppUiSurfaces.travelTrips,
        TravelRequestPageIds.createTripPlan,
        idempotencyKey: idempotencyKey,
      ),
    );
  }

  @override
  Future<TripPlanCommandResult> createFromTemplate(
    CreateTripPlanFromTemplateCommand command, {
    required String idempotencyKey,
  }) {
    return client.travelTripPlanCreateTripPlanFromTemplate(
      command,
      context: invocationContext(
        AppUiSurfaces.travelTemplates,
        TravelRequestPageIds.createTripPlanFromTemplate,
        idempotencyKey: idempotencyKey,
      ),
    );
  }
}
