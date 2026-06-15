import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/cloud/services/user/relationship_capability_repository.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/user/models/profile_mode.dart';
import 'package:quwoquan_app/components/object_page/profile_ios_components.dart';

/// 用户主页首屏 CTA：mine = 编辑资料 / 分享主页；other = 关注 / 私信。
class ProfileActionBar extends StatelessWidget {
  const ProfileActionBar({
    super.key,
    required this.mode,
    required this.isDark,
    required this.isFollowing,
    this.capability,
    this.onEditProfile,
    this.onShareProfile,
    this.onFollow,
    this.onMessage,
  });

  final ProfileMode mode;
  final bool isDark;
  final bool isFollowing;

  /// 关系能力位（他人主页须由外层在就绪后再构建本组件）
  final RelationshipCapabilityDto? capability;

  final VoidCallback? onEditProfile;
  final VoidCallback? onShareProfile;
  final VoidCallback? onFollow;
  final VoidCallback? onMessage;

  @override
  Widget build(BuildContext context) {
    final separator = AppColors.iosSeparator(
      context,
    ).withValues(alpha: isDark ? 0.22 : 0.14);
    final neutralFill = AppColors.iosSecondaryFill(context);
    final neutralForeground = AppColors.iosLabel(context);

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

    Widget primaryFollowAction({
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

    if (mode == ProfileMode.mine) {
      return _buildButtonRow(<Widget>[
        Expanded(
          child: neutralAction(
            label: UITextConstants.profileEditLabel,
            icon: CupertinoIcons.pencil,
            onPressed: onEditProfile,
          ),
        ),
        Expanded(
          child: neutralAction(
            label: UITextConstants.profileShareHomepage,
            icon: CupertinoIcons.share,
            onPressed: onShareProfile,
          ),
        ),
      ]);
    }

    final alreadyFollowing = capability?.viewerFollowsTarget ?? isFollowing;
    return _buildButtonRow(<Widget>[
      Expanded(
        child: alreadyFollowing
            ? neutralAction(
                label: UITextConstants.following,
                icon: CupertinoIcons.check_mark,
                onPressed: onFollow,
              )
            : primaryFollowAction(
                label: UITextConstants.follow,
                icon: CupertinoIcons.add,
                onPressed: onFollow,
              ),
      ),
      Expanded(
        child: neutralAction(
          label: UITextConstants.profileDirectMessage,
          icon: CupertinoIcons.chat_bubble,
          onPressed: onMessage,
        ),
      ),
    ]);
  }

  Widget _buildButtonRow(List<Widget> buttons) {
    return Row(
      children: <Widget>[
        for (var i = 0; i < buttons.length; i += 1) ...<Widget>[
          buttons[i],
          if (i != buttons.length - 1) SizedBox(width: AppSpacing.sm),
        ],
      ],
    );
  }
}
