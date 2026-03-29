import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/circle/providers/circle_state_provider.dart';

class CircleActionBar extends StatelessWidget {
  const CircleActionBar({
    super.key,
    required this.isDark,
    required this.role,
    required this.joinStatus,
    this.isFollowed = false,
    this.joinPolicy = 'open',
    this.hasConversation = false,
    this.onEditCircle,
    this.onManageCenter,
    this.onFollow,
    this.onJoinCircle,
    this.onOpenChat,
  });

  final bool isDark;
  final CircleRole role;
  final String joinStatus;
  final bool isFollowed;
  final String joinPolicy;
  final bool hasConversation;
  final VoidCallback? onEditCircle;
  final VoidCallback? onManageCenter;
  final VoidCallback? onFollow;
  final VoidCallback? onJoinCircle;
  final VoidCallback? onOpenChat;

  @override
  Widget build(BuildContext context) {
    final separator = AppColors.iosSeparator(
      context,
    ).withValues(alpha: isDark ? 0.22 : 0.14);
    final neutralFill = AppColors.iosSecondaryFill(context);
    final neutralForeground = AppColors.iosLabel(context);
    final joinLabel = joinPolicy == 'approval'
        ? UITextConstants.circleJoinApproval
        : UITextConstants.joinCircle;
    final isManager = role == CircleRole.owner || role == CircleRole.admin;
    final isMemberLike = isManager || role == CircleRole.member || joinStatus == 'joined';
    final isPending = joinStatus == 'pending';

    Widget neutralAction({
      required String label,
      required IconData icon,
      required VoidCallback? onPressed,
    }) {
      return _CircleIosActionButton(
        label: label,
        icon: icon,
        onPressed: onPressed,
        style: _CircleIosActionStyle.outlined,
        backgroundColor: neutralFill,
        foregroundColor: neutralForeground,
        borderColor: separator,
        labelFontWeight: AppTypography.medium,
      );
    }

    Widget primaryAction({
      required String label,
      required IconData icon,
      required VoidCallback? onPressed,
    }) {
      return _CircleIosActionButton(
        label: label,
        icon: icon,
        onPressed: onPressed,
        style: _CircleIosActionStyle.filled,
        labelFontWeight: AppTypography.medium,
      );
    }

    Widget secondaryAccentAction({
      required String label,
      required IconData icon,
      required VoidCallback? onPressed,
    }) {
      return _CircleIosActionButton(
        label: label,
        icon: icon,
        onPressed: onPressed,
        style: _CircleIosActionStyle.tinted,
        labelFontWeight: AppTypography.medium,
      );
    }

    if (isManager) {
      return Row(
        children: [
          Expanded(
            child: neutralAction(
              label: UITextConstants.editCircle,
              icon: CupertinoIcons.pencil,
              onPressed: onEditCircle,
            ),
          ),
          SizedBox(width: AppSpacing.sm),
          Expanded(
            child: neutralAction(
              label: UITextConstants.manageCenter,
              icon: CupertinoIcons.slider_horizontal_3,
              onPressed: onManageCenter,
            ),
          ),
        ],
      );
    }

    if (isMemberLike) {
      return Row(
        children: [
          Expanded(
            child: neutralAction(
              label: UITextConstants.circleGroups,
              icon: CupertinoIcons.chat_bubble_2,
              onPressed: hasConversation ? onOpenChat : null,
            ),
          ),
          SizedBox(width: AppSpacing.sm),
          Expanded(
            child: neutralAction(
              label: UITextConstants.joinedCircle,
              icon: CupertinoIcons.check_mark_circled,
              onPressed: null,
            ),
          ),
        ],
      );
    }

    return Row(
      children: [
        Expanded(
          child: isPending
              ? neutralAction(
                  label: UITextConstants.joinPending,
                  icon: CupertinoIcons.time,
                  onPressed: null,
                )
              : primaryAction(
                  label: joinLabel,
                  icon: CupertinoIcons.person_add,
                  onPressed: onJoinCircle,
                ),
        ),
        SizedBox(width: AppSpacing.sm),
        Expanded(
          child: isFollowed
              ? neutralAction(
                  label: UITextConstants.followedCircle,
                  icon: CupertinoIcons.check_mark,
                  onPressed: onFollow,
                )
              : secondaryAccentAction(
                  label: UITextConstants.followCircle,
                  icon: CupertinoIcons.add,
                  onPressed: onFollow,
                ),
        ),
      ],
    );
  }
}

enum _CircleIosActionStyle { filled, tinted, outlined }

class _CircleIosActionButton extends StatelessWidget {
  const _CircleIosActionButton({
    required this.label,
    this.icon,
    this.onPressed,
    this.style = _CircleIosActionStyle.tinted,
    this.backgroundColor,
    this.foregroundColor,
    this.borderColor,
    this.labelFontWeight,
  });

  final String label;
  final IconData? icon;
  final VoidCallback? onPressed;
  final _CircleIosActionStyle style;
  final Color? backgroundColor;
  final Color? foregroundColor;
  final Color? borderColor;
  final FontWeight? labelFontWeight;

  @override
  Widget build(BuildContext context) {
    final accent = AppColors.iosAccent(context);
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final foreground =
        foregroundColor ??
        switch (style) {
          _CircleIosActionStyle.filled => CupertinoColors.white,
          _CircleIosActionStyle.tinted => accent,
          _CircleIosActionStyle.outlined => AppColors.iosLabel(context),
        };
    final background =
        backgroundColor ??
        switch (style) {
          _CircleIosActionStyle.filled => accent,
          _CircleIosActionStyle.tinted => accent.withValues(
            alpha: isDark ? 0.24 : 0.12,
          ),
          _CircleIosActionStyle.outlined => AppColors.iosSystemBackground(context),
        };
    final resolvedBorderColor =
        borderColor ??
        switch (style) {
          _CircleIosActionStyle.outlined => AppColors.iosSeparator(
            context,
          ).withValues(alpha: 0.24),
          _ => AppColors.transparent,
        };

    return CupertinoButton(
      padding: EdgeInsets.zero,
      minimumSize: const Size(
        AppSpacing.minInteractiveSize,
        AppSpacing.minInteractiveSize,
      ),
      onPressed: onPressed,
      child: Container(
        height: AppSpacing.minInteractiveSize,
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.containerSm,
          vertical: AppSpacing.intraGroupXs,
        ),
        decoration: BoxDecoration(
          color: background,
          borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
          border: Border.all(
            color: resolvedBorderColor,
            width: AppSpacing.hairline,
          ),
        ),
        child: Center(
          child: FittedBox(
            fit: BoxFit.scaleDown,
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                if (icon != null) ...<Widget>[
                  Icon(icon, size: AppSpacing.iconSmall, color: foreground),
                  SizedBox(width: AppSpacing.intraGroupXs),
                ],
                Text(
                  label,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    fontSize: AppTypography.iosButton,
                    fontWeight: labelFontWeight ?? AppTypography.semiBold,
                    color: foreground,
                    letterSpacing: -0.18,
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
