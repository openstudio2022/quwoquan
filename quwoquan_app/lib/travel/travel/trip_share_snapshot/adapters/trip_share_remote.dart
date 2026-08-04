import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/travel/travel/trip_share_snapshot/application/trip_share_facet.dart';
import 'package:quwoquan_app/cloud/runtime/generated/travel/travel_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef TripShareInvocationContextFactory =
    CloudOperationInvocationContext Function(
      AppUiSurface surface,
      String clientPageId, {
      String? idempotencyKey,
    });

final class RemoteTripShareFacet implements TripShareFacet {
  const RemoteTripShareFacet({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final TripShareInvocationContextFactory invocationContext;

  @override
  Future<TripShareSnapshot> getSnapshot(String snapshotId) {
    return client.travelTripShareSnapshotGetTripShareSnapshot(
      GetTripShareSnapshotQuery(snapshotId: snapshotId),
      context: invocationContext(
        AppUiSurfaces.travelShare,
        TravelRequestPageIds.getTripShareSnapshot,
      ),
    );
  }

  @override
  Future<TripShareSnapshot> createSnapshot(
    CreateTripShareSnapshotRequest request, {
    required String idempotencyKey,
  }) {
    return client.travelTripShareSnapshotCreateTripShareSnapshot(
      request,
      context: invocationContext(
        AppUiSurfaces.travelShare,
        TravelRequestPageIds.createTripShareSnapshot,
        idempotencyKey: idempotencyKey,
      ),
    );
  }
}
