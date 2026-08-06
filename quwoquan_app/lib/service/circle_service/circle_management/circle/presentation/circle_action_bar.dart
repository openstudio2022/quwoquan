import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/object_page/object_action_bar.dart';
import 'package:quwoquan_app/design_system/object_page/profile_ios_components.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle/application/circle_state_provider.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show CircleJoinPolicy;

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
    this.joinPolicy = CircleJoinPolicy.open,
    this.onJoinCircle,
    this.onEnterDiscussion,
  });

  final bool isDark;
  final CircleRole role;
  final String joinStatus;
  final CircleJoinPolicy joinPolicy;
  final VoidCallback? onJoinCircle;
  final VoidCallback? onEnterDiscussion;

  @override
  Widget build(BuildContext context) {
    final separator = AppColors.iosSeparator(
      context,
    ).withValues(alpha: isDark ? 0.22 : 0.14);
    final neutralFill = AppColors.iosProfileSurface(context);
    final neutralForeground = AppColors.iosLabel(context);
    final joinLabel = switch (joinPolicy) {
      CircleJoinPolicy.open => CommunityText.joinCircle,
      CircleJoinPolicy.approval => CommunityText.circleJoinApproval,
      CircleJoinPolicy.inviteOnly => CommunityText.circleJoinInviteOnly,
    };
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
        label: CommunityText.joinPending,
        icon: CupertinoIcons.time,
        onPressed: null,
      );
    } else if (isMemberLike) {
      primary = neutralAction(
        label: CommunityText.joinedCircle,
        icon: CupertinoIcons.check_mark_circled,
        onPressed: null,
      );
    } else {
      primary = ObjectAction(
        label: joinLabel,
        icon: CupertinoIcons.person_add,
        onPressed: joinPolicy == CircleJoinPolicy.inviteOnly
            ? null
            : onJoinCircle,
        style: ProfileIosActionStyle.filled,
      );
    }

    return ObjectActionBar(
      actions: <ObjectAction>[
        primary,
        neutralAction(
          label: ObjectHomepageText.circleActionEnterDiscussion,
          icon: CupertinoIcons.chat_bubble_2,
          onPressed: onEnterDiscussion,
        ),
      ],
    );
  }
}
