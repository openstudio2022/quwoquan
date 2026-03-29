import 'package:flutter/material.dart';

/// 更多操作类型枚举
enum MoreActionType {
  share,
  copyLink,
  report,
  block,
  like,
  unlike,
  save,
  unsave,
  reward,
  message,
  viewOriginal,
  fontSettings,
  themeToggle,
  feedback,
  notInterested,
}

/// 扩展方法：获取操作类型的默认图标
extension MoreActionTypeExtension on MoreActionType {
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
      case MoreActionType.reward:
        return Icons.monetization_on;
      case MoreActionType.message:
        return Icons.message;
      case MoreActionType.viewOriginal:
        return Icons.image;
      case MoreActionType.fontSettings:
        return Icons.font_download;
      case MoreActionType.themeToggle:
        return Icons.brightness_6;
      case MoreActionType.feedback:
        return Icons.feedback;
      case MoreActionType.notInterested:
        return Icons.visibility_off;
    }
  }
}
