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
    final fgSecondary = AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary);
    final border = AppColorsFunctional.getColor(isDark, ColorType.borderPrimary);

    if (role == CircleRole.owner || role == CircleRole.admin) {
      return Row(
        children: [
          Expanded(
            child: _ActionButton(
              label: UITextConstants.editCircle,
              icon: Icons.edit_outlined,
              onTap: onEditCircle,
              fg: fg,
              border: border,
            ),
          ),
          SizedBox(width: AppSpacing.sm),
          Expanded(
            child: _ActionButton(
              label: UITextConstants.manageCenter,
              icon: Icons.settings_outlined,
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
            icon: isFollowed ? Icons.check : Icons.add,
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
                ? Icons.check_circle_outline
                : isPending
                    ? Icons.hourglass_top
                    : Icons.group_add_outlined,
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
      child: OutlinedButton.icon(
        onPressed: onTap,
        icon: Icon(icon, size: AppSpacing.iconSmall, color: fg),
        label: Text(
          label,
          style: TextStyle(
            fontSize: AppTypography.md,
            fontWeight: AppTypography.semiBold,
            color: fg,
          ),
        ),
        style: OutlinedButton.styleFrom(
          backgroundColor: filled ? AppColors.primaryColor : null,
          side: BorderSide(color: border.withValues(alpha: 0.5)),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
          ),
        ),
      ),
    );
  }
}
