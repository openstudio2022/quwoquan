// ignore_for_file: deprecated_member_use

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:video_player/video_player.dart';
import 'package:chewie/chewie.dart';

import 'package:quwoquan_app/core/quwoquan_core.dart';

/// 视频播放器组件
/// 继承自侵入式媒体浏览器，支持视频播放功能
class VideoPlayerWidget extends ConsumerStatefulWidget {
  final String videoUrl;
  final String? thumbnailUrl;
  final bool autoPlay;
  final bool showControls;
  final VoidCallback? onTap;
  final VoidCallback? onFullScreen;
  final Function(VideoPlayerController)? onControllerCreated;
  final double? aspectRatio;

  const VideoPlayerWidget({
    super.key,
    required this.videoUrl,
    this.thumbnailUrl,
    this.autoPlay = false,
    this.showControls = true,
    this.onTap,
    this.onFullScreen,
    this.onControllerCreated,
    this.aspectRatio,
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
    _initializeVideo();
  }

  @override
  void didUpdateWidget(covariant VideoPlayerWidget oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.videoUrl != oldWidget.videoUrl) {
      _replaceVideoController();
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
    try {
      final controller = VideoPlayerController.networkUrl(
        Uri.parse(widget.videoUrl),
      );
      _controller = controller;

      await controller.initialize();

      if (mounted &&
          generation == _videoInitGeneration &&
          identical(_controller, controller)) {
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
      }
    } catch (e) {
      if (mounted && generation == _videoInitGeneration) {
        setState(() {
          _hasError = true;
        });
      }
    }
  }

  Widget _buildVideoPlaceholder() {
    return Container(
      width: double.infinity,
      height: double.infinity,
      color: AppColors.black,
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(
            Icons.play_circle_outline,
            size: (AppSpacing.avatarSize * 2).sp,
            color: AppColors.white,
          ),
          SizedBox(height: AppSpacing.sm.h),
          Text(
            '视频加载中...',
            style: TextStyle(
              color: AppColors.white,
              fontSize: AppTypography.sm.sp,
            ),
          ),
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
            '视频暂时没加载出来',
            style: TextStyle(
              color: AppColors.white.withValues(alpha: 0.88),
              fontSize: AppTypography.sm.sp,
            ),
          ),
          SizedBox(height: AppSpacing.xs.h),
          Text(
            UITextConstants.checkNetworkAndTryAgain,
            style: TextStyle(
              color: AppColors.white.withOpacity(0.7),
              fontSize: AppTypography.xs.sp,
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

/// 视频播放器控制器管理
class VideoPlayerManager {
  static final Map<String, VideoPlayerController> _controllers = {};
  static final Map<String, ChewieController> _chewieControllers = {};

  /// 获取或创建视频控制器
  static Future<VideoPlayerController?> getController(String videoUrl) async {
    if (_controllers.containsKey(videoUrl)) {
      return _controllers[videoUrl];
    }

    try {
      final controller = VideoPlayerController.networkUrl(Uri.parse(videoUrl));
      await controller.initialize();
      _controllers[videoUrl] = controller;
      return controller;
    } catch (e) {
      debugPrint('Failed to initialize video controller: $e');
      return null;
    }
  }

  /// 获取或创建Chewie控制器
  static ChewieController? getChewieController(
    String videoUrl, {
    bool autoPlay = false,
    bool showControls = true,
  }) {
    if (_chewieControllers.containsKey(videoUrl)) {
      return _chewieControllers[videoUrl];
    }

    final videoController = _controllers[videoUrl];
    if (videoController == null) return null;

    final chewieController = ChewieController(
      videoPlayerController: videoController,
      autoPlay: autoPlay,
      looping: false,
      showControls: showControls,
      showOptions: false,
      showControlsOnInitialize: false,
      materialProgressColors: ChewieProgressColors(
        playedColor: AppColors.primaryColor,
        handleColor: AppColors.primaryColor,
        backgroundColor: AppColors.overlayMedium,
        bufferedColor: AppColors.overlayLight,
      ),
    );

    _chewieControllers[videoUrl] = chewieController;
    return chewieController;
  }

  /// 释放控制器
  static void disposeController(String videoUrl) {
    _chewieControllers[videoUrl]?.dispose();
    _controllers[videoUrl]?.dispose();
    _chewieControllers.remove(videoUrl);
    _controllers.remove(videoUrl);
  }

  /// 释放所有控制器
  static void disposeAll() {
    for (final controller in _chewieControllers.values) {
      controller.dispose();
    }
    for (final controller in _controllers.values) {
      controller.dispose();
    }
    _chewieControllers.clear();
    _controllers.clear();
  }
}
