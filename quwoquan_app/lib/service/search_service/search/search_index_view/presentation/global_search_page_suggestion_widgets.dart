part of 'global_search_page.dart';

class _KeywordSuggestionRow extends StatelessWidget {
  const _KeywordSuggestionRow({
    required this.entry,
    required this.query,
    required this.color,
    required this.onTap,
  });

  final SearchSuggestionEntry entry;
  final String query;
  final Color color;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final network = entry.cast<NetworkSearchSuggestion>();
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final secondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    if (network.isHomepagePreview) {
      final coverUrl = network.coverUrl?.trim() ?? '';
      return _BasicSuggestionTile(
        leading: ClipRRect(
          borderRadius: BorderRadius.circular(AppSpacing.smallBorderRadius),
          child: SizedBox.square(
            dimension: AppSpacing.avatarUserMd,
            child: coverUrl.isEmpty
                ? Icon(CupertinoIcons.map_fill, color: secondary)
                : AppCachedNetworkImage(
                    imageUrl: coverUrl,
                    fit: BoxFit.cover,
                    width: AppSpacing.avatarUserMd,
                    height: AppSpacing.avatarUserMd,
                    cdnPreset: CdnImagePreset.cover,
                    errorWidget: Icon(
                      CupertinoIcons.map_fill,
                      color: secondary,
                    ),
                  ),
          ),
        ),
        title: _highlightedText(
          network.displayTitle,
          query,
          TextStyle(
            fontSize: _SearchTokens.bodySize,
            fontWeight: _SearchTokens.bodyWeight,
            color: color,
          ),
        ),
        subtitle: Text(
          network.subtitle ?? '',
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: TextStyle(
            fontSize: AppTypography.iosFootnote,
            color: secondary,
          ),
        ),
        trailing: Icon(
          CupertinoIcons.chevron_forward,
          color: secondary,
          size: AppSpacing.iconSmall,
        ),
        onTap: onTap,
      );
    }
    return _BasicSuggestionTile(
      leading: DecoratedBox(
        decoration: BoxDecoration(
          color: AppColorsFunctional.getColor(
            isDark,
            ColorType.backgroundTertiary,
          ),
          shape: BoxShape.circle,
        ),
        child: SizedBox.square(
          dimension: AppSpacing.avatarUserMd,
          child: Icon(
            CupertinoIcons.search,
            size: AppSpacing.iconMedium,
            color: AppColors.primaryColor,
          ),
        ),
      ),
      title: _highlightedText(
        network.displayTitle,
        query,
        TextStyle(
          fontSize: _SearchTokens.bodySize,
          fontWeight: _SearchTokens.bodyWeight,
          color: color,
        ),
      ),
      subtitle: Text(
        SearchText.searchAllResults,
        style: TextStyle(fontSize: AppTypography.iosFootnote, color: secondary),
      ),
      trailing: Icon(
        CupertinoIcons.chevron_forward,
        color: secondary,
        size: AppSpacing.iconSmall,
      ),
      onTap: onTap,
    );
  }
}

class _BasicSuggestionTile extends StatelessWidget {
  const _BasicSuggestionTile({
    required this.leading,
    required this.title,
    required this.onTap,
    this.subtitle,
    this.trailing,
  });

  final Widget leading;
  final Widget title;
  final Widget? subtitle;
  final Widget? trailing;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return CupertinoButton(
      padding: EdgeInsets.all(AppSpacing.containerSm),
      minimumSize: Size.zero,
      onPressed: onTap,
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          leading,
          SizedBox(width: AppSpacing.containerSm),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                title,
                if (subtitle case final subtitleWidget?) ...[
                  SizedBox(height: AppSpacing.two),
                  subtitleWidget,
                ],
              ],
            ),
          ),
          if (trailing case final trailingWidget?) ...[
            SizedBox(width: AppSpacing.containerSm),
            trailingWidget,
          ],
        ],
      ),
    );
  }
}

class _ChatRecordTile extends ConsumerWidget {
  const _ChatRecordTile({
    required this.suggestion,
    required this.query,
    required this.isDark,
    required this.onTap,
  });

  final ChatRecordSearchSuggestion suggestion;
  final String query;
  final bool isDark;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final fgPrimary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    return CupertinoButton(
      padding: EdgeInsets.all(AppSpacing.containerSm),
      minimumSize: Size.zero,
      onPressed: onTap,
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          ref.watch(conversationAvatarBuilderProvider)(
            conversationId: suggestion.conversationId,
            conversationType: suggestion.conversationType,
            title: suggestion.conversationTitle,
            avatarUrl: suggestion.avatarUrl ?? '',
            size: AppSpacing.avatarUserMd,
            borderRadius: AppSpacing.avatarUserMd / 2,
            groupFallbackIcon: CupertinoIcons.person_2_fill,
            directFallbackIcon: CupertinoIcons.chat_bubble_2_fill,
          ),
          SizedBox(width: AppSpacing.containerSm),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(
                      child: _highlightedText(
                        suggestion.conversationTitle,
                        query,
                        TextStyle(
                          fontSize: _SearchTokens.bodySize,
                          fontWeight: _SearchTokens.bodyWeight,
                          color: fgPrimary,
                        ),
                      ),
                    ),
                    if (suggestion.timestamp case final timestamp?)
                      Text(
                        _formatDayLabel(timestamp),
                        style: TextStyle(
                          fontSize: AppTypography.iosCaption1,
                          color: fgSecondary,
                        ),
                      ),
                  ],
                ),
                SizedBox(height: AppSpacing.two),
                _highlightedText(
                  suggestion.matchedPreview,
                  query,
                  TextStyle(
                    fontSize: AppTypography.iosFootnote,
                    color: fgSecondary,
                  ),
                  maxLines: 2,
                ),
                SizedBox(height: AppSpacing.two),
                Text(
                  ChatText.searchChatRecordCount(suggestion.matchCount),
                  style: TextStyle(
                    fontSize: AppTypography.iosCaption1,
                    color: AppColors.primaryColor,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _DividerLine extends StatelessWidget {
  const _DividerLine({required this.isDark});

  final bool isDark;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerSm),
      child: Container(
        height: AppSpacing.one,
        color: AppColorsFunctional.getColor(isDark, ColorType.separatorSubtle),
      ),
    );
  }
}

Widget _highlightedText(
  String text,
  String query,
  TextStyle style, {
  int maxLines = 1,
}) {
  if (text.trim().isEmpty) {
    return Text('', style: style);
  }
  final spans = SearchHighlightSpan.build(text: text, keyword: query);
  if (spans.length == 1 && !spans.first.isMatch) {
    return Text(
      text,
      maxLines: maxLines,
      overflow: TextOverflow.ellipsis,
      style: style,
    );
  }
  return Text.rich(
    TextSpan(
      children: spans
          .map(
            (span) => TextSpan(
              text: span.text,
              style: span.isMatch
                  ? style.copyWith(
                      color: AppColors.primaryColor,
                      fontWeight: AppTypography.medium,
                    )
                  : style,
            ),
          )
          .toList(growable: false),
    ),
    maxLines: maxLines,
    overflow: TextOverflow.ellipsis,
  );
}

Widget _buildConversationLeading({
  required String? avatarUrl,
  required bool isDark,
  required IconData fallbackIcon,
}) {
  final effectiveImageUrl = (avatarUrl ?? '').trim();
  if (effectiveImageUrl.isNotEmpty) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
      child: Container(
        width: AppSpacing.avatarUserMd,
        height: AppSpacing.avatarUserMd,
        color: AppColorsFunctional.getColor(
          isDark,
          ColorType.backgroundSecondary,
        ),
        child: AppAvatarImage(
          imageUrl: effectiveImageUrl,
          size: AppSpacing.avatarUserMd,
          fit: BoxFit.cover,
          errorWidget: Icon(
            fallbackIcon,
            size: AppSpacing.iconMedium,
            color: AppColorsFunctional.getColor(
              isDark,
              ColorType.foregroundSecondary,
            ),
          ),
        ),
      ),
    );
  }
  return ClipRRect(
    borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
    child: Container(
      width: AppSpacing.avatarUserMd,
      height: AppSpacing.avatarUserMd,
      color: AppColorsFunctional.getColor(
        isDark,
        ColorType.backgroundSecondary,
      ),
      child: Icon(
        fallbackIcon,
        size: AppSpacing.iconMedium,
        color: AppColorsFunctional.getColor(
          isDark,
          ColorType.foregroundSecondary,
        ),
      ),
    ),
  );
}

String _formatDayLabel(DateTime value) {
  final now = DateTime.now();
  final today = DateTime(now.year, now.month, now.day);
  final target = DateTime(value.year, value.month, value.day);
  final difference = today.difference(target).inDays;
  if (difference <= 0) {
    return SearchText.searchDateToday;
  }
  if (difference == 1) {
    return SearchText.searchDateYesterday;
  }
  return UITextConstants.searchDateMonthDay(value.month, value.day);
}
