import 'package:quwoquan_app/l10n/copy/gathering_travel_text_constants.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/application/public/gathering_journey_travelogue_draft.dart';

/// 把 Circle 隐私快照组合为可编辑游记语义，不依赖 Content 编辑器实现。
final class GatheringTravelTextTravelogueDraftComposer
    implements GatheringJourneyTravelogueDraftComposer {
  const GatheringTravelTextTravelogueDraftComposer();

  @override
  GatheringJourneyTravelogueDraftContent compose(
    GatheringJourneyTravelogueDraftSource source,
  ) {
    final blocks = <GatheringJourneyTravelogueDraftBlock>[
      const GatheringJourneyTravelogueDraftBlock(
        kind: GatheringJourneyTravelogueDraftBlockKind.paragraph,
        text: GatheringTravelText.travelogueIntro,
      ),
    ];
    for (final day in source.days) {
      blocks.add(
        GatheringJourneyTravelogueDraftBlock(
          kind: GatheringJourneyTravelogueDraftBlockKind.heading,
          text:
              '${GatheringTravelText.dayPrefix}${day.dayIndex}${GatheringTravelText.daySuffix}',
        ),
      );
      for (final entry in day.entries) {
        blocks.add(
          GatheringJourneyTravelogueDraftBlock(
            kind: GatheringJourneyTravelogueDraftBlockKind.orderedItem,
            text: entry.title.trim().isEmpty
                ? GatheringTravelText.traveloguePlanItem
                : entry.title.trim(),
          ),
        );
      }
    }
    return GatheringJourneyTravelogueDraftContent(
      title: GatheringTravelText.travelogueDraftTitle,
      summary: GatheringTravelText.travelogueDraftSummary,
      blocks: blocks,
    );
  }
}
