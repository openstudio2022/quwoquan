import 'package:quwoquan_app/service/circle_service/circle_management/gathering/application/public/gathering_journey_moment_capability.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/application/public/gathering_journey_plan_capabilities.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/application/public/gathering_presentation_models.dart';

enum GatheringJourneyTimelineEntryKind {
  planItem,
  experience,
  contentReference,
}

final class GatheringJourneyTimelineEntry {
  const GatheringJourneyTimelineEntry({
    required this.entryId,
    required this.kind,
    required this.occurredAt,
    required this.title,
    required this.canonicalRef,
  });

  final String entryId;
  final GatheringJourneyTimelineEntryKind kind;
  final DateTime occurredAt;
  final String title;
  final String canonicalRef;
}

final class GatheringJourneyMapWaypoint {
  const GatheringJourneyMapWaypoint({
    required this.waypointId,
    required this.planItemId,
    required this.placeRef,
    required this.sequence,
  });

  final String waypointId;
  final String planItemId;
  final String placeRef;
  final int sequence;
}

/// Circle-owned Gathering 旅行体验的对象级组合 Slice。
///
/// Gathering、Plan 与 Experience 只通过 typed reference 组合；该 Slice
/// 不成为可写真相源。
final class GatheringJourneySnapshot {
  GatheringJourneySnapshot({
    required this.gathering,
    required this.plan,
    required Iterable<GatheringJourneyTimelineEntry> timeline,
    required Iterable<GatheringJourneyMapWaypoint> mapWaypoints,
    required Iterable<GatheringJourneyExperience> experiences,
    required this.sourceDigest,
  }) : timeline = List<GatheringJourneyTimelineEntry>.unmodifiable(timeline),
       mapWaypoints = List<GatheringJourneyMapWaypoint>.unmodifiable(
         mapWaypoints,
       ),
       experiences = List<GatheringJourneyExperience>.unmodifiable(experiences);

  final GatheringDetailPresentationSlice gathering;
  final GatheringPlan? plan;
  final List<GatheringJourneyTimelineEntry> timeline;
  final List<GatheringJourneyMapWaypoint> mapWaypoints;
  final List<GatheringJourneyExperience> experiences;
  final String sourceDigest;

  String get gatheringId => gathering.publicDetail.gatheringId;

  bool get planBelongsToGathering =>
      plan == null || plan!.gatheringId == gatheringId;
}

abstract interface class GatheringJourneyQuery {
  Future<GatheringJourneySnapshot> load(String gatheringId);
}
