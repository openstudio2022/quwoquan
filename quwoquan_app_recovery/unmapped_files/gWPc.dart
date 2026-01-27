import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/shared/components/more_actions_popup/more_action_config.dart';
import 'package:quwoquan_app/shared/components/more_actions_popup/more_action_style.dart';
import 'package:quwoquan_app/shared/components/more_actions_popup/more_action_types.dart';
import 'package:quwoquan_app/shared/components/more_actions_popup/more_action_utils.dart';

/// 媒体post更多功能配置
class MediaPostMoreActionConfig extends MoreActionConfig {
  final dynamic post;
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
  final VoidCallback? onReport;

  MediaPostMoreActionConfig({
    required this.post,
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
    this.onReport,
  });

  @override
  String get title => AppStrings.moreFunctions;

  @override
  List<MoreActionItem> get horizontalItems => [
    // 打赏功能
    if (onReward != null)
      MoreActionItem.simple(
        title: '打赏',
        icon: Icons.monetization_on,
        type: MoreActionType.reward,
        onTap: () {
          onReward?.call();
          // TODO: 实现打赏功能
        },
        permission: 'vip', // VIP用户才能打赏
      ),
    
    // 保存功能
    MoreActionItem.simple(
      title: '保存',
      icon: Icons.bookmark,
      type: MoreActionType.save,
      onTap: () {
        onSave?.call();
        // TODO: 实现保存功能
      },
    ),
    
    // 私信功能
    MoreActionItem.simple(
      title: '私信',
      icon: Icons.message,
      type: MoreActionType.privateMessage,
      onTap: () {
        onMessage?.call();
        // TODO: 实现私信功能
      },
    ),
    
    // 复制链接功能
    MoreActionItem.simple(
      title: '复制链接',
      icon: Icons.link,
      type: MoreActionType.copyLink,
      onTap: () {
        onCopyLink?.call();
        // TODO: 实现复制链接功能
      },
    ),
    
    // 查看原图功能
    MoreActionItem.simple(
      title: '查看原图',
      icon: Icons.zoom_in,
      type: MoreActionType.viewOriginal,
      onTap: () {
        onViewOriginal?.call();
        // TODO: 实现查看原图功能
      },
    ),
    
    // 字体设置功能
    MoreActionItem.simple(
      title: '字体设置',
      icon: Icons.font_download,
      type: MoreActionType.fontSettings,
      onTap: () {
        onFontSettings?.call();
        // TODO: 实现字体设置功能
      },
    ),
    
    // 主题切换功能
    MoreActionItem(
      title: _getThemeToggleTitle(),
      icon: _getThemeToggleIcon(),
      type: MoreActionType.nightMode, // 默认显示夜间模式
      onTap: () {
        onThemeToggle?.call();
        // TODO: 实现主题切换功能
      },
    ),
    
    // 功能反馈
    MoreActionItem.simple(
      title: '功能反馈',
      icon: Icons.feedback,
      type: MoreActionType.featureFeedback,
      onTap: () {
        onFeedback?.call();
        // TODO: 实现功能反馈功能
      },
    ),
  ];

  @override
  List<MoreActionItem> get bottomActions => [
    // 不感兴趣
    MoreActionItem(
      title: AppStrings.notInterested,
      subtitle: AppStrings.notInterestedDesc,
      icon: Icons.thumb_down,
      type: MoreActionType.notInterested,
      onTap: () {
        onNotInterested?.call();
        // TODO: 实现不感兴趣功能
      },
    ),
    
    // 屏蔽用户
    MoreActionItem(
      title: AppStrings.blockUser,
      subtitle: AppStrings.blockUserDesc,
      icon: Icons.block,
      type: MoreActionType.blockUser,
      onTap: () {
        onBlockUser?.call();
        // TODO: 实现屏蔽用户功能
      },
    ),
    
    // 举报
    MoreActionItem(
      title: AppStrings.report,
      subtitle: AppStrings.reportContent,
      icon: Icons.flag,
      type: MoreActionType.report,
      onTap: () {
        onReport?.call();
        // TODO: 实现举报功能
      },
    ),
  ];

  @override
  MoreActionStyle get style => MoreActionStyle.mediaPostStyle;

  @override
  MoreActionPermissionChecker? get permissionChecker => _checkPermission;

  /// 获取主题切换标题
  String _getThemeToggleTitle() {
    // TODO: 根据当前主题状态返回对应标题
    return AppStrings.dayMode; // 临时返回
  }

  /// 获取主题切换图标
  IconData _getThemeToggleIcon() {
    // TODO: 根据当前主题状态返回对应图标
    return Icons.light_mode_outlined; // 临时返回
  }

  /// 权限检查
  static bool _checkPermission(String permission) {
    return MoreActionUtils.checkPermission(permission);
  }
}
