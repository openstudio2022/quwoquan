// spec_ref: specs/feature-tree/travel-journey/collaborative-trip-lifecycle/trip-shared-timeline/spec.md#gwt-001
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/application/travel/trip_journey_query.dart';
import 'package:quwoquan_app/ui/travel/travel_text_constants.dart';
import 'package:quwoquan_app/ui/travel/widgets/trip_journey_overview.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  testWidgets(
    'compact journey keeps plan change, timeline and route together',
    (tester) async {
      await tester.binding.setSurfaceSize(const Size(390, 844));
      addTearDown(() => tester.binding.setSurfaceSize(null));

      var revised = false;
      var transitioned = false;
      var savedAsTemplate = false;
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: TripJourneyOverview(
              snapshot: _snapshot(),
              onRevisePlan: () => revised = true,
              transitionPlanLabel: '结束旅行',
              onTransitionPlan: () => transitioned = true,
              onSaveTemplate: () => savedAsTemplate = true,
            ),
          ),
        ),
      );

      expect(find.text('西湖七日同行'), findsOneWidget);
      expect(find.text('计划有更新'), findsOneWidget);
      expect(find.text('第1天'), findsOneWidget);
      expect(find.text('西湖晨游'), findsWidgets);
      expect(find.text('湖边晚风很好'), findsOneWidget);
      expect(find.text('路线地图'), findsOneWidget);
      await tester.tap(find.text('调整计划'));
      expect(revised, isTrue);
      await tester.tap(find.text('结束旅行'));
      expect(transitioned, isTrue);
      await tester.tap(find.text(TravelText.saveAsTemplate));
      expect(savedAsTemplate, isTrue);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets('expanded journey uses the same canonical projections', (
    tester,
  ) async {
    await tester.binding.setSurfaceSize(const Size(1024, 900));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(body: TripJourneyOverview(snapshot: _snapshot())),
      ),
    );

    expect(find.text('同行成员 1'), findsOneWidget);
    expect(find.text('旅途记录 1'), findsOneWidget);
    expect(find.text('关联分享 1'), findsOneWidget);
    expect(find.text('领队与讲解任务 0'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}

TripJourneySnapshot _snapshot() {
  final projectedAt = DateTime.utc(2026, 8, 2, 10);
  const place = TripTimelinePlaceRef(
    objectTypeRef: 'entity.Place',
    objectId: 'place-west-lake',
  );
  const mapPlace = TripMapPlaceRef(
    objectTypeRef: 'entity.Place',
    objectId: 'place-west-lake',
  );
  final item = TripTimelineItemSlice(
    itemId: 'item-1',
    orderInDay: 1,
    kind: TripPlanItemKind.sight,
    title: '西湖晨游',
    startAt: DateTime.utc(2026, 8, 8),
    endAt: DateTime.utc(2026, 8, 8, 2),
    placeRef: place,
    note: '避开午后高温',
    moments: <TripTimelineMomentSlice>[
      TripTimelineMomentSlice(
        momentId: 'moment-1',
        kind: TripMomentKind.text,
        inlineText: '湖边晚风很好',
        capturedAt: projectedAt,
        coarsePlaceRef: place,
        visibility: TripMomentVisibility.tripMembers,
        attributionPersonaId: 'persona-1',
      ),
    ],
    contentLinks: const <TripTimelineContentLinkSlice>[
      TripTimelineContentLinkSlice(
        linkId: 'link-1',
        postId: 'post-1',
        visibility: TripPlanContentLinkVisibility.tripMembers,
        linkedByPersonaId: 'persona-1',
      ),
    ],
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
      createdAt: projectedAt,
      updatedAt: projectedAt,
    ),
    timeline: TripTimelineView(
      tripId: 'trip-1',
      tripVersion: 4,
      tripStatus: TripPlanStatus.active,
      currentRevisionId: 'revision-3',
      currentRevisionNumber: 3,
      revisionChangeReason: '天气变化后调整午后安排',
      revisionSeverity: TripRevisionSeverity.minor,
      tripContentLinks: const <TripTimelineContentLinkSlice>[],
      days: <TripTimelineDaySlice>[
        TripTimelineDaySlice(
          dayIndex: 1,
          unassignedMoments: const <TripTimelineMomentSlice>[],
          unassignedContentLinks: const <TripTimelineContentLinkSlice>[],
          items: <TripTimelineItemSlice>[item],
        ),
      ],
      sourceMomentIds: const <String>['moment-1'],
      sourceContentLinkIds: const <String>['link-1'],
      sourceDigest:
          'sha256:94d192b3a326be1f019b71ef13ea5a367ffe939c5e9a88f1b270e53753d9569a',
      sourceEventId: 'event-timeline-1',
      projectedAt: projectedAt,
    ),
    map: TripMapView(
      tripId: 'trip-1',
      currentRevisionId: 'revision-3',
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
          contentLinkIds: <String>['link-1'],
        ),
      ],
      routeSegments: const <TripMapRouteSegmentSlice>[],
      momentMarkers: const <TripMapMomentMarkerSlice>[],
      sourceMomentIds: const <String>['moment-1'],
      sourceContentLinkIds: const <String>['link-1'],
      sourceDigest:
          'sha256:60be9861750facbfad8758254a2f76c0cfe78d54459a3bc187d49b1401fcd8e8',
      sourceEventId: 'event-map-1',
      projectedAt: projectedAt,
    ),
    memberships: TripMembershipListSlice(
      tripId: 'trip-1',
      memberships: <TripMembershipSlice>[
        TripMembershipSlice(
          membershipId: 'membership-1',
          version: 1,
          tripId: 'trip-1',
          personaId: 'persona-1',
          role: TripMembershipRole.organizer,
          state: TripMembershipState.active,
          sourceKind: TripMembershipSourceKind.tripInvitation,
          sourceVersion: 1,
          joinedAt: projectedAt,
          updatedAt: projectedAt,
        ),
      ],
    ),
    moments: TripMomentListSlice(
      tripId: 'trip-1',
      moments: <TripMomentSlice>[
        TripMomentSlice(
          momentId: 'moment-1',
          version: 1,
          tripId: 'trip-1',
          revisionNumber: 3,
          dayIndex: 1,
          itemId: 'item-1',
          kind: TripMomentKind.text,
          inlineText: '湖边晚风很好',
          assignmentStatus: TripMomentAssignmentStatus.confirmed,
          capturedAt: projectedAt,
          visibility: TripMomentVisibility.tripMembers,
          attributionPersonaId: 'persona-1',
          sourceVersion: 1,
          status: TripMomentStatus.active,
          createdAt: projectedAt,
          updatedAt: projectedAt,
        ),
      ],
    ),
    contentLinks: TripPlanContentLinkListSlice(
      tripId: 'trip-1',
      links: <TripPlanContentLinkSlice>[
        TripPlanContentLinkSlice(
          linkId: 'link-1',
          version: 1,
          tripId: 'trip-1',
          postId: 'post-1',
          revisionNumber: 3,
          targetKind: TripPlanContentLinkTargetKind.item,
          dayIndex: 1,
          itemId: 'item-1',
          visibility: TripPlanContentLinkVisibility.tripMembers,
          linkedByPersonaId: 'persona-1',
          sourceVersion: 1,
          status: TripPlanContentLinkStatus.active,
          createdAt: projectedAt,
          updatedAt: projectedAt,
        ),
      ],
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
