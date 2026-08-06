import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/presentation/generated/homepage_ui_config.g.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';

enum HomepageDetailTabTarget { record, discussion, relatedCircles }

String homepageTabLabelForKey(String labelKey) {
  return UITextConstants.contentLabelForKey(labelKey);
}

HomepageTabConfig? homepageTabById(String tabId) {
  for (final tab in HomepageUIConfig.tabs) {
    if (tab.id == tabId) {
      return tab;
    }
  }
  return null;
}

String homepageTabBodySlotForId(String tabId) {
  return homepageTabById(tabId)?.bodySlot ?? HomepageUIConfig.defaultTabId;
}

String homepageTabIdForTarget(HomepageDetailTabTarget? target) {
  final bodySlot = switch (target) {
    HomepageDetailTabTarget.record => 'content',
    HomepageDetailTabTarget.discussion => 'discussion',
    HomepageDetailTabTarget.relatedCircles => 'interest_circles',
    null => null,
  };
  if (bodySlot == null) {
    return HomepageUIConfig.defaultTabId;
  }
  for (final tab in HomepageUIConfig.tabs) {
    if (tab.bodySlot == bodySlot) {
      return tab.id;
    }
  }
  return HomepageUIConfig.defaultTabId;
}
