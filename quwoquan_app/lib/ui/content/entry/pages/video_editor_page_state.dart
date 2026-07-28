part of 'video_editor_page.dart';

class _VideoEditorPageState extends State<VideoEditorPage> {
  VideoPlayerController? _controller;
  late final IosVideoEditingService _editingService;

  Timer? _frameReloadDebounce;
  Timer? _previewSeekDebounce;
  bool _loading = true;
  bool _saving = false;
  bool _framesLoading = false;
  bool _previewDragging = false;
  bool _resumePlaybackAfterScrub = false;
  UiErrorSemantic? _pageErrorSemantic;
  UiErrorSemantic? _sectionErrorSemantic;
  int _durationMs = 1000;
  double _trimStartMs = 0;
  double _trimEndMs = 1000;
  double _coverTimeMs = 0;
  double _previewTimeMs = 0;
  bool _muted = false;
  List<VideoFrameCandidate> _frames = const <VideoFrameCandidate>[];
  String _selectedCoverPath = '';

  int get _normalizedInitialEndMs {
    final configured = widget.initialTrimEndMs > 0
        ? widget.initialTrimEndMs
        : _durationMs;
    return configured.clamp(0, _durationMs);
  }

  bool get _hasMediaEdits {
    return _trimStartMs.round() != widget.initialTrimStartMs ||
        _trimEndMs.round() != _normalizedInitialEndMs ||
        _muted != widget.initialMuted;
  }

  @override
  void initState() {
    super.initState();
    _editingService = widget.editingService ?? IosVideoEditingService();
    _selectedCoverPath = widget.initialThumbnailPath.trim();
    _bootstrap();
  }

  @override
  void dispose() {
    _frameReloadDebounce?.cancel();
    _previewSeekDebounce?.cancel();
    final controller = _controller;
    if (controller != null) {
      controller
        ..removeListener(_handlePlaybackTick)
        ..dispose();
    }
    super.dispose();
  }

  Future<void> _bootstrap() async {
    if (mounted) {
      setState(() {
        _loading = true;
        _pageErrorSemantic = null;
      });
    }
    try {
      final previousController = _controller;
      if (previousController != null) {
        previousController
          ..removeListener(_handlePlaybackTick)
          ..dispose();
        _controller = null;
      }
      final controller = await createInitializedLocalVideoController(
        widget.sourceVideoPath,
        readyProbe: widget.videoFileReadyProbe ?? waitForLocalVideoFileReady,
      );
      if (!mounted) {
        await controller.dispose();
        return;
      }
      controller.addListener(_handlePlaybackTick);
      final durationMs = math.max(
        controller.value.duration.inMilliseconds,
        1000,
      );
      final initialStart = widget.initialTrimStartMs.clamp(0, durationMs - 100);
      final initialEnd =
          (widget.initialTrimEndMs > 0 ? widget.initialTrimEndMs : durationMs)
              .clamp(initialStart + 100, durationMs);
      final initialCover = widget.initialCoverTimeMs > 0
          ? widget.initialCoverTimeMs.clamp(initialStart, initialEnd)
          : initialStart;
      if (!mounted) {
        return;
      }
      await controller.setVolume(widget.initialMuted ? 0 : 1);
      setState(() {
        _controller = controller;
        _durationMs = durationMs;
        _trimStartMs = initialStart.toDouble();
        _trimEndMs = initialEnd.toDouble();
        _coverTimeMs = initialCover.toDouble();
        _previewTimeMs = initialStart.toDouble();
        _muted = widget.initialMuted;
        _loading = false;
        _pageErrorSemantic = null;
      });
      await _loadFrames();
      await _seekToCurrentRangeStart();
    } catch (error, stackTrace) {
      unawaited(
        AppExceptionTelemetryService.instance.recordHandledException(
          source: 'content.video_editor.initialize',
          error: error,
          stackTrace: stackTrace,
        ),
      );
      if (!mounted) {
        return;
      }
      setState(() {
        _loading = false;
        _pageErrorSemantic = AppUserRecoveryContract.semanticFor(
          group: AppUserRecoveryGroup.reloadLater,
          category: UiErrorCategory.pageLoad,
          scope: UiErrorScope.page,
        );
      });
    }
  }

  Future<void> _loadFrames() async {
    setState(() {
      _framesLoading = true;
      _sectionErrorSemantic = null;
    });
    try {
      final frames = await _editingService.extractFrames(
        videoPath: widget.sourceVideoPath,
        startMs: _trimStartMs.round(),
        endMs: _trimEndMs.round(),
        frameCount: 24,
      );
      if (!mounted) {
        return;
      }
      final selected = _closestFrameTo(_coverTimeMs.round(), frames);
      setState(() {
        _frames = frames;
        if (selected != null) {
          _coverTimeMs = selected.timeMs.toDouble();
          _selectedCoverPath = selected.path;
        }
        _framesLoading = false;
        _sectionErrorSemantic = null;
      });
    } catch (error, stackTrace) {
      unawaited(
        AppExceptionTelemetryService.instance.recordHandledException(
          source: 'content.video_editor.extract_frames',
          error: error,
          stackTrace: stackTrace,
        ),
      );
      if (!mounted) {
        return;
      }
      setState(() {
        _framesLoading = false;
        _sectionErrorSemantic = AppUserRecoveryContract.semanticFor(
          group: AppUserRecoveryGroup.reloadLater,
          category: UiErrorCategory.sectionLoad,
          scope: UiErrorScope.section,
        );
      });
    }
  }

  VideoFrameCandidate? _closestFrameTo(
    int targetMs,
    List<VideoFrameCandidate> frames,
  ) {
    if (frames.isEmpty) {
      return null;
    }
    VideoFrameCandidate closest = frames.first;
    var delta = (closest.timeMs - targetMs).abs();
    for (final frame in frames.skip(1)) {
      final nextDelta = (frame.timeMs - targetMs).abs();
      if (nextDelta < delta) {
        closest = frame;
        delta = nextDelta;
      }
    }
    return closest;
  }

  Future<void> _seekToCurrentRangeStart() async {
    final controller = _controller;
    if (controller == null || !controller.value.isInitialized) {
      return;
    }
    await controller.seekTo(Duration(milliseconds: _trimStartMs.round()));
  }

  void _handlePlaybackTick() {
    final controller = _controller;
    if (controller == null || !controller.value.isInitialized) {
      return;
    }
    final positionMs = controller.value.position.inMilliseconds;
    if (positionMs > _trimEndMs.round()) {
      controller.pause();
      controller.seekTo(Duration(milliseconds: _trimStartMs.round()));
      if (mounted) {
        setState(() {
          _previewTimeMs = _trimStartMs;
        });
      }
      return;
    }
    if (!_previewDragging &&
        (positionMs - _previewTimeMs.round()).abs() >= 48 &&
        mounted) {
      setState(() {
        _previewTimeMs = positionMs
            .clamp(_trimStartMs.round(), _trimEndMs.round())
            .toDouble();
      });
    }
  }

  Future<void> _togglePlayback() async {
    final controller = _controller;
    if (controller == null || !controller.value.isInitialized) {
      return;
    }
    if (controller.value.isPlaying) {
      await controller.pause();
      return;
    }
    final positionMs = controller.value.position.inMilliseconds;
    if (positionMs < _trimStartMs.round() || positionMs >= _trimEndMs.round()) {
      await controller.seekTo(Duration(milliseconds: _trimStartMs.round()));
    }
    await controller.play();
  }

  Future<void> _toggleMuted(bool value) async {
    setState(() {
      _muted = value;
    });
    final controller = _controller;
    if (controller != null && controller.value.isInitialized) {
      await controller.setVolume(value ? 0 : 1);
    }
  }

  void _handleTrimChanged(RangeValues values) {
    final nextStart = values.start.round().clamp(0, _durationMs - 100);
    final nextEnd = values.end.round().clamp(nextStart + 100, _durationMs);
    setState(() {
      _trimStartMs = nextStart.toDouble();
      _trimEndMs = nextEnd.toDouble();
      _coverTimeMs = _coverTimeMs.clamp(
        nextStart.toDouble(),
        nextEnd.toDouble(),
      );
      _previewTimeMs = _previewTimeMs.clamp(
        nextStart.toDouble(),
        nextEnd.toDouble(),
      );
    });
    unawaited(_seekPreviewTo(_previewTimeMs.round(), immediate: true));
    _frameReloadDebounce?.cancel();
    _frameReloadDebounce = Timer(
      const Duration(milliseconds: 180),
      _loadFrames,
    );
  }

  void _handleCoverChanged(double value) {
    final clamped = value.clamp(_trimStartMs, _trimEndMs);
    final frame = _closestFrameTo(clamped.round(), _frames);
    setState(() {
      _coverTimeMs = clamped;
      _previewTimeMs = clamped;
      if (frame != null) {
        _selectedCoverPath = frame.path;
      }
    });
    unawaited(_seekPreviewTo(clamped.round()));
  }

  void _selectFrame(VideoFrameCandidate frame) {
    setState(() {
      _coverTimeMs = frame.timeMs.toDouble();
      _previewTimeMs = frame.timeMs.toDouble();
      _selectedCoverPath = frame.path;
    });
    unawaited(_seekPreviewTo(frame.timeMs, immediate: true));
  }

  Future<void> _saveEditing() async {
    if (_saving) {
      return;
    }
    setState(() {
      _saving = true;
      _sectionErrorSemantic = null;
    });
    try {
      final currentVideoPath = widget.initialVideoPath.trim().isEmpty
          ? widget.sourceVideoPath
          : widget.initialVideoPath.trim();
      var nextVideoPath = currentVideoPath;
      var nextCoverPath = _selectedCoverPath.trim();
      if (_hasMediaEdits) {
        final export = await _editingService.exportEdit(
          sourcePath: widget.sourceVideoPath,
          trimStartMs: _trimStartMs.round(),
          trimEndMs: _trimEndMs.round(),
          muted: _muted,
          coverTimeMs: _coverTimeMs.round(),
        );
        nextVideoPath = export.videoPath.trim().isEmpty
            ? currentVideoPath
            : export.videoPath.trim();
        if (export.coverPath.trim().isNotEmpty) {
          nextCoverPath = export.coverPath.trim();
        }
      }
      if (!mounted) {
        return;
      }
      final videoSize = _controller?.value.size ?? Size.zero;
      Navigator.of(context).pop(
        VideoEditorResult(
          videoPath: nextVideoPath,
          originalVideoPath: widget.sourceVideoPath,
          thumbnailPath: nextCoverPath,
          durationMs: _durationMs,
          trimStartMs: _trimStartMs.round(),
          trimEndMs: _trimEndMs.round(),
          coverTimeMs: _coverTimeMs.round(),
          coverStrategy: _coverTimeMs.round() > 0 ? 'manual' : 'first_frame',
          width: videoSize.width.round().clamp(0, 999999999),
          height: videoSize.height.round().clamp(0, 999999999),
          muted: _muted,
        ),
      );
    } catch (error) {
      if (!mounted) {
        return;
      }
      final resolved = runtimeErrorSemantic(
        context,
        error: error,
        category: UiErrorCategory.submit,
        scope: UiErrorScope.global,
      );
      final semantic = UiErrorSemantic(
        category: resolved.category,
        scope: resolved.scope,
        title: MediaText.videoEditorExportFailedTitle,
        message: resolved.message,
        secondaryMessage: resolved.secondaryMessage,
        primaryAction: const UiErrorAction(
          type: UiErrorActionType.retry,
          label: ContentText.tryAgain,
        ),
        secondaryAction: resolved.secondaryAction,
        dismissible: resolved.dismissible,
        sourceCode: resolved.sourceCode,
        failureKind: resolved.failureKind,
        recoveryAction: resolved.recoveryAction,
        presentation: resolved.presentation,
        tone: resolved.tone,
      );
      await AppActionErrorFeedback.show(
        context,
        semantic: semantic,
        onAction: (action) async {
          if (action.type == UiErrorActionType.retry ||
              action.type == UiErrorActionType.resubmit) {
            await _saveEditing();
          }
        },
      );
    } finally {
      if (mounted) {
        setState(() {
          _saving = false;
        });
      }
    }
  }

  String _formatMs(int ms) {
    final totalSeconds = (ms / 1000).floor();
    final minutes = (totalSeconds ~/ 60).toString().padLeft(2, '0');
    final seconds = (totalSeconds % 60).toString().padLeft(2, '0');
    return '$minutes:$seconds';
  }

  Future<void> _beginPreviewDrag() async {
    if (_previewDragging) {
      return;
    }
    final controller = _controller;
    if (controller == null) {
      return;
    }
    _resumePlaybackAfterScrub = controller.value.isPlaying;
    if (_resumePlaybackAfterScrub) {
      await controller.pause();
    }
    if (mounted) {
      setState(() {
        _previewDragging = true;
      });
    }
  }

  Future<void> _endPreviewDrag([double? value]) async {
    final targetMs = (value ?? _previewTimeMs).round();
    if (mounted) {
      setState(() {
        _previewDragging = false;
      });
    }
    await _seekPreviewTo(targetMs, immediate: true);
    final controller = _controller;
    if (_resumePlaybackAfterScrub &&
        controller != null &&
        controller.value.isInitialized) {
      await controller.play();
    }
    _resumePlaybackAfterScrub = false;
  }

  void _handlePreviewChanged(double value) {
    final clamped = value.clamp(_trimStartMs, _trimEndMs).toDouble();
    setState(() {
      _previewTimeMs = clamped;
    });
    unawaited(_seekPreviewTo(clamped.round()));
  }

  Future<void> _seekPreviewTo(int targetMs, {bool immediate = false}) async {
    final clampedMs = targetMs.clamp(_trimStartMs.round(), _trimEndMs.round());
    _previewSeekDebounce?.cancel();
    if (immediate) {
      final controller = _controller;
      if (controller != null && controller.value.isInitialized) {
        await controller.seekTo(Duration(milliseconds: clampedMs));
      }
      return;
    }
    _previewSeekDebounce = Timer(const Duration(milliseconds: 24), () async {
      final controller = _controller;
      if (controller == null || !controller.value.isInitialized) {
        return;
      }
      await controller.seekTo(Duration(milliseconds: clampedMs));
    });
  }

  double _timelineValueForDx(double dx, double width) {
    if (width <= 0) {
      return _trimStartMs;
    }
    final ratio = (dx / width).clamp(0.0, 1.0);
    return _trimStartMs + (_trimEndMs - _trimStartMs) * ratio;
  }

  Widget _buildHeaderBadge(BuildContext context, String label) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final scrim = AppColorsFunctional.getColor(
      isDark,
      ColorType.black,
    ).withValues(alpha: 0.38);
    final fg = AppColorsFunctional.getColor(
      isDark,
      ColorType.mediaThumbnailOverlayForeground,
    );
    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.containerSm,
        vertical: AppSpacing.intraGroupXs,
      ),
      decoration: BoxDecoration(
        color: scrim,
        borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
      ),
      child: Text(
        label,
        style: TextStyle(
          color: fg,
          fontSize: AppTypography.sm,
          fontWeight: AppTypography.medium,
        ),
      ),
    );
  }

  Widget _buildPreview() {
    final controller = _controller;
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final scrimBlack = AppColorsFunctional.getColor(isDark, ColorType.black);
    final onVideoFg = AppColorsFunctional.getColor(
      isDark,
      ColorType.mediaThumbnailOverlayForeground,
    );
    final playRingBorder = AppColorsFunctional.getColor(
      isDark,
      ColorType.white,
    ).withValues(alpha: 0.12);
    final aspectRatio = controller?.value.isInitialized == true
        ? controller!.value.aspectRatio.clamp(0.56, 1.8).toDouble()
        : 9 / 16;
    return Container(
      decoration: BoxDecoration(
        color: CupertinoColors.secondarySystemGroupedBackground.resolveFrom(
          context,
        ),
        borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
        child: AspectRatio(
          aspectRatio: aspectRatio,
          child: Stack(
            fit: StackFit.expand,
            children: <Widget>[
              if (controller != null && controller.value.isInitialized)
                VideoPlayer(controller)
              else if (_selectedCoverPath.isNotEmpty)
                Image.file(
                  File(_selectedCoverPath),
                  fit: BoxFit.cover,
                  errorBuilder: (context, error, stackTrace) =>
                      const ColoredBox(
                        color: AppColors.createMediaFallbackGradientBottom,
                      ),
                )
              else
                const ColoredBox(
                  color: AppColors.createMediaFallbackGradientBottom,
                ),
              DecoratedBox(
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    begin: Alignment.topCenter,
                    end: Alignment.bottomCenter,
                    colors: <Color>[
                      scrimBlack.withValues(alpha: 0.08),
                      scrimBlack.withValues(alpha: 0.44),
                    ],
                  ),
                ),
              ),
              Center(
                child: CupertinoButton(
                  padding: EdgeInsets.zero,
                  onPressed: _togglePlayback,
                  child: Container(
                    width: AppSpacing.buttonHeight + 8,
                    height: AppSpacing.buttonHeight + 8,
                    decoration: BoxDecoration(
                      color: scrimBlack.withValues(alpha: 0.28),
                      shape: BoxShape.circle,
                      border: Border.all(
                        color: playRingBorder,
                        width: AppSpacing.hairline,
                      ),
                    ),
                    child: Icon(
                      controller?.value.isPlaying == true
                          ? CupertinoIcons.pause_fill
                          : CupertinoIcons.play_fill,
                      color: onVideoFg,
                      size: AppSpacing.iconLarge,
                    ),
                  ),
                ),
              ),
              Positioned(
                left: AppSpacing.containerSm,
                top: AppSpacing.containerSm,
                child: Row(
                  children: <Widget>[
                    _buildHeaderBadge(
                      context,
                      '${_formatMs(_trimStartMs.round())} - ${_formatMs(_trimEndMs.round())}',
                    ),
                    if (_muted) ...<Widget>[
                      SizedBox(width: AppSpacing.intraGroupXs),
                      _buildHeaderBadge(context, MediaText.videoEditorMuted),
                    ],
                  ],
                ),
              ),
              Positioned(
                left: AppSpacing.containerSm,
                right: AppSpacing.containerSm,
                bottom: AppSpacing.containerSm,
                child: Align(
                  alignment: Alignment.centerLeft,
                  child: _buildHeaderBadge(
                    context,
                    '${MediaText.videoEditorCoverPrefix} ${_formatMs(_coverTimeMs.round())}',
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildActionBar() {
    return Row(
      children: <Widget>[
        Expanded(
          child: _EditorToggleChip(
            label: MediaText.videoEditorCoverTool,
            icon: CupertinoIcons.photo,
            selected: false,
            onPressed: () => _handleCoverChanged(_coverTimeMs),
          ),
        ),
        SizedBox(width: AppSpacing.intraGroupSm),
        Expanded(
          child: _EditorToggleChip(
            label: MediaText.videoEditorCropTool,
            icon: CupertinoIcons.crop,
            selected: false,
            onPressed: () =>
                _handleTrimChanged(RangeValues(_trimStartMs, _trimEndMs)),
          ),
        ),
        SizedBox(width: AppSpacing.intraGroupSm),
        Expanded(
          child: _EditorToggleChip(
            label: MediaText.videoEditorMuteTool,
            icon: _muted
                ? CupertinoIcons.speaker_slash_fill
                : CupertinoIcons.speaker_slash,
            selected: _muted,
            onPressed: () => _toggleMuted(!_muted),
          ),
        ),
        SizedBox(width: AppSpacing.intraGroupSm),
        Expanded(
          child: _EditorToggleChip(
            label: MediaText.videoEditorVolumeTool,
            icon: CupertinoIcons.speaker_2,
            selected: !_muted,
            onPressed: () => _toggleMuted(false),
          ),
        ),
      ],
    );
  }

  Widget _buildPreviewTimelineSection() {
    return _EditorSection(
      title: MediaText.videoEditorPreviewTimeline,
      trailing: _formatMs(_previewTimeMs.round()),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          Text(
            MediaText.videoEditorPreviewTimelineHint,
            style: TextStyle(
              color: CupertinoColors.secondaryLabel.resolveFrom(context),
              fontSize: AppTypography.sm,
            ),
          ),
          SizedBox(height: AppSpacing.intraGroupSm),
          _buildPreviewTimelineStrip(),
          SizedBox(height: AppSpacing.intraGroupSm),
          Slider(
            value: _previewTimeMs.clamp(_trimStartMs, _trimEndMs),
            min: _trimStartMs,
            max: _trimEndMs,
            divisions: math.max(((_trimEndMs - _trimStartMs) / 80).round(), 1),
            label: _formatMs(_previewTimeMs.round()),
            onChangeStart: (_) => _beginPreviewDrag(),
            onChanged: _handlePreviewChanged,
            onChangeEnd: (value) => _endPreviewDrag(value),
          ),
          Row(
            children: <Widget>[
              Text(
                _formatMs(_trimStartMs.round()),
                style: TextStyle(
                  color: CupertinoColors.secondaryLabel.resolveFrom(context),
                  fontSize: AppTypography.sm,
                ),
              ),
              const Spacer(),
              Text(
                '${MediaText.videoEditorCurrentTimePrefix} ${_formatMs(_previewTimeMs.round())}',
                style: TextStyle(
                  color: AppColors.iosAccentLight,
                  fontSize: AppTypography.sm,
                  fontWeight: AppTypography.medium,
                ),
              ),
              const Spacer(),
              Text(
                _formatMs(_trimEndMs.round()),
                style: TextStyle(
                  color: CupertinoColors.secondaryLabel.resolveFrom(context),
                  fontSize: AppTypography.sm,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildTrimSection() {
    final maxValue = math.max(_durationMs.toDouble(), 1000.0).toDouble();
    return _EditorSection(
      title: MediaText.videoEditorTrimSegment,
      trailing:
          '${_formatMs((_trimEndMs - _trimStartMs).round())} ${MediaText.videoEditorDurationSuffix}',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          RangeSlider(
            values: RangeValues(_trimStartMs, _trimEndMs),
            min: 0,
            max: maxValue,
            divisions: math.max((_durationMs / 200).round(), 1),
            labels: RangeLabels(
              _formatMs(_trimStartMs.round()),
              _formatMs(_trimEndMs.round()),
            ),
            onChanged: _handleTrimChanged,
          ),
          Row(
            children: <Widget>[
              Text(
                '${MediaText.videoEditorStartPrefix} ${_formatMs(_trimStartMs.round())}',
                style: TextStyle(
                  color: CupertinoColors.secondaryLabel.resolveFrom(context),
                  fontSize: AppTypography.sm,
                ),
              ),
              const Spacer(),
              Text(
                '${MediaText.videoEditorEndPrefix} ${_formatMs(_trimEndMs.round())}',
                style: TextStyle(
                  color: CupertinoColors.secondaryLabel.resolveFrom(context),
                  fontSize: AppTypography.sm,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    const isDark = true;
    final background = AppColorsFunctional.getColor(
      isDark,
      ColorType.backgroundPrimary,
    );
    final showPageError = _pageErrorSemantic != null && !_loading;
    final theme = CupertinoTheme.of(context).copyWith(
      brightness: Brightness.dark,
      scaffoldBackgroundColor: background,
      barBackgroundColor: background,
    );
    return CupertinoTheme(
      data: theme,
      child: AppScaffold(
        backgroundColor: background,
        navigationBar: AppNavigationBar(
          backgroundColor: background,
          middle: Text(
            MediaText.videoEditorTitle,
            style: AppNavigationSemanticConstants.barTitleTextStyle(isDark),
          ),
          leading: AppNavigationBarIconButton(
            icon: CupertinoIcons.chevron_left,
            onPressed: () => Navigator.of(context).pop(),
          ),
          trailing: null,
        ),
        child: SafeArea(
          child: showPageError
              ? AppPageErrorState(
                  semantic: _pageErrorSemantic!,
                  onAction: (action) async {
                    if (action.type == UiErrorActionType.retry ||
                        action.type == UiErrorActionType.resubmit) {
                      await _bootstrap();
                    }
                  },
                )
              : _loading
              ? AppRequestFeedback.section()
              : ListView(
                  padding: EdgeInsets.fromLTRB(
                    AppSpacing.containerMd,
                    AppSpacing.containerMd,
                    AppSpacing.containerMd,
                    AppSpacing.containerLg,
                  ),
                  children: <Widget>[
                    _buildPreview(),
                    SizedBox(height: AppSpacing.interGroupMd),
                    _buildActionBar(),
                    SizedBox(height: AppSpacing.interGroupMd),
                    _buildPreviewTimelineSection(),
                    SizedBox(height: AppSpacing.interGroupMd),
                    _buildTrimSection(),
                    SizedBox(height: AppSpacing.interGroupMd),
                    _buildCoverSection(),
                    if (_sectionErrorSemantic != null) ...<Widget>[
                      SizedBox(height: AppSpacing.interGroupSm),
                      AppSectionErrorCard(
                        semantic: _sectionErrorSemantic!,
                        onAction: (action) async {
                          if (action.type == UiErrorActionType.retry ||
                              action.type == UiErrorActionType.resubmit) {
                            await _loadFrames();
                          }
                        },
                      ),
                    ],
                    SizedBox(height: AppSpacing.interGroupMd),
                    MediaCreationBottomButton(
                      label: MediaText.mediaPickerNextStep,
                      variant:
                          MediaCreationBottomButtonVariant.fullWidthNeutral,
                      isLoading: _saving,
                      onPressed: (_loading || _saving) ? null : _saveEditing,
                    ),
                  ],
                ),
        ),
      ),
    );
  }
}
