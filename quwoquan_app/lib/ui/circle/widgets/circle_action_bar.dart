import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/components/object_page/profile_ios_components.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/circle/providers/circle_state_provider.dart';

class CircleActionBar extends StatelessWidget {
  const CircleActionBar({
    super.key,
    required this.isDark,
    required this.role,
    required this.joinStatus,
    this.joinPolicy = 'open',
    this.hasConversation = false,
    this.onJoinCircle,
    this.onOpenChat,
  });

  final bool isDark;
  final CircleRole role;
  final String joinStatus;
  final String joinPolicy;
  final bool hasConversation;
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
    final isMemberLike =
        isManager || role == CircleRole.member || joinStatus == 'joined';
    final isPending = joinStatus == 'pending';

    Widget neutralAction({
      required String label,
      required IconData icon,
      required VoidCallback? onPressed,
    }) {
      return ProfileIosActionButton(
        label: label,
        icon: icon,
        onPressed: onPressed,
        style: ProfileIosActionStyle.outlined,
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
      return ProfileIosActionButton(
        label: label,
        icon: icon,
        onPressed: onPressed,
        style: ProfileIosActionStyle.filled,
        labelFontWeight: AppTypography.medium,
      );
    }

    return Row(
      children: [
        Expanded(
          child: isMemberLike
              ? neutralAction(
                  label: UITextConstants.joinedCircle,
                  icon: CupertinoIcons.check_mark_circled,
                  onPressed: null,
                )
              : isPending
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
          child: neutralAction(
            label: UITextConstants.profileDirectMessage,
            icon: CupertinoIcons.chat_bubble,
            onPressed: hasConversation ? onOpenChat : null,
          ),
        ),
      ],
    );
  }
}
