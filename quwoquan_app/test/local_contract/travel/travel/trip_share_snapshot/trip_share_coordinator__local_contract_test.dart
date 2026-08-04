// spec_ref: specs/feature-tree/travel-journey/collaborative-trip-lifecycle/trip-shared-timeline/spec.md#gwt-001
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/travel/travel/trip_timeline_view/application/trip_journey_query.dart';
import 'package:quwoquan_app/travel/travel/trip_share_snapshot/application/trip_share_coordinator.dart';
import 'package:quwoquan_app/travel/travel/trip_share_snapshot/application/trip_share_facet.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test(
    'day share freezes one revision and only includes that day moments',
    () async {
      final facet = _RecordingShareFacet();
      final coordinator = TripShareCoordinator(
        facet: facet,
        idempotencyKeyFactory: () => 'share-intent-1',
      );

      final result = await coordinator.create(
        _snapshot(),
        const TripShareSelection.day(dayIndex: 1),
      );

      expect(facet.idempotencyKey, 'share-intent-1');
      expect(facet.request?.sourceRevisionId, 'revision-3');
      expect(
        facet.request?.sourceDigest,
        'sha256:94d192b3a326be1f019b71ef13ea5a367ffe939c5e9a88f1b270e53753d9569a',
      );
      expect(facet.request?.momentIds, const <String>['moment-1']);
      expect(result.sourceRevisionNumber, 3);
    },
  );

  test('share refuses projections from different revisions', () {
    final facet = _RecordingShareFacet();
    final coordinator = TripShareCoordinator(
      facet: facet,
      idempotencyKeyFactory: () => 'share-intent-2',
    );

    expect(
      () => coordinator.create(
        _snapshot(mapRevisionId: 'revision-2'),
        const TripShareSelection.full(),
      ),
      throwsStateError,
    );
    expect(facet.request, isNull);
  });
}

final class _RecordingShareFacet implements TripShareFacet {
  CreateTripShareSnapshotRequest? request;
  String? idempotencyKey;

  @override
  Future<TripShareSnapshot> createSnapshot(
    CreateTripShareSnapshotRequest request, {
    required String idempotencyKey,
  }) async {
    this.request = request;
    this.idempotencyKey = idempotencyKey;
    return _shareSnapshot(request);
  }

  @override
  Future<TripShareSnapshot> getSnapshot(String snapshotId) {
    throw UnimplementedError();
  }
}

TripJourneySnapshot _snapshot({String mapRevisionId = 'revision-3'}) {
  final now = DateTime.utc(2026, 8, 2, 10);
  const timelinePlace = TripTimelinePlaceRef(
    objectTypeRef: 'entity.Place',
    objectId: 'place-west-lake',
  );
  const mapPlace = TripMapPlaceRef(
    objectTypeRef: 'entity.Place',
    objectId: 'place-west-lake',
  );
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
      revisionChangeReason: '天气变化',
      revisionSeverity: TripRevisionSeverity.minor,
      tripContentLinks: const <TripTimelineContentLinkSlice>[],
      days: <TripTimelineDaySlice>[
        TripTimelineDaySlice(
          dayIndex: 1,
          items: <TripTimelineItemSlice>[
            TripTimelineItemSlice(
              itemId: 'item-1',
              orderInDay: 1,
              kind: TripPlanItemKind.sight,
              title: '西湖晨游',
              placeRef: timelinePlace,
              moments: const <TripTimelineMomentSlice>[],
              contentLinks: const <TripTimelineContentLinkSlice>[],
            ),
          ],
          unassignedMoments: const <TripTimelineMomentSlice>[],
          unassignedContentLinks: const <TripTimelineContentLinkSlice>[],
        ),
        const TripTimelineDaySlice(
          dayIndex: 2,
          items: <TripTimelineItemSlice>[],
          unassignedMoments: <TripTimelineMomentSlice>[],
          unassignedContentLinks: <TripTimelineContentLinkSlice>[],
        ),
      ],
      sourceMomentIds: const <String>['moment-1', 'moment-2'],
      sourceContentLinkIds: const <String>[],
      sourceDigest:
          'sha256:94d192b3a326be1f019b71ef13ea5a367ffe939c5e9a88f1b270e53753d9569a',
      sourceEventId: 'event-timeline-1',
      projectedAt: now,
    ),
    map: TripMapView(
      tripId: 'trip-1',
      currentRevisionId: mapRevisionId,
      currentRevisionNumber: 3,
      stops: const <TripMapStopSlice>[
        TripMapStopSlice(
          stopId: 'stop-1',
          sequence: 1,
          dayIndex: 1,
          itemId: 'item-1',
          title: '西湖晨游',
          placeRef: mapPlace,
          momentIds: <String>['moment-1'],
          contentLinkIds: <String>[],
        ),
      ],
      routeSegments: const <TripMapRouteSegmentSlice>[],
      momentMarkers: const <TripMapMomentMarkerSlice>[],
      sourceMomentIds: const <String>['moment-1', 'moment-2'],
      sourceContentLinkIds: const <String>[],
      sourceDigest:
          'sha256:60be9861750facbfad8758254a2f76c0cfe78d54459a3bc187d49b1401fcd8e8',
      sourceEventId: 'event-map-1',
      projectedAt: now,
    ),
    memberships: const TripMembershipListSlice(
      tripId: 'trip-1',
      memberships: <TripMembershipSlice>[],
    ),
    moments: TripMomentListSlice(
      tripId: 'trip-1',
      moments: <TripMomentSlice>[
        _moment(now, id: 'moment-1', dayIndex: 1),
        _moment(now, id: 'moment-2', dayIndex: 2),
      ],
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

TripMomentSlice _moment(
  DateTime now, {
  required String id,
  required int dayIndex,
}) {
  return TripMomentSlice(
    momentId: id,
    version: 1,
    tripId: 'trip-1',
    revisionNumber: 3,
    dayIndex: dayIndex,
    kind: TripMomentKind.photo,
    capturedAt: now,
    visibility: TripMomentVisibility.tripMembers,
    assignmentStatus: TripMomentAssignmentStatus.confirmed,
    attributionPersonaId: 'persona-1',
    sourceVersion: 1,
    status: TripMomentStatus.active,
    createdAt: now,
    updatedAt: now,
  );
}

TripShareSnapshot _shareSnapshot(CreateTripShareSnapshotRequest request) {
  return TripShareSnapshot(
    id: 'snapshot-1',
    version: 1,
    tripId: request.tripId,
    sourceRevisionId: request.sourceRevisionId,
    sourceRevisionNumber: 3,
    sourceDigest: request.sourceDigest,
    scope: request.scope,
    dayIndex: request.dayIndex,
    itemId: request.itemId,
    momentIds: request.momentIds,
    visibility: request.visibility,
    privacyPolicyDigest:
        'sha256:760672367557300130bdf88db43b01f07917475ae4f60ff0b9be95aa78d7e2f1',
    items: const <TripShareItemSlice>[],
    moments: const <TripShareMomentSlice>[],
    contentLinks: const <TripShareContentLinkSlice>[],
    routeStops: const <TripShareRouteStopSlice>[],
    createdByPersonaId: 'persona-1',
    status: TripShareSnapshotStatus.active,
    createdAt: DateTime.utc(2026, 8, 2, 10),
  );
}
