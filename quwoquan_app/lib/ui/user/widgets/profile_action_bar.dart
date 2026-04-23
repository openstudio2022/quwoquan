import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/cloud/services/user/relationship_capability_repository.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/user/models/profile_mode.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_ios_components.dart';

/// 用户主页五态按钮矩阵
///
/// | 状态           | 按钮布局                                         |
/// |---------------|------------------------------------------------|
/// | self          | 编辑资料 / 管理分身                               |
/// | not_following | 关注 / 私信                                      |
/// | following     | 已关注 / 私信                                    |
/// | followed_by   | 回关 / 私信                                      |
/// | mutual        | 消息 / 视频通话 / 语音通话 三等分                  |
class ProfileActionBar extends StatelessWidget {
  const ProfileActionBar({
    super.key,
    required this.mode,
    required this.isDark,
    this.capability,
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

  /// 关系能力位（他人主页须由外层在就绪后再构建本组件）
  final RelationshipCapabilityDto? capability;

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
    if (mode == ProfileMode.other && capability == null) {
      return const SizedBox.shrink();
    }
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
      final children = <Widget>[
        Expanded(
          child: neutralAction(
            label: UITextConstants.profileEditLabel,
            icon: CupertinoIcons.pencil,
            onPressed: onEditProfile,
          ),
        ),
      ];
      if (onManagePersonas != null) {
        children.add(
          Expanded(
            child: neutralAction(
              label: UITextConstants.profilePersonasLabel,
              icon: CupertinoIcons.person_2,
              onPressed: onManagePersonas,
            ),
          ),
        );
      }
      return _buildButtonRow(children);
    }

    final cap = capability;

    if (cap != null && cap.isMutual) {
      return _buildButtonRow(<Widget>[
        Expanded(
          child: neutralAction(
            label: UITextConstants.profileDirectMessage,
            icon: CupertinoIcons.chat_bubble,
            onPressed: cap.canMessage ? onMessage : null,
          ),
        ),
        Expanded(
          child: neutralAction(
            label: UITextConstants.callVideo,
            icon: CupertinoIcons.video_camera,
            onPressed: cap.canStartVideoCall ? onVideoCall : null,
          ),
        ),
        Expanded(
          child: neutralAction(
            label: UITextConstants.callVoice,
            icon: CupertinoIcons.phone,
            onPressed: cap.canStartVoiceCall ? onVoiceCall : null,
          ),
        ),
      ]);
    }

    if (cap != null && cap.isFollowedBy) {
      return _buildButtonRow(<Widget>[
        Expanded(
          child: primaryFollowAction(
            label: UITextConstants.followBack,
            icon: CupertinoIcons.add,
            onPressed: onFollow,
          ),
        ),
        Expanded(
          child: neutralAction(
            label: UITextConstants.profileDirectMessage,
            icon: CupertinoIcons.chat_bubble,
            onPressed: cap.canMessage ? onMessage : null,
          ),
        ),
      ]);
    }

    if (cap != null && (cap.isFollowing || cap.isNotFollowing)) {
      final alreadyFollowing = cap.viewerFollowsTarget;
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
            onPressed: cap.canMessage ? onMessage : null,
          ),
        ),
      ]);
    }

    return const SizedBox.shrink();
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
