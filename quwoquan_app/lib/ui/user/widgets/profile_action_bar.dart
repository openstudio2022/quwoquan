import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/user/models/profile_mode.dart';

class ProfileActionBar extends StatelessWidget {
  const ProfileActionBar({
    super.key,
    required this.mode,
    required this.isDark,
    this.isFollowing = false,
    this.onEditProfile,
    this.onManagePersonas,
    this.onFollow,
    this.onMessage,
  });

  final ProfileMode mode;
  final bool isDark;
  final bool isFollowing;
  final VoidCallback? onEditProfile;
  final VoidCallback? onManagePersonas;
  final VoidCallback? onFollow;
  final VoidCallback? onMessage;

  @override
  Widget build(BuildContext context) {
    final fg = AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary);
    final fgSecondary = AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary);
    final border = AppColorsFunctional.getColor(isDark, ColorType.borderPrimary);

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
