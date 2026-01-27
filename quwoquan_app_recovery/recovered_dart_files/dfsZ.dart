import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/shared/components/more_actions_popup/more_action_config.dart';
import 'package:quwoquan_app/shared/components/more_actions_popup/more_action_style.dart';
import 'package:quwoquan_app/shared/components/more_actions_popup/more_action_types.dart';
import 'package:quwoquan_app/shared/components/more_actions_popup/more_action_utils.dart';

/// 作者主页更多功能配置
class ProfileMoreActionConfig extends MoreActionConfig {
  final String userId;
  final String username;
  final bool isFollowing;
  final bool isBlocked;
  final bool isVerified;
  final VoidCallback? onFollow;
  final VoidCallback? onUnfollow;
  final VoidCallback? onMessage;
  final VoidCallback? onShare;
  final VoidCallback? onCopyLink;
  final VoidCallback? onBlockUser;
  final VoidCallback? onUnblockUser;
  final VoidCallback? onReport;
  final VoidCallback? onViewProfile;
  final VoidCallback? onViewPosts;
  final VoidCallback? onViewFollowers;
  final VoidCallback? onViewFollowing;

  ProfileMoreActionConfig({
    required this.userId,
    required this.username,
    this.isFollowing = false,
    this.isBlocked = false,
    this.isVerified = false,
    this.onFollow,
    this.onUnfollow,
    this.onMessage,
    this.onShare,
    this.onCopyLink,
    this.onBlockUser,
    this.onUnblockUser,
    this.onReport,
    this.onViewProfile,
    this.onViewPosts,
    this.onViewFollowers,
    this.onViewFollowing,
  });

  @override
  String get title => AppStrings.userOptions;

  @override
  List<MoreActionItem> get horizontalItems => [
    // 关注/取消关注功能
    if (!isBlocked)
      MoreActionItem(
        type: isFollowing ? MoreActionType.unfollow : MoreActionType.follow,
        title: isFollowing ? AppStrings.unfollow : AppStrings.follow,
        icon: isFollowing ? Icons.person_remove : Icons.person_add,
        onTap: () {
          if (isFollowing) {
            onUnfollow?.call();
          } else {
            onFollow?.call();
          }
          // TODO: 实现关注/取消关注功能
        },
      ),
    
    // 私信功能
    if (!isBlocked)
      MoreActionItem.simple(
        title: '私信',
        icon: Icons.message,
        type: MoreActionType.privateMessage,
        onTap: () {
          onMessage?.call();
          // TODO: 实现私信功能
        },
      ),
    
    // 分享功能
    MoreActionItem.simple(
      title: '分享',
      icon: Icons.share,
      type: MoreActionType.share,
      onTap: () {
        onShare?.call();
        // TODO: 实现分享功能
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
    
    // 查看资料功能
    MoreActionItem.custom(
      title: AppStrings.viewProfile,
      icon: Icons.person_outline,
      type: MoreActionType.custom,
      onTap: () {
        onViewProfile?.call();
        // TODO: 实现查看资料功能
      },
    ),
    
    // 查看动态功能
    MoreActionItem.custom(
      title: AppStrings.viewPosts,
      icon: Icons.dynamic_feed_outlined,
      type: MoreActionType.custom,
      onTap: () {
        onViewPosts?.call();
        // TODO: 实现查看动态功能
      },
    ),
  ];

  @override
  List<MoreActionItem> get bottomActions => [
    // 查看粉丝功能
    MoreActionItem.custom(
      title: AppStrings.viewFollowers,
      icon: Icons.people_outline,
      subtitle: AppStrings.viewFollowersDesc,
      type: MoreActionType.custom,
      onTap: () {
        onViewFollowers?.call();
        // TODO: 实现查看粉丝功能
      },
    ),
    
    // 查看关注功能
    MoreActionItem.custom(
      title: AppStrings.viewFollowing,
      icon: Icons.person_add_outlined,
      subtitle: AppStrings.viewFollowingDesc,
      type: MoreActionType.custom,
      onTap: () {
        onViewFollowing?.call();
        // TODO: 实现查看关注功能
      },
    ),
    
    // 屏蔽/取消屏蔽用户
    MoreActionItem(
      type: isBlocked ? MoreActionType.unblock : MoreActionType.blockUser,
      title: isBlocked ? AppStrings.unblockUser : AppStrings.blockUser,
      subtitle: isBlocked ? AppStrings.unblockUserDesc : AppStrings.blockUserDesc,
      icon: isBlocked ? Icons.person_add : Icons.block,
      onTap: () {
        if (isBlocked) {
          onUnblockUser?.call();
        } else {
          onBlockUser?.call();
        }
        // TODO: 实现屏蔽/取消屏蔽功能
      },
    ),
    
    // 举报用户
    MoreActionItem(
      type: MoreActionType.report,
      title: AppStrings.reportUser,
      subtitle: AppStrings.reportUserDesc,
      icon: Icons.report,
      onTap: () {
        onReport?.call();
        // TODO: 实现举报用户功能
      },
    ),
  ];

  @override
  MoreActionStyle get style => MoreActionStyle.profileStyle;

  @override
  MoreActionPermissionChecker? get permissionChecker => _checkPermission;

  /// 权限检查
  static bool _checkPermission(String permission) {
    return MoreActionUtils.checkPermission(permission);
  }
}
