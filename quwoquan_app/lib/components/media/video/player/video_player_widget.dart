import 'dart:developer' as developer;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:video_player/video_player.dart';
import 'package:chewie/chewie.dart';

import 'package:quwoquan_app/core/media/content_media_url.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/widgets/app_cached_network_image.dart';

/// 视频播放器组件
/// 继承自侵入式媒体浏览器，支持视频播放功能
class VideoPlayerWidget extends ConsumerStatefulWidget {
  final String videoUrl;
  final List<String>? videoUrlCandidates;
  final String? thumbnailUrl;
  final bool initialize;
  final bool autoPlay;
  final bool showControls;
  final VoidCallback? onTap;
  final VoidCallback? onFullScreen;
  final Function(VideoPlayerController)? onControllerCreated;
  final double? aspectRatio;

  /// 任务 B · 播放启动成功回调：startupLatency 为从初始化到可播放的耗时，
  /// candidateIndex 为命中的候选源序号（用于自动播放启动时延度量）。
  final void Function(Duration startupLatency, int candidateIndex)?
  onPlaybackStarted;

  /// 任务 B · 播放失败回调：candidatesTried 为已尝试的候选源数量（候选全部失败）。
  final void Function(int candidatesTried)? onPlaybackFailed;

  const VideoPlayerWidget({
    super.key,
    required this.videoUrl,
    this.videoUrlCandidates,
    this.thumbnailUrl,
    this.initialize = true,
    this.autoPlay = false,
    this.showControls = true,
    this.onTap,
    this.onFullScreen,
    this.onControllerCreated,
    this.aspectRatio,
    this.onPlaybackStarted,
    this.onPlaybackFailed,
  });

  @override
  ConsumerState<VideoPlayerWidget> createState() => _VideoPlayerWidgetState();
}

class _VideoPlayerWidgetState extends ConsumerState<VideoPlayerWidget> {
  VideoPlayerController? _controller;
  ChewieController? _chewieController;
  bool _isInitialized = false;
  bool _hasError = false;
  int _videoInitGeneration = 0;

  @override
  void initState() {
    super.initState();
    if (widget.initialize) {
      _initializeVideo();
    }
  }

  @override
  void didUpdateWidget(covariant VideoPlayerWidget oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.videoUrl != oldWidget.videoUrl ||
        !_sameStringList(
          widget.videoUrlCandidates,
          oldWidget.videoUrlCandidates,
        )) {
      if (widget.initialize) {
        _replaceVideoController();
      } else {
        _disposeActiveControllers();
        setState(() {
          _isInitialized = false;
          _hasError = false;
        });
      }
      return;
    }
    if (widget.initialize != oldWidget.initialize) {
      if (widget.initialize) {
        _initializeVideo();
      } else {
        _disposeActiveControllers();
        setState(() {
          _isInitialized = false;
          _hasError = false;
        });
      }
      return;
    }
    if (widget.autoPlay != oldWidget.autoPlay) {
      _syncPlaybackWithAutoPlay();
    }
  }

  @override
  void dispose() {
    _videoInitGeneration += 1;
    _chewieController?.dispose();
    _controller?.dispose();
    super.dispose();
  }

  void _disposeActiveControllers() {
    _chewieController?.dispose();
    _chewieController = null;
    _controller?.dispose();
    _controller = null;
  }

  void _replaceVideoController() {
    _disposeActiveControllers();
    setState(() {
      _isInitialized = false;
      _hasError = false;
    });
    _initializeVideo();
  }

  void _syncPlaybackWithAutoPlay() {
    final controller = _controller;
    if (!_isInitialized || controller == null) {
      return;
    }
    if (widget.autoPlay) {
      controller.play();
    } else {
      controller.pause();
    }
  }

  Future<void> _initializeVideo() async {
    final generation = _videoInitGeneration + 1;
    _videoInitGeneration = generation;
    final candidates = _resolvedVideoUrlCandidates;
    if (candidates.isEmpty) {
      if (mounted && generation == _videoInitGeneration) {
        setState(() {
          _hasError = true;
        });
      }
      widget.onPlaybackFailed?.call(0);
      return;
    }
    // 任务 B · 自动播放启动时延：从初始化起算，命中候选时上报耗时与序号。
    final startupStopwatch = Stopwatch()..start();
    for (var index = 0; index < candidates.length; index++) {
      final candidate = candidates[index];
      VideoPlayerController? controller;
      try {
        controller = VideoPlayerController.networkUrl(Uri.parse(candidate));
        await controller.initialize();
      } catch (error, stackTrace) {
        await controller?.dispose();
        // 任务 B · 候选源失败结构化归因：逐个回退、记录失败序号，禁止静默吞错。
        developer.log(
          'video candidate init failed '
          '(index=${index + 1}/${candidates.length})',
          name: 'VideoPlayerWidget',
          error: error,
          stackTrace: stackTrace,
        );
        continue;
      }
      if (!mounted || generation != _videoInitGeneration) {
        await controller.dispose();
        return;
      }
      _controller = controller;
      _chewieController = ChewieController(
        videoPlayerController: controller,
        autoPlay: widget.autoPlay,
        looping: false,
        showControls: widget.showControls,
        showOptions: false,
        showControlsOnInitialize: false,
        materialProgressColors: ChewieProgressColors(
          playedColor: AppColors.primaryColor,
          handleColor: AppColors.primaryColor,
          backgroundColor: AppColors.overlayMedium,
          bufferedColor: AppColors.overlayLight,
        ),
        placeholder: _buildVideoPlaceholder(),
      );
      setState(() {
        _isInitialized = true;
      });

      // 通知父组件控制器已创建
      widget.onControllerCreated?.call(controller);

      // 如果设置了自动播放，则开始播放
      _syncPlaybackWithAutoPlay();

      startupStopwatch.stop();
      widget.onPlaybackStarted?.call(startupStopwatch.elapsed, index);
      return;
    }
    startupStopwatch.stop();
    if (mounted && generation == _videoInitGeneration) {
      setState(() {
        _hasError = true;
      });
    }
    // 任务 B · 候选源全部失败：结构化记录并上报，供异常面板度量。
    developer.log(
      'video init failed: all ${candidates.length} candidate(s) exhausted',
      name: 'VideoPlayerWidget',
    );
    widget.onPlaybackFailed?.call(candidates.length);
  }

  List<String> get _resolvedVideoUrlCandidates {
    final values = <String>[...?widget.videoUrlCandidates, widget.videoUrl];
    final seen = <String>{};
    final result = <String>[];
    for (final value in values) {
      final normalized = value.trim();
      if (normalized.isEmpty || !seen.add(normalized)) {
        continue;
      }
      result.add(normalized);
    }
    return result;
  }

  bool _sameStringList(List<String>? left, List<String>? right) {
    final a = left ?? const <String>[];
    final b = right ?? const <String>[];
    if (a.length != b.length) {
      return false;
    }
    for (var i = 0; i < a.length; i++) {
      if (a[i] != b[i]) {
        return false;
      }
    }
    return true;
  }

  Widget _buildVideoPlaceholder() {
    final thumbnailUrl = widget.thumbnailUrl?.trim() ?? '';
    return Container(
      width: double.infinity,
      height: double.infinity,
      color: AppColors.black,
      child: Stack(
        fit: StackFit.expand,
        children: [
          if (thumbnailUrl.isNotEmpty)
            Positioned.fill(
              child: AppCachedNetworkImage(
                imageUrl: thumbnailUrl,
                imageUrlCandidates: resolveContentMediaUrlCandidates(
                  thumbnailUrl,
                ),
                fit: BoxFit.cover,
                placeholder: const SizedBox.shrink(),
                errorWidget: const SizedBox.shrink(),
              ),
            ),
          ColoredBox(color: AppColors.black.withValues(alpha: 0.22)),
          Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(
                Icons.play_circle_outline,
                size: (AppSpacing.avatarSize * 2).sp,
                color: AppColors.white,
              ),
              SizedBox(height: AppSpacing.sm.h),
              Text(
                UITextConstants.loading,
                style: TextStyle(
                  color: AppColors.white,
                  fontSize: AppTypography.sm.sp,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildDeferredWidget() {
    final thumbnailUrl = widget.thumbnailUrl?.trim() ?? '';
    return ColoredBox(
      color: AppColors.black,
      child: Stack(
        fit: StackFit.expand,
        children: [
          if (thumbnailUrl.isNotEmpty)
            AppCachedNetworkImage(
              imageUrl: thumbnailUrl,
              imageUrlCandidates: resolveContentMediaUrlCandidates(
                thumbnailUrl,
              ),
              fit: BoxFit.cover,
              placeholder: const SizedBox.shrink(),
              errorWidget: const SizedBox.shrink(),
            ),
          ColoredBox(color: AppColors.black.withValues(alpha: 0.16)),
        ],
      ),
    );
  }

  Widget _buildErrorWidget() {
    return Container(
      width: double.infinity,
      height: double.infinity,
      color: AppColors.black,
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Container(
            width: AppSpacing.sm.w,
            height: AppSpacing.sm.w,
            decoration: BoxDecoration(
              color: AppColors.white.withValues(alpha: 0.42),
              shape: BoxShape.circle,
            ),
          ),
          SizedBox(height: AppSpacing.sm.h),
          Text(
            UITextConstants.videoPlaybackFailed,
            style: TextStyle(
              color: AppColors.white.withValues(alpha: 0.88),
              fontSize: AppTypography.sm.sp,
            ),
          ),
          SizedBox(height: AppSpacing.xs.h),
          Text(
            UITextConstants.checkNetworkAndTryAgain,
            style: TextStyle(
              color: AppColors.white.withValues(alpha: 0.7),
              fontSize: AppTypography.xs.sp,
            ),
          ),
          SizedBox(height: AppSpacing.sm.h),
          // 任务 B · 视频加载失败可手动重试：重新串行回退候选源。
          GestureDetector(
            key: const ValueKey<String>('video-player-retry'),
            onTap: _replaceVideoController,
            child: Container(
              padding: EdgeInsets.symmetric(
                horizontal: AppSpacing.md.w,
                vertical: AppSpacing.xs.h,
              ),
              decoration: BoxDecoration(
                color: AppColors.white.withValues(alpha: 0.16),
                borderRadius: BorderRadius.circular(
                  AppSpacing.largeBorderRadius,
                ),
              ),
              child: Text(
                UITextConstants.retry,
                style: TextStyle(
                  color: AppColors.white,
                  fontSize: AppTypography.sm.sp,
                  fontWeight: AppTypography.semiBold,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  double get _resolvedAspectRatio {
    final widgetRatio = widget.aspectRatio;
    if (widgetRatio != null && widgetRatio > 0) {
      return widgetRatio;
    }
    final controllerRatio = _controller?.value.aspectRatio ?? 0;
    if (controllerRatio > 0) {
      return controllerRatio;
    }
    return 16 / 9;
  }

  Widget _buildCenteredVideoFrame(Widget child) {
    return ColoredBox(
      color: AppColors.black,
      child: Center(
        child: AspectRatio(aspectRatio: _resolvedAspectRatio, child: child),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.initialize) {
      return _buildCenteredVideoFrame(_buildDeferredWidget());
    }

    if (_hasError) {
      return _buildCenteredVideoFrame(_buildErrorWidget());
    }

    if (!_isInitialized || _chewieController == null) {
      return _buildCenteredVideoFrame(_buildVideoPlaceholder());
    }

    return GestureDetector(
      onTap: widget.onTap,
      child: _buildCenteredVideoFrame(Chewie(controller: _chewieController!)),
    );
  }
}

/// 视频播放器控制器管理（按 url 释放单个控制器）。
class VideoPlayerManager {
  static final Map<String, VideoPlayerController> _controllers = {};
  static final Map<String, ChewieController> _chewieControllers = {};

  /// 释放控制器
  static void disposeController(String videoUrl) {
    _chewieControllers[videoUrl]?.dispose();
    _controllers[videoUrl]?.dispose();
    _chewieControllers.remove(videoUrl);
    _controllers.remove(videoUrl);
  }
}
