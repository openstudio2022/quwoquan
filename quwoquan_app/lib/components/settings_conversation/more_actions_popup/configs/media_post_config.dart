import 'package:flutter/material.dart';

/// 媒体帖子更多操作配置（回调闭包捕获帖子上下文；本配置不持有业务对象以避免 dynamic）。
class MediaPostMoreActionConfig {
  final bool showShareAction;
  final bool showViewOriginalAction;
  final VoidCallback? onReward;
  final VoidCallback? onSave;
  final VoidCallback? onMessage;
  final VoidCallback? onCopyLink;
  final VoidCallback? onViewOriginal;
  final VoidCallback? onFontSettings;
  final VoidCallback? onThemeToggle;
  final VoidCallback? onFeedback;
  final VoidCallback? onNotInterested;
  final VoidCallback? onBlockUser;
  final VoidCallback? onBlockWords;
  final VoidCallback? onReport;
  final VoidCallback? onShare;

  const MediaPostMoreActionConfig({
    this.showShareAction = false,
    this.showViewOriginalAction = false,
    this.onReward,
    this.onSave,
    this.onMessage,
    this.onCopyLink,
    this.onViewOriginal,
    this.onFontSettings,
    this.onThemeToggle,
    this.onFeedback,
    this.onNotInterested,
    this.onBlockUser,
    this.onBlockWords,
    this.onReport,
    this.onShare,
  });
}
