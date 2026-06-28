// ignore_for_file: unnecessary_non_null_assertion
part of 'home_multi_form_feed.dart';

class _HomeRelationPostCard extends ConsumerStatefulWidget {
  const _HomeRelationPostCard({
    required this.cardContainerKey,
    required this.moreButtonKey,
    required this.wideLayout,
    required this.item,
    required this.isDark,
    required this.isLiked,
    required this.likeCount,
    required this.shareCount,
    required this.commentCount,
    required this.sourceCircleName,
    required this.inlineImageCarousel,
    required this.videoScrollSignal,
    required this.isFocused,
    required this.onUserTap,
    required this.onImageTap,
    required this.onCommentTap,
    required this.onShareTap,
    required this.onLikeTap,
    required this.onMoreTap,
  });

  final Key cardContainerKey;
  final Key moreButtonKey;
  final bool wideLayout;
  final PostBaseDto item;
  final bool isDark;
  final bool isLiked;
  final int likeCount;
  final int shareCount;
  final int commentCount;
  final String sourceCircleName;
  final bool inlineImageCarousel;
  final ValueListenable<_HomeFeedVideoScrollSignal> videoScrollSignal;
  final bool isFocused;
  final void Function(String) onUserTap;
  final void Function(int imageIndex) onImageTap;
  final VoidCallback onCommentTap;
  final VoidCallback onShareTap;
  final VoidCallback onLikeTap;
  final void Function(double cardWidth) onMoreTap;

  @override
  ConsumerState<_HomeRelationPostCard> createState() =>
      _HomeRelationPostCardState();
}

class _HomeRelationPostCardState extends ConsumerState<_HomeRelationPostCard>
    with SingleTickerProviderStateMixin {
  static const int _maxLines = 5;

  bool _isExpanded = false;
  late AnimationController _likeCtrl;

  @override
  void initState() {
    super.initState();
    _likeCtrl = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 200),
    );
  }

  @override
  void dispose() {
    _likeCtrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    ref.watch(userRelationshipStateProvider);
    ref.watch(discoveryStateProvider);
    return LayoutBuilder(
      builder: (context, constraints) {
        final item = widget.item;
        final isDark = widget.isDark;
        final cardWidth =
            constraints.hasBoundedWidth && constraints.maxWidth > 0
            ? constraints.maxWidth
            : MediaQuery.sizeOf(context).width;
        final fg = AppColorsFunctional.getColor(
          isDark,
          ColorType.foregroundPrimary,
        );
        final muted = AppColorsFunctional.getColor(
          isDark,
          ColorType.foregroundSecondary,
        );
        final cardBg = SettingsSemanticConstants.conversationSheetCardSurface(
          isDark,
        );
        final cardBorder = widget.wideLayout
            ? SettingsSemanticConstants.conversationSheetCardBorderColor(isDark)
            : AppColors.transparent;
        final borderRadius = widget.wideLayout
            ? BorderRadius.circular(AppSpacing.contentPreviewCornerRadius)
            : BorderRadius.zero;
        final primaryReason =
            widget.item.intersectionReasons?.isNotEmpty == true
            ? widget.item.intersectionReasons!.first
            : null;
        final profileSubjectId = item.subAccountId.trim().isNotEmpty
            ? item.subAccountId
            : item.authorId;

        return DecoratedBox(
          key: widget.cardContainerKey,
          decoration: BoxDecoration(
            color: cardBg,
            borderRadius: borderRadius,
            border: Border.all(color: cardBorder, width: AppSpacing.hairline),
          ),
          child: Padding(
            padding: const EdgeInsets.fromLTRB(
              AppSpacing.containerMd,
              _feedCardVerticalPadding,
              AppSpacing.containerMd,
              _feedCardVerticalPadding,
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  key: const ValueKey('home-relation-card-header'),
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    CupertinoButton(
                      padding: EdgeInsets.zero,
                      minimumSize: Size.zero,
                      onPressed: () => widget.onUserTap(profileSubjectId),
                      child: RoundedSquareAvatar(
                        size: AppSpacing.avatarUserSm,
                        imageUrl: item.avatarUrl,
                        name: item.displayName,
                        borderRadius: AppSpacing.avatarUserSm / 2,
                        backgroundColor: AppColors.iosSecondaryFill(context),
                        fallbackIcon: CupertinoIcons.person_crop_circle_fill,
                      ),
                    ),
                    SizedBox(width: AppSpacing.intraGroupMd),
                    Expanded(
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            item.displayName,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: TextStyle(
                              fontSize: AppTypography.feedAuthorNameResponsive(
                                context,
                              ),
                              fontWeight: AppTypography.medium,
                              color: fg,
                              letterSpacing: -0.08,
                              height: AppSpacing.textLineHeightDense,
                            ),
                          ),
                          const SizedBox(height: AppSpacing.two),
                          _AuthorMetaLine(
                            item: item,
                            fallbackText: _buildMetaLine(context),
                            color: muted,
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(width: AppSpacing.intraGroupMd),
                    _FollowPillButton(
                      isFollowing: effectiveProfileFollowing(
                        ref,
                        profileSubjectId,
                      ),
                      onPressed: () {
                        runWhenLoggedIn(
                          ref,
                          context,
                          AuthGateReason.follow,
                          () {
                            final wasFollowing = effectiveProfileFollowing(
                              ref,
                              profileSubjectId,
                            );
                            final nextFollowing = !wasFollowing;
                            syncProfileFollowIntent(
                              ref,
                              subAccountId: profileSubjectId,
                              previousFollowing: wasFollowing,
                              isFollowing: nextFollowing,
                            );
                          },
                        );
                      },
                    ),
                  ],
                ),

                const SizedBox(height: _feedCardSectionGap),
                _HomeConnectionBadgesRow(
                  item: item,
                  sourceCircleName: widget.sourceCircleName,
                  primaryReason: primaryReason,
                ),
                if (_HomeConnectionBadgesRow.hasAnyBadge(
                  item: item,
                  sourceCircleName: widget.sourceCircleName,
                  primaryReason: primaryReason,
                ))
                  const SizedBox(height: AppSpacing.intraGroupSm),
                if (item.isArticleLike)
                  _HomeArticlePostCard(
                    item: item,
                    isDark: isDark,
                    reason: primaryReason,
                    onTap: () => widget.onImageTap(0),
                    onFallbackTap: primaryReason == null
                        ? null
                        : () =>
                              _openFallbackIntersection(context, primaryReason),
                    onSpanTap: primaryReason == null
                        ? null
                        : (span) => _openSpanIntersection(
                            context,
                            primaryReason,
                            span,
                          ),
                  )
                else if (item.isVideoLike)
                  _HomeFeedVideoAutoPlayGate(
                    videoId: item.id,
                    scrollSignal: widget.videoScrollSignal,
                    hasPlayableSource: item.mediaVideoUrl.trim().isNotEmpty,
                    onFastScrollSuppressed: (attributes) => ref
                        .read(cacheTelemetrySinkProvider)
                        .record(
                          'video.init.suppressed_fast_scroll',
                          attributes,
                        ),
                    builder: (playback) => _HomeVideoPostCard(
                      item: item,
                      isDark: isDark,
                      reason: primaryReason,
                      initialize: playback.initialize,
                      autoPlay: playback.autoPlay,
                      onTap: () => widget.onImageTap(0),
                      onFallbackTap: primaryReason == null
                          ? null
                          : () => _openFallbackIntersection(
                              context,
                              primaryReason,
                            ),
                      onSpanTap: primaryReason == null
                          ? null
                          : (span) => _openSpanIntersection(
                              context,
                              primaryReason,
                              span,
                            ),
                    ),
                  )
                else
                  _HomeImagePostCard(
                    item: item,
                    isDark: isDark,
                    reason: primaryReason,
                    expanded: _isExpanded,
                    onToggleExpanded: () =>
                        setState(() => _isExpanded = !_isExpanded),
                    onTap: widget.onImageTap,
                    onFallbackTap: primaryReason == null
                        ? null
                        : () =>
                              _openFallbackIntersection(context, primaryReason),
                    onSpanTap: primaryReason == null
                        ? null
                        : (span) => _openSpanIntersection(
                            context,
                            primaryReason,
                            span,
                          ),
                  ),

                const SizedBox(height: _feedCardSectionGap),
                _ActionRow(
                  key: const ValueKey('home-relation-card-actions'),
                  moreButtonKey: widget.moreButtonKey,
                  item: item,
                  isDark: isDark,
                  isLiked: widget.isLiked,
                  likeCount: widget.likeCount,
                  shareCount: widget.shareCount,
                  commentCount: widget.commentCount,
                  likeCtrl: _likeCtrl,
                  onLike: () {
                    HapticFeedback.lightImpact();
                    // 任务 A · 动效尊重「减少动态效果」无障碍设置：仅在未禁用动画时播放点赞缩放。
                    if (!MediaQuery.disableAnimationsOf(context)) {
                      _likeCtrl.forward(from: 0);
                    }
                    widget.onLikeTap();
                  },
                  onComment: widget.onCommentTap,
                  onShare: widget.onShareTap,
                  onMore: () => widget.onMoreTap(cardWidth),
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  String _buildMetaLine(BuildContext context) {
    final time = _timeAgo(context, widget.item.createdAt);
    if (widget.sourceCircleName.isEmpty) return time;
    return '$time · ${UITextConstants.sourceFromPrefix}${widget.sourceCircleName}';
  }

  void _openSpanIntersection(
    BuildContext context,
    IntersectionReason reason,
    IntersectionTextSpan span,
  ) {
    final navigator = IntersectionTargetNavigator(
      onTrack: (target, attribution) {
        ref
            .read(contentBehaviorTrackerProvider)
            .trackTagClick(
              target.objectId,
              referralSource: ReferralSource.organicFeed,
              tags: attribution.tagRefs,
              intersectionId: attribution.intersectionId,
              intersectionDimension: attribution.dimension,
              intersectionSourceRef: attribution.sourceRef,
              intersectionTagRefs: attribution.tagRefs,
              intersectionClass: attribution.intersectionClass,
              intersectionEvidenceId: attribution.evidenceId,
            );
      },
    );
    navigator.open(
      context,
      span.target,
      sourceRef: reason.source,
      attribution: IntersectionNavAttribution(
        intersectionId: reason.intersectionId,
        dimension: reason.dimension,
        intersectionClass: reason.intersectionClass,
        sourceRef: reason.source,
        tagRefs: reason.tagRefs,
        evidenceId: reason.pointSummarySnapshotId,
      ),
    );
  }

  void _openFallbackIntersection(
    BuildContext context,
    IntersectionReason reason,
  ) {
    IntersectionTarget? firstVisualTarget;
    for (final visual in reason.sampleVisuals) {
      if (visual.target != null) {
        firstVisualTarget = visual.target;
        break;
      }
    }
    final navigator = IntersectionTargetNavigator(
      onTrack: (target, attribution) {
        ref
            .read(contentBehaviorTrackerProvider)
            .trackTagClick(
              target.objectId,
              referralSource: ReferralSource.organicFeed,
              tags: attribution.tagRefs,
              intersectionId: attribution.intersectionId,
              intersectionDimension: attribution.dimension,
              intersectionSourceRef: attribution.sourceRef,
              intersectionTagRefs: attribution.tagRefs,
              intersectionClass: attribution.intersectionClass,
              intersectionEvidenceId: attribution.evidenceId,
            );
      },
    );
    final opened = navigator.open(
      context,
      firstVisualTarget,
      sourceRef: reason.source,
      attribution: IntersectionNavAttribution(
        intersectionId: reason.intersectionId,
        dimension: reason.dimension,
        intersectionClass: reason.intersectionClass,
        sourceRef: reason.source,
        tagRefs: reason.tagRefs,
        evidenceId: reason.pointSummarySnapshotId,
      ),
    );
    if (opened) return;
    final dimension = reason.dimension.trim();
    if (dimension.isEmpty) return;
    navigator.open(
      context,
      IntersectionTarget(
        objectId: dimension,
        objectKind: 'tag',
        routeId: 'myIntersections',
      ),
      sourceRef: reason.source,
      attribution: IntersectionNavAttribution(
        intersectionId: reason.intersectionId,
        dimension: reason.dimension,
        intersectionClass: reason.intersectionClass,
        sourceRef: reason.source,
        tagRefs: reason.tagRefs,
        evidenceId: reason.pointSummarySnapshotId,
      ),
    );
  }

  static String _timeAgo(BuildContext context, DateTime t) {
    final l10n = Localizations.of<AppLocalizations>(context, AppLocalizations);
    final delta = DateTime.now().difference(t).inHours;
    if (delta < 1) return l10n?.justNow ?? '刚刚';
    if (delta < 24) return l10n?.hoursAgoTemplate(delta) ?? '$delta 小时前';
    return l10n?.monthDayTemplate(t.month, t.day) ?? '${t.month}/${t.day}';
  }
}

class _FollowingArticleCard extends StatelessWidget {
  const _FollowingArticleCard({
    required this.item,
    required this.isDark,
    required this.summaryLineLimit,
    required this.sourceCircleName,
    required this.onTap,
    required this.onMoreTap,
  });

  final PostBaseDto item;
  final bool isDark;
  final int summaryLineLimit;
  final String sourceCircleName;
  final VoidCallback onTap;
  final VoidCallback onMoreTap;

  @override
  Widget build(BuildContext context) {
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final eyebrowSegments = <String>[
      '文章',
      _articleTemplateLabel,
      if (sourceCircleName.isNotEmpty) sourceCircleName,
    ];

    return PostPreviewListTile(
      key: ValueKey<String>('following-article-card-${item.id}'),
      isDark: isDark,
      eyebrowText: eyebrowSegments.join(' · '),
      eyebrowColor: AppColors.primaryColor,
      title: _headlineText,
      supportingText: _supportingText,
      supportingTextMaxLines: summaryLineLimit,
      coverUrl: item.mediaCoverUrl,
      hideThumbnailWhenNoCover: true,
      thumbnailKey: item.mediaCoverUrl.isNotEmpty
          ? ValueKey<String>('following-article-thumbnail-${item.id}')
          : null,
      onTap: onTap,
      footer: Row(
        children: [
          Expanded(
            child: Text(
              item.displayName,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                fontSize: AppTypography.iosCaption1,
                color: fgSecondary,
              ),
            ),
          ),
          SizedBox(width: AppSpacing.intraGroupXs),
          Text(
            _HomeRelationPostCardState._timeAgo(context, item.createdAt),
            style: TextStyle(
              fontSize: AppTypography.iosCaption1,
              color: fgSecondary,
            ),
          ),
        ],
      ),
      trailing: _HomeFeedMoreButton(
        isDark: isDark,
        color: fgSecondary,
        onPressed: onMoreTap,
      ),
    );
  }

  String get _articleTemplateLabel {
    final templateId = item is ArticlePostDto
        ? (item as ArticlePostDto).articleTemplate
        : '';
    switch (templateId) {
      case 'ritual':
        return '礼记';
      case 'diffuse':
        return '弥散';
      case 'journal':
        return '手帐';
      case 'tech':
        return '科技';
      default:
        return '柔和';
    }
  }

  String get _headlineText {
    final title = item.normalizedTitle;
    final body = item.normalizedBody;
    if (title.isNotEmpty) return title;
    if (body.isNotEmpty) return body;
    return '文章';
  }

  String get _supportingText {
    final title = item.normalizedTitle;
    final body = item.normalizedBody;
    if (title.isEmpty || body.isEmpty || title == body) {
      return '';
    }
    return body;
  }
}

class _HomeConnectionBadgesRow extends StatelessWidget {
  const _HomeConnectionBadgesRow({
    required this.item,
    required this.sourceCircleName,
    required this.primaryReason,
  });

  final PostBaseDto item;
  final String sourceCircleName;
  final IntersectionReason? primaryReason;

  static bool hasAnyBadge({
    required PostBaseDto item,
    required String sourceCircleName,
    required IntersectionReason? primaryReason,
  }) {
    return _entityLabel(primaryReason) != null ||
        sourceCircleName.trim().isNotEmpty ||
        _showCompanionBadge(item, primaryReason);
  }

  static String? _entityLabel(IntersectionReason? reason) {
    if (reason == null) {
      return null;
    }
    final visualLabel = reason.objectVisual?.displayName.trim() ?? '';
    if (visualLabel.isNotEmpty) {
      return visualLabel;
    }
    for (final span in reason.primarySpans) {
      final kind = span.target?.objectKind.trim() ?? '';
      if (kind == 'homepage' || kind == 'place') {
        final text = span.text.trim();
        if (text.isNotEmpty) {
          return text;
        }
      }
    }
    return null;
  }

  static bool _showCompanionBadge(
    PostBaseDto item,
    IntersectionReason? reason,
  ) {
    if (reason != null) {
      for (final hint in reason.actionHints) {
        if (IntersectionActionKeys.isHeavySocialAction(hint.actionKey)) {
          return true;
        }
      }
    }
    final text = '${item.normalizedTitle} ${item.normalizedBody}';
    const travelHints = <String>['稻城', '峨眉', '川西', '结伴', '同行'];
    return travelHints.any(text.contains);
  }

  @override
  Widget build(BuildContext context) {
    if (!hasAnyBadge(
      item: item,
      sourceCircleName: sourceCircleName,
      primaryReason: primaryReason,
    )) {
      return const SizedBox.shrink();
    }

    final accent = AppColors.iosAccent(context);
    final chips = <Widget>[];

    final entity = _entityLabel(primaryReason);
    if (entity != null) {
      chips.add(
        _badgeChip(
          context,
          label: entity,
          prefix: PlazaTextConstants.feedBadgeEntity,
          accent: accent,
        ),
      );
    }

    final circle = sourceCircleName.trim();
    if (circle.isNotEmpty) {
      chips.add(
        _badgeChip(
          context,
          label: circle,
          prefix: PlazaTextConstants.feedBadgeCircle,
          accent: accent,
        ),
      );
    }

    if (_showCompanionBadge(item, primaryReason)) {
      chips.add(
        _badgeChip(
          context,
          label: PlazaTextConstants.feedBadgeCompanion,
          accent: accent,
        ),
      );
    }

    return Wrap(
      key: const ValueKey<String>('home-connection-badges-row'),
      spacing: AppSpacing.intraGroupSm,
      runSpacing: AppSpacing.intraGroupXs,
      children: chips,
    );
  }

  Widget _badgeChip(
    BuildContext context, {
    required String label,
    String? prefix,
    required Color accent,
  }) {
    final text = prefix == null || prefix.isEmpty ? label : '$prefix · $label';
    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.intraGroupSm,
        vertical: AppSpacing.intraGroupXs,
      ),
      decoration: BoxDecoration(
        color: accent.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(AppSpacing.radiusTen),
      ),
      child: Text(
        text,
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
        style: TextStyle(
          fontSize: AppTypography.iosCaption2,
          fontWeight: AppTypography.medium,
          color: accent,
        ),
      ),
    );
  }
}

class _AuthorMetaLine extends StatelessWidget {
  const _AuthorMetaLine({
    required this.item,
    required this.fallbackText,
    required this.color,
  });

  final PostBaseDto item;
  final String fallbackText;
  final Color color;

  @override
  Widget build(BuildContext context) {
    final segments = <String>[
      if (item.authorRoleLabel.trim().isNotEmpty) item.authorRoleLabel.trim(),
      ...item.authorIdentityTags
          .map((tag) => tag.trim())
          .where((tag) => tag.isNotEmpty)
          .take(2),
      if (item.authorRoleLabel.trim().isEmpty &&
          item.authorIdentityTags.isEmpty)
        fallbackText,
    ];
    return Row(
      children: [
        if (item.authorVerified) ...[
          Icon(
            CupertinoIcons.checkmark_seal_fill,
            size: AppSpacing.iconXSmall,
            color: AppColors.iosAccent(context),
          ),
          const SizedBox(width: AppSpacing.intraGroupXs),
        ],
        Expanded(
          child: Text(
            segments.join(' · '),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              fontSize: AppTypography.iosCaption1,
              color: color,
              letterSpacing: -0.04,
              height: AppSpacing.one,
            ),
          ),
        ),
      ],
    );
  }
}

class _FollowPillButton extends StatelessWidget {
  const _FollowPillButton({required this.isFollowing, required this.onPressed});

  final bool isFollowing;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    final accent = AppColors.iosAccent(context);
    final bg = isFollowing
        ? AppColors.iosSecondaryFill(context)
        : accent.withValues(alpha: 0.12);
    return CupertinoButton(
      padding: EdgeInsets.zero,
      minimumSize: Size.zero,
      onPressed: onPressed,
      child: Container(
        key: const ValueKey<String>('home-post-author-follow-button'),
        width: AppSpacing.followButtonWidthCompact,
        height: AppSpacing.buttonHeightXs,
        alignment: Alignment.center,
        decoration: BoxDecoration(
          color: bg,
          borderRadius: BorderRadius.circular(AppSpacing.circularBorderRadius),
        ),
        child: Text(
          isFollowing ? UITextConstants.following : UITextConstants.follow,
          maxLines: 1,
          overflow: TextOverflow.fade,
          softWrap: false,
          style: TextStyle(
            fontSize: AppTypography.xs,
            fontWeight: AppTypography.semiBold,
            color: isFollowing ? AppColors.iosSecondaryLabel(context) : accent,
          ),
        ),
      ),
    );
  }
}

class _PostIntersectionLine extends StatelessWidget {
  const _PostIntersectionLine({
    required this.reason,
    this.onSpanTap,
    this.onFallbackTap,
  });

  final IntersectionReason reason;
  final void Function(IntersectionTextSpan span)? onSpanTap;
  final VoidCallback? onFallbackTap;

  @override
  Widget build(BuildContext context) {
    final accent = AppColors.iosAccent(context);
    // 任务 B · 分层强度：事实型交集（共同关注/到访/收藏）视觉强于推测型，
    // 推测型背景/描边更弱、导语颜色向次级文本混合，但仍保留可点击 affordance。
    final bool isFact = _isFactIntersection(reason);
    final double backgroundOpacity = isFact
        ? DiscoveryFeedSpacing.homeFeedIntersectionBackgroundOpacity
        : DiscoveryFeedSpacing.homeFeedIntersectionBackgroundOpacitySoft;
    final double borderOpacity = isFact
        ? DiscoveryFeedSpacing.homeFeedIntersectionBorderOpacity
        : DiscoveryFeedSpacing.homeFeedIntersectionBorderOpacitySoft;
    return DecoratedBox(
      key: const ValueKey('home-relation-card-reason'),
      decoration: BoxDecoration(
        color: accent.withValues(alpha: backgroundOpacity),
        borderRadius: BorderRadius.circular(
          DiscoveryFeedSpacing.homeFeedMediaCornerRadius,
        ),
        border: Border.all(
          color: accent.withValues(alpha: borderOpacity),
          width: AppSpacing.hairline,
        ),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(
          horizontal: DiscoveryFeedSpacing.homeFeedIntersectionPadding,
          vertical: DiscoveryFeedSpacing.homeFeedIntersectionPadding,
        ),
        child: InteractiveIntersectionText(
          spans: reason.primarySpans,
          fallbackText: reason.primaryText,
          maxLines: 1,
          onSpanTap: onSpanTap,
          onFallbackTap: onFallbackTap,
          // 任务 B · 分层强度：首页交集证据行把可点击片段（姓名/数字）做成
          // 比正文更重的字重，强化「可点击行动召唤」的视觉识别，而组件默认
          // 字重仍保持常规（见 interactive_intersection_text_test）。
          accentFontWeight: AppTypography.medium,
          baseStyle: TextStyle(
            fontSize: AppTypography.iosFootnote,
            height: AppSpacing.textLineHeightFootnote,
            color: AppColors.iosLabel(context),
            letterSpacing: 0,
          ),
        ),
      ),
    );
  }
}

/// 任务 B · 分层强度：事实型交集（共同关注/到访/收藏等硬证据）。
/// 云侧 `intersectionClass` 是唯一真相源，端侧只读不自造；默认按事实型从重显示。
bool _isFactIntersection(IntersectionReason reason) {
  final normalized = reason.intersectionClass.trim().toLowerCase();
  // 仅显式标记为推测型时弱化，其余（含空值/fact）按事实型从重。
  return normalized != 'recommended' &&
      normalized != 'inferred' &&
      normalized != 'affinity';
}

Widget? _buildPostIntersectionRow({
  required IntersectionReason? reason,
  required void Function(IntersectionTextSpan span)? onSpanTap,
  required VoidCallback? onFallbackTap,
  Key key = const ValueKey('home-post-inline-intersection'),
}) {
  if (!_shouldShowIntersection(reason)) {
    return null;
  }
  return KeyedSubtree(
    key: key,
    child: _PostIntersectionLine(
      reason: reason!,
      onSpanTap: onSpanTap,
      onFallbackTap: onFallbackTap,
    ),
  );
}

/// 任务 A · 加载态：首页推荐占位骨架屏。脉冲渐显在「减少动态效果」下退化为静态占位。
