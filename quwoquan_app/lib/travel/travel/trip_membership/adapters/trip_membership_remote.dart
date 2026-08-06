import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/travel/travel_request_page_ids.g.dart';
import 'package:quwoquan_app/travel/travel/trip_membership/application/trip_membership_facet.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// TripMembership 对象的 invocation context 工厂。
typedef TripMembershipInvocationContextFactory =
    CloudOperationInvocationContext Function(
      AppUiSurface surface,
      String clientPageId, {
      String? idempotencyKey,
    });

final class RemoteTripMembershipFacet implements TripMembershipFacet {
  const RemoteTripMembershipFacet({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final TripMembershipInvocationContextFactory invocationContext;

  @override
  Future<TripMembershipSlice> putMembership(
    PutTripMembershipRequest request, {
    required String idempotencyKey,
  }) => client.travelTripMembershipPutTripMembership(
    request,
    context: _context(TravelRequestPageIds.putTripMembership, idempotencyKey),
  );

  @override
  Future<TripMembershipSlice> departMembership(
    DepartTripMembershipRequest request, {
    required String idempotencyKey,
  }) => client.travelTripMembershipDepartTripMembership(
    request,
    context: _context(
      TravelRequestPageIds.departTripMembership,
      idempotencyKey,
    ),
  );

  CloudOperationInvocationContext _context(
    String clientPageId,
    String idempotencyKey,
  ) => invocationContext(
    AppUiSurfaces.travelTrips,
    clientPageId,
    idempotencyKey: idempotencyKey,
  );
}
