import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/travel/travel/trip_plan/application/trip_plan_directory.dart';
import 'package:quwoquan_app/travel/travel/trip_timeline_view/adapters/trip_journey_query_remote.dart';
import 'package:quwoquan_app/cloud/runtime/generated/travel/travel_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

final class RemoteTripPlanDirectory implements TripPlanDirectory {
  const RemoteTripPlanDirectory({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final TravelInvocationContextFactory invocationContext;

  @override
  Future<TripPlanListSlice> list({
    TripPlanStatus? status,
    String? cursor,
    int limit = 20,
  }) {
    return client.travelTripPlanListTripPlans(
      ListTripPlansQuery(status: status, cursor: cursor, limit: limit),
      context: invocationContext(
        AppUiSurfaces.travelTrips,
        TravelRequestPageIds.listTripPlans,
      ),
    );
  }
}
