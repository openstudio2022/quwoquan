// spec_ref: specs/feature-tree/travel-journey/collaborative-trip-lifecycle/trip-shared-timeline/spec.md#gwt-001
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/travel/travel/trip_share_snapshot/application/trip_travelogue_draft.dart';
import 'package:quwoquan_app/ui/travel/sharing/trip_travelogue_draft_composer.dart';
import 'package:quwoquan_app/ui/travel/travel_text_constants.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test('privacy-safe day facts become editable travelogue semantic blocks', () {
    final content = const TravelTextTripTravelogueDraftComposer().compose(
      _source(),
    );

    expect(content.title, TravelText.travelogueDraftTitle);
    expect(content.summary, TravelText.travelogueDraftSummary);
    expect(
      content.blocks.map((block) => block.text),
      containsAllInOrder(<String>[
        TravelText.travelogueIntro,
        '第1天',
        TravelText.itemSight,
        TravelText.travelogueRouteSection,
        '西湖晨游',
        TravelText.travelogueMomentSummary(1),
        TravelText.travelogueContentSummary(1),
      ]),
    );
    expect(
      content.blocks.map((block) => block.kind),
      contains(TripTravelogueDraftBlockKind.orderedItem),
    );
  });
}

TripTravelogueDraftSource _source() {
  return TripTravelogueDraftSource(
    localDraftId: 'travelogue-share-1',
    snapshotId: 'share-1',
    snapshotVersion: 1,
    tripId: 'trip-1',
    sourceRevisionId: 'revision-1',
    sourceRevisionNumber: 1,
    sourceDigest:
        'sha256:41cf6794ba4200b839c53531555f0f3998df4cbb01a4d5cb0b94e3ca5e23947d',
    privacyPolicyDigest:
        'sha256:760672367557300130bdf88db43b01f07917475ae4f60ff0b9be95aa78d7e2f1',
    scope: TripShareSnapshotScope.full,
    visibility: TripShareSnapshotVisibility.public,
    days: <TripTravelogueDaySource>[
      TripTravelogueDaySource(
        dayIndex: 1,
        items: const <TripShareItemSlice>[
          TripShareItemSlice(
            dayIndex: 1,
            itemId: 'item-1',
            orderInDay: 1,
            kind: 'sight',
          ),
        ],
        moments: const <TripShareMomentSlice>[
          TripShareMomentSlice(
            momentId: 'moment-1',
            dayIndex: 1,
            kind: 'image',
            contentObjectTypeRef: 'content.MediaAsset',
            contentObjectId: 'media-1',
          ),
        ],
        contentLinks: const <TripShareContentLinkSlice>[
          TripShareContentLinkSlice(
            linkId: 'link-1',
            postId: 'post-1',
            dayIndex: 1,
          ),
        ],
        routeStops: const <TripShareRouteStopSlice>[
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
      ),
    ],
  );
}
