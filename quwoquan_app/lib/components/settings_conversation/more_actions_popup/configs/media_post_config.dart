import 'package:flutter/material.dart';

/// 「更多」菜单中的作品形态筛选项（id/label 来自 metadata codegen，禁止硬编码业务串）。
class MoreActionFilterOption {
  final String id;
  final String label;

  const MoreActionFilterOption({required this.id, required this.label});
}

/// Work Browser 文章阅读设置项（id/label 来自 metadata codegen）。
class MoreActionReadingOption {
  final String id;
  final String label;

  const MoreActionReadingOption({required this.id, required this.label});
}

/// 媒体帖子更多操作配置（回调闭包捕获帖子上下文；本配置不持有业务对象以避免 dynamic）。
class MediaPostMoreActionConfig {
  final bool showShareAction;
  final bool showViewOriginalAction;
  final VoidCallback? onReward;
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
  final bool showDeleteAction;
  final VoidCallback? onDelete;

  /// 作品形态筛选（全部作品/图片/视频/文章）；空列表则不渲染“内容过滤”入口。
  final List<MoreActionFilterOption> filterOptions;
  final List<String> selectedFilterIds;
  final ValueChanged<Set<String>>? onFilterSelectionChanged;

  /// 文章阅读设置；仅在 Work Browser 当前作品为文章时由宿主传入。
  final List<MoreActionReadingOption> readingOptions;
  final String? selectedReadingOptionId;
  final ValueChanged<String>? onReadingOptionChanged;

  /// Work Browser 沉浸式浏览器要求“更多功能”整页深色，
  /// 独立于全局主题切换。
  final bool forceDarkAppearance;

  const MediaPostMoreActionConfig({
    this.showShareAction = false,
    this.showViewOriginalAction = false,
    this.onReward,
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
    this.showDeleteAction = false,
    this.onDelete,
    this.filterOptions = const <MoreActionFilterOption>[],
    this.selectedFilterIds = const <String>[],
    this.onFilterSelectionChanged,
    this.readingOptions = const <MoreActionReadingOption>[],
    this.selectedReadingOptionId,
    this.onReadingOptionChanged,
    this.forceDarkAppearance = false,
  });
}
