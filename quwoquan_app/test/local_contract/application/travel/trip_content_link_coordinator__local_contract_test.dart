// spec_ref: specs/feature-tree/travel-journey/collaborative-trip-lifecycle/trip-moment-content-link/spec.md#gwt-001
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/application/travel/trip_content_link_coordinator.dart';
import 'package:quwoquan_app/application/travel/trip_content_link_facet.dart';
import 'package:quwoquan_app/application/travel/trip_journey_query.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test(
    'confirmed Post link freezes revision target source version and key',
    () async {
      final facet = _RecordingContentLinkFacet();
      final coordinator = TripContentLinkCoordinator(
        facet,
        (scope) => '$scope-intent-1',
      );
      final intent = coordinator.preparePut(
        snapshot: _snapshot(),
        postId: ' post-1 ',
        sourceVersion: 7,
        target: const TripContentTarget.item(dayIndex: 1, itemId: 'item-1'),
        visibility: TripPlanContentLinkVisibility.tripMembers,
      );

      await coordinator.put(intent);
      await coordinator.put(intent);

      expect(intent.request.postId, 'post-1');
      expect(intent.request.revisionNumber, 3);
      expect(intent.request.targetKind, TripPlanContentLinkTargetKind.item);
      expect(intent.request.dayIndex, 1);
      expect(intent.request.itemId, 'item-1');
      expect(intent.request.sourceVersion, 7);
      expect(facet.keys, <String>['put-intent-1', 'put-intent-1']);
    },
  );

  test('stale projections invalid targets and source versions fail closed', () {
    final coordinator = TripContentLinkCoordinator(
      _RecordingContentLinkFacet(),
      (scope) => '$scope-intent-1',
    );

    expect(
      () => coordinator.preparePut(
        snapshot: _snapshot(mapRevisionId: 'revision-2'),
        postId: 'post-1',
        sourceVersion: 1,
        target: const TripContentTarget.day(1),
        visibility: TripPlanContentLinkVisibility.tripMembers,
      ),
      throwsStateError,
    );
    expect(
      () => coordinator.preparePut(
        snapshot: _snapshot(),
        postId: 'post-1',
        sourceVersion: 0,
        target: const TripContentTarget.day(1),
        visibility: TripPlanContentLinkVisibility.tripMembers,
      ),
      throwsArgumentError,
    );
    expect(
      () => coordinator.preparePut(
        snapshot: _snapshot(),
        postId: 'post-1',
        sourceVersion: 1,
        target: const TripContentTarget.item(dayIndex: 1, itemId: 'missing'),
        visibility: TripPlanContentLinkVisibility.tripMembers,
      ),
      throwsArgumentError,
    );
  });

  test('trip-level travelogue link keeps a stable publication key', () {
    final coordinator = TripContentLinkCoordinator(
      _RecordingContentLinkFacet(),
      (scope) => '$scope-random',
    );

    final intent = coordinator.preparePut(
      snapshot: _snapshot(),
      postId: 'post-travelogue',
      sourceVersion: 8,
      target: const TripContentTarget.trip(),
      visibility: TripPlanContentLinkVisibility.public,
      idempotencyKey: 'travelogue-draft-1-post-travelogue',
    );

    expect(intent.request.targetKind, TripPlanContentLinkTargetKind.trip);
    expect(intent.request.dayIndex, isNull);
    expect(intent.request.itemId, isNull);
    expect(intent.idempotencyKey, 'travelogue-draft-1-post-travelogue');
  });

  test('active link removal freezes version reason and retry key', () async {
    final facet = _RecordingContentLinkFacet();
    final coordinator = TripContentLinkCoordinator(
      facet,
      (scope) => '$scope-intent-1',
    );
    final intent = coordinator.prepareRemoval(
      current: _link(),
      reason: ' 行程已调整 ',
    );

    await coordinator.remove(intent);
    await coordinator.remove(intent);

    expect(intent.request.expectedVersion, 2);
    expect(intent.request.reason, '行程已调整');
    expect(facet.keys, <String>['remove-intent-1', 'remove-intent-1']);
  });
}

final class _RecordingContentLinkFacet implements TripContentLinkFacet {
  final List<String> keys = <String>[];

  @override
  Future<TripPlanContentLinkSlice> put(
    PutTripPlanContentLinkRequest request, {
    required String idempotencyKey,
  }) async {
    keys.add(idempotencyKey);
    return _link(
      postId: request.postId,
      revisionNumber: request.revisionNumber,
      dayIndex: request.dayIndex,
      itemId: request.itemId,
      visibility: request.visibility,
      sourceVersion: request.sourceVersion,
    );
  }

  @override
  Future<TripPlanContentLinkSlice> remove(
    RemoveTripPlanContentLinkRequest request, {
    required String idempotencyKey,
  }) async {
    keys.add(idempotencyKey);
    return _link(status: TripPlanContentLinkStatus.removed);
  }
}

TripPlanContentLinkSlice _link({
  String postId = 'post-1',
  int revisionNumber = 3,
  int? dayIndex = 1,
  String? itemId = 'item-1',
  TripPlanContentLinkVisibility visibility =
      TripPlanContentLinkVisibility.tripMembers,
  int sourceVersion = 7,
  TripPlanContentLinkStatus status = TripPlanContentLinkStatus.active,
}) {
  final now = DateTime.utc(2026, 8, 2, 10);
  return TripPlanContentLinkSlice(
    linkId: 'link-1',
    version: 2,
    tripId: 'trip-1',
    postId: postId,
    revisionNumber: revisionNumber,
    targetKind: itemId == null
        ? TripPlanContentLinkTargetKind.day
        : TripPlanContentLinkTargetKind.item,
    dayIndex: dayIndex,
    itemId: itemId,
    visibility: visibility,
    linkedByPersonaId: 'persona-1',
    sourceVersion: sourceVersion,
    status: status,
    createdAt: now,
    updatedAt: now,
  );
}

TripJourneySnapshot _snapshot({String mapRevisionId = 'revision-3'}) {
  final now = DateTime.utc(2026, 8, 2, 10);
  return TripJourneySnapshot(
    plan: TripPlanSlice(
      tripId: 'trip-1',
      version: 4,
      organizerPersonaId: 'persona-1',
      title: '西湖七日同行',
      status: TripPlanStatus.active,
      sourceAttributions: const <TripPlanSourceAttribution>[],
      currentRevisionId: 'revision-3',
      currentRevisionNumber: 3,
      items: const <TripPlanItemSlice>[],
      createdAt: now,
      updatedAt: now,
    ),
    timeline: TripTimelineView(
      tripId: 'trip-1',
      tripVersion: 4,
      tripStatus: TripPlanStatus.active,
      currentRevisionId: 'revision-3',
      currentRevisionNumber: 3,
      revisionChangeReason: '',
      revisionSeverity: TripRevisionSeverity.minor,
      tripContentLinks: const <TripTimelineContentLinkSlice>[],
      days: const <TripTimelineDaySlice>[
        TripTimelineDaySlice(
          dayIndex: 1,
          items: <TripTimelineItemSlice>[
            TripTimelineItemSlice(
              itemId: 'item-1',
              orderInDay: 1,
              kind: TripPlanItemKind.sight,
              title: '西湖晨游',
              moments: <TripTimelineMomentSlice>[],
              contentLinks: <TripTimelineContentLinkSlice>[],
            ),
          ],
          unassignedMoments: <TripTimelineMomentSlice>[],
          unassignedContentLinks: <TripTimelineContentLinkSlice>[],
        ),
      ],
      sourceMomentIds: const <String>[],
      sourceContentLinkIds: const <String>[],
      sourceDigest: 'sha256:timeline',
      sourceEventId: 'event-timeline-1',
      projectedAt: now,
    ),
    map: TripMapView(
      tripId: 'trip-1',
      currentRevisionId: mapRevisionId,
      currentRevisionNumber: 3,
      stops: const <TripMapStopSlice>[],
      routeSegments: const <TripMapRouteSegmentSlice>[],
      momentMarkers: const <TripMapMomentMarkerSlice>[],
      sourceMomentIds: const <String>[],
      sourceContentLinkIds: const <String>[],
      sourceDigest: 'sha256:map',
      sourceEventId: 'event-map-1',
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
