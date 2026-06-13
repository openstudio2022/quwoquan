import 'package:quwoquan_app/cloud/runtime/generated/entity/homepage_ui_config.g.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';

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
