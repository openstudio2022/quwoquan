part of 'start_group_chat_page.dart';

class _SelectedMemberAvatar extends StatelessWidget {
  const _SelectedMemberAvatar({
    required this.name,
    required this.avatarUrl,
    required this.onRemove,
    required this.isDark,
  });

  final String name;
  final String avatarUrl;
  final VoidCallback onRemove;
  final bool isDark;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: AppSpacing.iconButtonMinSizeMd,
      child: Stack(
        clipBehavior: Clip.none,
        children: [
          Column(
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
          Positioned(
            right: -2,
            top: -2,
            child: GestureDetector(
              onTap: onRemove,
              child: Container(
                width: AppSpacing.eighteen,
                height: AppSpacing.eighteen,
                decoration: BoxDecoration(
                  color:
                      SettingsSemanticConstants.selectionAvatarAccessoryBackground(
                        isDark,
                      ),
                  shape: BoxShape.circle,
                  border: Border.all(
                    color:
                        SettingsSemanticConstants.selectionAvatarAccessoryBorder(
                          isDark,
                        ),
                  ),
                ),
                child: Icon(
                  CupertinoIcons.clear,
                  size: AppSpacing.ten + AppSpacing.one,
                  color:
                      SettingsSemanticConstants.selectionAvatarAccessoryForeground(
                        isDark,
                      ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _SelectionSectionLabel extends StatelessWidget {
  const _SelectionSectionLabel({required this.title, required this.color});

  final String title;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.fromLTRB(
        SettingsSemanticConstants.blockHorizontalPadding,
        AppSpacing.xs,
        AppSpacing.xs,
        AppSpacing.xs,
      ),
      child: Text(
        title,
        style: TextStyle(
          fontSize: AppTypography.iosFootnote,
          fontWeight: AppTypography.medium,
          color: color,
        ),
      ),
    );
  }
}

class _SelectionCard extends StatelessWidget {
  const _SelectionCard({
    required this.isDark,
    required this.child,
    this.padding = EdgeInsets.zero,
  });

  final bool isDark;
  final Widget child;
  final EdgeInsetsGeometry padding;

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(
        SettingsSemanticConstants.insetFormSectionCornerRadius,
      ),
      child: ColoredBox(
        color: SettingsSemanticConstants.insetFormSectionSurface(isDark),
        child: Padding(padding: padding, child: child),
      ),
    );
  }
}

class _SelectionListDivider extends StatelessWidget {
  const _SelectionListDivider({required this.isDark, this.leadingInset = 0});

  final bool isDark;
  final double leadingInset;

  @override
  Widget build(BuildContext context) {
    return Container(
      height: SettingsSemanticConstants.dividerThickness,
      margin: EdgeInsets.only(
        left: SettingsSemanticConstants.blockHorizontalPadding + leadingInset,
        right: SettingsSemanticConstants.blockHorizontalPadding,
      ),
      color: SettingsSemanticConstants.insetFormSectionDividerColor(isDark),
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
    required this.onTap,
    required this.onAvatarTap,
  });

  final String name;
  final String username;
  final String avatarUrl;
  final bool selected;
  final Color fgPrimary;
  final Color fgSecondary;
  final bool locked;
  final VoidCallback? onTap;
  final VoidCallback onAvatarTap;

  @override
  Widget build(BuildContext context) {
    return CupertinoButton(
      padding: EdgeInsets.zero,
      onPressed: onTap,
      child: ConstrainedBox(
        constraints: BoxConstraints(
          minHeight: SettingsSemanticConstants.selectionRowMinHeight,
        ),
        child: Padding(
          padding: EdgeInsets.symmetric(
            horizontal: SettingsSemanticConstants.blockHorizontalPadding,
            vertical: AppSpacing.sm,
          ),
          child: Row(
            children: [
              _SelectionIndicator(
                selected: selected,
                onTap: onTap,
                enabled: !locked && onTap != null,
              ),
              GestureDetector(
                onTap: onAvatarTap,
                child: RoundedSquareAvatar(
                  size: AppSpacing.avatarSize,
                  imageUrl: avatarUrl,
                  name: name,
                  fallbackIcon: CupertinoIcons.person_fill,
                ),
              ),
              SizedBox(width: AppSpacing.sm),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      name,
                      style: TextStyle(
                        fontSize: AppTypography.lg,
                        color: locked ? fgSecondary : fgPrimary,
                      ),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                    if (locked)
                      Text(
                        UITextConstants.startGroupChatAlreadyInGroup,
                        style: TextStyle(
                          fontSize: AppTypography.sm,
                          color: fgSecondary,
                        ),
                      ),
                  ],
                ),
              ),
            ],
          ),
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
    final fgSecondary = isDark
        ? AppColors.white.withValues(alpha: 0.45)
        : AppColors.black.withValues(alpha: 0.45);
    return Column(
      mainAxisAlignment: MainAxisAlignment.center,
      children: List.generate(letters.length, (i) {
        return GestureDetector(
          onTap: () => onTap(i),
          child: Padding(
            padding: EdgeInsets.symmetric(vertical: AppSpacing.xs),
            child: Text(
              letters[i],
              style: TextStyle(
                fontSize: AppTypography.xs,
                color: fgSecondary,
                fontWeight: FontWeight.normal,
              ),
            ),
          ),
        );
      }),
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
