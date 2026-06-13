import 'package:quwoquan_app/cloud/user/generated/user_profile_ui_config.g.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';

/// 一级 Tab — 与 user_profile/ui_config.yaml profile_tabs 对齐
enum ProfileTab { creations, circles, interaction, lifestyle }

/// 创作二级 identity filter。
enum CreationSubTab { all, moment, work, micro, image, video, article }

/// 创作内容格式过滤。
enum CreationWorkFormat { all, image, video, note }

/// 创作可见性过滤。
enum CreationVisibility { all, public_, private_ }

/// 互动子维度。
enum InteractionSubTab { likes, comments, shares }

/// 互动方向。
enum InteractionDirection { received, sent }

extension ProfileTabMetadata on ProfileTab {
  String get id => switch (this) {
    ProfileTab.creations => 'creations',
    ProfileTab.circles => 'circles',
    ProfileTab.interaction => 'interaction',
    ProfileTab.lifestyle => 'lifestyle',
  };
}

extension CreationSubTabMetadata on CreationSubTab {
  String get id => switch (this) {
    CreationSubTab.all => 'all',
    CreationSubTab.moment => 'moment',
    CreationSubTab.work => 'work',
    CreationSubTab.micro => 'micro',
    CreationSubTab.image => 'image',
    CreationSubTab.video => 'video',
    CreationSubTab.article => 'article',
  };
}

extension InteractionSubTabMetadata on InteractionSubTab {
  String get id => switch (this) {
    InteractionSubTab.likes => 'likes',
    InteractionSubTab.comments => 'comments',
    InteractionSubTab.shares => 'shares',
  };
}

ProfileTab? profileTabFromId(String id) {
  return switch (id) {
    'creations' => ProfileTab.creations,
    'circles' => ProfileTab.circles,
    'interaction' => ProfileTab.interaction,
    'lifestyle' => ProfileTab.lifestyle,
    _ => null,
  };
}

CreationSubTab creationSubTabFromId(String id) {
  return switch (id) {
    'moment' => CreationSubTab.moment,
    'work' => CreationSubTab.work,
    'micro' => CreationSubTab.micro,
    'image' => CreationSubTab.image,
    'video' => CreationSubTab.video,
    'article' => CreationSubTab.article,
    _ => CreationSubTab.all,
  };
}

InteractionSubTab interactionSubTabFromId(String id) {
  return switch (id) {
    'comments' => InteractionSubTab.comments,
    'shares' => InteractionSubTab.shares,
    _ => InteractionSubTab.likes,
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
