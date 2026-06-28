part of 'start_group_chat_page.dart';

class _SelectedMemberAvatar extends StatelessWidget {
  const _SelectedMemberAvatar({
    super.key,
    required this.name,
    required this.avatarUrl,
    required this.onTap,
  });

  final String name;
  final String avatarUrl;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: AppSpacing.iconButtonMinSizeMd,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: onTap,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            RoundedSquareAvatar(
              size: AppSpacing.largeButtonSize,
              imageUrl: avatarUrl,
              name: name,
              fallbackIcon: CupertinoIcons.person_fill,
            ),
            SizedBox(height: AppSpacing.xs),
            Text(
              name,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              textAlign: TextAlign.center,
              style: TextStyle(fontSize: AppTypography.sm),
            ),
          ],
        ),
      ),
    );
  }
}

class _ContactListSectionBand extends StatelessWidget {
  const _ContactListSectionBand({
    super.key,
    required this.title,
    required this.color,
    required this.bandColor,
  });

  final String title;
  final Color color;
  final Color bandColor;

  @override
  Widget build(BuildContext context) {
    return Container(
      height: AppSpacing.twenty,
      alignment: Alignment.centerLeft,
      padding: EdgeInsets.symmetric(horizontal: AppSpacing.md),
      color: bandColor,
      child: Text(
        title,
        style: TextStyle(
          fontSize: AppTypography.xs,
          fontWeight: AppTypography.semiBold,
          color: color,
        ),
      ),
    );
  }
}

class _RelatedFriendRow extends StatelessWidget {
  const _RelatedFriendRow({
    required this.name,
    required this.username,
    required this.avatarUrl,
    required this.selected,
    required this.fgPrimary,
    required this.fgSecondary,
    required this.locked,
    required this.rowBackground,
    required this.dividerColor,
    required this.onTap,
    required this.onAvatarTap,
  });

  static const double _avatarSize = ChatConversationAvatarTokens.listSize;

  final String name;
  final String username;
  final String avatarUrl;
  final bool selected;
  final Color fgPrimary;
  final Color fgSecondary;
  final bool locked;
  final Color rowBackground;
  final Color dividerColor;
  final VoidCallback? onTap;
  final VoidCallback onAvatarTap;

  @override
  Widget build(BuildContext context) {
    return CupertinoButton(
      padding: EdgeInsets.zero,
      minimumSize: Size.zero,
      onPressed: onTap,
      child: Container(
        key: ValueKey<String>('start-group-candidate-row-$username'),
        color: rowBackground,
        padding: EdgeInsets.symmetric(horizontal: AppSpacing.md),
        child: Column(
          children: [
            Padding(
              padding: EdgeInsets.symmetric(
                vertical: AppSpacing.sm + AppSpacing.xs,
              ),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.center,
                children: [
                  _SelectionIndicator(
                    selected: selected,
                    onTap: onTap,
                    enabled: !locked && onTap != null,
                  ),
                  GestureDetector(
                    onTap: onAvatarTap,
                    child: RoundedSquareAvatar(
                      size: _avatarSize,
                      imageUrl: avatarUrl,
                      name: name,
                      fallbackIcon: CupertinoIcons.person_fill,
                    ),
                  ),
                  SizedBox(width: ChatConversationAvatarTokens.leadingGap),
                  Expanded(
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          name,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            fontSize: AppTypography.iosBody,
                            fontWeight: AppTypography.regular,
                            color: locked ? fgSecondary : fgPrimary,
                            height: AppTypography.lineHeightTight,
                          ),
                        ),
                        if (locked) ...[
                          SizedBox(height: AppSpacing.xs),
                          Text(
                            UITextConstants.startGroupChatAlreadyInGroup,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: TextStyle(
                              fontSize: AppTypography.iosFootnote,
                              color: fgSecondary.withValues(alpha: 0.9),
                              height: AppTypography.lineHeightCompact,
                            ),
                          ),
                        ],
                      ],
                    ),
                  ),
                ],
              ),
            ),
            Padding(
              padding: EdgeInsets.only(
                left: AppSpacing.minInteractiveSize +
                    ChatConversationAvatarTokens.dividerInset(_avatarSize),
              ),
              child: Divider(
                key: ValueKey<String>('start-group-candidate-divider-$username'),
                height: AppSpacing.one,
                thickness: AppSpacing.hairline,
                color: dividerColor,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _ActionEntryRow extends StatelessWidget {
  const _ActionEntryRow({
    required this.icon,
    required this.title,
    required this.rowBackground,
    required this.dividerColor,
    required this.fgPrimary,
    required this.onTap,
  });

  final IconData icon;
  final String title;
  final Color rowBackground;
  final Color dividerColor;
  final Color fgPrimary;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return CupertinoButton(
      padding: EdgeInsets.zero,
      minimumSize: Size.zero,
      onPressed: onTap,
      child: Container(
        key: ValueKey<String>('start-group-action-entry-$title'),
        color: rowBackground,
        padding: EdgeInsets.symmetric(horizontal: AppSpacing.md),
        child: Column(
          children: [
            Padding(
              padding: EdgeInsets.symmetric(
                vertical: AppSpacing.sm + AppSpacing.xs,
              ),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.center,
                children: [
                  SizedBox(
                    width: AppSpacing.minInteractiveSize,
                    height: AppSpacing.minInteractiveSize,
                    child: Align(
                      alignment: Alignment.centerLeft,
                      child: Icon(
                        icon,
                        size: AppSpacing.iconMedium,
                        color: AppColors.primaryColor,
                      ),
                    ),
                  ),
                  SizedBox(
                    width: ChatConversationAvatarTokens.listSize -
                        AppSpacing.minInteractiveSize +
                        ChatConversationAvatarTokens.leadingGap,
                  ),
                  Expanded(
                    child: Text(
                      title,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: AppTypography.iosBody,
                        fontWeight: AppTypography.regular,
                        color: fgPrimary,
                        height: AppTypography.lineHeightTight,
                      ),
                    ),
                  ),
                  Icon(
                    CupertinoIcons.chevron_right,
                    size: AppSpacing.iconSmall,
                    color: fgPrimary.withValues(alpha: 0.4),
                  ),
                ],
              ),
            ),
            Padding(
              padding: EdgeInsets.only(
                left: AppSpacing.minInteractiveSize +
                    ChatConversationAvatarTokens.dividerInset(
                      ChatConversationAvatarTokens.listSize,
                    ),
              ),
              child: Divider(
                key: ValueKey<String>('start-group-action-entry-divider-$title'),
                height: AppSpacing.one,
                thickness: AppSpacing.hairline,
                color: dividerColor,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _LetterIndex extends StatelessWidget {
  const _LetterIndex({required this.letters, required this.onTap});

  final List<String> letters;
  final void Function(int index) onTap;

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: List.generate(letters.length, (i) {
          return CupertinoButton(
            padding: EdgeInsets.zero,
            minimumSize: Size.zero,
            onPressed: () => onTap(i),
            child: Container(
              width: AppSpacing.twenty,
              height: AppSpacing.twenty,
              alignment: Alignment.center,
              margin: EdgeInsets.symmetric(vertical: AppSpacing.one),
              child: Text(
                letters[i],
                style: TextStyle(
                  fontSize: AppTypography.xs,
                  fontWeight: AppTypography.semiBold,
                  color: fgSecondary,
                ),
              ),
            ),
          );
        }),
      ),
    );
  }
}

class _SelectionIndicator extends StatelessWidget {
  const _SelectionIndicator({
    required this.selected,
    required this.onTap,
    this.enabled = true,
  });

  final bool selected;
  final VoidCallback? onTap;
  final bool enabled;

  @override
  Widget build(BuildContext context) {
    return CupertinoButton(
      padding: EdgeInsets.zero,
      onPressed: enabled ? onTap : null,
      minimumSize: Size(
        AppSpacing.minInteractiveSize,
        AppSpacing.minInteractiveSize,
      ),
      child: Icon(
        selected
            ? CupertinoIcons.check_mark_circled_solid
            : CupertinoIcons.circle,
        color: selected
            ? AppColors.primaryColor.withValues(alpha: enabled ? 1 : 0.6)
            : CupertinoColors.systemGrey2,
        size: AppSpacing.iconMedium,
      ),
    );
  }
}
