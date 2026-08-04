import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// “活的共同旅行时间线”所需的唯一读面。
///
/// 每个方法保持对象级 typed operation；[TripJourneyLoader] 只在应用层并发
/// 组合当前旅程工作台，不复制 Travel Service 的事实或 wire model。
abstract interface class TripJourneyQuery {
  Future<TripPlanSlice> getPlan(String tripId);

  Future<TripTimelineView> getTimeline(String tripId);

  Future<TripMapView> getMap(String tripId);

  Future<TripMembershipListSlice> listMemberships(String tripId);

  Future<TripMomentListSlice> listMoments(String tripId);

  Future<TripPlanContentLinkListSlice> listContentLinks(String tripId);

  Future<TripPlanPlacementListSlice> listPlacements(String tripId);

  Future<TripGuideAssignmentListSlice> listGuideAssignments(String tripId);
}

/// 单次加载冻结在各 Travel projection 自带的 revision/source digest 上。
///
/// App 不把该快照写入本地业务真相源；刷新时始终重新读取所属对象。
final class TripJourneySnapshot {
  const TripJourneySnapshot({
    required this.plan,
    required this.timeline,
    required this.map,
    required this.memberships,
    required this.moments,
    required this.contentLinks,
    required this.placements,
    required this.guideAssignments,
  });

  final TripPlanSlice plan;
  final TripTimelineView timeline;
  final TripMapView map;
  final TripMembershipListSlice memberships;
  final TripMomentListSlice moments;
  final TripPlanContentLinkListSlice contentLinks;
  final TripPlanPlacementListSlice placements;
  final TripGuideAssignmentListSlice guideAssignments;

  bool get usesOneCurrentRevision =>
      plan.currentRevisionNumber == timeline.currentRevisionNumber &&
      timeline.currentRevisionNumber == map.currentRevisionNumber &&
      plan.currentRevisionId == timeline.currentRevisionId &&
      timeline.currentRevisionId == map.currentRevisionId;
}

/// 并发装载旅行工作台；任何必需投影失败时保持失败语义，不降级为“空行程”。
final class TripJourneyLoader {
  const TripJourneyLoader(this.query);

  final TripJourneyQuery query;

  Future<TripJourneySnapshot> load(String tripId) async {
    final normalizedTripId = tripId.trim();
    if (normalizedTripId.isEmpty) {
      throw ArgumentError.value(tripId, 'tripId', 'must not be blank');
    }

    final plan = query.getPlan(normalizedTripId);
    final timeline = query.getTimeline(normalizedTripId);
    final map = query.getMap(normalizedTripId);
    final memberships = query.listMemberships(normalizedTripId);
    final moments = query.listMoments(normalizedTripId);
    final contentLinks = query.listContentLinks(normalizedTripId);
    final placements = query.listPlacements(normalizedTripId);
    final guideAssignments = query.listGuideAssignments(normalizedTripId);

    return TripJourneySnapshot(
      plan: await plan,
      timeline: await timeline,
      map: await map,
      memberships: await memberships,
      moments: await moments,
      contentLinks: await contentLinks,
      placements: await placements,
      guideAssignments: await guideAssignments,
    );
  }
}
