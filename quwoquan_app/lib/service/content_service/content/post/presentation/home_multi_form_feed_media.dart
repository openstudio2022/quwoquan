// ignore_for_file: unnecessary_non_null_assertion
part of 'home_multi_form_feed.dart';

class _HomeImagePostCard extends ConsumerWidget {
  const _HomeImagePostCard({
    required this.item,
    required this.isDark,
    required this.reason,
    required this.expanded,
    required this.onToggleExpanded,
    required this.onTap,
    required this.onSpanTap,
    required this.onFallbackTap,
  });

  final ContentPostViewData item;
  final bool isDark;
  final IntersectionReason? reason;
  final bool expanded;
  final VoidCallback onToggleExpanded;
  final void Function(int index) onTap;
  final void Function(IntersectionTextSpan span)? onSpanTap;
  final VoidCallback? onFallbackTap;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final title = item.normalizedTitle;
    final body = item.normalizedBody;
    final contextObjectName = title.isNotEmpty ? title : body;
    final contextObjectTarget = IntersectionTarget(
      objectType: 'post',
      objectId: item.id,
      objectKind: 'content',
      routeId: 'workBrowser',
    );
    final media = _buildMedia(context, ref.watch(mediaEndpointConfigProvider));
    final isMomentGrid = _isMomentGridPost(item);
    final intersectionRow = _buildPostIntersectionRow(
      reason: reason,
      contextObjectName: contextObjectName,
      contextObjectTarget: contextObjectTarget,
      onSpanTap: onSpanTap,
      onFallbackTap: onFallbackTap,
    );
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (isMomentGrid) ...[
          if (body.isNotEmpty)
            KeyedSubtree(
              key: const ValueKey('home-relation-card-body'),
              child: _ExpandableText(
                text: body,
                maxLines: _HomeRelationPostCardState._maxLines,
                isDark: isDark,
                expanded: expanded,
                onToggle: onToggleExpanded,
              ),
            ),
          if (media != null) ...[
            if (body.isNotEmpty)
              const SizedBox(height: AppSpacing.intraGroupSm),
            KeyedSubtree(
              key: const ValueKey('home-relation-card-media'),
              child: media,
            ),
          ],
          if (intersectionRow != null) ...[
            if (body.isNotEmpty || media != null)
              const SizedBox(height: AppSpacing.intraGroupSm),
            intersectionRow,
          ],
        ] else ...[
          if (title.isNotEmpty) _PostTitle(title: title),
          if (title.isNotEmpty && media != null)
            const SizedBox(height: AppSpacing.intraGroupSm),
          if (media != null)
            KeyedSubtree(
              key: const ValueKey('home-relation-card-media'),
              child: media,
            ),
          if (body.isNotEmpty) ...[
            const SizedBox(height: AppSpacing.intraGroupSm),
            KeyedSubtree(
              key: const ValueKey('home-relation-card-body'),
              child: _ExpandableText(
                text: body,
                maxLines: _HomeRelationPostCardState._maxLines,
                isDark: isDark,
                expanded: expanded,
                onToggle: onToggleExpanded,
              ),
            ),
          ],
          if (intersectionRow != null) ...[
            if (title.isNotEmpty || media != null || body.isNotEmpty)
              const SizedBox(height: AppSpacing.intraGroupSm),
            intersectionRow,
          ],
        ],
      ],
    );
  }

  Widget? _buildMedia(
    BuildContext context,
    MediaEndpointConfig? endpointConfig,
  ) {
    final urls = item.mediaImageUrls;
    if (_isMomentGridPost(item)) {
      final visibleCount = _momentGridVisibleCount(urls.length);
      final sparseWidthFactor = urls.length <= 2
          ? _momentGridColumns(visibleCount) *
                DiscoveryFeedSpacing.homeFeedMomentSparseGridWidthFactor
          : null;
      return _ConstrainedMediaBox(
        aspectRatio: _momentGridAspectRatio(urls.length),
        fullWidth: sparseWidthFactor == null,
        widthFactor: sparseWidthFactor,
        child: _HomeMomentGridCard(urls: urls, isDark: isDark, onTap: onTap),
      );
    }
    if (urls.length > 1) {
      return _ConstrainedMediaBox(
        aspectRatio: _mediaAspectRatio(item),
        fullWidth: true,
        child: _HomeFeedImageCarousel(
          urls: urls,
          isDark: isDark,
          onTap: onTap,
          aspectRatio: _mediaAspectRatio(item),
        ),
      );
    }
    final url = item.primaryVisualUrl;
    if (url.isEmpty) return null;
    return _ConstrainedMediaBox(
      aspectRatio: _mediaAspectRatio(item),
      fullWidth: true,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: () => onTap(0),
        child: ClipRRect(
          borderRadius: BorderRadius.circular(
            DiscoveryFeedSpacing.homeFeedMediaCornerRadius,
          ),
          child: AppCachedNetworkImage(
            imageUrl: url,
            imageUrlCandidates: resolveContentMediaUrlCandidates(
              url,
              endpointConfig: endpointConfig,
            ),
            cdnPreset: CdnImagePreset.cover,
            fit: BoxFit.cover,
            placeholder: _mediaPlaceholder(isDark),
            // 失败态必须与加载占位可区分：静默灰块会把「media-edge 缺对象」
            // 伪装成加载中，用户与 UAT 都无法发现（errorWidget 缺省时使用
            // AppCachedNetworkImage 的显式失败件）。
          ),
        ),
      ),
    );
  }
}

class _HomeFeedVideoPlaybackState {
  const _HomeFeedVideoPlaybackState({
    required this.initialize,
    required this.autoPlay,
  });

  const _HomeFeedVideoPlaybackState.idle()
    : initialize = false,
      autoPlay = false;

  final bool initialize;
  final bool autoPlay;
}

class _HomeFeedVideoAutoPlayGate extends StatefulWidget {
  const _HomeFeedVideoAutoPlayGate({
    required this.videoId,
    required this.scrollSignal,
    required this.hasPlayableSource,
    required this.onFastScrollSuppressed,
    required this.builder,
  });

  /// 卡片在单活跃视频协调器中的唯一标识（用 post id）。
  final String videoId;
  final ValueListenable<_HomeFeedVideoScrollSignal> scrollSignal;
  final bool hasPlayableSource;
  final ValueChanged<Map<String, Object?>> onFastScrollSuppressed;
  final Widget Function(_HomeFeedVideoPlaybackState playback) builder;

  @override
  State<_HomeFeedVideoAutoPlayGate> createState() =>
      _HomeFeedVideoAutoPlayGateState();
}

class _HomeVideoPostCard extends StatelessWidget {
  const _HomeVideoPostCard({
    required this.item,
    required this.isDark,
    required this.reason,
    required this.initialize,
    required this.autoPlay,
    required this.onTap,
    required this.onSpanTap,
    required this.onFallbackTap,
  });

  final ContentPostViewData item;
  final bool isDark;
  final IntersectionReason? reason;
  final bool initialize;
  final bool autoPlay;
  final VoidCallback onTap;
  final void Function(IntersectionTextSpan span)? onSpanTap;
  final VoidCallback? onFallbackTap;

  @override
  Widget build(BuildContext context) {
    final title = item.normalizedTitle;
    final body = item.normalizedBody;
    final contextObjectName = title.isNotEmpty ? title : body;
    final contextObjectTarget = IntersectionTarget(
      objectType: 'post',
      objectId: item.id,
      objectKind: 'content',
      routeId: 'workBrowser',
    );
    final intersectionRow = _buildPostIntersectionRow(
      reason: reason,
      contextObjectName: contextObjectName,
      contextObjectTarget: contextObjectTarget,
      onSpanTap: onSpanTap,
      onFallbackTap: onFallbackTap,
    );
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (title.isNotEmpty) _PostTitle(title: title),
        if (title.isNotEmpty) const SizedBox(height: AppSpacing.intraGroupSm),
        KeyedSubtree(
          key: const ValueKey('home-relation-card-media'),
          child: _ConstrainedMediaBox(
            aspectRatio: _mediaAspectRatio(item),
            maxPortraitWidth:
                DiscoveryFeedSpacing.homeFeedVideoPortraitMaxWidth,
            child: _HomeFeedVideoCard(
              dto: item,
              isDark: isDark,
              initialize: initialize,
              autoPlay: autoPlay,
              onTap: onTap,
            ),
          ),
        ),
        if (body.isNotEmpty) ...[
          const SizedBox(height: AppSpacing.intraGroupSm),
          KeyedSubtree(
            key: const ValueKey('home-relation-card-body'),
            child: _PostBodyText(text: body, maxLines: 3),
          ),
        ],
        if (intersectionRow != null) ...[
          const SizedBox(height: AppSpacing.intraGroupSm),
          intersectionRow,
        ],
      ],
    );
  }
}

class _HomeArticlePostCard extends StatelessWidget {
  const _HomeArticlePostCard({
    required this.item,
    required this.isDark,
    required this.reason,
    required this.onTap,
    required this.onSpanTap,
    required this.onFallbackTap,
  });

  final ContentPostViewData item;
  final bool isDark;
  final IntersectionReason? reason;
  final VoidCallback onTap;
  final void Function(IntersectionTextSpan span)? onSpanTap;
  final VoidCallback? onFallbackTap;

  @override
  Widget build(BuildContext context) {
    final coverUrl = item.mediaCoverUrl;
    final hasCover = coverUrl.isNotEmpty;
    final useTopImage = hasCover && _articlePrefersTopImage(item);
    final layoutKey = !hasCover
        ? 'home-article-layout-text-only'
        : (useTopImage
              ? 'home-article-layout-top-image'
              : 'home-article-layout-side-image');
    return CupertinoButton(
      key: const ValueKey('home-article-card'),
      padding: EdgeInsets.zero,
      minimumSize: Size.zero,
      onPressed: onTap,
      child: KeyedSubtree(
        key: ValueKey<String>(layoutKey),
        child: !hasCover
            ? _buildTextOnlyLayout()
            : (useTopImage
                  ? _buildTopImageLayout(coverUrl)
                  : _buildSideImageLayout(context, coverUrl)),
      ),
    );
  }

  Widget _buildTextOnlyLayout() {
    return _ArticleTextBlock(
      item: item,
      reason: reason,
      onSpanTap: onSpanTap,
      onFallbackTap: onFallbackTap,
    );
  }

  Widget _buildTopImageLayout(String coverUrl) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _ArticleTextBlock(
          item: item,
          reason: reason,
          onSpanTap: onSpanTap,
          onFallbackTap: onFallbackTap,
        ),
        const SizedBox(height: AppSpacing.intraGroupMd),
        _ArticleThumb(
          url: coverUrl,
          isDark: isDark,
          aspectRatio: DiscoveryFeedSpacing.homeFeedMediaMaxAspectRatio,
        ),
      ],
    );
  }

  Widget _buildSideImageLayout(BuildContext context, String coverUrl) {
    final title = item.normalizedTitle;
    final body = item.articlePreviewText;
    final contextObjectName = title.isNotEmpty ? title : body;
    final contextObjectTarget = IntersectionTarget(
      objectType: 'post',
      objectId: item.id,
      objectKind: 'content',
      routeId: 'workBrowser',
    );
    final intersectionRow = _buildPostIntersectionRow(
      reason: reason,
      contextObjectName: contextObjectName,
      contextObjectTarget: contextObjectTarget,
      onSpanTap: onSpanTap,
      onFallbackTap: onFallbackTap,
      key: const ValueKey('home-article-inline-intersection'),
    );
    return LayoutBuilder(
      builder: (context, constraints) {
        final thumbWidth = min(
          constraints.maxWidth *
              DiscoveryFeedSpacing.homeFeedArticleThumbWidthFactor,
          DiscoveryFeedSpacing.homeFeedArticleSideThumbMaxWidth,
        );
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (title.isNotEmpty) _PostTitle(title: title, maxLines: 1),
            if (body.isNotEmpty) ...[
              if (title.isNotEmpty)
                const SizedBox(height: AppSpacing.intraGroupSm),
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(child: _ArticleBodyPreview(text: body)),
                  const SizedBox(width: AppSpacing.containerSm),
                  SizedBox(
                    key: const ValueKey('home-article-side-thumb'),
                    width: thumbWidth,
                    child: AspectRatio(
                      aspectRatio: DiscoveryFeedSpacing
                          .homeFeedArticleSideThumbAspectRatio,
                      child: _ArticleCoverImage(url: coverUrl, isDark: isDark),
                    ),
                  ),
                ],
              ),
            ] else ...[
              if (title.isNotEmpty)
                const SizedBox(height: AppSpacing.intraGroupSm),
              Align(
                alignment: Alignment.centerRight,
                child: SizedBox(
                  key: const ValueKey('home-article-side-thumb'),
                  width: thumbWidth,
                  child: AspectRatio(
                    aspectRatio: DiscoveryFeedSpacing
                        .homeFeedArticleSideThumbAspectRatio,
                    child: _ArticleCoverImage(url: coverUrl, isDark: isDark),
                  ),
                ),
              ),
            ],
            if (intersectionRow != null) ...[
              if (title.isNotEmpty || body.isNotEmpty)
                const SizedBox(height: AppSpacing.intraGroupSm),
              intersectionRow,
            ],
          ],
        );
      },
    );
  }

  bool _articlePrefersTopImage(ContentPostViewData item) {
    return item.articlePreviewText.length >=
        DiscoveryFeedSpacing.homeFeedArticleTopImageTextLength;
  }
}

class _ArticleTextBlock extends StatelessWidget {
  const _ArticleTextBlock({
    required this.item,
    required this.reason,
    required this.onSpanTap,
    required this.onFallbackTap,
  });

  final ContentPostViewData item;
  final IntersectionReason? reason;
  final void Function(IntersectionTextSpan span)? onSpanTap;
  final VoidCallback? onFallbackTap;

  @override
  Widget build(BuildContext context) {
    final title = item.normalizedTitle;
    final body = item.articlePreviewText;
    final contextObjectName = title.isNotEmpty ? title : body;
    final contextObjectTarget = IntersectionTarget(
      objectType: 'post',
      objectId: item.id,
      objectKind: 'content',
      routeId: 'workBrowser',
    );
    final intersectionRow = _buildPostIntersectionRow(
      reason: reason,
      contextObjectName: contextObjectName,
      contextObjectTarget: contextObjectTarget,
      onSpanTap: onSpanTap,
      onFallbackTap: onFallbackTap,
      key: const ValueKey('home-article-inline-intersection'),
    );
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (title.isNotEmpty) _PostTitle(title: title, maxLines: 1),
        if (body.isNotEmpty) ...[
          if (title.isNotEmpty) const SizedBox(height: AppSpacing.intraGroupSm),
          _ArticleBodyPreview(text: body),
        ],
        if (intersectionRow != null) ...[
          if (title.isNotEmpty || body.isNotEmpty)
            const SizedBox(height: AppSpacing.intraGroupSm),
          intersectionRow,
        ],
      ],
    );
  }
}

class _ArticleBodyPreview extends StatelessWidget {
  const _ArticleBodyPreview({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    final style = _articleSummaryTextStyle(context);
    return LayoutBuilder(
      builder: (context, constraints) {
        final painter = TextPainter(
          text: TextSpan(text: text, style: style),
          maxLines: 3,
          textDirection: TextDirection.ltr,
        )..layout(maxWidth: constraints.maxWidth);
        final overflowed = painter.didExceedMaxLines;
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              text,
              maxLines: 3,
              overflow: TextOverflow.ellipsis,
              style: style,
            ),
            if (overflowed) ...[
              const SizedBox(height: AppSpacing.intraGroupXs),
              Text(
                key: const ValueKey('home-article-full-text'),
                '${CommunityText.ellipsis}${CommunityText.fullText}',
                style: TextStyle(
                  fontSize: AppTypography.iosFootnote,
                  color: AppColors.iosAccent(context),
                  fontWeight: AppTypography.medium,
                ),
              ),
            ],
          ],
        );
      },
    );
  }
}

class _PostTitle extends StatelessWidget {
  const _PostTitle({required this.title, this.maxLines = 2});

  final String title;
  final int maxLines;

  @override
  Widget build(BuildContext context) {
    return Text(
      key: const ValueKey('home-post-title'),
      title,
      maxLines: maxLines,
      overflow: TextOverflow.ellipsis,
      style: TextStyle(
        fontSize: AppTypography.iosSubheadline,
        fontWeight: AppTypography.medium,
        color: AppColors.iosLabel(context),
        height: AppSpacing.textLineHeightBody,
        letterSpacing: -0.18,
      ),
    );
  }
}

class _PostBodyText extends StatelessWidget {
  const _PostBodyText({required this.text, required this.maxLines});

  final String text;
  final int maxLines;

  @override
  Widget build(BuildContext context) {
    return Text(
      text,
      maxLines: maxLines,
      overflow: TextOverflow.ellipsis,
      style: _postBodyTextStyle(context),
    );
  }
}

class _ConstrainedMediaBox extends StatelessWidget {
  const _ConstrainedMediaBox({
    required this.aspectRatio,
    required this.child,
    this.fullWidth = false,
    this.maxPortraitWidth,
    this.widthFactor,
  });

  final double aspectRatio;
  final Widget child;
  final bool fullWidth;
  final double? maxPortraitWidth;
  final double? widthFactor;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final available = constraints.maxWidth;
        final isLandscape = aspectRatio > AppSpacing.one;
        final portraitWidthFactor = AppSpacing.responsiveWideValue(
          context,
          compact: DiscoveryFeedSpacing.homeFeedMediaPortraitWidthFactor,
          regular: DiscoveryFeedSpacing.homeFeedMediaPortraitWidthFactor,
          expanded: DiscoveryFeedSpacing.homeFeedMediaPortraitWideWidthFactor,
          wide: DiscoveryFeedSpacing.homeFeedMediaPortraitWideWidthFactor,
        );
        final explicitWidthFactor = widthFactor;
        final preferredWidth = explicitWidthFactor != null
            ? available * explicitWidthFactor.clamp(0.0, 1.0)
            : fullWidth || isLandscape
            ? available
            : available * portraitWidthFactor;
        final portraitMax = maxPortraitWidth;
        final mediaWidth = !isLandscape && portraitMax != null
            ? min(preferredWidth, portraitMax)
            : preferredWidth;
        final maxHeight =
            MediaQuery.sizeOf(context).height *
            DiscoveryFeedSpacing.homeFeedMediaPortraitMaxHeightFactor;
        final height = (mediaWidth / aspectRatio).clamp(0.0, maxHeight);
        return Align(
          alignment: explicitWidthFactor == null && (fullWidth || isLandscape)
              ? Alignment.center
              : Alignment.centerLeft,
          child: SizedBox(width: mediaWidth, height: height, child: child),
        );
      },
    );
  }
}

class _ArticleThumb extends StatelessWidget {
  const _ArticleThumb({
    required this.url,
    required this.isDark,
    this.aspectRatio,
  });

  final String url;
  final bool isDark;
  final double? aspectRatio;

  @override
  Widget build(BuildContext context) {
    return AspectRatio(
      aspectRatio: aspectRatio ?? AppSpacing.one,
      child: _ArticleCoverImage(url: url, isDark: isDark),
    );
  }
}

class _ArticleCoverImage extends ConsumerWidget {
  const _ArticleCoverImage({required this.url, required this.isDark});

  final String url;
  final bool isDark;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(
        DiscoveryFeedSpacing.homeFeedMediaCornerRadius,
      ),
      child: AppCachedNetworkImage(
        imageUrl: url,
        imageUrlCandidates: resolveContentMediaUrlCandidates(
          url,
          endpointConfig: ref.watch(mediaEndpointConfigProvider),
        ),
        cdnPreset: CdnImagePreset.cover,
        fit: BoxFit.cover,
        placeholder: _mediaPlaceholder(isDark),
        // 失败态走 AppCachedNetworkImage 显式失败件，与加载占位可区分。
      ),
    );
  }
}

TextStyle _postBodyTextStyle(BuildContext context) {
  return TextStyle(
    fontSize: AppTypography.feedBodyResponsive(context),
    color: AppColors.iosLabel(context),
    height: AppSpacing.textLineHeightBody,
    letterSpacing: -0.12,
  );
}

TextStyle _articleSummaryTextStyle(BuildContext context) {
  return TextStyle(
    fontSize: AppTypography.feedBodyResponsive(context),
    color: AppColors.iosLabel(context),
    fontWeight: FontWeight.normal,
    height: AppSpacing.textLineHeightBody,
    letterSpacing: -0.08,
  );
}

double _mediaAspectRatio(ContentPostViewData item) {
  return clampDisplayAspectRatioValue(
    item.aspectRatio,
    fallback: item.hasVideo
        ? kDisplayVideoFallbackAspectRatio
        : kDisplayFallbackAspectRatio,
  );
}

bool _isMomentGridPost(ContentPostViewData item) {
  return item.identity == 'moment' && item.mediaImageUrls.isNotEmpty;
}

int _momentGridVisibleCount(int total) {
  if (total <= 0) return 0;
  if (total <= 2) return total;
  if (total == 4) return total;
  if (total == 5) return 3;
  if (total <= 8) return total.clamp(1, 6).toInt();
  return total.clamp(1, 9).toInt();
}

int _momentGridColumns(int visibleCount) {
  if (visibleCount <= 1) return 1;
  if (visibleCount == 2) return 2;
  if (visibleCount == 4) return 2;
  return 3;
}

double _momentGridAspectRatio(int total) {
  final visibleCount = _momentGridVisibleCount(total);
  final columns = _momentGridColumns(visibleCount);
  final rows = ((visibleCount + columns - 1) ~/ columns).clamp(1, 3).toInt();
  return columns / rows;
}

bool _shouldShowIntersection(
  IntersectionReason? reason, {
  IntersectionTarget? contextObjectTarget,
}) {
  if (reason == null) return false;
  return HomeFeedCrossObjectComposition.displayReadyIntersection(
        reason,
        contextObjectTarget: contextObjectTarget,
      ) !=
      null;
}

Widget _mediaPlaceholder(bool isDark) {
  return DecoratedBox(
    decoration: BoxDecoration(
      color: AppColorsFunctional.getColor(isDark, ColorType.surfaceMuted),
    ),
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// 可展开文字
// ─────────────────────────────────────────────────────────────────────────────

class _ExpandableText extends StatelessWidget {
  const _ExpandableText({
    required this.text,
    required this.maxLines,
    required this.isDark,
    required this.expanded,
    required this.onToggle,
  });

  final String text;
  final int maxLines;
  final bool isDark;
  final bool expanded;
  final VoidCallback onToggle;

  @override
  Widget build(BuildContext context) {
    final fg = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final textStyle = TextStyle(
      fontSize: AppTypography.feedBodyResponsive(context),
      color: fg,
      height: AppSpacing.textLineHeightBodyRelaxed,
      letterSpacing: -0.18,
    );

    return LayoutBuilder(
      builder: (context, constraints) {
        final tp = TextPainter(
          text: TextSpan(text: text, style: textStyle),
          maxLines: maxLines,
          textDirection: TextDirection.ltr,
        )..layout(maxWidth: constraints.maxWidth);
        final isOverflow = tp.didExceedMaxLines;

        if (!isOverflow) {
          return Text(text, style: textStyle);
        }

        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              text,
              style: textStyle,
              maxLines: expanded ? null : maxLines,
              overflow: expanded ? null : TextOverflow.ellipsis,
            ),
            SizedBox(height: AppSpacing.intraGroupXs),
            CupertinoButton(
              padding: EdgeInsets.zero,
              minimumSize: Size.zero,
              onPressed: onToggle,
              child: Text(
                expanded ? CommunityText.collapse : CommunityText.fullText,
                style: TextStyle(
                  fontSize: AppTypography.iosFootnote,
                  color: AppColors.iosAccent(context),
                  fontWeight: AppTypography.semiBold,
                ),
              ),
            ),
          ],
        );
      },
    );
  }
}
