part of 'works_immersive_viewer.dart';

extension _WorksImageStageComposition on _WorksImmersiveViewerState {
  double _landscapeAspectRatioForPost(ContentPostViewData post) {
    if (_isImageLikePost(post)) {
      final ratios = _imageAspectRatiosForPost(post);
      final index = (_photoInnerIndex[post.id] ?? _defaultImageIndexFor(post))
          .clamp(0, max(0, ratios.length - 1))
          .toInt();
      final readiness = _imageReadiness[post.id];
      return (ratios.isEmpty ? null : ratios[index]) ??
          (readiness?.index == index ? readiness?.aspectRatio : null) ??
          0.0;
    }
    if (_isVideoLikePost(post)) {
      final items = _videoItemsFor(post);
      if (items.isEmpty) return 0.0;
      final index = _videoIndexFor(post.id, items).clamp(0, items.length - 1);
      final itemRatio = items[index].aspectRatio;
      return itemRatio > 0
          ? itemRatio
          : (_activeVideoBinding?.session.snapshot.mediaAspectRatio ?? 0.0);
    }
    return 0.0;
  }

  Widget _buildImageStage(BuildContext context, ContentPostViewData post) {
    final ratios = _imageAspectRatiosForPost(post);
    final imageIndex =
        (_photoInnerIndex[post.id] ?? _defaultImageIndexFor(post))
            .clamp(0, max(0, ratios.length - 1))
            .toInt();
    final readiness = _imageReadiness[post.id];
    final ratio =
        (ratios.isEmpty ? null : ratios[imageIndex]) ??
        (readiness?.index == imageIndex ? readiness?.aspectRatio : null);
    final showEntry =
        !_pureMediaLandscape &&
        (ratio ?? 0) > 1 &&
        MediaQuery.sizeOf(context).height > MediaQuery.sizeOf(context).width;
    final reason = _primaryIntersectionReasonFor(post);
    return _WorksImageStage(
      aspectRatio: ratio,
      fullscreen: _pureMediaLandscape,
      topInset:
          widget.topChromeSafeInset + AppSpacing.appChromeTopBarHeight(context),
      toolbarHeight: widget.showWorksToolbar
          ? ImmersiveEngagementBar.reservedHeight(context)
          : 0,
      caption: MediaCaptionBlock(
        layoutSpec: _layoutSpecForPost(post),
        railKey: const ValueKey('works-caption-rail'),
        header: ratios.length > 1
            ? _WorksPageIndicator(total: ratios.length, current: imageIndex + 1)
            : null,
        title: _overlayTitleForPost(post),
        caption: _overlayBodyForPost(post),
        imageCaption: _overlayImageCaptionForPost(post),
        isExpanded: false,
        onToggle: () => _toggleCaptionExpanded(post.id),
        footer: reason == null
            ? null
            : HomeFeedCrossObjectComposition.immersiveIntersectionStatement(
                key: const ValueKey('works-caption-intersection-reason'),
                reason: reason,
                contextObjectName: post.normalizedTitle,
                contextObjectTarget: _postIntersectionContextTarget(post),
                onSpanTap: (_) => _showIntersectionDetail(context, post),
                onFallbackTap: () => _showIntersectionDetail(context, post),
              ),
      ),
      entry: showEntry
          ? _MediaLandscapeButton(
              key: const ValueKey('works-media-landscape-entry'),
              onPressed:
                  readiness?.index == imageIndex && readiness?.isReady == true
                  ? _enterPureMediaLandscape
                  : null,
            )
          : null,
      mediaBuilder: (bottomInset, entryExtent) {
        return ImageBookCanvas(
          deliveries: _imageDeliveriesForPost(post),
          mediaAspectRatios: ratios,
          usePortraitBands: !_pureMediaLandscape,
          mediaTopInset:
              widget.topChromeSafeInset +
              AppSpacing.appChromeTopBarHeight(context),
          mediaBottomInset: bottomInset,
          landscapeEntryExtent: entryExtent,
          interactionEnabled: !_pureMediaLandscape,
          initialIndex:
              _photoInnerIndex[post.id] ?? _defaultImageIndexFor(post),
          gestureIntentController: _gestureIntentController,
          onCurrentMediaStateChanged: _imageReadinessListeners.putIfAbsent(
            post.id,
            () {
              late final ValueChanged<ImageBookCurrentMediaState> listener;
              listener = (state) {
                if (identical(_imageReadinessListeners[post.id], listener)) {
                  _handleImageReadiness(post.id, state);
                }
              };
              return listener;
            },
          ),
          onImageChanged: (index) => _setMountedState(() {
            _rememberPostLocalState(post.id);
            _photoInnerIndex[post.id] = index;
          }),
          onPageflipMotion: (event) => _trackImagePageflipMotion(post, event),
          onMediaLoad: (event) => ref
              .read(pageLifecycleObservabilityProvider)
              .recordMediaLoad(
                mediaType: 'image',
                result: event.result,
                pageName: PageNames.workBrowser,
                surfaceId: AppUiSurfaces.workBrowser.id,
                objectType: 'contentPost',
                objectId: post.id,
                copyKey: event.result == 'failure' ? 'imageLoadFailed' : null,
                error: event.error,
                durationMs: event.durationMs,
                candidatesTried: event.candidatesTried,
              ),
          onOverflowPrevious: null,
          onOverflowNext: null,
        );
      },
    );
  }
}

/// 媒体与文字在同一次布局中测量并定位，不再以碰撞后隐藏补偿布局。
class _WorksVideoBottomChrome extends StatefulWidget {
  const _WorksVideoBottomChrome({
    super.key,
    required this.layoutSpec,
    required this.media,
    required this.isActive,
    required this.aspectRatio,
    required this.topInset,
    required this.toolbarHeight,
    required this.intersection,
    this.association,
    required this.title,
    required this.caption,
    required this.sourceAttribution,
    required this.isExpanded,
    required this.onToggleCaption,
    required this.session,
    required this.sharedTimelineEnabled,
    required this.previewTrackDescriptor,
    required this.previewTrackQuery,
    required this.episodeCurrent,
    required this.episodeTotal,
    required this.onEnterLandscape,
    required this.pureMediaMode,
    required this.controlsVisible,
  });

  final ImmersiveViewerStageLayoutSpec layoutSpec;
  final Widget media;
  final bool isActive;
  final double aspectRatio;
  final double topInset;
  final double toolbarHeight;
  final Widget? intersection;
  final Widget? association;
  final String title;
  final String caption;
  final PublicSourceAttribution? sourceAttribution;
  final bool isExpanded;
  final VoidCallback onToggleCaption;
  final VideoPlaybackSession session;
  final bool sharedTimelineEnabled;
  final VideoPreviewTrackDescriptor? previewTrackDescriptor;
  final VideoPreviewTrackQuery previewTrackQuery;
  final int episodeCurrent;
  final int episodeTotal;
  final VoidCallback? onEnterLandscape;
  final bool pureMediaMode;
  final bool controlsVisible;

  @override
  State<_WorksVideoBottomChrome> createState() =>
      _WorksVideoBottomChromeState();
}

class _WorksVideoBottomChromeState extends State<_WorksVideoBottomChrome> {
  final _layoutRevision = ValueNotifier<int>(0);
  bool _scheduled = false;
  @override
  void initState() {
    super.initState();
    widget.session.addListener(_sessionChanged);
  }

  void _sessionChanged() {
    if (_scheduled) return;
    _scheduled = true;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _scheduled = false;
      if (mounted) _layoutRevision.value++;
    });
    WidgetsBinding.instance.ensureVisualUpdate();
  }

  @override
  void didUpdateWidget(covariant _WorksVideoBottomChrome oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (!identical(oldWidget.session, widget.session)) {
      oldWidget.session.removeListener(_sessionChanged);
      widget.session.addListener(_sessionChanged);
    }
  }

  @override
  void dispose() {
    widget.session.removeListener(_sessionChanged);
    _layoutRevision.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final session = widget.session;
    final layoutSpec = widget.layoutSpec;
    final topInset = widget.topInset;
    final toolbarHeight = widget.toolbarHeight;
    final media = widget.media;
    final isActive = widget.isActive;
    final title = widget.title;
    final caption = widget.caption;
    final intersection = widget.intersection;
    final isExpanded = widget.isExpanded;
    final onToggleCaption = widget.onToggleCaption;
    final episodeTotal = widget.episodeTotal;
    final episodeCurrent = widget.episodeCurrent;
    final previewTrackDescriptor = widget.previewTrackDescriptor;
    final previewTrackQuery = widget.previewTrackQuery;
    final sharedTimelineEnabled = widget.sharedTimelineEnabled;
    final attribution = widget.sourceAttribution?.attributionText.trim() ?? '';
    return AnimatedBuilder(
      animation: _layoutRevision,
      builder: (context, _) {
        final snapshot = session.snapshot;
        final aspectRatio = widget.aspectRatio > 0
            ? widget.aspectRatio
            : (snapshot.mediaAspectRatio ?? 0);
        final showEntry =
            !widget.pureMediaMode &&
            widget.onEnterLandscape != null &&
            aspectRatio > 1;
        return CustomMultiChildLayout(
          delegate: _WorksVideoLayoutDelegate(
            aspectRatio: aspectRatio,
            fullscreen: widget.pureMediaMode,
            fullscreenSafeInsets: MediaQuery.viewPaddingOf(context),
            topInset: topInset,
            toolbarHeight: toolbarHeight,
            inset: layoutSpec.horizontalInset,
            // 拖动借用已隐藏的说明区，不改变媒体档位或裁剪窗口。
            scrubHeight: 0,
          ),
          children: [
            LayoutId(
              id: _VideoSlot.media,
              child: ClipRect(
                child: LayoutBuilder(
                  builder: (context, constraints) => OverflowBox(
                    minWidth: constraints.maxWidth,
                    maxWidth: constraints.maxWidth,
                    minHeight: aspectRatio > 0
                        ? constraints.maxWidth / aspectRatio
                        : constraints.maxHeight,
                    maxHeight: aspectRatio > 0
                        ? constraints.maxWidth / aspectRatio
                        : constraints.maxHeight,
                    child: Stack(
                      fit: StackFit.expand,
                      children: [
                        media,
                        if (widget.pureMediaMode &&
                            snapshot.isInitialized &&
                            !snapshot.isScrubbing &&
                            !snapshot.isBuffering &&
                            snapshot.transport !=
                                VideoPlaybackTransport.failure)
                          Center(
                            child: Visibility(
                              visible: widget.controlsVisible,
                              maintainState: true,
                              maintainAnimation: true,
                              child: CupertinoButton(
                                key: const ValueKey(
                                  'works-landscape-play-toggle',
                                ),
                                onPressed: () => unawaited(session.toggle()),
                                child: Semantics(
                                  label: snapshot.isPlaying
                                      ? AppLocalizations.of(context).media_pause
                                      : AppLocalizations.of(context).media_play,
                                  child: snapshot.isPlaying
                                      ? const Icon(
                                          CupertinoIcons.pause_fill,
                                          color: AppColors.white,
                                          size: AppSpacing
                                              .videoPlayRoundedGlyphSize,
                                        )
                                      : const VideoPlaybackCenterPlayGlyph(),
                                ),
                              ),
                            ),
                          ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
            LayoutId(
              id: _VideoSlot.gradient,
              child: IgnorePointer(
                child: DecoratedBox(
                  key: const ValueKey('works-video-local-gradient'),
                  decoration: BoxDecoration(
                    gradient: LinearGradient(
                      begin: Alignment.topCenter,
                      end: Alignment.bottomCenter,
                      colors: [
                        AppColors.transparent,
                        AppColors.black.withValues(alpha: 0.62),
                      ],
                    ),
                  ),
                ),
              ),
            ),
            if (widget.association != null || intersection != null)
              LayoutId(
                id: _VideoSlot.association,
                child: widget.pureMediaMode
                    ? const SizedBox.shrink()
                    : VideoPlaybackChromeVisibility(
                        snapshot: snapshot,
                        child: SingleChildScrollView(
                          key: const ValueKey('works-video-association-slot'),
                          child: Column(
                            mainAxisSize: MainAxisSize.min,
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              if (widget.association != null)
                                widget.association!,
                              if (widget.association != null &&
                                  intersection != null)
                                const SizedBox(height: AppSpacing.intraGroupXs),
                              ?intersection,
                            ],
                          ),
                        ),
                      ),
              ),
            LayoutId(
              id: _VideoSlot.caption,
              child: widget.pureMediaMode
                  ? const SizedBox.shrink()
                  : VideoPlaybackChromeVisibility(
                      snapshot: snapshot,
                      child: SingleChildScrollView(
                        child: MediaCaptionBlock(
                          layoutSpec: layoutSpec,
                          railKey: const ValueKey('works-caption-rail'),
                          header: episodeTotal > 1 || attribution.isNotEmpty
                              ? Column(
                                  mainAxisSize: MainAxisSize.min,
                                  children: [
                                    if (episodeTotal > 1)
                                      _WorksVideoSeriesBadge(
                                        episodeCurrent: episodeCurrent,
                                        episodeTotal: episodeTotal,
                                      ),
                                    if (attribution.isNotEmpty)
                                      Text(
                                        attribution,
                                        key: const ValueKey(
                                          'works-video-source-attribution',
                                        ),
                                        maxLines: 2,
                                        overflow: TextOverflow.ellipsis,
                                        style: TextStyle(
                                          color: AppColors.white,
                                          fontSize: AppTypography.xxs,
                                        ),
                                      ),
                                  ],
                                )
                              : null,
                          title: title,
                          caption: caption,
                          isExpanded: isExpanded,
                          onToggle: onToggleCaption,
                        ),
                      ),
                    ),
            ),
            LayoutId(
              id: _VideoSlot.entry,
              child: !showEntry
                  ? const SizedBox.shrink()
                  : VideoPlaybackChromeVisibility(
                      snapshot: snapshot,
                      child: Visibility(
                        visible:
                            snapshot.isInitialized && !snapshot.isScrubbing,
                        maintainState: true,
                        maintainAnimation: true,
                        maintainSize: true,
                        child: _MediaLandscapeButton(
                          key: const ValueKey('works-video-landscape-entry'),
                          onPressed: snapshot.isInitialized
                              ? widget.onEnterLandscape
                              : null,
                        ),
                      ),
                    ),
            ),
            LayoutId(
              id: _VideoSlot.timeline,
              child: Visibility(
                visible: !widget.pureMediaMode || widget.controlsVisible,
                maintainState: true,
                maintainAnimation: true,
                child: VideoPlaybackTimeline(
                  key: const ValueKey('works-video-control-row'),
                  session: session,
                  profile: VideoPlaybackTimelineProfile.workBrowser,
                  isActive: isActive,
                  showDuration: false,
                  externallyControlledVisibility: widget.pureMediaMode,
                  showVisuals: sharedTimelineEnabled && snapshot.isInitialized,
                  previewBuilder: previewTrackDescriptor == null
                      ? null
                      : (context, snapshot, target) => VideoTimelinePreview(
                          descriptor: previewTrackDescriptor,
                          query: previewTrackQuery,
                          target: target,
                        ),
                ),
              ),
            ),
          ],
        );
      },
    );
  }
}

/// 先测量说明，再在同一布局阶段构建媒体；不使用晚一帧的几何补偿。
class _WorksImageStage extends StatelessWidget {
  const _WorksImageStage({
    required this.aspectRatio,
    required this.fullscreen,
    required this.topInset,
    required this.toolbarHeight,
    required this.caption,
    required this.entry,
    required this.mediaBuilder,
  });
  final double? aspectRatio;
  final bool fullscreen;
  final double topInset;
  final double toolbarHeight;
  final Widget caption;
  final Widget? entry;
  final Widget Function(double, double) mediaBuilder;

  @override
  Widget build(BuildContext context) {
    final measurement = _WorksImageMeasurement();
    return CustomMultiChildLayout(
      delegate: _WorksImageLayoutDelegate(
        measurement: measurement,
        aspectRatio: aspectRatio ?? double.nan,
        fullscreen: fullscreen,
        topInset: topInset,
        toolbarHeight: toolbarHeight,
        fullscreenSafeInsets: MediaQuery.viewPaddingOf(context),
      ),
      children: [
        LayoutId(
          id: _VideoSlot.media,
          child: LayoutBuilder(
            builder: (_, _) =>
                mediaBuilder(measurement.bottomInset, measurement.entryExtent),
          ),
        ),
        LayoutId(
          id: _VideoSlot.caption,
          child: Visibility(
            visible: !fullscreen,
            maintainState: true,
            maintainAnimation: true,
            child: SingleChildScrollView(child: caption),
          ),
        ),
        LayoutId(id: _VideoSlot.entry, child: entry ?? const SizedBox.shrink()),
      ],
    );
  }
}

class _WorksImageMeasurement {
  double bottomInset = 0;
  double entryExtent = 0;
}

class _WorksImageLayoutDelegate extends MultiChildLayoutDelegate {
  _WorksImageLayoutDelegate({
    required this.measurement,
    required this.aspectRatio,
    required this.fullscreen,
    required this.topInset,
    required this.toolbarHeight,
    required this.fullscreenSafeInsets,
  });
  final _WorksImageMeasurement measurement;
  final double aspectRatio;
  final bool fullscreen;
  final double topInset;
  final double toolbarHeight;
  final EdgeInsets fullscreenSafeInsets;

  @override
  void performLayout(Size size) {
    if (fullscreen) {
      final landscape = ImmersiveLandscapeGeometry(
        size: size,
        safeInsets: fullscreenSafeInsets,
        aspectRatio: aspectRatio,
      );
      layoutChild(_VideoSlot.caption, BoxConstraints.tight(Size.zero));
      layoutChild(_VideoSlot.entry, BoxConstraints.tight(Size.zero));
      layoutChild(
        _VideoSlot.media,
        BoxConstraints.tight(landscape.visibleMediaRect.size),
      );
      positionChild(_VideoSlot.media, landscape.visibleMediaRect.topLeft);
      positionChild(_VideoSlot.caption, Offset.zero);
      positionChild(_VideoSlot.entry, Offset.zero);
      return;
    }
    final caption = layoutChild(
      _VideoSlot.caption,
      BoxConstraints(
        minWidth: size.width,
        maxWidth: size.width,
        maxHeight: max(0, (size.height - topInset - toolbarHeight) * 0.55),
      ),
    );
    final entry = layoutChild(
      _VideoSlot.entry,
      BoxConstraints(maxWidth: size.width),
    );
    measurement.bottomInset =
        toolbarHeight +
        caption.height +
        (caption.height > 0 ? AppSpacing.containerSm : 0);
    measurement.entryExtent = entry.height > 0
        ? entry.height + AppSpacing.intraGroupXs
        : 0;
    final geometry = ImmersiveMediaGeometry(
      size: size,
      aspectRatio: aspectRatio,
      topInset: topInset,
      bottomInset: measurement.bottomInset,
      entryExtent: measurement.entryExtent,
      fullscreen: fullscreen,
    );
    layoutChild(_VideoSlot.media, BoxConstraints.tight(size));
    positionChild(_VideoSlot.media, Offset.zero);
    positionChild(
      _VideoSlot.caption,
      Offset(
        0,
        max(
          0,
          size.height -
              toolbarHeight -
              caption.height -
              (caption.height > 0 ? AppSpacing.containerSm : 0),
        ),
      ),
    );
    positionChild(
      _VideoSlot.entry,
      Offset((size.width - entry.width) / 2, geometry.entryRect.top),
    );
  }

  @override
  bool shouldRelayout(covariant _WorksImageLayoutDelegate oldDelegate) => true;
}

enum _VideoSlot { media, gradient, association, caption, entry, timeline }

class _WorksVideoLayoutDelegate extends MultiChildLayoutDelegate {
  _WorksVideoLayoutDelegate({
    required this.aspectRatio,
    required this.topInset,
    required this.toolbarHeight,
    required this.inset,
    required this.scrubHeight,
    required this.fullscreen,
    required this.fullscreenSafeInsets,
  });
  final EdgeInsets fullscreenSafeInsets;
  final bool fullscreen;
  final double aspectRatio;
  final double topInset;
  final double toolbarHeight;
  final double inset;
  final double scrubHeight;

  @override
  void performLayout(Size size) {
    final railWidth = max(0.0, size.width - inset * 2);
    if (fullscreen) {
      final geometry = ImmersiveLandscapeGeometry(
        size: size,
        safeInsets: fullscreenSafeInsets,
        aspectRatio: aspectRatio,
      );
      layoutChild(
        _VideoSlot.media,
        BoxConstraints.tight(geometry.visibleMediaRect.size),
      );
      positionChild(_VideoSlot.media, geometry.visibleMediaRect.topLeft);
      for (final slot in [
        _VideoSlot.entry,
        _VideoSlot.caption,
        _VideoSlot.association,
        _VideoSlot.gradient,
      ]) {
        if (hasChild(slot)) {
          layoutChild(slot, BoxConstraints.tight(Size.zero));
          positionChild(slot, Offset.zero);
        }
      }
      layoutChild(
        _VideoSlot.timeline,
        BoxConstraints.tight(
          Size(geometry.visibleMediaRect.width, AppSpacing.minInteractiveSize),
        ),
      );
      positionChild(
        _VideoSlot.timeline,
        Offset(
          geometry.visibleMediaRect.left,
          max(
            geometry.visibleMediaRect.top,
            geometry.visibleMediaRect.bottom -
                toolbarHeight -
                AppSpacing.minInteractiveSize,
          ),
        ),
      );
      return;
    }
    final entry = layoutChild(
      _VideoSlot.entry,
      BoxConstraints(maxWidth: railWidth),
    );
    // 文本以实际字体测量；极端大字时内部滚动，不侵入时长或控制热区。
    final available = max(
      0.0,
      size.height -
          topInset -
          toolbarHeight -
          AppSpacing.minInteractiveSize -
          entry.height -
          scrubHeight -
          AppSpacing.containerLg,
    );
    final association = hasChild(_VideoSlot.association)
        ? layoutChild(
            _VideoSlot.association,
            BoxConstraints.tightFor(width: railWidth)
                .copyWith(maxHeight: available * 0.25),
          )
        : Size.zero;
    final caption = layoutChild(
      _VideoSlot.caption,
      BoxConstraints(
        maxWidth: size.width,
        maxHeight: max(0, available * 0.55 - association.height),
      ),
    );
    final geometry = WorksVideoGeometry(
      size: size,
      aspectRatio: aspectRatio,
      topInset: topInset,
      toolbarHeight: toolbarHeight,
      captionHeight: caption.height,
      associationHeight: association.height,
      entryHeight: entry.height > 0
          ? entry.height + AppSpacing.intraGroupXs
          : 0,
      scrubHeight: scrubHeight,
      horizontalInset: inset,
    );
    layoutChild(
      _VideoSlot.media,
      BoxConstraints.tight(geometry.stageRect.size),
    );
    positionChild(_VideoSlot.media, geometry.stageRect.topLeft);
    layoutChild(
      _VideoSlot.gradient,
      BoxConstraints.tight(geometry.gradientRect.size),
    );
    positionChild(_VideoSlot.gradient, geometry.gradientRect.topLeft);
    positionChild(_VideoSlot.caption, Offset(0, geometry.captionRect.top));
    if (hasChild(_VideoSlot.association)) {
      positionChild(_VideoSlot.association, geometry.associationRect.topLeft);
    }
    positionChild(
      _VideoSlot.entry,
      Offset((size.width - entry.width) / 2, geometry.entryRect.top),
    );
    layoutChild(
      _VideoSlot.timeline,
      BoxConstraints.tight(geometry.timelineRect.size),
    );
    positionChild(_VideoSlot.timeline, geometry.timelineRect.topLeft);
  }

  @override
  bool shouldRelayout(covariant _WorksVideoLayoutDelegate oldDelegate) =>
      aspectRatio != oldDelegate.aspectRatio ||
      topInset != oldDelegate.topInset ||
      toolbarHeight != oldDelegate.toolbarHeight ||
      inset != oldDelegate.inset ||
      fullscreen != oldDelegate.fullscreen ||
      fullscreenSafeInsets != oldDelegate.fullscreenSafeInsets ||
      scrubHeight != oldDelegate.scrubHeight;
}
