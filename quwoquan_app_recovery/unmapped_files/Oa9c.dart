import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

/// 更多功能弹窗 - 功能类型枚举
/// 定义所有支持的功能类型，确保类型安全
enum MoreActionType {
  // 通用功能
  share,
  copyLink,
  report,
  block,
  
  // 内容相关
  like,
  unlike,
  save,
  unsave,
  download,
  
  // 用户相关  
  follow,
  unfollow,
  blockUser,
  unblock,
  privateMessage,
  
  // 图片相关
  viewOriginal,
  reward,
  
  // 内容管理
  notInterested,
  featureFeedback,
  
  // 主题设置
  fontSettings,
  nightMode,
  dayMode,
  
  // 自定义类型
  custom,
}

/// 更多功能类型扩展
extension MoreActionTypeExtension on MoreActionType {
  /// 获取功能类型的默认图标
  IconData get defaultIcon {
    switch (this) {
      case MoreActionType.share:
        return Icons.share;
      case MoreActionType.copyLink:
        return Icons.link;
      case MoreActionType.report:
        return Icons.flag;
      case MoreActionType.block:
        return Icons.block;
      case MoreActionType.like:
        return Icons.favorite_border;
      case MoreActionType.unlike:
        return Icons.favorite;
      case MoreActionType.save:
        return Icons.bookmark_border;
      case MoreActionType.unsave:
        return Icons.bookmark;
      case MoreActionType.download:
        return Icons.download;
      case MoreActionType.follow:
        return Icons.person_add;
      case MoreActionType.unfollow:
        return Icons.person_remove;
      case MoreActionType.blockUser:
        return Icons.block;
      case MoreActionType.unblock:
        return Icons.block_outlined;
      case MoreActionType.privateMessage:
        return Icons.message_outlined;
      case MoreActionType.viewOriginal:
        return Icons.image_outlined;
      case MoreActionType.reward:
        return Icons.card_giftcard;
      case MoreActionType.notInterested:
        return Icons.thumb_down_outlined;
      case MoreActionType.featureFeedback:
        return Icons.feedback_outlined;
      case MoreActionType.fontSettings:
        return Icons.text_fields;
      case MoreActionType.nightMode:
        return Icons.dark_mode;
      case MoreActionType.dayMode:
        return Icons.light_mode;
    }
  }
  
  /// 获取功能类型的默认标题 - 使用语义文本常量
  String get defaultTitle {
    switch (this) {
      case MoreActionType.share:
        return UITextConstants.share;
      case MoreActionType.copyLink:
        return UITextConstants.copyLink;
      case MoreActionType.report:
        return UITextConstants.report;
      case MoreActionType.block:
        return UITextConstants.block;
      case MoreActionType.like:
        return UITextConstants.like;
      case MoreActionType.unlike:
        return UITextConstants.unlike;
      case MoreActionType.save:
        return UITextConstants.bookmark;
      case MoreActionType.unsave:
        return UITextConstants.unbookmark;
      case MoreActionType.download:
        return UITextConstants.save;
      case MoreActionType.follow:
        return UITextConstants.follow;
      case MoreActionType.unfollow:
        return UITextConstants.unfollow;
      case MoreActionType.blockUser:
        return UITextConstants.blockUser;
      case MoreActionType.unblock:
        return AppStrings.unblockUser;
      case MoreActionType.privateMessage:
        return UITextConstants.privateMessage;
      case MoreActionType.viewOriginal:
        return UITextConstants.viewOriginalImage;
      case MoreActionType.reward:
        return UITextConstants.reward;
      case MoreActionType.notInterested:
        return UITextConstants.notInterested;
      case MoreActionType.featureFeedback:
        return UITextConstants.featureFeedback;
      case MoreActionType.fontSettings:
        return UITextConstants.fontSettings;
      case MoreActionType.nightMode:
        return UITextConstants.nightMode;
      case MoreActionType.dayMode:
        return UITextConstants.dayMode;
    }
  }
}
