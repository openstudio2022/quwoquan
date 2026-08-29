part of 'video_player_widget.dart';

/// 播放器状态的展示投影；控制器生命周期仍由主 State 单轨持有。
extension _VideoPlayerWidgetPresentation on _VideoPlayerWidgetState {
  Widget _buildVideoPlaceholder() {
    return VideoPlayerSurfaceBuilder.buildPlaceholder(
      thumbnailBinding: widget.thumbnailBinding,
      autoPlay: widget.autoPlay,
      showProgress: _showCompactProgress,
      showSlowHint: _isInitializationSlow,
    );
  }

  Widget _buildDeferredWidget() {
    return VideoPlayerSurfaceBuilder.buildDeferred(
      thumbnailBinding: widget.thumbnailBinding,
    );
  }

  Widget _buildErrorWidget() {
    final failure =
        _playbackFailure ??
        MediaPlaybackFailure.fromKind(MediaCandidateFailureKind.other);
    return VideoPlayerSurfaceBuilder.buildFailure(
      failure: failure,
      thumbnailBinding: widget.thumbnailBinding,
      retrying: _isRetrying,
      onRetry: failure.isRetryable
          ? () {
              unawaited(_retryPlayback());
            }
          : null,
      onExit: failure.isRetryable ? null : widget.onExit,
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
    return VideoPlayerSurfaceBuilder.buildCenteredFrame(
      aspectRatio: _resolvedAspectRatio,
      child: child,
    );
  }
}
