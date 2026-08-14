part of 'chat_settings_page.dart';

class _GroupCapabilityGrid extends StatelessWidget {
  const _GroupCapabilityGrid({
    required this.isDark,
    required this.enabledCapabilities,
    required this.onVoiceCall,
    required this.onVideoCall,
    this.onOpenBoard,
    this.onOpenAlbum,
    this.onOpenFiles,
  });

  final bool isDark;
  final List<String> enabledCapabilities;
  final VoidCallback onVoiceCall;
  final VoidCallback onVideoCall;

  /// 活动群（gatheringId 绑定）直达 Board；普通群不展示活动格。
  final VoidCallback? onOpenBoard;

  /// 群空间相册/文件宫格的真实承接（ListConversationAssets 读面）。
  final VoidCallback? onOpenAlbum;
  final VoidCallback? onOpenFiles;

  bool _enabled(String capability) {
    return enabledCapabilities.isEmpty ||
        enabledCapabilities.contains(capability);
  }

  @override
  Widget build(BuildContext context) {
    final items = <_GroupCapabilityItem>[
      _GroupCapabilityItem(
        key: const ValueKey<String>('chat_settings_album_entry'),
        label: ChatText.groupCapabilityAlbum,
        icon: CupertinoIcons.photo,
        enabled: _enabled('album') && onOpenAlbum != null,
        onPressed: _enabled('album') ? onOpenAlbum : null,
      ),
      _GroupCapabilityItem(
        key: const ValueKey<String>('chat_settings_files_entry'),
        label: ChatText.groupCapabilityFile,
        icon: CupertinoIcons.folder,
        enabled: _enabled('file') && onOpenFiles != null,
        onPressed: _enabled('file') ? onOpenFiles : null,
      ),
      if (onOpenBoard != null)
        _GroupCapabilityItem(
          key: const ValueKey<String>('chat_settings_board_entry'),
          label: ChatText.groupCapabilityActivity,
          icon: CupertinoIcons.calendar,
          enabled: true,
          onPressed: onOpenBoard,
        ),
      _GroupCapabilityItem(
        label: CallText.callGroupVoice,
        icon: CupertinoIcons.phone,
        enabled: true,
        onPressed: onVoiceCall,
      ),
      _GroupCapabilityItem(
        label: CallText.callGroupVideo,
        icon: CupertinoIcons.video_camera,
        enabled: true,
        onPressed: onVideoCall,
      ),
    ];
    final fgPrimary = SettingsSemanticConstants.labelColor(isDark);
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    return Row(
      children: items
          .map(
            (item) => Expanded(
              child: CupertinoButton(
                key: item.key,
                padding: EdgeInsets.symmetric(vertical: AppSpacing.sm),
                onPressed: item.enabled ? item.onPressed : null,
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(
                      item.icon,
                      size: AppSpacing.iconLarge,
                      color: item.enabled ? fgPrimary : fgSecondary,
                    ),
                    SizedBox(height: AppSpacing.xs),
                    Text(
                      item.label,
                      style: TextStyle(
                        fontSize: AppTypography.iosFootnote,
                        color: item.enabled ? fgPrimary : fgSecondary,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          )
          .toList(growable: false),
    );
  }
}

class _GroupCapabilityItem {
  const _GroupCapabilityItem({
    required this.label,
    required this.icon,
    required this.enabled,
    this.onPressed,
    this.key,
  });

  final String label;
  final IconData icon;
  final bool enabled;
  final VoidCallback? onPressed;
  final Key? key;
}

class _MemberAvatar extends StatelessWidget {
  const _MemberAvatar({
    required this.name,
    required this.avatarUrl,
    required this.textColor,
    required this.onTap,
    this.role,
  });

  final String name;
  final String avatarUrl;
  final Color textColor;
  final VoidCallback? onTap;
  final String? role;

  static final double _settingsAvatarSize = AppSpacing.avatarUserLg;

  @override
  Widget build(BuildContext context) {
    final roleLabel = role == 'owner'
        ? ChatText.owner
        : role == 'admin'
        ? ChatText.admin
        : null;
    return GestureDetector(
      onTap: onTap,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Stack(
            clipBehavior: Clip.none,
            children: [
              RoundedSquareAvatar(
                size: _settingsAvatarSize,
                imageUrl: avatarUrl,
                name: name,
              ),
              if (roleLabel != null)
                Positioned(
                  bottom: -2,
                  left: 0,
                  right: 0,
                  child: Center(
                    child: Container(
                      padding: EdgeInsets.symmetric(
                        horizontal: AppSpacing.xs,
                        vertical: AppSpacing.one,
                      ),
                      decoration: BoxDecoration(
                        color: AppColors.primaryColor,
                        borderRadius: BorderRadius.circular(
                          AppSpacing.borderRadius,
                        ),
                      ),
                      child: Text(
                        roleLabel,
                        style: TextStyle(
                          fontSize: AppTypography.xxs,
                          color: AppColors.white,
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                    ),
                  ),
                ),
            ],
          ),
          SizedBox(height: AppSpacing.xs),
          SizedBox(
            width: AppSpacing.largeButtonSize,
            child: Text(
              name,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              textAlign: TextAlign.center,
              style: TextStyle(fontSize: AppTypography.xs, color: textColor),
            ),
          ),
        ],
      ),
    );
  }
}

class _AddMemberPlaceholder extends StatelessWidget {
  const _AddMemberPlaceholder({
    super.key,
    required this.borderColor,
    required this.size,
    required this.onTap,
    this.icon = CupertinoIcons.add,
  });

  final Color borderColor;
  final double size;
  final VoidCallback onTap;
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: SizedBox(
        width: size,
        height: size,
        child: DecoratedBox(
          decoration: BoxDecoration(
            border: Border.all(color: borderColor, style: BorderStyle.solid),
            borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
          ),
          child: Icon(icon, size: AppSpacing.iconMedium, color: borderColor),
        ),
      ),
    );
  }
}
