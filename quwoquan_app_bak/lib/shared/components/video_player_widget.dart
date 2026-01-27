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

  @override
  void initState() {
    super.initState();
    _initializeVideo();
  }

  @override
  void dispose() {
    _chewieController?.dispose();
    _controller?.dispose();
    super.dispose();
  }

  Future<void> _initializeVideo() async {
    try {
      _controller = VideoPlayerController.networkUrl(
        Uri.parse(widget.videoUrl),
      );

      await _controller!.initialize();
      
      if (mounted) {
        setState(() {
          _isInitialized = true;
        });

        // 通知父组件控制器已创建
        widget.onControllerCreated?.call(_controller!);

        // 如果设置了自动播放，则开始播放
        if (widget.autoPlay) {
          _controller!.play();
        }

        // 创建Chewie控制器
        _chewieController = ChewieController(
          videoPlayerController: _controller!,
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
          placeholder: widget.thumbnailUrl != null
              ? Image.network(
                  widget.thumbnailUrl!,
                  fit: BoxFit.cover,
                  errorBuilder: (context, error, stackTrace) {
                    return _buildVideoPlaceholder();
                  },
                )
              : _buildVideoPlaceholder(),
        );
      }
    } catch (e) {
      if (mounted) {
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
          Icon(
            Icons.error_outline,
            size: (AppSpacing.avatarSize * 1.5).sp,
            color: AppColors.error,
          ),
          SizedBox(height: AppSpacing.sm.h),
          Text(
            '视频加载失败',
            style: TextStyle(
              color: AppColors.error,
              fontSize: AppTypography.sm.sp,
            ),
          ),
          SizedBox(height: AppSpacing.xs.h),
          Text(
            '请检查网络连接',
            style: TextStyle(
              color: AppColors.white.withOpacity(0.7),
              fontSize: AppTypography.xs.sp,
            ),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    if (_hasError) {
      return _buildErrorWidget();
    }

    if (!_isInitialized || _chewieController == null) {
      return _buildVideoPlaceholder();
    }

    return GestureDetector(
      onTap: widget.onTap,
      child: Container(
        width: double.infinity,
        height: double.infinity,
        color: AppColors.black,
        child: AspectRatio(
          aspectRatio: widget.aspectRatio ?? _controller!.value.aspectRatio,
          child: Chewie(controller: _chewieController!),
        ),
      ),
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
  static ChewieController? getChewieController(String videoUrl, {
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
