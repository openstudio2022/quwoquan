import 'package:quwoquan_app/travel/travel/trip_share_snapshot/application/trip_travelogue_draft.dart';
import 'package:quwoquan_app/ui/travel/travel_text_constants.dart';

/// 把隐私安全旅行事实组合为可编辑游记语义，不依赖 Content 编辑器实现。
final class TravelTextTripTravelogueDraftComposer
    implements TripTravelogueDraftComposer {
  const TravelTextTripTravelogueDraftComposer();

  @override
  TripTravelogueDraftContent compose(TripTravelogueDraftSource source) {
    final blocks = <TripTravelogueDraftBlock>[
      const TripTravelogueDraftBlock(
        kind: TripTravelogueDraftBlockKind.paragraph,
        text: TravelText.travelogueIntro,
      ),
    ];
    for (final day in source.days) {
      blocks.add(
        TripTravelogueDraftBlock(
          kind: TripTravelogueDraftBlockKind.heading,
          text: '${TravelText.dayPrefix}${day.dayIndex}${TravelText.daySuffix}',
        ),
      );
      for (final item in day.items) {
        final title = (item.title ?? '').trim();
        blocks.add(
          TripTravelogueDraftBlock(
            kind: TripTravelogueDraftBlockKind.orderedItem,
            text: title.isEmpty ? _itemKindLabel(item.kind) : title,
          ),
        );
      }
      if (day.routeStops.isNotEmpty) {
        blocks.add(
          const TripTravelogueDraftBlock(
            kind: TripTravelogueDraftBlockKind.paragraph,
            text: TravelText.travelogueRouteSection,
          ),
        );
        for (final stop in day.routeStops) {
          final title = (stop.title ?? '').trim();
          blocks.add(
            TripTravelogueDraftBlock(
              kind: TripTravelogueDraftBlockKind.bulletItem,
              text: title.isEmpty
                  ? '${TravelText.stopPrefix}${stop.sequence}${TravelText.stopSuffix}'
                  : title,
            ),
          );
        }
      }
      if (day.moments.isNotEmpty) {
        blocks.add(
          TripTravelogueDraftBlock(
            kind: TripTravelogueDraftBlockKind.paragraph,
            text: TravelText.travelogueMomentSummary(day.moments.length),
          ),
        );
      }
      if (day.contentLinks.isNotEmpty) {
        blocks.add(
          TripTravelogueDraftBlock(
            kind: TripTravelogueDraftBlockKind.paragraph,
            text: TravelText.travelogueContentSummary(day.contentLinks.length),
          ),
        );
      }
    }
    return TripTravelogueDraftContent(
      title: TravelText.travelogueDraftTitle,
      summary: TravelText.travelogueDraftSummary,
      blocks: blocks,
    );
  }
}

String _itemKindLabel(String kind) => switch (kind.trim()) {
  'stay' => TravelText.itemStay,
  'food' => TravelText.itemFood,
  'sight' => TravelText.itemSight,
  'activity' => TravelText.itemActivity,
  'transport' => TravelText.itemTransport,
  'rest' => TravelText.itemRest,
  'free_time' => TravelText.itemFreeTime,
  _ => TravelText.traveloguePlanItem,
};
