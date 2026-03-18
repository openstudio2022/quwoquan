import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:quwoquan_app/cloud/services/user/relationship_capability_repository.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/user/models/profile_mode.dart';

/// 用户主页五态按钮矩阵
///
/// | 状态           | 按钮布局                                         |
/// |---------------|------------------------------------------------|
/// | self          | 编辑资料 / 管理分身                               |
/// | not_following | 关注 / 私信                                      |
/// | following     | 已关注 / 私信                                    |
/// | followed_by   | 回关 / 私信                                      |
/// | mutual        | 私信 / 视频通话 / 语音通话 三等分                  |
class ProfileActionBar extends StatelessWidget {
  const ProfileActionBar({
    super.key,
    required this.mode,
    required this.isDark,
    this.capability,
    // legacy callbacks (兼容已有 caller)
    this.isFollowing = false,
    this.onEditProfile,
    this.onManagePersonas,
    this.onFollow,
    this.onMessage,
    // 新增回调
    this.onGreet,
    this.onVoiceCall,
    this.onVideoCall,
  });

  final ProfileMode mode;
  final bool isDark;

  /// 关系能力位（载入后提供，null 时回退到 isFollowing 旧逻辑）
  final RelationshipCapabilityDto? capability;

  // — Legacy
  final bool isFollowing;
  final VoidCallback? onEditProfile;
  final VoidCallback? onManagePersonas;
  final VoidCallback? onFollow;
  final VoidCallback? onMessage;

  // — 新增
  final VoidCallback? onGreet;
  final VoidCallback? onVoiceCall;
  final VoidCallback? onVideoCall;

  @override
  Widget build(BuildContext context) {
    final fg = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final border = AppColorsFunctional.getColor(
      isDark,
      ColorType.borderPrimary,
    );

    if (mode == ProfileMode.mine) {
      return Row(
        children: [
          Expanded(
            child: _ActionButton(
              label: UITextConstants.profileEditLabel,
              icon: Icons.edit_outlined,
              onTap: onEditProfile,
              fg: fg,
              border: border,
            ),
          ),
          SizedBox(width: AppSpacing.sm),
          Expanded(
            child: _ActionButton(
              label: UITextConstants.profilePersonasLabel,
              icon: Icons.people_outline,
              onTap: onManagePersonas,
              fg: fg,
              border: border,
            ),
          ),
        ],
      );
    }

    final cap = capability;

    if (cap != null && cap.isMutual) {
      return Row(
        children: [
          Expanded(
            child: _ActionButton(
              label: UITextConstants.profileDirectMessage,
              icon: Icons.chat_bubble_outline,
              onTap: onMessage,
              fg: fg,
              border: border,
            ),
          ),
          SizedBox(width: AppSpacing.sm),
          Expanded(
            child: _ActionButton(
              label: UITextConstants.callVideo,
              icon: CupertinoIcons.video_camera,
              onTap: cap.canStartVideoCall ? onVideoCall : null,
              fg: fg,
              border: border,
            ),
          ),
          SizedBox(width: AppSpacing.sm),
          Expanded(
            child: _ActionButton(
              label: UITextConstants.callVoice,
              icon: CupertinoIcons.phone,
              onTap: cap.canStartVoiceCall ? onVoiceCall : null,
              fg: fg,
              border: border,
            ),
          ),
        ],
      );
    }

    if (cap != null && cap.isFollowedBy) {
      return Row(
        children: [
          Expanded(
            child: _ActionButton(
              label: UITextConstants.followBack,
              icon: Icons.add,
              onTap: onFollow,
              fg: Colors.white,
              border: AppColors.primaryColor,
              filled: true,
            ),
          ),
          SizedBox(width: AppSpacing.sm),
          Expanded(
            child: _ActionButton(
              label: UITextConstants.profileDirectMessage,
              icon: Icons.chat_bubble_outline,
              onTap: onMessage,
              fg: fg,
              border: border,
            ),
          ),
        ],
      );
    }

    if (cap != null && (cap.isFollowing || cap.isNotFollowing)) {
      final alreadyFollowing = cap.isFollowing;
      return Row(
        children: [
          Expanded(
            child: _ActionButton(
              label: alreadyFollowing
                  ? UITextConstants.following
                  : UITextConstants.follow,
              icon: alreadyFollowing ? Icons.check : Icons.add,
              onTap: onFollow,
              fg: alreadyFollowing ? fgSecondary : Colors.white,
              border: alreadyFollowing ? border : AppColors.primaryColor,
              filled: !alreadyFollowing,
            ),
          ),
          SizedBox(width: AppSpacing.sm),
          Expanded(
            child: _ActionButton(
              label: UITextConstants.profileDirectMessage,
              icon: Icons.chat_bubble_outline,
              onTap: onMessage,
              fg: fg,
              border: border,
            ),
          ),
        ],
      );
    }

    // fallback：旧版 isFollowing 逻辑（capability 未载入时）
    return Row(
      children: [
        Expanded(
          child: _ActionButton(
            label: isFollowing
                ? UITextConstants.following
                : UITextConstants.follow,
            icon: isFollowing ? Icons.check : Icons.add,
            onTap: onFollow,
            fg: isFollowing ? fgSecondary : Colors.white,
            border: isFollowing ? border : AppColors.primaryColor,
            filled: !isFollowing,
          ),
        ),
        SizedBox(width: AppSpacing.sm),
        Expanded(
          child: _ActionButton(
            label: UITextConstants.profileDirectMessage,
            icon: Icons.chat_bubble_outline,
            onTap: onMessage,
            fg: fg,
            border: border,
          ),
        ),
      ],
    );
  }
}

class _ActionButton extends StatelessWidget {
  const _ActionButton({
    required this.label,
    required this.icon,
    this.onTap,
    required this.fg,
    required this.border,
    this.filled = false,
  });

  final String label;
  final IconData icon;
  final VoidCallback? onTap;
  final Color fg;
  final Color border;
  final bool filled;

  @override
  Widget build(BuildContext context) {
    final btn = SizedBox(
      height: AppSpacing.minInteractiveSize,
      child: CupertinoButton(
        padding: EdgeInsets.zero,
        borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
        color: filled ? AppColors.primaryColor : null,
        onPressed: onTap,
        child: DecoratedBox(
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
            border: filled
                ? null
                : Border.all(color: border.withValues(alpha: 0.5)),
          ),
          child: Center(
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(icon, size: AppSpacing.iconSmall, color: fg),
                SizedBox(width: AppSpacing.xs),
                Text(
                  label,
                  style: TextStyle(
                    fontSize: AppTypography.md,
                    fontWeight: AppTypography.semiBold,
                    color: fg,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
    return btn;
  }
}
