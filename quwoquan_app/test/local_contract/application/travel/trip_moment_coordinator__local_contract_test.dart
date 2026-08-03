// spec_ref: specs/feature-tree/travel-journey/collaborative-trip-lifecycle/trip-moment-content-link/spec.md#gwt-001
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/application/travel/trip_journey_query.dart';
import 'package:quwoquan_app/application/travel/trip_moment_coordinator.dart';
import 'package:quwoquan_app/application/travel/trip_moment_facet.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test(
    'confirmed text moment freezes current item and one retry key',
    () async {
      final facet = _RecordingMomentFacet();
      final coordinator = TripMomentCoordinator(
        facet: facet,
        idempotencyKeyFactory: () => 'moment-intent-1',
        now: () => DateTime.utc(2026, 8, 2, 10),
      );
      final intent = coordinator.prepareText(
        snapshot: _snapshot(),
        text: '  西湖晚风  ',
        target: const TripMomentTarget(dayIndex: 1, itemId: 'item-1'),
        visibility: TripMomentVisibility.tripMembers,
      );

      await coordinator.create(intent);
      await coordinator.create(intent);

      expect(intent.command.inlineText, '西湖晚风');
      expect(intent.command.revisionNumber, 3);
      expect(intent.command.dayIndex, 1);
      expect(intent.command.itemId, 'item-1');
      expect(
        intent.command.assignmentStatus,
        TripMomentAssignmentStatus.confirmed,
      );
      expect(facet.keys, <String>['moment-intent-1', 'moment-intent-1']);
    },
  );

  test('unassigned or stale targets fail closed before Remote mutation', () {
    final coordinator = TripMomentCoordinator(
      facet: _RecordingMomentFacet(),
      idempotencyKeyFactory: () => 'moment-intent-1',
    );

    expect(
      () => coordinator.prepareText(
        snapshot: _snapshot(),
        text: '待整理',
        visibility: TripMomentVisibility.tripMembers,
      ),
      throwsArgumentError,
    );
    expect(
      () => coordinator.prepareText(
        snapshot: _snapshot(),
        text: '错误目标',
        target: const TripMomentTarget(dayIndex: 2, itemId: 'missing'),
      ),
      throwsArgumentError,
    );
  });

  test('media moment freezes canonical asset identity and version', () {
    final coordinator = TripMomentCoordinator(
      facet: _RecordingMomentFacet(),
      idempotencyKeyFactory: () => 'moment-photo-1',
      now: () => DateTime.utc(2026, 8, 2, 11),
    );

    final intent = coordinator.prepareMedia(
      snapshot: _snapshot(),
      kind: TripMomentKind.photo,
      assetId: ' media-42 ',
      assetVersion: 7,
      target: const TripMomentTarget(dayIndex: 1, itemId: 'item-1'),
      visibility: TripMomentVisibility.tripMembers,
    );

    expect(intent.command.kind, TripMomentKind.photo);
    expect(intent.command.contentRef?.objectTypeRef, 'content.MediaAsset');
    expect(intent.command.contentRef?.objectId, 'media-42');
    expect(intent.command.sourceVersion, 7);
    expect(intent.command.capturedAt, DateTime.utc(2026, 8, 2, 11));
    expect(
      intent.command.assignmentStatus,
      TripMomentAssignmentStatus.confirmed,
    );
  });

  test(
    'post moment requires canonical version and preserves personal staging',
    () {
      final coordinator = TripMomentCoordinator(
        facet: _RecordingMomentFacet(),
        idempotencyKeyFactory: () => 'moment-post-1',
      );

      final intent = coordinator.preparePostReference(
        snapshot: _snapshot(),
        postId: 'post-9',
        postVersion: 3,
      );

      expect(intent.command.kind, TripMomentKind.postReference);
      expect(intent.command.contentRef?.objectTypeRef, 'content.Post');
      expect(intent.command.contentRef?.objectId, 'post-9');
      expect(intent.command.sourceVersion, 3);
      expect(intent.command.dayIndex, isNull);
      expect(intent.command.visibility, TripMomentVisibility.personal);
      expect(
        intent.command.assignmentStatus,
        TripMomentAssignmentStatus.unassigned,
      );
      expect(
        () => coordinator.preparePostReference(
          snapshot: _snapshot(),
          postId: 'post-without-version',
          postVersion: 0,
        ),
        throwsArgumentError,
      );
    },
  );

  test('media kind and shared unassigned media fail closed', () {
    final coordinator = TripMomentCoordinator(
      facet: _RecordingMomentFacet(),
      idempotencyKeyFactory: () => 'moment-media-1',
    );

    expect(
      () => coordinator.prepareMedia(
        snapshot: _snapshot(),
        kind: TripMomentKind.text,
        assetId: 'media-1',
        assetVersion: 1,
      ),
      throwsArgumentError,
    );
    expect(
      () => coordinator.prepareMedia(
        snapshot: _snapshot(),
        kind: TripMomentKind.photo,
        assetId: 'media-1',
        assetVersion: 1,
        visibility: TripMomentVisibility.tripMembers,
      ),
      throwsArgumentError,
    );
  });

  test(
    'assignment freezes moment CAS, current revision, target and retry key',
    () async {
      final facet = _RecordingMomentFacet();
      final coordinator = TripMomentCoordinator(
        facet: facet,
        idempotencyKeyFactory: () => 'moment-assign-1',
      );
      final snapshot = _snapshot(moments: <TripMomentSlice>[_existingMoment()]);

      final intent = coordinator.prepareAssignment(
        snapshot: snapshot,
        momentId: 'moment-existing',
        target: const TripMomentTarget(dayIndex: 1, itemId: 'item-1'),
        visibility: TripMomentVisibility.tripMembers,
      );
      await coordinator.assign(intent);
      await coordinator.assign(intent);

      expect(intent.command.expectedVersion, 4);
      expect(intent.command.revisionNumber, 3);
      expect(intent.command.sourceVersion, 9);
      expect(intent.command.dayIndex, 1);
      expect(intent.command.itemId, 'item-1');
      expect(facet.keys, <String>['moment-assign-1', 'moment-assign-1']);
    },
  );

  test(
    'delete freezes current version and refuses stale or unknown moment',
    () async {
      final facet = _RecordingMomentFacet();
      final coordinator = TripMomentCoordinator(
        facet: facet,
        idempotencyKeyFactory: () => 'moment-delete-1',
      );
      final snapshot = _snapshot(moments: <TripMomentSlice>[_existingMoment()]);

      final intent = coordinator.prepareDelete(
        snapshot: snapshot,
        momentId: 'moment-existing',
        reason: ' 用户移除 ',
      );
      await coordinator.delete(intent);

      expect(intent.command.expectedVersion, 4);
      expect(intent.command.reason, '用户移除');
      expect(facet.keys, <String>['moment-delete-1']);
      expect(
        () => coordinator.prepareDelete(
          snapshot: snapshot,
          momentId: 'missing',
          reason: '用户移除',
        ),
        throwsArgumentError,
      );
    },
  );
}

final class _RecordingMomentFacet implements TripMomentFacet {
  final List<String> keys = <String>[];

  @override
  Future<TripMomentSlice> create(
    CreateTripMomentRequest request, {
    required String idempotencyKey,
  }) async {
    keys.add(idempotencyKey);
    return _moment(request);
  }

  @override
  Future<TripMomentSlice> assign(
    AssignTripMomentRequest request, {
    required String idempotencyKey,
  }) async {
    keys.add(idempotencyKey);
    final now = DateTime.utc(2026, 8, 2, 10);
    return TripMomentSlice(
      momentId: request.momentId,
      version: request.expectedVersion + 1,
      tripId: request.tripId,
      revisionNumber: request.revisionNumber,
      dayIndex: request.dayIndex,
      itemId: request.itemId,
      kind: TripMomentKind.photo,
      contentRef: const TripMomentObjectRef(
        objectTypeRef: 'content.MediaAsset',
        objectId: 'media-1',
      ),
      capturedAt: now,
      visibility: request.visibility,
      assignmentStatus: TripMomentAssignmentStatus.confirmed,
      attributionPersonaId: 'persona-1',
      sourceVersion: request.sourceVersion,
      status: TripMomentStatus.active,
      createdAt: now,
      updatedAt: now,
    );
  }

  @override
  Future<TripMomentSlice> delete(
    DeleteTripMomentRequest request, {
    required String idempotencyKey,
  }) async {
    keys.add(idempotencyKey);
    final now = DateTime.utc(2026, 8, 2, 10);
    return TripMomentSlice(
      momentId: request.momentId,
      version: request.expectedVersion + 1,
      tripId: request.tripId,
      revisionNumber: 3,
      kind: TripMomentKind.text,
      inlineText: 'removed',
      capturedAt: now,
      visibility: TripMomentVisibility.personal,
      assignmentStatus: TripMomentAssignmentStatus.unassigned,
      attributionPersonaId: 'persona-1',
      sourceVersion: 0,
      status: TripMomentStatus.deleted,
      createdAt: now,
      updatedAt: now,
    );
  }
}

TripMomentSlice _moment(CreateTripMomentRequest request) => TripMomentSlice(
  momentId: 'moment-1',
  version: 1,
  tripId: request.tripId,
  revisionNumber: request.revisionNumber,
  dayIndex: request.dayIndex,
  itemId: request.itemId,
  kind: request.kind,
  inlineText: request.inlineText,
  capturedAt: request.capturedAt,
  visibility: request.visibility,
  assignmentStatus: request.assignmentStatus,
  attributionPersonaId: 'persona-1',
  sourceVersion: request.sourceVersion,
  status: TripMomentStatus.active,
  createdAt: request.capturedAt,
  updatedAt: request.capturedAt,
);

TripMomentSlice _existingMoment() {
  final now = DateTime.utc(2026, 8, 2, 9);
  return TripMomentSlice(
    momentId: 'moment-existing',
    version: 4,
    tripId: 'trip-1',
    revisionNumber: 2,
    kind: TripMomentKind.photo,
    contentRef: const TripMomentObjectRef(
      objectTypeRef: 'content.MediaAsset',
      objectId: 'media-1',
    ),
    capturedAt: now,
    visibility: TripMomentVisibility.personal,
    assignmentStatus: TripMomentAssignmentStatus.unassigned,
    attributionPersonaId: 'persona-1',
    sourceVersion: 9,
    status: TripMomentStatus.active,
    createdAt: now,
    updatedAt: now,
  );
}

TripJourneySnapshot _snapshot({
  List<TripMomentSlice> moments = const <TripMomentSlice>[],
}) {
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
      currentRevisionId: 'revision-3',
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
    moments: TripMomentListSlice(tripId: 'trip-1', moments: moments),
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
