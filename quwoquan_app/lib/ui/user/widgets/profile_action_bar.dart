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
/// | none（陌生人）  | 关注（全宽主按钮）                                |
/// | following_only | 打招呼（主）/ 已关注（次）                         |
/// | same_interest  | 消息 / 视频通话 / 语音通话 三等分                  |
/// | close_friend   | 消息 / 视频通话 / 语音通话 三等分 + 密友标记         |
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
    final fg =
        AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary);
    final fgSecondary =
        AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary);
    final border =
        AppColorsFunctional.getColor(isDark, ColorType.borderPrimary);

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

    // 同好/密友：三等分按钮（消息 / 视频 / 语音）
    if (cap != null &&
        (cap.isSameInterest || cap.isCloseFriend)) {
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

    // 关注用户（following_only）：打招呼（主）/ 已关注（次）
    if (cap != null && cap.isFollowingOnly) {
      return Row(
        children: [
          Expanded(
            child: _ActionButton(
              label: UITextConstants.profileGreet,
              icon: Icons.waving_hand_outlined,
              onTap: cap.canGreet ? onGreet : null,
              fg: Colors.white,
              border: AppColors.primaryColor,
              filled: true,
            ),
          ),
          SizedBox(width: AppSpacing.sm),
          Expanded(
            child: _ActionButton(
              label: UITextConstants.following,
              icon: Icons.check,
              onTap: onFollow,
              fg: fgSecondary,
              border: border,
            ),
          ),
        ],
      );
    }

    // 陌生人（none）：仅关注按钮
    if (cap != null && cap.isStranger) {
      return _ActionButton(
        label: UITextConstants.follow,
        icon: Icons.add,
        onTap: onFollow,
        fg: Colors.white,
        border: AppColors.primaryColor,
        filled: true,
        fullWidth: true,
      );
    }

    // fallback：旧版 isFollowing 逻辑（capability 未载入时）
    return Row(
      children: [
        Expanded(
          child: _ActionButton(
            label: isFollowing ? UITextConstants.following : UITextConstants.follow,
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
    this.fullWidth = false,
  });

  final String label;
  final IconData icon;
  final VoidCallback? onTap;
  final Color fg;
  final Color border;
  final bool filled;
  final bool fullWidth;

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
    return fullWidth ? SizedBox(width: double.infinity, child: btn) : btn;
  }
}
