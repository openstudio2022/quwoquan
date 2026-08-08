import 'package:quwoquan_app/service/user_service/account/user_account/application/public/generated/user_profile_ui_config.g.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';

/// 一级 Tab — 与 user_profile/ui_config.yaml profile_tabs 对齐。
enum ProfileTab { creations, interaction }

/// 作品二级内容形式筛选：全部 / 图片 / 视频 / 文字。
enum CreationSubTab { all, image, video, article }

/// 创作内容格式过滤。
enum CreationWorkFormat { all, image, video, note }

/// 创作可见性过滤。
enum CreationVisibility { all, public_, private_ }

extension ProfileTabMetadata on ProfileTab {
  String get id => switch (this) {
    ProfileTab.creations => 'creations',
    ProfileTab.interaction => 'interaction',
  };
}

extension CreationSubTabMetadata on CreationSubTab {
  String get id => switch (this) {
    CreationSubTab.all => 'all',
    CreationSubTab.image => 'image',
    CreationSubTab.video => 'video',
    CreationSubTab.article => 'article',
  };
}

ProfileTab? profileTabFromId(String id) {
  return switch (id) {
    'creations' => ProfileTab.creations,
    'interaction' => ProfileTab.interaction,
    _ => null,
  };
}

CreationSubTab creationSubTabFromId(String id) {
  return switch (id) {
    'image' => CreationSubTab.image,
    'video' => CreationSubTab.video,
    'article' => CreationSubTab.article,
    _ => CreationSubTab.all,
  };
}

String profileTabLabelForId(String tabId) {
  for (final tab in UserProfileUIConfig.profileTabs) {
    if (tab.id == tabId) {
      return UITextConstants.contentLabelForKey(tab.labelKey);
    }
  }
  return UITextConstants.contentLabelForKey(tabId);
}
