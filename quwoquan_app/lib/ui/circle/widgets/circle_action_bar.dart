import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/circle/providers/circle_state_provider.dart';

class CircleActionBar extends StatelessWidget {
  const CircleActionBar({
    super.key,
    required this.isDark,
    required this.role,
    required this.joinStatus,
    this.isFollowed = false,
    this.onEditCircle,
    this.onManageCenter,
    this.onFollow,
    this.onJoinCircle,
  });

  final bool isDark;
  final CircleRole role;
  final String joinStatus;
  final bool isFollowed;
  final VoidCallback? onEditCircle;
  final VoidCallback? onManageCenter;
  final VoidCallback? onFollow;
  final VoidCallback? onJoinCircle;

  @override
  Widget build(BuildContext context) {
    final fg = AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary);
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final border = AppColorsFunctional.getColor(isDark, ColorType.borderPrimary);

    if (role == CircleRole.owner || role == CircleRole.admin) {
      return Row(
        children: [
          Expanded(
            child: _ActionButton(
              label: UITextConstants.editCircle,
              icon: CupertinoIcons.pencil,
              onTap: onEditCircle,
              fg: fg,
              border: border,
            ),
          ),
          SizedBox(width: AppSpacing.sm),
          Expanded(
            child: _ActionButton(
              label: UITextConstants.manageCenter,
              icon: CupertinoIcons.slider_horizontal_3,
              onTap: onManageCenter,
              fg: fg,
              border: border,
            ),
          ),
        ],
      );
    }

    final isJoined = joinStatus == 'joined';
    final isPending = joinStatus == 'pending';

    return Row(
      children: [
        Expanded(
          child: _ActionButton(
            label: isFollowed ? UITextConstants.following : UITextConstants.follow,
            icon: isFollowed ? CupertinoIcons.check_mark : CupertinoIcons.add,
            onTap: onFollow,
            fg: isFollowed ? fgSecondary : Colors.white,
            border: isFollowed ? border : AppColors.primaryColor,
            filled: !isFollowed,
          ),
        ),
        SizedBox(width: AppSpacing.sm),
        Expanded(
          child: _ActionButton(
            label: isJoined
                ? UITextConstants.joinedCircle
                : isPending
                    ? UITextConstants.joinPending
                    : UITextConstants.joinCircle,
            icon: isJoined
                ? CupertinoIcons.check_mark_circled
                : isPending
                    ? CupertinoIcons.time
                    : CupertinoIcons.person_add,
            onTap: onJoinCircle,
            fg: isJoined ? fgSecondary : (isPending ? fgSecondary : Colors.white),
            border: isJoined ? border : (isPending ? border : AppColors.primaryColor),
            filled: !isJoined && !isPending,
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
    return SizedBox(
      height: AppSpacing.minInteractiveSize,
      child: CupertinoButton(
        padding: EdgeInsets.zero,
        borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
        color: filled ? AppColors.primaryColor : null,
        onPressed: onTap,
        child: Container(
          decoration: BoxDecoration(
            color: filled ? AppColors.primaryColor : Colors.transparent,
            borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
            border: filled
                ? null
                : Border.all(color: border.withValues(alpha: 0.45)),
            boxShadow: filled
                ? [
                    BoxShadow(
                      color: AppColors.primaryColor.withValues(alpha: 0.2),
                      blurRadius: AppSpacing.md,
                      offset: const Offset(0, 6),
                    ),
                  ]
                : null,
          ),
          padding: EdgeInsets.symmetric(horizontal: AppSpacing.sm),
          child: Center(
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(icon, size: AppSpacing.iconSmall, color: fg),
                SizedBox(width: AppSpacing.xs),
                Flexible(
                  child: Text(
                    label,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: AppTypography.md,
                      fontWeight: AppTypography.semiBold,
                      color: fg,
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
