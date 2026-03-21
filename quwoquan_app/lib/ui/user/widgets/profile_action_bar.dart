import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
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
/// | mutual        | 私信 / 视频通话 / 语音通话 三等分                  |
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
    final secondaryStyle = isDark
        ? ProfileIosActionStyle.outlined
        : ProfileIosActionStyle.tinted;

    if (mode == ProfileMode.mine) {
      return _buildButtonRow(<Widget>[
        Expanded(
          flex: 6,
          child: ProfileIosActionButton(
            label: UITextConstants.profileEditLabel,
            icon: CupertinoIcons.pencil,
            onPressed: onEditProfile,
            style: ProfileIosActionStyle.filled,
          ),
        ),
        Expanded(
          flex: 5,
          child: ProfileIosActionButton(
            label: UITextConstants.profilePersonasLabel,
            icon: CupertinoIcons.person_2,
            onPressed: onManagePersonas,
            style: secondaryStyle,
          ),
        ),
      ]);
    }

    final cap = capability;

    if (cap != null && cap.isMutual) {
      return _buildButtonRow(<Widget>[
        Expanded(
          flex: 6,
          child: ProfileIosActionButton(
            label: UITextConstants.profileDirectMessage,
            icon: CupertinoIcons.chat_bubble,
            onPressed: onMessage,
            style: ProfileIosActionStyle.filled,
          ),
        ),
        Expanded(
          child: ProfileIosActionButton(
            label: UITextConstants.callVideo,
            icon: CupertinoIcons.video_camera,
            onPressed: cap.canStartVideoCall ? onVideoCall : null,
            style: secondaryStyle,
          ),
        ),
        Expanded(
          child: ProfileIosActionButton(
            label: UITextConstants.callVoice,
            icon: CupertinoIcons.phone,
            onPressed: cap.canStartVoiceCall ? onVoiceCall : null,
            style: secondaryStyle,
          ),
        ),
      ]);
    }

    if (cap != null && cap.isFollowedBy) {
      return _buildButtonRow(<Widget>[
        Expanded(
          child: ProfileIosActionButton(
            label: UITextConstants.followBack,
            icon: CupertinoIcons.add,
            onPressed: onFollow,
            style: ProfileIosActionStyle.filled,
          ),
        ),
        Expanded(
          child: ProfileIosActionButton(
            label: UITextConstants.profileDirectMessage,
            icon: CupertinoIcons.chat_bubble,
            onPressed: onMessage,
            style: secondaryStyle,
          ),
        ),
      ]);
    }

    if (cap != null && (cap.isFollowing || cap.isNotFollowing)) {
      final alreadyFollowing = cap.isFollowing;
      return _buildButtonRow(<Widget>[
        Expanded(
          child: ProfileIosActionButton(
            label: alreadyFollowing
                ? UITextConstants.following
                : UITextConstants.follow,
            icon: alreadyFollowing
                ? CupertinoIcons.check_mark
                : CupertinoIcons.add,
            onPressed: onFollow,
            style: alreadyFollowing
                ? secondaryStyle
                : ProfileIosActionStyle.filled,
          ),
        ),
        Expanded(
          child: ProfileIosActionButton(
            label: UITextConstants.profileDirectMessage,
            icon: CupertinoIcons.chat_bubble,
            onPressed: onMessage,
            style: secondaryStyle,
          ),
        ),
      ]);
    }

    // fallback：旧版 isFollowing 逻辑（capability 未载入时）
    return _buildButtonRow(<Widget>[
      Expanded(
        child: ProfileIosActionButton(
          label: isFollowing
              ? UITextConstants.following
              : UITextConstants.follow,
          icon: isFollowing ? CupertinoIcons.check_mark : CupertinoIcons.add,
          onPressed: onFollow,
          style: isFollowing ? secondaryStyle : ProfileIosActionStyle.filled,
        ),
      ),
      Expanded(
        child: ProfileIosActionButton(
          label: UITextConstants.profileDirectMessage,
          icon: CupertinoIcons.chat_bubble,
          onPressed: onMessage,
          style: secondaryStyle,
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
