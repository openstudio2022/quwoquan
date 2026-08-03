import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/application/travel/trip_moment_facet.dart';
import 'package:quwoquan_app/cloud/runtime/generated/travel/travel_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

final class RemoteTripMomentFacet implements TripMomentFacet {
  const RemoteTripMomentFacet({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final TripMomentInvocationContextFactory invocationContext;

  @override
  Future<TripMomentSlice> create(
    CreateTripMomentRequest request, {
    required String idempotencyKey,
  }) {
    return client.travelTripMomentCreateTripMoment(
      request,
      context: invocationContext(
        AppUiSurfaces.travelTimeline,
        TravelRequestPageIds.createTripMoment,
        idempotencyKey: idempotencyKey,
      ),
    );
  }

  @override
  Future<TripMomentSlice> assign(
    AssignTripMomentRequest request, {
    required String idempotencyKey,
  }) {
    return client.travelTripMomentAssignTripMoment(
      request,
      context: invocationContext(
        AppUiSurfaces.travelTimeline,
        TravelRequestPageIds.assignTripMoment,
        idempotencyKey: idempotencyKey,
      ),
    );
  }

  @override
  Future<TripMomentSlice> delete(
    DeleteTripMomentRequest request, {
    required String idempotencyKey,
  }) {
    return client.travelTripMomentDeleteTripMoment(
      request,
      context: invocationContext(
        AppUiSurfaces.travelTimeline,
        TravelRequestPageIds.deleteTripMoment,
        idempotencyKey: idempotencyKey,
      ),
    );
  }
}
