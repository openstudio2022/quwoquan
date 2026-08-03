import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/application/travel/trip_journey_query.dart';
import 'package:quwoquan_app/cloud/runtime/generated/travel/travel_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef TravelInvocationContextFactory =
    CloudOperationInvocationContext Function(
      AppUiSurface surface,
      String clientPageId,
    );

/// Travel 读面的 production generated-client 适配器。
///
/// 路径、查询参数、鉴权、错误和 decoder 全部来自 canonical contracts；这里
/// 只选择所属 surface 并调用强类型 operation，不维护手写 HTTP/wire 旁路。
final class RemoteTripJourneyQuery implements TripJourneyQuery {
  const RemoteTripJourneyQuery({
    required this.client,
    required this.surface,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final AppUiSurface surface;
  final TravelInvocationContextFactory invocationContext;

  @override
  Future<TripPlanSlice> getPlan(String tripId) {
    return client.travelTripPlanGetTripPlan(
      TripPlanIDQuery(tripId: tripId),
      context: invocationContext(surface, TravelRequestPageIds.getTripPlan),
    );
  }

  @override
  Future<TripTimelineView> getTimeline(String tripId) {
    return client.travelTripTimelineViewGetTripTimeline(
      GetTripTimelineQuery(tripId: tripId),
      context: invocationContext(surface, TravelRequestPageIds.getTripTimeline),
    );
  }

  @override
  Future<TripMapView> getMap(String tripId) {
    return client.travelTripMapViewGetTripMap(
      GetTripMapQuery(tripId: tripId),
      context: invocationContext(surface, TravelRequestPageIds.getTripMap),
    );
  }

  @override
  Future<TripMembershipListSlice> listMemberships(String tripId) {
    return client.travelTripMembershipListTripMemberships(
      ListTripMembershipsQuery(tripId: tripId),
      context: invocationContext(
        surface,
        TravelRequestPageIds.listTripMemberships,
      ),
    );
  }

  @override
  Future<TripMomentListSlice> listMoments(String tripId) {
    return client.travelTripMomentListTripMoments(
      ListTripMomentsQuery(tripId: tripId),
      context: invocationContext(surface, TravelRequestPageIds.listTripMoments),
    );
  }

  @override
  Future<TripPlanContentLinkListSlice> listContentLinks(String tripId) {
    return client.travelTripPlanContentLinkListTripPlanContentLinks(
      ListTripPlanContentLinksQuery(tripId: tripId),
      context: invocationContext(
        surface,
        TravelRequestPageIds.listTripPlanContentLinks,
      ),
    );
  }

  @override
  Future<TripPlanPlacementListSlice> listPlacements(String tripId) {
    return client.travelTripPlanPlacementListTripPlanPlacements(
      ListTripPlanPlacementsQuery(tripId: tripId),
      context: invocationContext(
        surface,
        TravelRequestPageIds.listTripPlanPlacements,
      ),
    );
  }

  @override
  Future<TripGuideAssignmentListSlice> listGuideAssignments(String tripId) {
    return client.travelTripGuideAssignmentListTripGuideAssignments(
      ListTripGuideAssignmentsQuery(tripId: tripId),
      context: invocationContext(
        surface,
        TravelRequestPageIds.listTripGuideAssignments,
      ),
    );
  }
}
