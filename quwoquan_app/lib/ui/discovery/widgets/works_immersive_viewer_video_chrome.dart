part of 'works_immersive_viewer.dart';

/// 视频 caption 与时间轴共用的底部布局。
///
/// 该组件读取实际 RenderParagraph 字形框与时长 RenderBox，避免页面通过字符数
/// 或整条 rail 包围盒猜测轨道上方时长是否安全可见。
class _WorksVideoBottomChrome extends StatefulWidget {
  const _WorksVideoBottomChrome({
    super.key,
    required this.layoutSpec,
    required this.intersection,
    required this.title,
    required this.caption,
    required this.sourceAttribution,
    required this.isExpanded,
    required this.onToggleCaption,
    required this.session,
    required this.durationWindowActive,
    required this.sharedTimelineEnabled,
    required this.previewTrackDescriptor,
    required this.previewTrackQuery,
    required this.episodeCurrent,
    required this.episodeTotal,
  });

  final ImmersiveViewerStageLayoutSpec layoutSpec;
  final Widget? intersection;
  final String title;
  final String caption;
  final SourceAttributionDto? sourceAttribution;
  final bool isExpanded;
  final VoidCallback onToggleCaption;
  final VideoPlaybackSession? session;
  final bool durationWindowActive;
  final bool sharedTimelineEnabled;
  final VideoPreviewTrackDescriptor? previewTrackDescriptor;
  final VideoPreviewTrackQuery previewTrackQuery;
  final int episodeCurrent;
  final int episodeTotal;

  @override
  State<_WorksVideoBottomChrome> createState() =>
      _WorksVideoBottomChromeState();
}

class _WorksVideoBottomChromeState extends State<_WorksVideoBottomChrome> {
  final GlobalKey _captionKey = GlobalKey();
  final GlobalKey _durationKey = GlobalKey();
  final GlobalKey _scrubTimeKey = GlobalKey();

  // 先以透明但参与布局的状态完成首帧测量，确认无碰撞后才显示，避免
  // 高文字缩放或窄视口下先闪现一帧重叠的总时长。
  bool _durationVisible = false;
  bool _scrubTimeVisible = false;
  bool _isScrubbing = false;
  bool _collisionCheckScheduled = false;
  ({
    bool initialized,
    bool playing,
    bool scrubbing,
    VideoPlaybackTransport transport,
    Duration duration,
    String scrubTimeText,
  })?
  _sessionGeometry;
  ({Size size, TextScaler textScaler, EdgeInsets viewPadding})? _layoutGeometry;

  @override
  void initState() {
    super.initState();
    _bindSession(widget.session);
  }

  @override
  void didUpdateWidget(covariant _WorksVideoBottomChrome oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (!identical(oldWidget.session, widget.session)) {
      oldWidget.session?.removeListener(_handleSessionChanged);
      _bindSession(widget.session);
    }
    if (oldWidget.durationWindowActive != widget.durationWindowActive ||
        oldWidget.title != widget.title ||
        oldWidget.caption != widget.caption ||
        oldWidget.sourceAttribution != widget.sourceAttribution ||
        oldWidget.isExpanded != widget.isExpanded ||
        !identical(oldWidget.intersection, widget.intersection)) {
      _durationVisible = false;
      _scrubTimeVisible = false;
    }
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final geometry = (
      size: MediaQuery.sizeOf(context),
      textScaler: MediaQuery.textScalerOf(context),
      viewPadding: MediaQuery.viewPaddingOf(context),
    );
    if (_layoutGeometry == geometry) {
      return;
    }
    _layoutGeometry = geometry;
    _durationVisible = false;
    _scrubTimeVisible = false;
  }

  @override
  void dispose() {
    widget.session?.removeListener(_handleSessionChanged);
    super.dispose();
  }

  void _bindSession(VideoPlaybackSession? session) {
    final snapshot = session?.snapshot;
    _isScrubbing = snapshot?.isScrubbing ?? false;
    _sessionGeometry = snapshot == null ? null : _geometryFor(snapshot);
    _durationVisible = false;
    _scrubTimeVisible = false;
    session?.addListener(_handleSessionChanged);
  }

  void _handleSessionChanged() {
    final snapshot = widget.session?.snapshot;
    final geometry = snapshot == null ? null : _geometryFor(snapshot);
    if (geometry == _sessionGeometry || !mounted) {
      return;
    }
    setState(() {
      _sessionGeometry = geometry;
      _isScrubbing = snapshot?.isScrubbing ?? false;
      // 播放/暂停、拖动与原生时长修正都会改变标签几何。新几何必须先
      // 透明测量，再决定是否绘制，不能沿用上一状态的碰撞结论。
      _durationVisible = false;
      _scrubTimeVisible = false;
    });
  }

  ({
    bool initialized,
    bool playing,
    bool scrubbing,
    VideoPlaybackTransport transport,
    Duration duration,
    String scrubTimeText,
  })
  _geometryFor(VideoPlaybackSnapshot snapshot) {
    return (
      initialized: snapshot.isInitialized,
      playing: snapshot.isPlaying,
      scrubbing: snapshot.isScrubbing,
      transport: snapshot.transport,
      duration: snapshot.duration,
      scrubTimeText: snapshot.isScrubbing
          ? '${formatVideoPlaybackDuration(snapshot.effectivePosition)} / '
                '${formatVideoPlaybackDuration(snapshot.duration)}'
          : '',
    );
  }

  Rect? _globalRect(GlobalKey key) {
    final renderObject = key.currentContext?.findRenderObject();
    if (renderObject is! RenderBox ||
        !renderObject.hasSize ||
        !renderObject.attached) {
      return null;
    }
    return renderObject.localToGlobal(Offset.zero) & renderObject.size;
  }

  List<Rect>? _globalTextPaintRects(GlobalKey key) {
    final root = key.currentContext?.findRenderObject();
    if (root == null || !root.attached) {
      return null;
    }
    final result = <Rect>[];
    void collect(RenderObject object) {
      if (object is RenderParagraph && object.attached && object.hasSize) {
        final textLength = object.text.toPlainText().length;
        if (textLength > 0) {
          final boxes = object.getBoxesForSelection(
            TextSelection(baseOffset: 0, extentOffset: textLength),
          );
          for (final box in boxes) {
            final localRect = box.toRect();
            result.add(
              Rect.fromPoints(
                object.localToGlobal(localRect.topLeft),
                object.localToGlobal(localRect.bottomRight),
              ),
            );
          }
        }
      }
      object.visitChildren(collect);
    }

    collect(root);
    return result;
  }

  bool? _collidesWithCaption(GlobalKey targetKey) {
    final targetRect = _globalRect(targetKey);
    final textRects = _globalTextPaintRects(_captionKey);
    if (textRects == null || targetRect == null) {
      return null;
    }
    return textRects.any(
      (rect) => rect.inflate(AppSpacing.intraGroupXs).overlaps(targetRect),
    );
  }

  void _scheduleCollisionCheck() {
    if (_collisionCheckScheduled) {
      return;
    }
    _collisionCheckScheduled = true;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _collisionCheckScheduled = false;
      if (!mounted) {
        return;
      }
      final durationCollision = _collidesWithCaption(_durationKey);
      final scrubTimeCollision = _collidesWithCaption(_scrubTimeKey);
      final nextDurationVisible = durationCollision == false;
      final nextScrubTimeVisible = !_isScrubbing || scrubTimeCollision == false;
      if (nextDurationVisible == _durationVisible &&
          nextScrubTimeVisible == _scrubTimeVisible) {
        return;
      }
      setState(() {
        _durationVisible = nextDurationVisible;
        _scrubTimeVisible = nextScrubTimeVisible;
      });
    });
  }

  @override
  Widget build(BuildContext context) {
    _scheduleCollisionCheck();
    // 互动栏是底部唯一固定锚点；时间轴紧贴其上沿，交集说明随 caption
    // 一起向上排布，不得再把文本插入工具栏与时间轴之间。
    final timelineBottom = ImmersiveEngagementBar.reservedHeight(context);
    final scrubOverlayReserve = !_isScrubbing
        ? AppSpacing.zero
        : AppTypography.base * AppSpacing.textLineHeightBody +
              AppSpacing.interGroupSm +
              (widget.previewTrackDescriptor == null
                  ? AppSpacing.zero
                  : VideoTimelinePreview.maximumHeight +
                        AppSpacing.interGroupSm);
    final captionBottom =
        timelineBottom +
        AppSpacing.minInteractiveSize +
        AppSpacing.intraGroupXs +
        scrubOverlayReserve;
    final seriesHeader = widget.episodeTotal > 1
        ? _WorksVideoSeriesBadge(
            episodeCurrent: widget.episodeCurrent,
            episodeTotal: widget.episodeTotal,
          )
        : null;
    final attributionText =
        widget.sourceAttribution?.attributionText.trim() ?? '';
    final attributionHeader = attributionText.isEmpty
        ? null
        : _WorksVideoSourceAttribution(text: attributionText);
    final header = switch ((seriesHeader, attributionHeader)) {
      (null, null) => null,
      (final Widget series, null) => series,
      (null, final Widget attribution) => attribution,
      (final Widget series, final Widget attribution) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          series,
          SizedBox(height: AppSpacing.intraGroupXs),
          attribution,
        ],
      ),
    };

    return Stack(
      fit: StackFit.expand,
      children: [
        Positioned(
          left: 0,
          right: 0,
          bottom: captionBottom,
          child: KeyedSubtree(
            key: _captionKey,
            child: MediaCaptionBlock(
              layoutSpec: widget.layoutSpec,
              railKey: const ValueKey<String>('works-caption-rail'),
              header: header,
              title: widget.title,
              caption: widget.caption,
              isExpanded: widget.isExpanded,
              onToggle: widget.onToggleCaption,
              footer: widget.intersection,
            ),
          ),
        ),
        Positioned(
          left: 0,
          right: 0,
          bottom: timelineBottom,
          child: ImmersiveViewerLayout.alignToRail(
            context: context,
            layoutSpec: widget.layoutSpec,
            includeBottomSafeSideInset: true,
            child: SizedBox(
              width: double.infinity,
              child: _WorksVideoControlRow(
                key: const ValueKey<String>('works-video-timeline'),
                session: widget.session,
                sharedTimelineEnabled: widget.sharedTimelineEnabled,
                previewTrackDescriptor: widget.previewTrackDescriptor,
                previewTrackQuery: widget.previewTrackQuery,
                durationVisible:
                    widget.durationWindowActive && _durationVisible,
                scrubTimeVisible: _scrubTimeVisible,
                durationKey: _durationKey,
                scrubTimeKey: _scrubTimeKey,
              ),
            ),
          ),
        ),
      ],
    );
  }
}

class _WorksVideoSourceAttribution extends StatelessWidget {
  const _WorksVideoSourceAttribution({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      label: text,
      child: Container(
        key: const ValueKey<String>('works-video-source-attribution'),
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.intraGroupSm,
          vertical: AppSpacing.intraGroupXs / 2,
        ),
        decoration: BoxDecoration(
          color: AppColors.black.withValues(alpha: 0.28),
          borderRadius: BorderRadius.circular(AppSpacing.circularBorderRadius),
          border: Border.all(color: AppColors.white.withValues(alpha: 0.14)),
        ),
        child: Text(
          text,
          maxLines: 2,
          overflow: TextOverflow.ellipsis,
          style: TextStyle(
            color: AppColors.white.withValues(alpha: 0.88),
            fontSize: AppTypography.xxs,
            fontWeight: AppTypography.medium,
          ),
        ),
      ),
    );
  }
}
