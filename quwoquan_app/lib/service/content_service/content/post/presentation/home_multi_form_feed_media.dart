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
    final deliveryIndex = _feedImageDeliveryIndex(item);
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
        child: _HomeMomentGridCard(
          urls: urls,
          deliveryIndex: deliveryIndex,
          isDark: isDark,
          onTap: onTap,
        ),
      );
    }
    if (urls.length > 1) {
      return _ConstrainedMediaBox(
        aspectRatio: _mediaAspectRatio(item),
        fullWidth: true,
        child: _HomeFeedImageCarousel(
          urls: urls,
          deliveryIndex: deliveryIndex,
          isDark: isDark,
          onTap: onTap,
          aspectRatio: _mediaAspectRatio(item),
        ),
      );
    }
    final url = item.primaryVisualUrl;
    if (url.isEmpty) return null;
    final delivery = deliveryIndex[url];
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
          // DEC-033：signedGrant 资产分流到私有媒体桥接原子，公开资产
          // 维持既有公开候选路径完全不变。
          child: _feedDeliveryImage(
            binding: _feedBinding(url, delivery),
            isDark: isDark,
            endpointConfig: endpointConfig,
          ),
        ),
      ),
    );
  }
}

/// feed 图片渲染点的私有媒体交付绑定（DEC-033）。
///
/// 只承载 typed 声明分流所需的两字段；绑定与 URL 的关联由投影
/// `mediaItems` 提供，App 不从 URL 形态推断交付形态。缺席保持 contract failure。
class _FeedImageDelivery {
  const _FeedImageDelivery({required this.assetId, required this.accessMode});

  final String assetId;
  final MediaDeliveryAccessMode? accessMode;

  bool get isSignedGrant =>
      accessMode == MediaDeliveryAccessMode.signedGrant && assetId.isNotEmpty;
}

/// 从投影 `mediaItems` 建立「渲染 URL → 交付绑定」查找表：
/// 逐条媒体 url→(mediaAssetId, accessMode)，封面 coverUrl→(coverAssetId,
/// accessMode)。契约缺席 accessMode 保持 fail closed；legacy public 必须由已确认
/// contract version 的具名 adapter 进入。
Map<String, _FeedImageDelivery> _feedImageDeliveryIndex(
  ContentPostViewData item,
) {
  final index = <String, _FeedImageDelivery>{};
  for (final media in item.mediaItems) {
    final url = media.url.trim();
    if (url.isNotEmpty) {
      index[url] = _FeedImageDelivery(
        assetId: media.mediaAssetId?.trim() ?? '',
        accessMode: media.accessMode,
      );
    }
    final coverUrl = media.coverUrl?.trim() ?? '';
    if (coverUrl.isNotEmpty) {
      index[coverUrl] = _FeedImageDelivery(
        assetId: media.coverAssetId?.trim() ?? '',
        accessMode: media.accessMode,
      );
    }
  }
  return index;
}

/// signedGrant feed 图与封面的统一桥接调用（kind 固定 image；头像面另走 avatar）。
/// 首页信息流媒体的 typed 交付原子（DEC-033）。
///
/// 公开与私有两路都从这里出去：消费点只交出绑定，不再自己判 accessMode。
/// 每个调用点手写一次 `isSignedGrant ? 私有 : 公开`，就等于把「什么算私有」
/// 复制成了第二真相源——新增一处消费点漏判就是一次私有资产泄漏或空图。
Widget _feedDeliveryImage({
  required MediaDeliveryBinding binding,
  required bool isDark,
  required MediaEndpointConfig? endpointConfig,
  BoxFit fit = BoxFit.cover,
  CdnImagePreset cdnPreset = CdnImagePreset.cover,
  Widget? placeholder,
}) {
  final waiting = placeholder ?? _mediaPlaceholder(isDark);
  return mediaDeliveryImage(
    binding: binding,
    kind: MediaDeliveryKind.image,
    fit: fit,
    placeholder: waiting,
    // 失败态必须与加载占位可区分：静默灰块会把「media-edge 缺对象」伪装成
    // 加载中，用户与 UAT 都无法发现，因此公开路沿用原子自带的显式失败件。
    publicBuilder: (context, publicUrl) => AppCachedNetworkImage(
      imageUrl: publicUrl,
      imageUrlCandidates: resolveContentMediaUrlCandidates(
        publicUrl,
        endpointConfig: endpointConfig,
      ),
      cdnPreset: cdnPreset,
      fit: fit,
      placeholder: waiting,
    ),
  );
}

/// 把信息流交付索引项收敛成 typed 绑定；索引缺该 URL 时保持 contract failure，
/// 不在此处替它猜一个 accessMode。
MediaDeliveryBinding _feedBinding(String url, _FeedImageDelivery? delivery) {
  return MediaDeliveryBinding(
    assetId: delivery?.assetId ?? '',
    accessMode: delivery?.accessMode,
    publicUrl: url,
  );
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
    final coverDelivery = _feedImageDeliveryIndex(item)[coverUrl];
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
                  ? _buildTopImageLayout(coverUrl, coverDelivery)
                  : _buildSideImageLayout(context, coverUrl, coverDelivery)),
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

  Widget _buildTopImageLayout(String coverUrl, _FeedImageDelivery? delivery) {
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
          delivery: delivery,
          isDark: isDark,
          aspectRatio: DiscoveryFeedSpacing.homeFeedMediaMaxAspectRatio,
        ),
      ],
    );
  }

  Widget _buildSideImageLayout(
    BuildContext context,
    String coverUrl,
    _FeedImageDelivery? delivery,
  ) {
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
                      child: _ArticleCoverImage(
                        url: coverUrl,
                        delivery: delivery,
                        isDark: isDark,
                      ),
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
                    child: _ArticleCoverImage(
                      url: coverUrl,
                      delivery: delivery,
                      isDark: isDark,
                    ),
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
    this.delivery,
    this.aspectRatio,
  });

  final String url;
  final bool isDark;
  final _FeedImageDelivery? delivery;
  final double? aspectRatio;

  @override
  Widget build(BuildContext context) {
    return AspectRatio(
      aspectRatio: aspectRatio ?? AppSpacing.one,
      child: _ArticleCoverImage(url: url, delivery: delivery, isDark: isDark),
    );
  }
}

class _ArticleCoverImage extends ConsumerWidget {
  const _ArticleCoverImage({
    required this.url,
    required this.isDark,
    this.delivery,
  });

  final String url;
  final bool isDark;
  final _FeedImageDelivery? delivery;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final signedDelivery = delivery;
    return ClipRRect(
      borderRadius: BorderRadius.circular(
        DiscoveryFeedSpacing.homeFeedMediaCornerRadius,
      ),
      // DEC-033：signedGrant 封面分流到私有媒体桥接原子，公开封面不变。
      child: _feedDeliveryImage(
        binding: _feedBinding(url, signedDelivery),
        isDark: isDark,
        endpointConfig: ref.watch(mediaEndpointConfigProvider),
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
