// spec_ref: specs/feature-tree/travel-journey/collaborative-trip-lifecycle/trip-shared-timeline/spec.md#gwt-001
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/application/travel/trip_travelogue_draft.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test(
    'privacy snapshot becomes one deterministic ordered draft source',
    () async {
      final writer = _RecordingWriter();
      final coordinator = TripTravelogueDraftCoordinator(
        composer: const _RecordingComposer(),
        writer: writer,
        draftIdFactory: (snapshotId) => 'travelogue-$snapshotId',
      );

      final firstId = await coordinator.create(_snapshot());
      final retryId = await coordinator.create(_snapshot());

      expect(firstId, 'travelogue-share-1');
      expect(retryId, firstId);
      expect(writer.sources, hasLength(2));
      expect(
        writer.sources.map((source) => source.localDraftId),
        everyElement(firstId),
      );
      final source = writer.sources.first;
      expect(source.sourceEntityRef, 'travel.TripShareSnapshot:share-1@2');
      expect(source.sourceDigest, 'sha256:share-source');
      expect(
        source.privacyPolicyDigest,
        'sha256:760672367557300130bdf88db43b01f07917475ae4f60ff0b9be95aa78d7e2f1',
      );
      expect(source.visibility, TripShareSnapshotVisibility.public);
      expect(writer.contents.first.title, '旅行游记');
      expect(source.days.map((day) => day.dayIndex), <int>[1, 2]);
      expect(source.days.first.items.map((item) => item.itemId), <String>[
        'item-1',
        'item-2',
      ]);
      expect(source.days.first.routeStops.map((stop) => stop.sequence), <int>[
        1,
        2,
      ]);
    },
  );

  test('non-frozen or empty snapshot is rejected before Content adapter', () {
    final coordinator = TripTravelogueDraftCoordinator(
      composer: const _RecordingComposer(),
      writer: _RecordingWriter(),
      draftIdFactory: (_) => 'draft',
    );
    final empty = _snapshot(
      items: const <TripShareItemSlice>[],
      moments: const <TripShareMomentSlice>[],
      links: const <TripShareContentLinkSlice>[],
      stops: const <TripShareRouteStopSlice>[],
    );

    expect(() => coordinator.buildSource(empty), throwsArgumentError);
  });
}

final class _RecordingWriter implements TripTravelogueDraftWriter {
  final List<TripTravelogueDraftSource> sources = <TripTravelogueDraftSource>[];
  final List<TripTravelogueDraftContent> contents =
      <TripTravelogueDraftContent>[];

  @override
  Future<String> save(
    TripTravelogueDraftSource source,
    TripTravelogueDraftContent content,
  ) async {
    sources.add(source);
    contents.add(content);
    return source.localDraftId;
  }
}

final class _RecordingComposer implements TripTravelogueDraftComposer {
  const _RecordingComposer();

  @override
  TripTravelogueDraftContent compose(TripTravelogueDraftSource source) {
    return TripTravelogueDraftContent(
      title: '旅行游记',
      summary: '可编辑旅行时间线',
      blocks: const <TripTravelogueDraftBlock>[
        TripTravelogueDraftBlock(
          kind: TripTravelogueDraftBlockKind.paragraph,
          text: '旅行正文',
        ),
      ],
    );
  }
}

TripShareSnapshot _snapshot({
  List<TripShareItemSlice>? items,
  List<TripShareMomentSlice>? moments,
  List<TripShareContentLinkSlice>? links,
  List<TripShareRouteStopSlice>? stops,
}) {
  final now = DateTime.utc(2026, 8, 2, 10);
  return TripShareSnapshot(
    id: 'share-1',
    version: 2,
    tripId: 'trip-1',
    sourceRevisionId: 'revision-3',
    sourceRevisionNumber: 3,
    sourceDigest: 'sha256:share-source',
    scope: TripShareSnapshotScope.full,
    momentIds: const <String>['moment-1'],
    visibility: TripShareSnapshotVisibility.public,
    privacyPolicyDigest:
        'sha256:760672367557300130bdf88db43b01f07917475ae4f60ff0b9be95aa78d7e2f1',
    items:
        items ??
        const <TripShareItemSlice>[
          TripShareItemSlice(
            dayIndex: 2,
            itemId: 'item-3',
            orderInDay: 1,
            kind: 'food',
            title: '河坊街晚餐',
          ),
          TripShareItemSlice(
            dayIndex: 1,
            itemId: 'item-2',
            orderInDay: 2,
            kind: 'food',
            title: '湖边午餐',
          ),
          TripShareItemSlice(
            dayIndex: 1,
            itemId: 'item-1',
            orderInDay: 1,
            kind: 'sight',
            title: '西湖晨游',
          ),
        ],
    moments:
        moments ??
        const <TripShareMomentSlice>[
          TripShareMomentSlice(
            momentId: 'moment-1',
            dayIndex: 1,
            itemId: 'item-1',
            kind: 'image',
            contentObjectTypeRef: 'content.MediaAsset',
            contentObjectId: 'media-1',
          ),
        ],
    contentLinks:
        links ??
        const <TripShareContentLinkSlice>[
          TripShareContentLinkSlice(
            linkId: 'link-1',
            postId: 'post-1',
            dayIndex: 1,
            itemId: 'item-1',
          ),
        ],
    routeStops:
        stops ??
        const <TripShareRouteStopSlice>[
          TripShareRouteStopSlice(
            dayIndex: 1,
            itemId: 'item-2',
            sequence: 2,
            title: '湖边午餐',
            placeRef: TripSharePlaceRef(
              objectTypeRef: 'entity.Place',
              objectId: 'place-2',
            ),
          ),
          TripShareRouteStopSlice(
            dayIndex: 1,
            itemId: 'item-1',
            sequence: 1,
            title: '西湖晨游',
            placeRef: TripSharePlaceRef(
              objectTypeRef: 'entity.Place',
              objectId: 'place-1',
            ),
          ),
        ],
    createdByPersonaId: 'persona-1',
    status: TripShareSnapshotStatus.active,
    createdAt: now,
  );
}
