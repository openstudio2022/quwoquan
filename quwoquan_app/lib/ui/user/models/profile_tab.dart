import 'package:quwoquan_app/cloud/user/generated/user_profile_ui_config.g.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';

/// 一级 Tab — 与 user_profile/ui_config.yaml profile_tabs 对齐
enum ProfileTab { creations, interaction }

/// 作品二级内容形式筛选：全部 / 图片 / 视频 / 文字。
enum CreationSubTab { all, image, video, article }

/// 创作内容格式过滤。
enum CreationWorkFormat { all, image, video, note }

/// 创作可见性过滤。
enum CreationVisibility { all, public_, private_ }

/// 互动子维度。
enum InteractionSubTab { all, comments, likes, shares }

/// 互动方向。
enum InteractionDirection { received, sent }

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

extension InteractionSubTabMetadata on InteractionSubTab {
  String get id => switch (this) {
    InteractionSubTab.all => 'all',
    InteractionSubTab.comments => 'comments',
    InteractionSubTab.likes => 'likes',
    InteractionSubTab.shares => 'shares',
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

InteractionSubTab interactionSubTabFromId(String id) {
  return switch (id) {
    'comments' => InteractionSubTab.comments,
    'likes' => InteractionSubTab.likes,
    'shares' => InteractionSubTab.shares,
    _ => InteractionSubTab.all,
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
