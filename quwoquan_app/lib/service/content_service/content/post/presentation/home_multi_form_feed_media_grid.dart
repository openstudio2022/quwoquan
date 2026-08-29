// ignore_for_file: unnecessary_non_null_assertion
part of 'home_multi_form_feed.dart';

const double _feedMediaGap = AppSpacing.xs;

/// 首页视频卡的播放器装配。
///
/// 公开路与私有短签路只在取址来源上不同，播放 chrome、埋点与失败上报必须
/// 完全一致；两处各写一遍会让两路观感与观测悄悄漂移。
Widget _homeFeedVideoPlayer({
  required ContentPostViewData dto,
  required MediaDeliveryBinding coverBinding,
  required bool initialize,
  required bool autoPlay,
  required bool sharedTimelineEnabled,
  required VoidCallback? onTap,
  required FeedPerformanceObservability performanceObservability,
  required ContentBehaviorTrackerPort behaviorTracker,
  MediaDeliveryReference? deliveryReference,
  MediaDeliveryReference? adaptiveReference,
  SignedVideoDelivery? signedDelivery,
}) {
  return HomeFeedCrossObjectComposition.videoPlayer(
    key: ValueKey<String>('home-video-player-${dto.id}'),
    deliveryReference: deliveryReference,
    signedDelivery: signedDelivery,
    adaptiveDeliveryReference: adaptiveReference,
    adaptiveDescriptorVersion: dto.hlsCmafDescriptorVersion ?? 0,
    thumbnailBinding: coverBinding,
    initialize: initialize,
    autoPlay: autoPlay,
    inlineOverlay: sharedTimelineEnabled,
    verifiedDuration: dto.durationMs == null
        ? null
        : Duration(milliseconds: dto.durationMs!),
    aspectRatio: _mediaAspectRatio(dto),
    onTap: onTap,
    onPlaybackStarted: (startupLatency, candidateIndex) {
      performanceObservability.recordVideoPlaybackStarted(
        contentId: dto.id,
        startupMs: startupLatency.inMilliseconds,
        candidateIndex: candidateIndex,
        autoPlay: autoPlay,
      );
    },
    onEffectivePlayback: (evidence) {
      behaviorTracker.trackEffectivePlayback(
        dto.id,
        playbackSessionId: evidence.playbackSessionId,
        effectivePlayMs: evidence.effectivePlayMs,
        consumedRatio: evidence.consumedRatio,
        totalUnits: evidence.totalUnits,
        contentType: 'video',
        referralSource: ReferralSource.organicFeed,
      );
    },
    onPlaybackFailed: (failure) {
      performanceObservability.recordVideoPlaybackFailed(
        contentId: dto.id,
        candidatesTried: failure.candidatesTried,
        failureKind: failure.kind.name,
        userScene: failure.userScene.name,
        retryable: failure.isRetryable,
        autoPlay: autoPlay,
      );
    },
  );
}

class _HomeFeedMediaOverlayPill extends StatelessWidget {
  const _HomeFeedMediaOverlayPill({super.key, required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.black.withValues(
          alpha: DiscoveryFeedSpacing.homeFeedGridMorePillOpacity,
        ),
        borderRadius: BorderRadius.circular(AppSpacing.radiusNinetyNine),
        border: Border.all(
          color: AppColors.white.withValues(
            alpha: DiscoveryFeedSpacing.homeFeedGridMorePillBorderOpacity,
          ),
          width: AppSpacing.hairline,
        ),
        boxShadow: [
          BoxShadow(
            color: AppColors.black.withValues(
              alpha: DiscoveryFeedSpacing.homeFeedGridMoreScrimBottomOpacity,
            ),
            blurRadius: AppSpacing.xs,
            offset: const Offset(AppSpacing.zero, AppSpacing.one),
          ),
        ],
      ),
      child: ConstrainedBox(
        constraints: const BoxConstraints(
          minHeight: DiscoveryFeedSpacing.homeFeedGridMorePillHeight,
        ),
        child: Padding(
          padding: const EdgeInsets.symmetric(
            horizontal:
                DiscoveryFeedSpacing.homeFeedGridMorePillHorizontalPadding,
          ),
          child: Align(
            widthFactor: AppSpacing.one,
            heightFactor: AppSpacing.one,
            child: Text(
              label,
              style: TextStyle(
                fontSize: AppTypography.iosFootnote,
                fontWeight: AppTypography.semiBold,
                color: AppColors.white,
                height: AppSpacing.one,
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _HomeMomentGridCard extends StatelessWidget {
  const _HomeMomentGridCard({
    required this.urls,
    required this.deliveryIndex,
    required this.isDark,
    required this.onTap,
  });

  final List<String> urls;

  /// URL → 交付绑定（DEC-033）：tile 按 typed 声明分流 signedGrant 资产。
  final Map<String, _FeedImageDelivery> deliveryIndex;
  final bool isDark;
  final void Function(int index) onTap;

  @override
  Widget build(BuildContext context) {
    final visibleCount = _momentGridVisibleCount(urls.length);
    final columns = _momentGridColumns(visibleCount);
    final rows = ((visibleCount + columns - 1) ~/ columns).clamp(1, 3).toInt();
    final remaining = urls.length - visibleCount;
    return ClipRRect(
      key: const ValueKey('home-moment-grid'),
      borderRadius: BorderRadius.circular(
        DiscoveryFeedSpacing.homeFeedMediaCornerRadius,
      ),
      child: LayoutBuilder(
        builder: (context, constraints) {
          if (!constraints.hasBoundedWidth ||
              !constraints.hasBoundedHeight ||
              visibleCount <= 0) {
            return const SizedBox.shrink();
          }
          final tileWidth =
              ((constraints.maxWidth - _feedMediaGap * (columns - 1)) / columns)
                  .clamp(AppSpacing.zero, double.infinity)
                  .toDouble();
          final tileHeight =
              ((constraints.maxHeight - _feedMediaGap * (rows - 1)) / rows)
                  .clamp(AppSpacing.zero, double.infinity)
                  .toDouble();
          return Stack(
            fit: StackFit.expand,
            children: [
              for (var index = 0; index < visibleCount; index++)
                Positioned(
                  left: (index % columns) * (tileWidth + _feedMediaGap),
                  top: (index ~/ columns) * (tileHeight + _feedMediaGap),
                  width: tileWidth,
                  height: tileHeight,
                  child: _HomeMomentGridTile(
                    tileKey: ValueKey<String>('home-moment-grid-tile-$index'),
                    url: urls[index],
                    delivery: deliveryIndex[urls[index].trim()],
                    isDark: isDark,
                    showMore: remaining > 0 && index == visibleCount - 1,
                    remaining: remaining,
                    onTap: () => onTap(index),
                  ),
                ),
            ],
          );
        },
      ),
    );
  }
}

class _HomeMomentGridTile extends ConsumerWidget {
  const _HomeMomentGridTile({
    required this.tileKey,
    required this.url,
    required this.delivery,
    required this.isDark,
    required this.showMore,
    required this.remaining,
    required this.onTap,
  });

  final Key tileKey;
  final String url;
  final _FeedImageDelivery? delivery;
  final bool isDark;
  final bool showMore;
  final int remaining;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final signedDelivery = delivery;
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: Stack(
        key: tileKey,
        fit: StackFit.expand,
        children: [
          _feedDeliveryImage(
            binding: _feedBinding(url, signedDelivery),
            isDark: isDark,
            endpointConfig: ref.watch(mediaEndpointConfigProvider),
            cdnPreset: CdnImagePreset.thumbnail,
          ),
          if (showMore)
            Positioned.fill(
              child: DecoratedBox(
                key: const ValueKey('home-moment-grid-more-scrim'),
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    begin: Alignment.topCenter,
                    end: Alignment.bottomCenter,
                    colors: [
                      AppColors.black.withValues(
                        alpha: DiscoveryFeedSpacing
                            .homeFeedGridMoreScrimTopOpacity,
                      ),
                      AppColors.black.withValues(
                        alpha: DiscoveryFeedSpacing
                            .homeFeedGridMoreScrimBottomOpacity,
                      ),
                    ],
                  ),
                ),
              ),
            ),
          if (showMore)
            Positioned(
              top: AppSpacing.intraGroupSm,
              right: AppSpacing.intraGroupSm,
              child: _HomeFeedMediaOverlayPill(
                key: const ValueKey('home-moment-grid-more'),
                label: '+$remaining',
              ),
            ),
        ],
      ),
    );
  }
}

class _HomeFeedImageCarousel extends ConsumerStatefulWidget {
  const _HomeFeedImageCarousel({
    required this.urls,
    required this.deliveryIndex,
    required this.isDark,
    required this.onTap,
    required this.aspectRatio,
  });

  final List<String> urls;

  /// URL → 交付绑定（DEC-033）：逐页按 typed 声明分流 signedGrant 资产。
  final Map<String, _FeedImageDelivery> deliveryIndex;
  final bool isDark;
  final void Function(int index) onTap;
  final double aspectRatio;

  @override
  ConsumerState<_HomeFeedImageCarousel> createState() =>
      _HomeFeedImageCarouselState();
}

class _HomeFeedImageCarouselState
    extends ConsumerState<_HomeFeedImageCarousel> {
  late final PageController _controller;
  int _index = 0;

  @override
  void initState() {
    super.initState();
    _controller = PageController();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final urls = widget.urls
        .map((url) => url.trim())
        .where((url) => url.isNotEmpty)
        .toList(growable: false);
    if (urls.isEmpty) return const SizedBox.shrink();

    return AspectRatio(
      aspectRatio: widget.aspectRatio,
      child: ClipRRect(
        borderRadius: BorderRadius.circular(
          DiscoveryFeedSpacing.homeFeedMediaCornerRadius,
        ),
        child: Stack(
          fit: StackFit.expand,
          children: [
            PageView.builder(
              controller: _controller,
              itemCount: urls.length,
              onPageChanged: (next) => setState(() => _index = next),
              itemBuilder: (context, index) {
                final delivery = widget.deliveryIndex[urls[index]];
                return GestureDetector(
                  behavior: HitTestBehavior.opaque,
                  onTap: () => widget.onTap(index),
                  // DEC-033：signedGrant 资产分流到私有媒体桥接原子，
                  // 公开资产维持既有路径不变。
                  child: _feedDeliveryImage(
                    binding: _feedBinding(urls[index], delivery),
                    isDark: widget.isDark,
                    endpointConfig: ref.watch(mediaEndpointConfigProvider),
                    placeholder: _placeholder(),
                  ),
                );
              },
            ),
            if (urls.length > 1) ...[
              Positioned(
                top: AppSpacing.intraGroupSm,
                right: AppSpacing.intraGroupSm,
                child: _HomeFeedMediaOverlayPill(
                  key: const ValueKey('home-image-carousel-counter'),
                  label: '${_index + 1}/${urls.length}',
                ),
              ),
              Positioned(
                left: 0,
                right: 0,
                bottom: AppSpacing.intraGroupSm,
                child: _CarouselDots(
                  total: urls.length,
                  activeIndex: _index,
                  isDark: widget.isDark,
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _placeholder() {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColorsFunctional.getColor(
          widget.isDark,
          ColorType.surfaceMuted,
        ),
      ),
    );
  }
}

class _CarouselDots extends StatelessWidget {
  const _CarouselDots({
    required this.total,
    required this.activeIndex,
    required this.isDark,
  });

  final int total;
  final int activeIndex;
  final bool isDark;

  @override
  Widget build(BuildContext context) {
    final visibleTotal = total.clamp(1, 6).toInt();
    final active = total <= visibleTotal
        ? activeIndex
        : ((activeIndex / (total - 1)) * (visibleTotal - 1)).round();
    final dotColor = AppColorsFunctional.getColor(
      isDark,
      ColorType.mediaThumbnailOverlayForeground,
    );
    final surfaceColor = AppColorsFunctional.getColor(
      isDark,
      ColorType.mediaThumbnailOverlayScrim,
    ).withValues(alpha: 0.08);
    final borderColor = AppColorsFunctional.getColor(
      isDark,
      ColorType.mediaThumbnailOverlayBorder,
    ).withValues(alpha: 0.06);
    return Center(
      child: ClipRRect(
        key: const ValueKey('home-image-carousel-dots'),
        borderRadius: BorderRadius.circular(AppSpacing.radiusNinetyNine),
        child: BackdropFilter(
          filter: ImageFilter.blur(
            sigmaX: DiscoveryFeedSpacing.homeFeedCarouselDotsBackdropBlur,
            sigmaY: DiscoveryFeedSpacing.homeFeedCarouselDotsBackdropBlur,
          ),
          child: DecoratedBox(
            decoration: BoxDecoration(
              color: surfaceColor,
              borderRadius: BorderRadius.circular(AppSpacing.radiusNinetyNine),
              border: Border.all(
                color: borderColor,
                width: AppSpacing.hairline,
              ),
            ),
            child: Padding(
              padding: const EdgeInsets.symmetric(
                horizontal: AppSpacing.intraGroupSm,
                vertical: AppSpacing.xs,
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  for (var i = 0; i < visibleTotal; i++) ...[
                    if (i > 0) const SizedBox(width: AppSpacing.xs),
                    AnimatedContainer(
                      key: ValueKey<String>('home-image-carousel-dot-$i'),
                      duration: const Duration(milliseconds: 160),
                      width: AppSpacing.xs + AppSpacing.hairline,
                      height: AppSpacing.xs + AppSpacing.hairline,
                      decoration: BoxDecoration(
                        color: dotColor.withValues(
                          alpha: i == active ? 0.94 : 0.38,
                        ),
                        shape: BoxShape.circle,
                      ),
                    ),
                  ],
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// 视频卡片（静态封面 + 时长 + 播放标识）
// ─────────────────────────────────────────────────────────────────────────────

class _HomeFeedVideoCard extends ConsumerWidget {
  const _HomeFeedVideoCard({
    required this.dto,
    required this.isDark,
    required this.initialize,
    required this.autoPlay,
    required this.onTap,
  });

  final ContentPostViewData dto;
  final bool isDark;
  final bool initialize;
  final bool autoPlay;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    // 这些回调可能在播放器子树 dispose 时才执行。此时 ConsumerElement 已经
    // deactivate，不能再经 WidgetRef 查 Provider；在活跃 build 帧捕获 typed
    // port，既保持当前 actor epoch，也保证控制器释放不会因 Ref 生命周期中断。
    final behaviorTracker = ref.watch(contentBehaviorTrackerProvider);
    final performanceObservability = ref.watch(
      feedPerformanceObservabilityProvider,
    );
    final surfaceMuted = AppColorsFunctional.getColor(
      isDark,
      ColorType.surfaceMuted,
    );
    final sharedTimelineEnabled = ref.watch(
      contentFeatureFlagProvider('enable_shared_video_timeline'),
    );
    final endpointConfig = ref.watch(mediaEndpointConfigProvider);
    final resolver = endpointConfig == null
        ? null
        : MediaDeliveryResolver(endpointConfig);
    final mediaAssetId = dto.mediaAssetId?.trim() ?? '';
    final mediaAssetVersion = dto.mediaAssetVersion ?? 0;
    // 视频本体的交付声明取自投影 mediaItems 的同一条目。私有视频走短签渐进式
    // MP4：分段 Range 由原生播放器发起、交付边缘按段复算签名，因此单签 URL 即可
    // 播放。绝不按公开地址播放私有资产——那会把授权判定悄悄跳过。
    final videoDelivery = _feedImageDeliveryIndex(dto)[dto.mediaVideoUrl.trim()];
    final videoBinding = MediaDeliveryBinding(
      assetId: videoDelivery?.assetId ?? mediaAssetId,
      accessMode: videoDelivery?.accessMode,
      publicUrl: dto.mediaVideoUrl,
    );
    final adaptiveReference = mediaAssetId.isEmpty || mediaAssetVersion <= 0
        ? null
        : resolver?.tryResolve(
            dto.hlsCmafMasterManifestUrl,
            kind: MediaDeliveryKind.video,
            assetId: mediaAssetId,
            version: mediaAssetVersion,
          );
    final coverRaw = dto.mediaVideoCoverUrl.isNotEmpty
        ? dto.mediaVideoCoverUrl
        : dto.primaryVisualUrl;
    // 封面的 typed 交付绑定取自投影 mediaItems 的逐媒体声明（含 coverAssetId 与
    // accessMode），不以 dto.id 冒充媒体资产标识。索引缺该 URL 即契约未声明，
    // 显式落公开路。
    final coverDelivery = _feedImageDeliveryIndex(dto)[coverRaw.trim()];
    final coverBinding = MediaDeliveryBinding(
      assetId: coverDelivery?.assetId ?? '',
      accessMode: coverDelivery?.accessMode,
      publicUrl: coverRaw,
    );
    return GestureDetector(
      onTap: onTap,
      child: ClipRRect(
        borderRadius: BorderRadius.circular(
          DiscoveryFeedSpacing.homeFeedMediaCornerRadius,
        ),
        child: Stack(
          fit: StackFit.expand,
          children: [
            DecoratedBox(decoration: BoxDecoration(color: surfaceMuted)),
            if (videoBinding.hasRenderableSource)
              mediaDeliveryVideo(
                binding: videoBinding,
                placeholder: coverBinding.hasRenderableSource
                    ? _feedDeliveryImage(
                        binding: coverBinding,
                        isDark: isDark,
                        endpointConfig: endpointConfig,
                      )
                    : null,
                absentWidget: coverBinding.hasRenderableSource
                    ? _feedDeliveryImage(
                        binding: coverBinding,
                        isDark: isDark,
                        endpointConfig: endpointConfig,
                      )
                    : null,
                publicBuilder: (context, publicUrl) {
                  final videoReference = resolver?.tryResolve(
                    publicUrl,
                    kind: MediaDeliveryKind.video,
                    // 资产身份缺席就传空：以 post 标识冒充媒体资产标识会让缓存与
                    // 埋点按错误身份归并，封面侧已锁定禁止，视频侧同禁。
                    assetId: mediaAssetId,
                    version: mediaAssetVersion,
                  );
                  if (videoReference == null) {
                    return coverBinding.hasRenderableSource
                        // 同一封面在播放态由 typed 绑定交付，静态态若改回裸 URL，
                        // 私有封面就会在未播放时空图——两态必须同源。
                        ? _feedDeliveryImage(
                            binding: coverBinding,
                            isDark: isDark,
                            endpointConfig: endpointConfig,
                          )
                        : const SizedBox.shrink();
                  }
                  return _homeFeedVideoPlayer(
                    dto: dto,
                    deliveryReference: videoReference,
                    adaptiveReference: adaptiveReference,
                    coverBinding: coverBinding,
                    initialize: initialize,
                    autoPlay: autoPlay,
                    sharedTimelineEnabled: sharedTimelineEnabled,
                    onTap: onTap,
                    performanceObservability: performanceObservability,
                    behaviorTracker: behaviorTracker,
                  );
                },
                signedBuilder: (context, signedDelivery) => _homeFeedVideoPlayer(
                  dto: dto,
                  signedDelivery: signedDelivery,
                  coverBinding: coverBinding,
                  initialize: initialize,
                  autoPlay: autoPlay,
                  sharedTimelineEnabled: sharedTimelineEnabled,
                  onTap: onTap,
                  performanceObservability: performanceObservability,
                  behaviorTracker: behaviorTracker,
                ),
              )
            else if (coverBinding.hasRenderableSource)
              _feedDeliveryImage(
                binding: coverBinding,
                isDark: isDark,
                endpointConfig: endpointConfig,
              ),
            // 中央播放标识只属于完全未初始化的静态封面态；预热/初始化后由
            // VideoPlayerWidget 自己呈现加载或画面，避免长按时叠出两个播放按钮。
            // 与沉浸暂停态共用无背景圆角三角，避免 tip 角与圆形底造成两套视觉语言。
            if (!initialize && !autoPlay)
              Center(
                child: KeyedSubtree(
                  key: ValueKey<String>('home-video-focus-paused-${dto.id}'),
                  child: HomeFeedCrossObjectComposition.videoCenterPlayGlyph(),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
/// Action row for moment (微趣) posts.
/// 赞 / 转 / 评三列等宽，数字变化不挤压图标位置。
