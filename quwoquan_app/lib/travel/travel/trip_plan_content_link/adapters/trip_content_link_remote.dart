import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/travel/travel/trip_plan_content_link/application/trip_content_link_facet.dart';
import 'package:quwoquan_app/travel/travel/trip_share_snapshot/adapters/trip_share_remote.dart';
import 'package:quwoquan_app/cloud/runtime/generated/travel/travel_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

final class RemoteTripContentLinkFacet implements TripContentLinkFacet {
  const RemoteTripContentLinkFacet({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final TripShareInvocationContextFactory invocationContext;

  @override
  Future<TripPlanContentLinkSlice> put(
    PutTripPlanContentLinkRequest request, {
    required String idempotencyKey,
  }) => client.travelTripPlanContentLinkPutTripPlanContentLink(
    request,
    context: invocationContext(
      AppUiSurfaces.travelTimeline,
      TravelRequestPageIds.putTripPlanContentLink,
      idempotencyKey: idempotencyKey,
    ),
  );

  @override
  Future<TripPlanContentLinkSlice> remove(
    RemoveTripPlanContentLinkRequest request, {
    required String idempotencyKey,
  }) => client.travelTripPlanContentLinkRemoveTripPlanContentLink(
    request,
    context: invocationContext(
      AppUiSurfaces.travelTimeline,
      TravelRequestPageIds.removeTripPlanContentLink,
      idempotencyKey: idempotencyKey,
    ),
  );
}
