import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/components/object_page/object_action_bar.dart';
import 'package:quwoquan_app/components/object_page/profile_ios_components.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/circle/providers/circle_state_provider.dart';

/// 圈子首屏 CTA：主=加入圈子/已加入/审批中，次=进入讨论（高保口径 #4 圈子主动作是加入）。
///
/// 真相源下沉到共享 [ObjectActionBar]；主/次按钮 token 与用户主页 `ProfileActionBar`、
/// 实体主页同源（中性按钮用 `iosProfileSurface` + `regular` 字重）。此处只负责把圈子
/// 角色/加入状态映射为主/次 [ObjectAction]。
class CircleActionBar extends StatelessWidget {
  const CircleActionBar({
    super.key,
    required this.isDark,
    required this.role,
    required this.joinStatus,
    this.joinPolicy = 'open',
    this.onJoinCircle,
    this.onEnterDiscussion,
  });

  final bool isDark;
  final CircleRole role;
  final String joinStatus;
  final String joinPolicy;
  final VoidCallback? onJoinCircle;
  final VoidCallback? onEnterDiscussion;

  @override
  Widget build(BuildContext context) {
    final separator = AppColors.iosSeparator(
      context,
    ).withValues(alpha: isDark ? 0.22 : 0.14);
    final neutralFill = AppColors.iosProfileSurface(context);
    final neutralForeground = AppColors.iosLabel(context);
    final joinLabel = joinPolicy == 'approval'
        ? UITextConstants.circleJoinApproval
        : UITextConstants.joinCircle;
    final isManager = role == CircleRole.owner || role == CircleRole.admin;
    final isMemberLike =
        joinStatus == 'joined' && (isManager || role == CircleRole.member);
    final isPending = joinStatus == 'pending';

    ObjectAction neutralAction({
      required String label,
      required IconData icon,
      required VoidCallback? onPressed,
    }) {
      return ObjectAction(
        label: label,
        icon: icon,
        onPressed: onPressed,
        style: ProfileIosActionStyle.outlined,
        backgroundColor: neutralFill,
        foregroundColor: neutralForeground,
        borderColor: separator,
      );
    }

    final ObjectAction primary;
    if (isPending) {
      primary = neutralAction(
        label: UITextConstants.joinPending,
        icon: CupertinoIcons.time,
        onPressed: null,
      );
    } else if (isMemberLike) {
      primary = neutralAction(
        label: UITextConstants.joinedCircle,
        icon: CupertinoIcons.check_mark_circled,
        onPressed: null,
      );
    } else {
      primary = ObjectAction(
        label: joinLabel,
        icon: CupertinoIcons.person_add,
        onPressed: onJoinCircle,
        style: ProfileIosActionStyle.filled,
      );
    }

    return ObjectActionBar(
      actions: <ObjectAction>[
        primary,
        neutralAction(
          label: UITextConstants.circleActionEnterDiscussion,
          icon: CupertinoIcons.chat_bubble_2,
          onPressed: onEnterDiscussion,
        ),
      ],
    );
  }
}
