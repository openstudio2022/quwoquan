// spec_ref: specs/feature-tree/travel-journey/collaborative-trip-lifecycle/trip-guide-template-assignment/spec.md#gwt-001
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/application/travel/trip_journey_query.dart';
import 'package:quwoquan_app/application/travel/trip_template_coordinator.dart';
import 'package:quwoquan_app/application/travel/trip_template_facet.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test(
    'current Trip becomes a privacy-safe independently identified template',
    () {
      var itemSequence = 0;
      final coordinator = TripTemplateCoordinator(
        facet: _RecordingTemplateFacet(),
        itemIdFactory: (_) => 'template-item-${++itemSequence}',
        idempotencyKeyFactory: () => 'template-intent-1',
      );

      final intent = coordinator.prepare(
        _snapshot(),
        title: ' 西湖两日模板 ',
        summary: ' 适合朋友同行 ',
      );

      expect(intent.idempotencyKey, 'template-intent-1');
      expect(intent.request.title, '西湖两日模板');
      expect(intent.request.summary, '适合朋友同行');
      expect(intent.request.dayCount, 2);
      expect(intent.request.items.map((item) => item.templateItemId), <String>[
        'template-item-1',
        'template-item-2',
        'template-item-3',
      ]);
      final stay = intent.request.items.first;
      expect(stay.kind, 'stay');
      expect(stay.title, isNull);
      expect(stay.note, isNull);
      expect(stay.publicPlaceRef, isNull);
      final sight = intent.request.items[1];
      expect(sight.dayOffset, 0);
      expect(sight.title, '西湖晨游');
      expect(sight.note, isNull);
      expect(sight.publicPlaceRef?.objectTypeRef, 'entity.Place');
      expect(sight.publicPlaceRef?.objectId, 'place-west-lake');
      expect(sight.attributionIds, <String>['source-1']);
      expect(intent.request.items.last.dayOffset, 1);
      expect(
        intent.request.attributions.single.referenceObjectTypeRef,
        'content.Post',
      );
      expect(intent.request.attributions.single.referenceObjectId, 'post-1');
    },
  );

  test('projection mismatch is rejected before remote template mutation', () {
    final coordinator = TripTemplateCoordinator(
      facet: _RecordingTemplateFacet(),
      itemIdFactory: (item) => 'template-${item.itemId}',
      idempotencyKeyFactory: () => 'template-intent-1',
    );

    expect(
      () => coordinator.prepare(
        _snapshot(mapRevisionId: 'revision-old'),
        title: '西湖模板',
      ),
      throwsStateError,
    );
  });

  test(
    'template revision preserves reusable structure and public attribution',
    () async {
      final facet = _RecordingTemplateFacet();
      final coordinator = TripTemplateCoordinator(
        facet: facet,
        itemIdFactory: (item) => 'template-${item.itemId}',
        idempotencyKeyFactory: () => 'template-revise-intent-1',
      );
      final template = _template();

      final intent = coordinator.prepareRevision(
        template,
        title: ' 西湖亲子周末 ',
        summary: ' 春秋季亲子同行 ',
      );
      final result = await coordinator.revise(intent);

      expect(intent.idempotencyKey, 'template-revise-intent-1');
      expect(intent.request.templateId, 'template-1');
      expect(intent.request.expectedVersion, 3);
      expect(intent.request.title, '西湖亲子周末');
      expect(intent.request.summary, '春秋季亲子同行');
      expect(intent.request.items, template.items);
      expect(intent.request.attributions, template.attributions);
      expect(facet.reviseKey, 'template-revise-intent-1');
      expect(result.title, '西湖亲子周末');
    },
  );
}

final class _RecordingTemplateFacet implements TripTemplateFacet {
  String? reviseKey;

  @override
  Future<TripPlanTemplate> createTemplate(
    CreateTripPlanTemplateRequest request, {
    required String idempotencyKey,
  }) {
    throw UnimplementedError();
  }

  @override
  Future<TripPlanTemplate> getTemplate(GetTripPlanTemplateQuery query) async {
    return _template();
  }

  @override
  Future<TripPlanTemplateListSlice> listTemplates() {
    throw UnimplementedError();
  }

  @override
  Future<TripPlanTemplate> reviseTemplate(
    PutTripPlanTemplateRequest request, {
    required String idempotencyKey,
  }) async {
    reviseKey = idempotencyKey;
    return _template(
      title: request.title,
      summary: request.summary,
      version: request.expectedVersion + 1,
    );
  }
}

TripPlanTemplate _template({
  String title = '西湖两日模板',
  String? summary = '适合朋友同行',
  int version = 3,
}) {
  final now = DateTime.utc(2026, 8, 2, 10);
  return TripPlanTemplate(
    id: 'template-1',
    version: version,
    ownerPersonaId: 'persona-1',
    title: title,
    summary: summary,
    dayCount: 1,
    templateItemIds: const <String>['template-item-1'],
    items: const <TripPlanTemplateItem>[
      TripPlanTemplateItem(
        templateItemId: 'template-item-1',
        dayOffset: 0,
        orderInDay: 1,
        kind: 'sight',
        title: '西湖',
        attributionIds: <String>['source-1'],
      ),
    ],
    attributionIds: const <String>['source-1'],
    attributionPersonaIds: const <String>['persona-author'],
    attributions: const <TripPlanTemplateAttribution>[
      TripPlanTemplateAttribution(
        attributionId: 'source-1',
        kind: TripPlanTemplateAttributionKind.professionalCommentary,
        referenceObjectTypeRef: 'content.Post',
        referenceObjectId: 'post-1',
        authorPersonaId: 'persona-author',
        title: '领队讲解',
      ),
    ],
    status: TripPlanTemplateStatus.active,
    createdAt: now,
    updatedAt: now,
  );
}

TripJourneySnapshot _snapshot({String mapRevisionId = 'revision-3'}) {
  final now = DateTime.utc(2026, 8, 2, 10);
  const place = TripPlaceRef(
    objectTypeRef: 'entity.Place',
    objectId: 'place-west-lake',
  );
  return TripJourneySnapshot(
    plan: TripPlanSlice(
      tripId: 'trip-1',
      version: 4,
      organizerPersonaId: 'persona-1',
      title: '西湖两日同行',
      status: TripPlanStatus.completed,
      sourceAttributions: const <TripPlanSourceAttribution>[
        TripPlanSourceAttribution(
          attributionId: 'source-1',
          kind: TripPlanSourceAttributionKind.publicSource,
          postId: 'post-1',
          authorPersonaId: 'persona-author',
          title: '西湖晨游参考',
        ),
      ],
      currentRevisionId: 'revision-3',
      currentRevisionNumber: 3,
      items: const <TripPlanItemSlice>[
        TripPlanItemSlice(
          itemId: 'item-stay',
          dayIndex: 1,
          orderInDay: 1,
          kind: TripPlanItemKind.stay,
          title: '1208 房',
          placeRef: place,
          note: '门锁密码 1234',
        ),
        TripPlanItemSlice(
          itemId: 'item-sight',
          dayIndex: 1,
          orderInDay: 2,
          kind: TripPlanItemKind.sight,
          title: '西湖晨游',
          placeRef: place,
          note: '集合电话 13800000000',
        ),
        TripPlanItemSlice(
          itemId: 'item-food',
          dayIndex: 2,
          orderInDay: 1,
          kind: TripPlanItemKind.food,
          title: '湖滨午餐',
        ),
      ],
      createdAt: now,
      updatedAt: now,
    ),
    timeline: TripTimelineView(
      tripId: 'trip-1',
      tripVersion: 4,
      tripStatus: TripPlanStatus.completed,
      currentRevisionId: 'revision-3',
      currentRevisionNumber: 3,
      revisionChangeReason: '',
      revisionSeverity: TripRevisionSeverity.minor,
      tripContentLinks: const <TripTimelineContentLinkSlice>[],
      days: const <TripTimelineDaySlice>[
        TripTimelineDaySlice(
          dayIndex: 1,
          unassignedMoments: <TripTimelineMomentSlice>[],
          unassignedContentLinks: <TripTimelineContentLinkSlice>[],
          items: <TripTimelineItemSlice>[
            TripTimelineItemSlice(
              itemId: 'item-sight',
              orderInDay: 2,
              kind: TripPlanItemKind.sight,
              title: '西湖晨游',
              moments: <TripTimelineMomentSlice>[],
              contentLinks: <TripTimelineContentLinkSlice>[
                TripTimelineContentLinkSlice(
                  linkId: 'link-1',
                  postId: 'post-1',
                  visibility: TripPlanContentLinkVisibility.public,
                  linkedByPersonaId: 'persona-1',
                ),
              ],
            ),
          ],
        ),
      ],
      sourceMomentIds: const <String>[],
      sourceContentLinkIds: const <String>['link-1'],
      sourceDigest:
          'sha256:94d192b3a326be1f019b71ef13ea5a367ffe939c5e9a88f1b270e53753d9569a',
      sourceEventId: 'event-timeline',
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
      sourceContentLinkIds: const <String>['link-1'],
      sourceDigest:
          'sha256:60be9861750facbfad8758254a2f76c0cfe78d54459a3bc187d49b1401fcd8e8',
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
