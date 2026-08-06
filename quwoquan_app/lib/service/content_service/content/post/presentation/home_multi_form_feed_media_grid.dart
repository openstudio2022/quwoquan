// ignore_for_file: unnecessary_non_null_assertion
part of 'home_multi_form_feed.dart';

const double _feedMediaGap = AppSpacing.xs;

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
    required this.isDark,
    required this.onTap,
  });

  final List<String> urls;
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
    required this.isDark,
    required this.showMore,
    required this.remaining,
    required this.onTap,
  });

  final Key tileKey;
  final String url;
  final bool isDark;
  final bool showMore;
  final int remaining;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: Stack(
        key: tileKey,
        fit: StackFit.expand,
        children: [
          AppCachedNetworkImage(
            imageUrl: url,
            imageUrlCandidates: resolveContentMediaUrlCandidates(
              url,
              endpointConfig: ref.watch(mediaEndpointConfigProvider),
            ),
            cdnPreset: CdnImagePreset.thumbnail,
            fit: BoxFit.cover,
            placeholder: _mediaPlaceholder(isDark),
            errorWidget: _mediaPlaceholder(isDark),
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
    required this.isDark,
    required this.onTap,
    required this.aspectRatio,
  });

  final List<String> urls;
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
                return GestureDetector(
                  behavior: HitTestBehavior.opaque,
                  onTap: () => widget.onTap(index),
                  child: AppCachedNetworkImage(
                    imageUrl: urls[index],
                    imageUrlCandidates: resolveContentMediaUrlCandidates(
                      urls[index],
                      endpointConfig: ref.watch(mediaEndpointConfigProvider),
                    ),
                    cdnPreset: CdnImagePreset.cover,
                    fit: BoxFit.cover,
                    placeholder: _placeholder(),
                    errorWidget: _placeholder(),
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
    final videoReference = resolver?.tryResolve(
      dto.mediaVideoUrl,
      kind: MediaDeliveryKind.video,
      assetId: mediaAssetId.isEmpty ? dto.id : mediaAssetId,
      version: mediaAssetVersion,
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
    final coverReference = resolver?.tryResolve(
      coverRaw,
      kind: MediaDeliveryKind.image,
      assetId: dto.id,
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
            if (videoReference != null)
              HomeFeedCrossObjectComposition.videoPlayer(
                key: ValueKey<String>('home-video-player-${dto.id}'),
                deliveryReference: videoReference,
                adaptiveDeliveryReference: adaptiveReference,
                adaptiveDescriptorVersion: dto.hlsCmafDescriptorVersion ?? 0,
                thumbnailReference: coverReference,
                initialize: initialize,
                autoPlay: autoPlay,
                inlineOverlay: sharedTimelineEnabled,
                verifiedDuration: dto.durationMs == null
                    ? null
                    : Duration(milliseconds: dto.durationMs!),
                aspectRatio: _mediaAspectRatio(dto),
                onTap: onTap,
                onPlaybackStarted: (startupLatency, candidateIndex) {
                  ref
                      .read(feedPerformanceObservabilityProvider)
                      .recordVideoPlaybackStarted(
                        contentId: dto.id,
                        startupMs: startupLatency.inMilliseconds,
                        candidateIndex: candidateIndex,
                        autoPlay: autoPlay,
                      );
                },
                onEffectivePlayback: (evidence) {
                  ref
                      .read(contentBehaviorTrackerProvider)
                      .trackEffectivePlayback(
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
                  ref
                      .read(feedPerformanceObservabilityProvider)
                      .recordVideoPlaybackFailed(
                        contentId: dto.id,
                        candidatesTried: failure.candidatesTried,
                        failureKind: failure.kind.name,
                        userScene: failure.userScene.name,
                        retryable: failure.isRetryable,
                        autoPlay: autoPlay,
                      );
                },
              )
            else if (dto.primaryVisualUrl.trim().isNotEmpty)
              AppCachedNetworkImage(
                imageUrl: dto.primaryVisualUrl,
                imageUrlCandidates: resolveContentMediaUrlCandidates(
                  dto.primaryVisualUrl,
                  endpointConfig: endpointConfig,
                ),
                cdnPreset: CdnImagePreset.cover,
                fit: BoxFit.cover,
                placeholder: _mediaPlaceholder(isDark),
                errorWidget: _mediaPlaceholder(isDark),
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
