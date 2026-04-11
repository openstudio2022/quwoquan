import 'dart:async';
import 'dart:io';
import 'dart:math' as math;

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/constants/navigation_semantic_constants.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/ui/content/entry/services/ios_video_editing_service.dart';
import 'package:video_player/video_player.dart';

class VideoEditorResult {
  const VideoEditorResult({
    required this.videoPath,
    required this.originalVideoPath,
    required this.thumbnailPath,
    required this.durationMs,
    required this.trimStartMs,
    required this.trimEndMs,
    required this.coverTimeMs,
    required this.muted,
  });

  final String videoPath;
  final String originalVideoPath;
  final String thumbnailPath;
  final int durationMs;
  final int trimStartMs;
  final int trimEndMs;
  final int coverTimeMs;
  final bool muted;
}

/// 本地视频剪辑；持久草稿在父链 `CreateEditorState`（`ContentPublishDraftComposite`）。
/// 剪辑结果回写草稿后，发布确认页的帖子元数据预览与 `publish_draft_projection_bridge`
///（`postReadPreviewBundleFromPublishConfirmSummary` / `PostReadSurfaceId.draftPreview`）同源。
class VideoEditorPage extends StatefulWidget {
  const VideoEditorPage({
    super.key,
    required this.sourceVideoPath,
    required this.initialVideoPath,
    required this.initialThumbnailPath,
    required this.initialDurationMs,
    required this.initialTrimStartMs,
    required this.initialTrimEndMs,
    required this.initialCoverTimeMs,
    required this.initialMuted,
    this.editingService,
  });

  final String sourceVideoPath;
  final String initialVideoPath;
  final String initialThumbnailPath;
  final int initialDurationMs;
  final int initialTrimStartMs;
  final int initialTrimEndMs;
  final int initialCoverTimeMs;
  final bool initialMuted;
  final IosVideoEditingService? editingService;

  @override
  State<VideoEditorPage> createState() => _VideoEditorPageState();
}

class _VideoEditorPageState extends State<VideoEditorPage> {
  late final VideoPlayerController _controller;
  late final IosVideoEditingService _editingService;

  Timer? _frameReloadDebounce;
  Timer? _previewSeekDebounce;
  bool _loading = true;
  bool _saving = false;
  bool _framesLoading = false;
  bool _previewDragging = false;
  bool _resumePlaybackAfterScrub = false;
  String? _errorMessage;
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
    _controller = VideoPlayerController.file(File(widget.sourceVideoPath))
      ..addListener(_handlePlaybackTick);
    _bootstrap();
  }

  @override
  void dispose() {
    _frameReloadDebounce?.cancel();
    _previewSeekDebounce?.cancel();
    _controller
      ..removeListener(_handlePlaybackTick)
      ..dispose();
    super.dispose();
  }

  Future<void> _bootstrap() async {
    try {
      await _controller.initialize();
      final durationMs = math.max(
        _controller.value.duration.inMilliseconds,
        1000,
      );
      final initialStart = widget.initialTrimStartMs.clamp(0, durationMs - 100);
      final initialEnd = (widget.initialTrimEndMs > 0
              ? widget.initialTrimEndMs
              : durationMs)
          .clamp(initialStart + 100, durationMs);
      final initialCover = widget.initialCoverTimeMs > 0
          ? widget.initialCoverTimeMs.clamp(initialStart, initialEnd)
          : ((initialStart + initialEnd) / 2).round();
      if (!mounted) {
        return;
      }
      await _controller.setVolume(widget.initialMuted ? 0 : 1);
      setState(() {
        _durationMs = durationMs;
        _trimStartMs = initialStart.toDouble();
        _trimEndMs = initialEnd.toDouble();
        _coverTimeMs = initialCover.toDouble();
        _previewTimeMs = initialStart.toDouble();
        _muted = widget.initialMuted;
        _loading = false;
      });
      await _loadFrames();
      await _seekToCurrentRangeStart();
    } catch (_) {
      if (!mounted) {
        return;
      }
      setState(() {
        _loading = false;
        _errorMessage = '暂时无法加载视频预览，但仍可返回重新选择素材。';
      });
    }
  }

  Future<void> _loadFrames() async {
    setState(() {
      _framesLoading = true;
      _errorMessage = null;
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
      });
    } catch (_) {
      if (!mounted) {
        return;
      }
      setState(() {
        _framesLoading = false;
        _errorMessage = '时间轴帧加载失败，请稍后再试。';
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
    if (!_controller.value.isInitialized) {
      return;
    }
    await _controller.seekTo(Duration(milliseconds: _trimStartMs.round()));
  }

  void _handlePlaybackTick() {
    if (!_controller.value.isInitialized) {
      return;
    }
    final positionMs = _controller.value.position.inMilliseconds;
    if (positionMs > _trimEndMs.round()) {
      _controller.pause();
      _controller.seekTo(Duration(milliseconds: _trimStartMs.round()));
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
    if (!_controller.value.isInitialized) {
      return;
    }
    if (_controller.value.isPlaying) {
      await _controller.pause();
      return;
    }
    final positionMs = _controller.value.position.inMilliseconds;
    if (positionMs < _trimStartMs.round() || positionMs >= _trimEndMs.round()) {
      await _controller.seekTo(Duration(milliseconds: _trimStartMs.round()));
    }
    await _controller.play();
  }

  Future<void> _toggleMuted(bool value) async {
    setState(() {
      _muted = value;
    });
    if (_controller.value.isInitialized) {
      await _controller.setVolume(value ? 0 : 1);
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
    _frameReloadDebounce = Timer(const Duration(milliseconds: 180), _loadFrames);
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

  Future<void> _resetEditing() async {
    final initialEnd = _normalizedInitialEndMs.toDouble();
    setState(() {
      _trimStartMs = widget.initialTrimStartMs.toDouble();
      _trimEndMs = initialEnd;
      _coverTimeMs = (widget.initialCoverTimeMs > 0
              ? widget.initialCoverTimeMs
              : ((widget.initialTrimStartMs + initialEnd) / 2).round())
          .clamp(widget.initialTrimStartMs, initialEnd)
          .toDouble();
      _previewTimeMs = widget.initialTrimStartMs.toDouble();
      _muted = widget.initialMuted;
      _selectedCoverPath = widget.initialThumbnailPath.trim();
    });
    if (_controller.value.isInitialized) {
      await _controller.setVolume(_muted ? 0 : 1);
      await _controller.seekTo(Duration(milliseconds: _trimStartMs.round()));
    }
    await _loadFrames();
  }

  Future<void> _saveEditing() async {
    if (_saving) {
      return;
    }
    setState(() {
      _saving = true;
      _errorMessage = null;
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
      Navigator.of(context).pop(
        VideoEditorResult(
          videoPath: nextVideoPath,
          originalVideoPath: widget.sourceVideoPath,
          thumbnailPath: nextCoverPath,
          durationMs: _durationMs,
          trimStartMs: _trimStartMs.round(),
          trimEndMs: _trimEndMs.round(),
          coverTimeMs: _coverTimeMs.round(),
          muted: _muted,
        ),
      );
    } catch (_) {
      if (!mounted) {
        return;
      }
      setState(() {
        _errorMessage = '视频导出失败，请稍后重试。';
      });
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
    _resumePlaybackAfterScrub = _controller.value.isPlaying;
    if (_resumePlaybackAfterScrub) {
      await _controller.pause();
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
    if (_resumePlaybackAfterScrub && _controller.value.isInitialized) {
      await _controller.play();
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
    final clampedMs = targetMs.clamp(
      _trimStartMs.round(),
      _trimEndMs.round(),
    );
    _previewSeekDebounce?.cancel();
    if (immediate) {
      if (_controller.value.isInitialized) {
        await _controller.seekTo(Duration(milliseconds: clampedMs));
      }
      return;
    }
    _previewSeekDebounce = Timer(const Duration(milliseconds: 24), () async {
      if (!_controller.value.isInitialized) {
        return;
      }
      await _controller.seekTo(Duration(milliseconds: clampedMs));
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
    final isDark =
        CupertinoTheme.of(context).brightness == Brightness.dark;
    final scrim = AppColorsFunctional.getColor(isDark, ColorType.black)
        .withValues(alpha: 0.38);
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
    final isDark =
        CupertinoTheme.of(context).brightness == Brightness.dark;
    final scrimBlack = AppColorsFunctional.getColor(isDark, ColorType.black);
    final onVideoFg = AppColorsFunctional.getColor(
      isDark,
      ColorType.mediaThumbnailOverlayForeground,
    );
    final playRingBorder = AppColorsFunctional.getColor(isDark, ColorType.white)
        .withValues(alpha: 0.12);
    final aspectRatio = _controller.value.isInitialized
        ? _controller.value.aspectRatio.clamp(0.56, 1.8).toDouble()
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
              if (_controller.value.isInitialized)
                VideoPlayer(_controller)
              else if (_selectedCoverPath.isNotEmpty)
                Image.file(
                  File(_selectedCoverPath),
                  fit: BoxFit.cover,
                  errorBuilder: (context, error, stackTrace) => const ColoredBox(
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
                      _controller.value.isPlaying
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
                      _buildHeaderBadge(context, '已静音'),
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
                    '封面 ${_formatMs(_coverTimeMs.round())}',
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
            label: _muted ? '已静音' : '保留原声',
            icon: _muted ? CupertinoIcons.speaker_slash : CupertinoIcons.speaker_2,
            selected: _muted,
            onPressed: () => _toggleMuted(!_muted),
          ),
        ),
        SizedBox(width: AppSpacing.intraGroupSm),
        Expanded(
          child: _EditorToggleChip(
            label: '恢复初始编辑',
            icon: CupertinoIcons.arrow_counterclockwise,
            selected: false,
            onPressed: _resetEditing,
          ),
        ),
      ],
    );
  }

  Widget _buildPreviewTimelineSection() {
    return _EditorSection(
      title: '播放头预览',
      trailing: _formatMs(_previewTimeMs.round()),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          Text(
            '拖动播放头，边拖边看当前帧',
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
                '当前 ${_formatMs(_previewTimeMs.round())}',
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

  Widget _buildPreviewTimelineStrip() {
    if (_frames.isEmpty) {
      return Container(
        height: AppSpacing.buttonHeight + AppSpacing.lg + AppSpacing.xs,
        decoration: BoxDecoration(
          color: CupertinoColors.systemBackground.resolveFrom(context),
          borderRadius: BorderRadius.circular(AppSpacing.containerSm),
        ),
        alignment: Alignment.center,
        child: Text(
          _framesLoading ? '正在缓存更细颗粒度视频帧...' : '暂无可用预览帧',
          style: TextStyle(
            color: CupertinoColors.secondaryLabel.resolveFrom(context),
            fontSize: AppTypography.sm,
          ),
        ),
      );
    }
    return LayoutBuilder(
      builder: (context, constraints) {
        final isDark =
            CupertinoTheme.of(context).brightness == Brightness.dark;
        final playheadRing = AppColorsFunctional.getColor(
          isDark,
          ColorType.white,
        );
        final width = constraints.maxWidth;
        final fraction = ((_previewTimeMs - _trimStartMs) /
                math.max(_trimEndMs - _trimStartMs, 1))
            .clamp(0.0, 1.0);
        final playheadLeft = width * fraction;

        Future<void> previewAtOffset(double dx) async {
          final value = _timelineValueForDx(dx, width);
          _handlePreviewChanged(value);
        }

        return GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTapDown: (details) async {
            await _beginPreviewDrag();
            await previewAtOffset(details.localPosition.dx);
            await _endPreviewDrag();
          },
          onHorizontalDragStart: (_) => _beginPreviewDrag(),
          onHorizontalDragUpdate: (details) => previewAtOffset(details.localPosition.dx),
          onHorizontalDragEnd: (_) => _endPreviewDrag(),
          child: SizedBox(
            height: AppSpacing.buttonHeight + AppSpacing.lg + AppSpacing.xs,
            child: Stack(
              children: <Widget>[
                ClipRRect(
                  borderRadius: BorderRadius.circular(AppSpacing.containerSm),
                  child: Row(
                    children: _frames
                        .map(
                          (frame) => Expanded(
                            child: Image.file(
                              File(frame.path),
                              fit: BoxFit.cover,
                              errorBuilder: (context, error, stackTrace) =>
                                  const ColoredBox(
                                color: AppColors.createMediaFallbackGradientBottom,
                              ),
                            ),
                          ),
                        )
                        .toList(growable: false),
                  ),
                ),
                Positioned.fill(
                  child: DecoratedBox(
                    decoration: BoxDecoration(
                      borderRadius: BorderRadius.circular(AppSpacing.containerSm),
                      border: Border.all(
                        color: CupertinoColors.separator
                            .resolveFrom(context)
                            .withValues(alpha: 0.16),
                        width: AppSpacing.hairline,
                      ),
                    ),
                  ),
                ),
                Positioned(
                  left: (playheadLeft - AppSpacing.oneHalf).clamp(
                    0.0,
                    math.max(width - AppSpacing.three, 0.0),
                  ),
                  top: 0,
                  bottom: 0,
                  child: Container(
                    width: AppSpacing.three,
                    decoration: BoxDecoration(
                      color: AppColors.iosAccentLight,
                      borderRadius: BorderRadius.circular(
                        AppSpacing.radiusNinetyNine,
                      ),
                      boxShadow: <BoxShadow>[
                        BoxShadow(
                          color: AppColors.iosAccentLight.withValues(alpha: 0.32),
                          blurRadius: 10,
                        ),
                      ],
                    ),
                  ),
                ),
                Positioned(
                  left: (playheadLeft - AppSpacing.eighteen / 2).clamp(
                    0.0,
                    math.max(width - AppSpacing.eighteen, 0.0),
                  ),
                  top: AppSpacing.six,
                  child: Container(
                    width: AppSpacing.eighteen,
                    height: AppSpacing.eighteen,
                    decoration: BoxDecoration(
                      color: AppColors.iosAccentLight,
                      shape: BoxShape.circle,
                      border: Border.all(
                        color: playheadRing,
                        width: AppSpacing.two,
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  Widget _buildTrimSection() {
    final maxValue = math.max(_durationMs.toDouble(), 1000.0).toDouble();
    return _EditorSection(
      title: '裁切片段',
      trailing: '${_formatMs((_trimEndMs - _trimStartMs).round())} 时长',
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
                '开始 ${_formatMs(_trimStartMs.round())}',
                style: TextStyle(
                  color: CupertinoColors.secondaryLabel.resolveFrom(context),
                  fontSize: AppTypography.sm,
                ),
              ),
              const Spacer(),
              Text(
                '结束 ${_formatMs(_trimEndMs.round())}',
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

  Widget _buildCoverSection() {
    return _EditorSection(
      title: '封面时间轴',
      trailing: _framesLoading ? '生成中' : '${_frames.length} 帧',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          Slider(
            value: _coverTimeMs.clamp(_trimStartMs, _trimEndMs),
            min: _trimStartMs,
            max: _trimEndMs,
            divisions: math.max(((_trimEndMs - _trimStartMs) / 120).round(), 1),
            label: _formatMs(_coverTimeMs.round()),
            onChanged: _handleCoverChanged,
          ),
          SizedBox(height: AppSpacing.intraGroupXs),
          SizedBox(
            height:
                AppSpacing.largeAvatarSize + AppSpacing.lg + AppSpacing.xs,
            child: _frames.isEmpty
                ? Center(
                    child: Text(
                      _framesLoading ? '正在生成视频帧...' : '暂无可选封面帧',
                      style: TextStyle(
                        color: CupertinoColors.secondaryLabel.resolveFrom(
                          context,
                        ),
                        fontSize: AppTypography.sm,
                      ),
                    ),
                  )
                : ListView.separated(
                    scrollDirection: Axis.horizontal,
                    itemCount: _frames.length,
                    separatorBuilder: (_, _) =>
                        SizedBox(width: AppSpacing.intraGroupSm),
                    itemBuilder: (context, index) {
                      final isDark =
                          CupertinoTheme.of(context).brightness ==
                              Brightness.dark;
                      final scrimBlack = AppColorsFunctional.getColor(
                        isDark,
                        ColorType.black,
                      );
                      final onVideoFg = AppColorsFunctional.getColor(
                        isDark,
                        ColorType.mediaThumbnailOverlayForeground,
                      );
                      final frame = _frames[index];
                      final selected =
                          frame.timeMs == _closestFrameTo(
                            _coverTimeMs.round(),
                            _frames,
                          )?.timeMs;
                      return GestureDetector(
                        onTap: () => _selectFrame(frame),
                        child: AnimatedContainer(
                          duration: const Duration(milliseconds: 180),
                          width: AppSpacing.largeAvatarSize + AppSpacing.ten,
                          padding: EdgeInsets.all(
                            selected ? AppSpacing.two : 0,
                          ),
                          decoration: BoxDecoration(
                            color: CupertinoColors
                                .secondarySystemGroupedBackground
                                .resolveFrom(context),
                            borderRadius: BorderRadius.circular(
                              AppSpacing.containerSm,
                            ),
                            border: Border.all(
                              color: selected
                                  ? AppColors.iosAccentLight
                                  : CupertinoColors.separator
                                        .resolveFrom(context)
                                        .withValues(alpha: 0.16),
                              width: selected
                                  ? AppSpacing.oneHalf
                                  : AppSpacing.hairline,
                            ),
                          ),
                          child: ClipRRect(
                            borderRadius: BorderRadius.circular(
                              AppSpacing.containerSm - 2,
                            ),
                            child: Stack(
                              fit: StackFit.expand,
                              children: <Widget>[
                                Image.file(
                                  File(frame.path),
                                  fit: BoxFit.cover,
                                  errorBuilder: (context, error, stackTrace) =>
                                      const ColoredBox(
                                    color:
                                        AppColors.createMediaFallbackGradientBottom,
                                  ),
                                ),
                                Positioned(
                                  left: AppSpacing.intraGroupXs,
                                  right: AppSpacing.intraGroupXs,
                                  bottom: AppSpacing.intraGroupXs,
                                  child: DecoratedBox(
                                    decoration: BoxDecoration(
                                      color: scrimBlack.withValues(alpha: 0.44),
                                      borderRadius: BorderRadius.circular(
                                        AppSpacing.radiusTwenty,
                                      ),
                                    ),
                                    child: Padding(
                                      padding: EdgeInsets.symmetric(
                                        horizontal: AppSpacing.intraGroupXs,
                                        vertical: AppSpacing.intraGroupXs / 2,
                                      ),
                                      child: Text(
                                        _formatMs(frame.timeMs),
                                        textAlign: TextAlign.center,
                                        style: TextStyle(
                                          color: onVideoFg,
                                          fontSize: AppTypography.xsPlus,
                                          fontWeight: AppTypography.medium,
                                        ),
                                      ),
                                    ),
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ),
                      );
                    },
                  ),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final background = CupertinoColors.systemGroupedBackground.resolveFrom(
      context,
    );
    final isDark =
        CupertinoTheme.of(context).brightness == Brightness.dark;
    return AppScaffold(
      backgroundColor: background,
      navigationBar: AppNavigationBar(
        backgroundColor: background,
        middle: Text(
          '视频编辑',
          style: AppNavigationSemanticConstants.barTitleTextStyle(isDark),
        ),
        leading: AppNavigationBarIconButton(
          icon: CupertinoIcons.xmark,
          onPressed: () => Navigator.of(context).pop(),
        ),
        trailing: CupertinoButton(
          padding: EdgeInsets.zero,
          onPressed: (_loading || _saving) ? null : _saveEditing,
          child: _saving
              ? const CupertinoActivityIndicator()
              : const Text('完成'),
        ),
      ),
      child: SafeArea(
        child: _loading
            ? const Center(child: CupertinoActivityIndicator())
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
                  if (_errorMessage != null) ...<Widget>[
                    SizedBox(height: AppSpacing.interGroupSm),
                    Text(
                      _errorMessage!,
                      style: TextStyle(
                        color: CupertinoColors.destructiveRed.resolveFrom(
                          context,
                        ),
                        fontSize: AppTypography.sm,
                      ),
                    ),
                  ],
                ],
              ),
      ),
    );
  }
}

class _EditorSection extends StatelessWidget {
  const _EditorSection({
    required this.title,
    required this.child,
    this.trailing,
  });

  final String title;
  final String? trailing;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.all(AppSpacing.containerMd),
      decoration: BoxDecoration(
        color: CupertinoColors.secondarySystemGroupedBackground.resolveFrom(
          context,
        ),
        borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          Row(
            children: <Widget>[
              Text(
                title,
                style: const TextStyle(
                  fontSize: AppTypography.base,
                  fontWeight: AppTypography.semiBold,
                ),
              ),
              const Spacer(),
              if (trailing != null)
                Text(
                  trailing!,
                  style: TextStyle(
                    color: CupertinoColors.secondaryLabel.resolveFrom(context),
                    fontSize: AppTypography.sm,
                  ),
                ),
            ],
          ),
          SizedBox(height: AppSpacing.intraGroupSm),
          child,
        ],
      ),
    );
  }
}

class _EditorToggleChip extends StatelessWidget {
  const _EditorToggleChip({
    required this.label,
    required this.icon,
    required this.selected,
    required this.onPressed,
  });

  final String label;
  final IconData icon;
  final bool selected;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return CupertinoButton(
      padding: EdgeInsets.zero,
      onPressed: onPressed,
      child: Container(
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.containerSm,
          vertical: AppSpacing.containerSm,
        ),
        decoration: BoxDecoration(
          color: selected
              ? AppColors.iosAccentLight.withValues(alpha: 0.12)
              : CupertinoColors.secondarySystemGroupedBackground.resolveFrom(
                  context,
                ),
          borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
          border: Border.all(
            color: selected
                ? AppColors.iosAccentLight.withValues(alpha: 0.28)
                : CupertinoColors.separator
                      .resolveFrom(context)
                      .withValues(alpha: 0.16),
            width: AppSpacing.hairline,
          ),
        ),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: <Widget>[
            Icon(
              icon,
              size: AppSpacing.iconMedium,
              color: selected
                  ? AppColors.iosAccentLight
                  : CupertinoColors.label.resolveFrom(context),
            ),
            SizedBox(width: AppSpacing.intraGroupXs),
            Flexible(
              child: Text(
                label,
                textAlign: TextAlign.center,
                style: TextStyle(
                  color: selected
                      ? AppColors.iosAccentLight
                      : CupertinoColors.label.resolveFrom(context),
                  fontSize: AppTypography.base,
                  fontWeight: AppTypography.medium,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
