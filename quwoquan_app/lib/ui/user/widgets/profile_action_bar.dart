import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/application/rtc/call_session/rtc_call_entry_coordinator.dart';
import 'package:quwoquan_app/cloud/services/user/relationship_capability_repository.dart';
import 'package:quwoquan_app/components/object_page/object_action_bar.dart';
import 'package:quwoquan_app/components/object_page/profile_ios_components.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/user/models/profile_mode.dart';

/// 用户主页首屏 CTA：mine = 管理分身 / 编辑资料；other = 关注 / 私信。
///
/// 真相源下沉到共享 [ObjectActionBar]；此处只负责把用户态映射为主/次 [ObjectAction]。
class ProfileActionBar extends StatelessWidget {
  const ProfileActionBar({
    super.key,
    required this.mode,
    required this.isDark,
    required this.isFollowing,
    this.profileComplete = true,
    this.capability,
    this.onEditProfile,
    this.onManagePersonas,
    this.onShareProfile,
    this.onFollow,
    this.onMessage,
    this.onVoiceCall,
    this.onVideoCall,
  });

  final ProfileMode mode;
  final bool isDark;
  final bool isFollowing;
  final bool profileComplete;

  /// 关系能力位（他人主页须由外层在就绪后再构建本组件）
  final RelationshipCapabilityDto? capability;

  final VoidCallback? onEditProfile;
  final VoidCallback? onManagePersonas;
  final VoidCallback? onShareProfile;
  final VoidCallback? onFollow;
  final VoidCallback? onMessage;
  final VoidCallback? onVoiceCall;
  final VoidCallback? onVideoCall;

  @override
  Widget build(BuildContext context) {
    final separator = AppColors.iosSeparator(
      context,
    ).withValues(alpha: isDark ? 0.22 : 0.14);
    final neutralFill = AppColors.iosProfileSurface(context);
    final neutralForeground = AppColors.iosLabel(context);

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
        labelFontWeight: AppTypography.regular,
      );
    }

    ObjectAction primaryFollowAction({
      required String label,
      required IconData icon,
      required VoidCallback? onPressed,
    }) {
      return ObjectAction(
        label: label,
        icon: icon,
        onPressed: onPressed,
        style: ProfileIosActionStyle.filled,
        labelFontWeight: AppTypography.regular,
      );
    }

    if (mode == ProfileMode.mine) {
      final editAction = profileComplete
          ? neutralAction(
              label: ProfileText.profileEditLabel,
              icon: CupertinoIcons.pencil,
              onPressed: onEditProfile,
            )
          : primaryFollowAction(
              label: ProfileText.profileEditLabel,
              icon: CupertinoIcons.pencil,
              onPressed: onEditProfile,
            );
      return ObjectActionBar(
        actions: <ObjectAction>[
          if (onManagePersonas != null)
            profileComplete
                ? primaryFollowAction(
                    label: ProfileText.personaSwitchProfile,
                    icon: CupertinoIcons.person_2,
                    onPressed: onManagePersonas,
                  )
                : neutralAction(
                    label: ProfileText.personaSwitchProfile,
                    icon: CupertinoIcons.person_2,
                    onPressed: onManagePersonas,
                  ),
          editAction,
        ],
      );
    }

    final alreadyFollowing = capability?.viewerFollowsTarget ?? isFollowing;
    final primaryActions = <ObjectAction>[
      alreadyFollowing
          ? neutralAction(
              label: FoundationText.following,
              icon: CupertinoIcons.check_mark,
              onPressed: onFollow,
            )
          : primaryFollowAction(
              label: FoundationText.follow,
              icon: CupertinoIcons.add,
              onPressed: onFollow,
            ),
      neutralAction(
        label: ProfileText.profileDirectMessage,
        icon: CupertinoIcons.chat_bubble,
        onPressed: onMessage,
      ),
    ];
    final targetUserId = capability?.targetPersonaId ?? '';
    final voiceAvailable = RtcCallEntryIntent.direct(
      mediaType: RtcCallEntryMediaType.audio,
      targetUserId: targetUserId,
      capability: capability,
    ).availability.isAvailable;
    final videoAvailable = RtcCallEntryIntent.direct(
      mediaType: RtcCallEntryMediaType.video,
      targetUserId: targetUserId,
      capability: capability,
    ).availability.isAvailable;
    final callActions = <ObjectAction>[
      if (voiceAvailable)
        neutralAction(
          label: CallText.callVoice,
          icon: CupertinoIcons.phone,
          onPressed: onVoiceCall,
        ),
      if (videoAvailable)
        neutralAction(
          label: CallText.callVideo,
          icon: CupertinoIcons.video_camera,
          onPressed: onVideoCall,
        ),
    ];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        ObjectActionBar(actions: primaryActions),
        if (callActions.isNotEmpty) ...<Widget>[
          SizedBox(height: AppSpacing.sm),
          ObjectActionBar(actions: callActions),
        ],
      ],
    );
  }
}
