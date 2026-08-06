import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle/presentation/generated/circle_ui_config.g.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';

String circleTabLabelForKey(String labelKey) {
  return UITextConstants.contentLabelForKey(labelKey);
}

CircleTabConfig? circleTabById(String tabId) {
  for (final tab in CircleUIConfig.tabs) {
    if (tab.id == tabId) {
      return tab;
    }
  }
  return null;
}

CircleSectionConfig? circleSectionByType(String sectionType) {
  for (final section in CircleUIConfig.sections) {
    if (section.sectionType == sectionType) {
      return section;
    }
  }
  return null;
}

String circleSectionLabel(String sectionType) {
  final section = circleSectionByType(sectionType);
  if (section == null) {
    return sectionType;
  }
  return UITextConstants.contentLabelForKey(section.labelKey);
}

IconData circleSectionIcon(String sectionType) {
  final icon = circleSectionByType(sectionType)?.icon;
  return switch (icon) {
    'sparkles' => CupertinoIcons.sparkles,
    'heart' => CupertinoIcons.heart,
    'chat_bubble_2' => CupertinoIcons.chat_bubble_2,
    'folder' => CupertinoIcons.folder,
    _ => CupertinoIcons.square_grid_2x2,
  };
}
