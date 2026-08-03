// spec_ref: specs/feature-tree/travel-journey/collaborative-trip-lifecycle/trip-guide-template-assignment/spec.md#gwt-001
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/application/travel/trip_guide_assignment_coordinator.dart';
import 'package:quwoquan_app/application/travel/trip_guide_assignment_facet.dart';
import 'package:quwoquan_app/application/travel/trip_journey_query.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test(
    'guide task progression freezes CAS version and one retry key',
    () async {
      final facet = _RecordingGuideFacet();
      final coordinator = TripGuideAssignmentCoordinator(
        facet: facet,
        idempotencyKeyFactory: () => 'guide-intent-1',
      );
      final intent = coordinator.prepareNext(_assignment())!;

      await coordinator.transition(intent);
      await coordinator.transition(intent);

      expect(intent.command.expectedVersion, 2);
      expect(intent.command.targetStatus, TripGuideAssignmentStatus.accepted);
      expect(facet.keys, <String>['guide-intent-1', 'guide-intent-1']);
    },
  );

  test('terminal guide task has no implicit next transition', () {
    final coordinator = TripGuideAssignmentCoordinator(
      facet: _RecordingGuideFacet(),
      idempotencyKeyFactory: () => 'guide-intent-1',
    );

    expect(
      coordinator.prepareNext(
        _assignment(status: TripGuideAssignmentStatus.completed),
      ),
      isNull,
    );
  });

  test(
    'organizer creates and reassigns one typed guide task with CAS',
    () async {
      final facet = _RecordingGuideFacet();
      final coordinator = TripGuideAssignmentCoordinator(
        facet: facet,
        idempotencyKeyFactory: () => 'guide-put-intent',
        taskKeyFactory: () => 'guide-task-new',
      );
      final create = coordinator.prepareCreate(
        snapshot: _journeySnapshot(),
        actorPersonaId: 'persona-organizer',
        assigneePersonaId: 'persona-guide',
        role: TripGuideRole.licensedGuide,
        taskKind: TripGuideTaskKind.commentary,
        title: '西湖专业讲解',
      );
      await coordinator.put(create);

      expect(create.command.expectedVersion, 0);
      expect(create.command.taskKey, 'guide-task-new');
      expect(
        create.command.attributionKind,
        TripGuideAttributionKind.professionalCommentary,
      );
      expect(create.command.attributionPersonaId, 'persona-guide');
      expect(create.command.publicQualificationPersonaId, 'persona-guide');

      final reassign = coordinator.prepareReassign(
        snapshot: _journeySnapshot(),
        actorPersonaId: 'persona-organizer',
        assignment: _assignment(),
        assigneePersonaId: 'persona-guide-2',
      );
      expect(reassign.command.expectedVersion, 2);
      expect(reassign.command.taskKey, 'west-lake-collection');
      expect(reassign.command.assigneePersonaId, 'persona-guide-2');
      expect(reassign.command.publicQualificationPersonaId, 'persona-guide-2');
      expect(facet.putKeys, <String>['guide-put-intent']);
    },
  );
}

final class _RecordingGuideFacet implements TripGuideAssignmentFacet {
  final List<String> keys = <String>[];
  final List<String> putKeys = <String>[];

  @override
  Future<TripGuideAssignment> put(
    PutTripGuideAssignmentRequest request, {
    required String idempotencyKey,
  }) async {
    putKeys.add(idempotencyKey);
    return _assignment();
  }

  @override
  Future<TripGuideAssignment> transition(
    TransitionTripGuideAssignmentRequest request, {
    required String idempotencyKey,
  }) async {
    keys.add(idempotencyKey);
    return _assignment(status: request.targetStatus);
  }
}

TripJourneySnapshot _journeySnapshot() {
  final now = DateTime.utc(2026, 8, 2, 10);
  return TripJourneySnapshot(
    plan: TripPlanSlice(
      tripId: 'trip-1',
      version: 1,
      organizerPersonaId: 'persona-organizer',
      title: '西湖同行',
      status: TripPlanStatus.active,
      sourceAttributions: const <TripPlanSourceAttribution>[],
      currentRevisionId: 'revision-3',
      currentRevisionNumber: 3,
      items: const <TripPlanItemSlice>[
        TripPlanItemSlice(
          itemId: 'item-1',
          dayIndex: 1,
          orderInDay: 1,
          kind: TripPlanItemKind.sight,
          title: '西湖',
        ),
      ],
      createdAt: now,
      updatedAt: now,
    ),
    timeline: TripTimelineView(
      tripId: 'trip-1',
      tripVersion: 1,
      tripStatus: TripPlanStatus.active,
      currentRevisionId: 'revision-3',
      currentRevisionNumber: 3,
      revisionChangeReason: '',
      revisionSeverity: TripRevisionSeverity.minor,
      tripContentLinks: const <TripTimelineContentLinkSlice>[],
      days: const <TripTimelineDaySlice>[],
      sourceMomentIds: const <String>[],
      sourceContentLinkIds: const <String>[],
      sourceDigest: 'sha256:timeline',
      sourceEventId: 'event-timeline',
      projectedAt: now,
    ),
    map: TripMapView(
      tripId: 'trip-1',
      currentRevisionId: 'revision-3',
      currentRevisionNumber: 3,
      stops: const <TripMapStopSlice>[],
      routeSegments: const <TripMapRouteSegmentSlice>[],
      momentMarkers: const <TripMapMomentMarkerSlice>[],
      sourceMomentIds: const <String>[],
      sourceContentLinkIds: const <String>[],
      sourceDigest: 'sha256:map',
      sourceEventId: 'event-map',
      projectedAt: now,
    ),
    memberships: const TripMembershipListSlice(
      tripId: 'trip-1',
      memberships: <TripMembershipSlice>[],
    ),
    moments: const TripMomentListSlice(
      tripId: 'trip-1',
      moments: <TripMomentSlice>[],
    ),
    contentLinks: const TripPlanContentLinkListSlice(
      tripId: 'trip-1',
      links: <TripPlanContentLinkSlice>[],
    ),
    placements: const TripPlanPlacementListSlice(
      tripId: 'trip-1',
      placements: <TripPlanPlacementSlice>[],
    ),
    guideAssignments: const TripGuideAssignmentListSlice(
      tripId: 'trip-1',
      assignments: <TripGuideAssignment>[],
    ),
  );
}

TripGuideAssignment _assignment({
  TripGuideAssignmentStatus status = TripGuideAssignmentStatus.assigned,
}) {
  final now = DateTime.utc(2026, 8, 2, 10);
  return TripGuideAssignment(
    id: 'assignment-1',
    version: 2,
    tripId: 'trip-1',
    taskKey: 'west-lake-collection',
    assigneePersonaId: 'persona-guide',
    role: TripGuideRole.licensedGuide,
    taskKind: TripGuideTaskKind.collection,
    title: '集合与出发说明',
    sourceRevisionNumber: 3,
    attributionKind: TripGuideAttributionKind.professionalCommentary,
    attributionPersonaId: 'persona-guide',
    publicQualificationPersonaId: 'persona-guide',
    status: status,
    createdByPersonaId: 'persona-organizer',
    createdAt: now,
    updatedAt: now,
  );
}
