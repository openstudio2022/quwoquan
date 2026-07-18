import 'dart:async';
import 'dart:developer' as developer;

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:video_player/video_player.dart';
import 'package:chewie/chewie.dart';

import 'package:quwoquan_app/core/media/media_candidate_failure.dart';
import 'package:quwoquan_app/core/media/media_delivery_reference.dart';
import 'package:quwoquan_app/core/media/media_load_failure_cache.dart';
import 'package:quwoquan_app/core/media/media_playback_failure.dart';
import 'package:quwoquan_app/core/platform/video_player_controller_factory.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/trackers/page_lifecycle_observability.dart';
import 'package:quwoquan_app/core/widgets/app_cached_network_image.dart';
import 'package:quwoquan_app/cloud/runtime/generated/ops/app_telemetry_catalog.g.dart';
import 'package:quwoquan_app/components/media/video/player/video_playback_failure_overlay.dart';
import 'package:quwoquan_app/components/media/video/player/video_playback_session.dart';

/// Surface-specific playback chrome. It intentionally excludes command handling:
/// commands always go through [VideoPlaybackSession].
enum VideoPlaybackOverlayMode { none, inlineFeed }

/// 视频播放器组件
/// 继承自侵入式媒体浏览器，支持视频播放功能
class VideoPlayerWidget extends ConsumerStatefulWidget {
  /// 已在 mapper/边界验证的公开媒体交付引用；播放器不再解析业务 object key。
  final MediaDeliveryReference deliveryReference;
  final MediaDeliveryReference? thumbnailReference;
  final bool initialize;
  final bool autoPlay;
  final bool showControls;
  final VoidCallback? onTap;
  final VoidCallback? onFullScreen;
  final Function(VideoPlayerController)? onControllerCreated;
  final VideoPlaybackSession? playbackSession;
  final ValueChanged<VideoPlaybackSession>? onPlaybackSessionCreated;
  final VideoPlaybackOverlayMode overlayMode;
  final Duration? verifiedDuration;
  final double? aspectRatio;

  /// 任务 B · 播放启动成功回调：startupLatency 为从初始化到可播放的耗时，
  /// candidateIndex 为命中的候选源序号（用于自动播放启动时延度量）。
  final void Function(Duration startupLatency, int candidateIndex)?
  onPlaybackStarted;

  /// 播放失败回调：只暴露确定性的脱敏失败结果。
  final void Function(MediaPlaybackFailure failure)? onPlaybackFailed;

  const VideoPlayerWidget({
    super.key,
    required this.deliveryReference,
    this.thumbnailReference,
    this.initialize = true,
    this.autoPlay = false,
    this.showControls = true,
    this.onTap,
    this.onFullScreen,
    this.onControllerCreated,
    this.playbackSession,
    this.onPlaybackSessionCreated,
    this.overlayMode = VideoPlaybackOverlayMode.none,
    this.verifiedDuration,
    this.aspectRatio,
    this.onPlaybackStarted,
    this.onPlaybackFailed,
  });

  @override
  ConsumerState<VideoPlayerWidget> createState() => _VideoPlayerWidgetState();

  /// 测试钩子：暴露当前并发控制器槽占用数。
  @visibleForTesting
  static int get debugActiveControllerCount =>
      _VideoPlayerWidgetState._activeControllerCount;

  @visibleForTesting
  static void debugResetControllerSlots() {
    _VideoPlayerWidgetState._activeControllerCount = 0;
  }
}

class _VideoPlayerWidgetState extends ConsumerState<VideoPlayerWidget>
    with WidgetsBindingObserver {
  /// Soft cap on concurrent ExoPlayer/MediaCodec instances (OEM hard-decode slots).
  static int _activeControllerCount = 0;
  static const int _maxConcurrentControllers = 2;
  static const Duration _slotWaitTimeout = Duration(seconds: 8);
  static const Duration _slotRetryInterval = Duration(milliseconds: 250);

  VideoPlayerController? _controller;
  ChewieController? _chewieController;
  bool _isInitialized = false;
  bool _hasError = false;
  bool _isDeferredWaitingForSlot = false;
  bool _isRetrying = false;
  MediaPlaybackFailure? _playbackFailure;
  int _videoInitGeneration = 0;
  bool _holdingControllerSlot = false;
  VoidCallback? _controllerErrorListener;
  int? _reportedNativeErrorGeneration;
  bool _qoeReportedForController = false;
  bool _appIsForeground = true;
  late final VideoPlaybackSession _ownedPlaybackSession;

  VideoPlaybackSession get _playbackSession =>
      widget.playbackSession ?? _ownedPlaybackSession;

  @override
  void initState() {
    super.initState();
    _ownedPlaybackSession = VideoPlaybackSession();
    _playbackSession.setAutomaticPlaybackEligible(widget.autoPlay);
    WidgetsBinding.instance.addObserver(this);
    if (widget.initialize) {
      _initializeVideo();
    }
  }

  @override
  void didUpdateWidget(covariant VideoPlayerWidget oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.playbackSession != widget.playbackSession) {
      final controller = _controller;
      if (controller != null) {
        (oldWidget.playbackSession ?? _ownedPlaybackSession).detach(controller);
        _playbackSession.attach(
          controller,
          verifiedDuration: widget.verifiedDuration,
        );
      }
      _playbackSession.setAutomaticPlaybackEligible(widget.autoPlay);
      widget.onPlaybackSessionCreated?.call(_playbackSession);
    }
    if (widget.verifiedDuration != oldWidget.verifiedDuration) {
      _playbackSession.setVerifiedDuration(widget.verifiedDuration);
    }
    if (widget.deliveryReference.cacheIdentity !=
        oldWidget.deliveryReference.cacheIdentity) {
      if (widget.initialize) {
        _replaceVideoController();
      } else {
        _disposeActiveControllers();
        setState(() {
          _isInitialized = false;
          _hasError = false;
          _playbackFailure = null;
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
          _playbackFailure = null;
        });
      }
      return;
    }
    if (widget.autoPlay != oldWidget.autoPlay) {
      _playbackSession.setAutomaticPlaybackEligible(widget.autoPlay);
    }
  }

  @override
  void dispose() {
    _videoInitGeneration += 1;
    WidgetsBinding.instance.removeObserver(this);
    _disposeActiveControllers();
    _ownedPlaybackSession.dispose();
    super.dispose();
  }

  void _disposeActiveControllers({
    String qoeResult = 'success',
    String? qoeFailureCode,
  }) {
    _detachControllerErrorListener();
    final controller = _controller;
    if (controller != null) {
      _reportPlaybackQoe(result: qoeResult, failReasonCode: qoeFailureCode);
      _playbackSession.detach(controller);
    }
    _chewieController?.dispose();
    _chewieController = null;
    _controller?.dispose();
    _controller = null;
    _isInitialized = false;
    _isDeferredWaitingForSlot = false;
    _isRetrying = false;
    _releaseControllerSlot();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    super.didChangeAppLifecycleState(state);
    final nextForeground = state == AppLifecycleState.resumed;
    if (_appIsForeground == nextForeground) {
      return;
    }
    _appIsForeground = nextForeground;
    _playbackSession.setForeground(nextForeground);
  }

  bool _acquireControllerSlot() {
    if (_holdingControllerSlot) {
      return true;
    }
    if (_activeControllerCount >= _maxConcurrentControllers) {
      return false;
    }
    _activeControllerCount += 1;
    _holdingControllerSlot = true;
    return true;
  }

  void _releaseControllerSlot() {
    if (!_holdingControllerSlot) {
      return;
    }
    _holdingControllerSlot = false;
    if (_activeControllerCount > 0) {
      _activeControllerCount -= 1;
    }
  }

  Future<void> _waitForControllerSlot(int generation) async {
    final deadline = DateTime.now().add(_slotWaitTimeout);
    while (mounted && generation == _videoInitGeneration) {
      if (_acquireControllerSlot()) {
        if (mounted && generation == _videoInitGeneration) {
          setState(() {
            _isDeferredWaitingForSlot = false;
          });
          await _initializeVideoWithHeldSlot(generation);
        } else {
          _releaseControllerSlot();
        }
        return;
      }
      if (DateTime.now().isAfter(deadline)) {
        developer.log(
          'video init deferred timeout: slot unavailable',
          name: 'VideoPlayerWidget',
        );
        if (mounted && generation == _videoInitGeneration) {
          _reportPlaybackFailure(
            MediaPlaybackFailure.fromKind(
              MediaCandidateFailureKind.controllerSlotTimeout,
            ),
          );
        }
        return;
      }
      await Future<void>.delayed(_slotRetryInterval);
    }
  }

  /// Slot already acquired; continue initialization without re-acquiring.
  Future<void> _initializeVideoWithHeldSlot(int generation) async {
    final candidates = <String>[widget.deliveryReference.url];
    final startupStopwatch = Stopwatch()..start();
    final observedFailures = <MediaCandidateFailureKind>[];
    var retainControllerSlot = false;
    try {
      for (var index = 0; index < candidates.length; index++) {
        final candidate = candidates[index];
        List<_PlayableVideoSource> sources;
        try {
          sources = await _playableSourcesForCandidate(candidate);
        } catch (error, stackTrace) {
          final kind = _classifyPlaybackFailure(error, candidate);
          observedFailures.add(kind);
          _logCandidateFailure(
            index: index,
            candidateCount: candidates.length,
            source: 'source_lookup',
            kind: kind,
            error: error,
            stackTrace: stackTrace,
          );
          continue;
        }
        if (!mounted || generation != _videoInitGeneration) {
          return;
        }
        if (sources.isEmpty) {
          observedFailures.add(MediaCandidateFailureKind.noPlayableSource);
          continue;
        }
        for (final source in sources) {
          VideoPlayerController? controller;
          ChewieController? chewieController;
          try {
            controller = source.createController();
            await controller.initialize();
            if (!mounted || generation != _videoInitGeneration) {
              await controller.dispose();
              return;
            }
            chewieController = ChewieController(
              videoPlayerController: controller,
              autoPlay: false,
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
          } catch (error, stackTrace) {
            chewieController?.dispose();
            await controller?.dispose();
            final kind = _classifyPlaybackFailure(error, candidate);
            observedFailures.add(kind);
            _logCandidateFailure(
              index: index,
              candidateCount: candidates.length,
              source: source.label,
              kind: kind,
              error: error,
              stackTrace: stackTrace,
            );
            continue;
          }

          _controller = controller;
          _chewieController = chewieController;
          retainControllerSlot = true;
          _attachControllerErrorListener(
            controller,
            generation: generation,
            candidate: candidate,
            source: source.label,
          );
          setState(() {
            _isInitialized = true;
            _hasError = false;
            _isDeferredWaitingForSlot = false;
            _isRetrying = false;
            _playbackFailure = null;
          });
          _playbackSession.attach(
            controller,
            verifiedDuration: widget.verifiedDuration,
            readyMs: startupStopwatch.elapsedMilliseconds,
          );
          _qoeReportedForController = false;
          _playbackSession.setAutomaticPlaybackEligible(widget.autoPlay);
          widget.onControllerCreated?.call(controller);
          widget.onPlaybackSessionCreated?.call(_playbackSession);
          startupStopwatch.stop();
          ref
              .read(pageLifecycleObservabilityProvider)
              .recordMediaLoad(
                mediaType: 'video',
                result: 'success',
                durationMs: startupStopwatch.elapsedMilliseconds,
                candidatesTried: index + 1,
              );
          widget.onPlaybackStarted?.call(startupStopwatch.elapsed, index);
          return;
        }
      }

      if (mounted && generation == _videoInitGeneration) {
        _reportPlaybackFailure(
          MediaPlaybackFailure.select(
            observedFailures,
            candidatesTried: candidates.length,
          ),
        );
      }
    } catch (error, stackTrace) {
      if (mounted && generation == _videoInitGeneration) {
        final kind = _classifyPlaybackFailure(
          error,
          widget.deliveryReference.url,
        );
        _logCandidateFailure(
          index: 0,
          candidateCount: candidates.length,
          source: 'player_setup',
          kind: kind,
          error: error,
          stackTrace: stackTrace,
        );
        _reportPlaybackFailure(
          MediaPlaybackFailure.select(<MediaCandidateFailureKind>[
            ...observedFailures,
            kind,
          ], candidatesTried: candidates.length),
        );
      }
    } finally {
      startupStopwatch.stop();
      if (!retainControllerSlot) {
        _releaseControllerSlot();
      }
    }
  }

  bool _looksLikeDecoderInitFailure(Object error) {
    final text = error.toString();
    return text.contains('MediaCodec') ||
        text.contains('DecoderInitialization') ||
        text.contains('Video codec error') ||
        text.contains('OMX.');
  }

  MediaCandidateFailureKind _classifyPlaybackFailure(
    Object error,
    String candidate,
  ) {
    if (_looksLikeDecoderInitFailure(error)) {
      return MediaCandidateFailureKind.decoderInitialization;
    }
    return classifyMediaCandidateLoadFailure(error, candidateUrl: candidate);
  }

  void _logCandidateFailure({
    required int index,
    required int candidateCount,
    required String source,
    required MediaCandidateFailureKind kind,
    required Object error,
    required StackTrace stackTrace,
  }) {
    developer.log(
      'video candidate init failed '
      '(index=${index + 1}/$candidateCount, source=$source, kind=${kind.name})',
      name: 'VideoPlayerWidget',
      error: error,
      stackTrace: stackTrace,
    );
  }

  void _attachControllerErrorListener(
    VideoPlayerController controller, {
    required int generation,
    required String candidate,
    required String source,
  }) {
    _detachControllerErrorListener();
    _reportedNativeErrorGeneration = null;
    void listener() {
      if (!mounted ||
          generation != _videoInitGeneration ||
          !identical(_controller, controller) ||
          !controller.value.hasError ||
          _reportedNativeErrorGeneration == generation) {
        return;
      }
      _reportedNativeErrorGeneration = generation;
      final description = controller.value.errorDescription?.trim();
      unawaited(
        _handleNativePlaybackError(
          controller: controller,
          generation: generation,
          candidate: candidate,
          source: '$source.runtime',
          error: StateError(
            description == null || description.isEmpty
                ? 'native_video_player_reported_error'
                : description,
          ),
          stackTrace: StackTrace.current,
        ),
      );
    }

    _controllerErrorListener = listener;
    controller.addListener(listener);
  }

  void _detachControllerErrorListener() {
    final controller = _controller;
    final listener = _controllerErrorListener;
    if (controller != null && listener != null) {
      controller.removeListener(listener);
    }
    _controllerErrorListener = null;
  }

  Future<void> _handleNativePlaybackError({
    required VideoPlayerController controller,
    required int generation,
    required String candidate,
    required String source,
    required Object error,
    required StackTrace stackTrace,
  }) async {
    if (!mounted ||
        generation != _videoInitGeneration ||
        !identical(_controller, controller) ||
        _hasError) {
      return;
    }
    final kind = _classifyPlaybackFailure(error, candidate);
    _logCandidateFailure(
      index: 0,
      candidateCount: 1,
      source: source,
      kind: kind,
      error: error,
      stackTrace: stackTrace,
    );
    _disposeActiveControllers(qoeResult: 'failure', qoeFailureCode: kind.name);
    if (!mounted || generation != _videoInitGeneration) {
      return;
    }
    _reportPlaybackFailure(
      MediaPlaybackFailure.fromKind(kind, candidatesTried: 1),
    );
  }

  void _reportPlaybackFailure(MediaPlaybackFailure failure) {
    _playbackSession.markFailure();
    if (failure.shouldNegativeCache) {
      MediaLoadFailureCache.instance.recordTerminalFailure(
        widget.deliveryReference.cacheIdentity,
        kind: failure.kind,
        statusCode: failure.runtimeFailure.transportStatus,
      );
    }
    setState(() {
      _isDeferredWaitingForSlot = false;
      _hasError = true;
      _isInitialized = false;
      _isRetrying = false;
      _playbackFailure = failure;
    });
    ref
        .read(pageLifecycleObservabilityProvider)
        .recordMediaLoad(
          mediaType: 'video',
          result: 'failure',
          error: failure.runtimeFailure,
          candidatesTried: failure.candidatesTried,
          mediaFailureKind: failure.kind.name,
          userScene: failure.userScene.name,
          retryable: failure.isRetryable,
        );
    widget.onPlaybackFailed?.call(failure);
    if (_controller == null && !_qoeReportedForController) {
      _qoeReportedForController = true;
      unawaited(
        ref
            .read(appTelemetryReporterProvider)
            .record(
              AppTelemetryPayload.videoPlaybackQoe(
                readyMs: 0,
                rebufferCount: 0,
                rebufferMs: 0,
                seekCount: 0,
                playbackMode: widget.autoPlay ? 'autoplay' : 'manual',
                result: 'failure',
                failReasonCode: failure.kind.name,
              ),
            ),
      );
    }
    _reportPlaybackQoe(result: 'failure', failReasonCode: failure.kind.name);
  }

  void _reportPlaybackQoe({required String result, String? failReasonCode}) {
    if (_qoeReportedForController) {
      return;
    }
    final controller = _controller;
    if (controller == null) {
      return;
    }
    _qoeReportedForController = true;
    final summary = _playbackSession.takeQoeSummary(
      result: result,
      failReasonCode: failReasonCode,
    );
    unawaited(
      ref
          .read(appTelemetryReporterProvider)
          .record(
            AppTelemetryPayload.videoPlaybackQoe(
              readyMs: summary.readyMs,
              rebufferCount: summary.rebufferCount,
              rebufferMs: summary.rebufferMs,
              seekCount: summary.seekCount,
              playbackMode: summary.playbackMode,
              declaredDurationMs: summary.declaredDurationMs,
              observedDurationMs: summary.observedDurationMs,
              durationMismatch: summary.durationMismatch,
              result: summary.result,
              failReasonCode: summary.failReasonCode,
            ),
          ),
    );
  }

  Future<void> _replaceVideoController() async {
    _disposeActiveControllers();
    setState(() {
      _isInitialized = false;
      _hasError = false;
      _playbackFailure = null;
    });
    await _initializeVideo();
  }

  Future<void> _retryPlayback() async {
    if (_isRetrying) {
      return;
    }
    MediaLoadFailureCache.instance.clearIdentity(
      widget.deliveryReference.cacheIdentity,
    );
    setState(() {
      _isRetrying = true;
      _hasError = false;
      _playbackFailure = null;
    });
    await _replaceVideoController();
    if (mounted && _isRetrying) {
      setState(() {
        _isRetrying = false;
      });
    }
  }

  Future<void> _initializeVideo() async {
    final generation = _videoInitGeneration + 1;
    _videoInitGeneration = generation;
    _qoeReportedForController = false;
    final cachedFailure = MediaLoadFailureCache.instance.activeFailure(
      widget.deliveryReference.cacheIdentity,
    );
    if (cachedFailure != null) {
      if (mounted && generation == _videoInitGeneration) {
        _reportPlaybackFailure(
          MediaPlaybackFailure.fromKind(cachedFailure.kind),
        );
      }
      return;
    }
    final candidates = <String>[widget.deliveryReference.url];
    if (candidates.isEmpty) {
      if (mounted && generation == _videoInitGeneration) {
        _reportPlaybackFailure(
          MediaPlaybackFailure.fromKind(
            MediaCandidateFailureKind.noPlayableSource,
          ),
        );
      }
      return;
    }
    if (!_acquireControllerSlot()) {
      developer.log(
        'video init deferred: concurrent MediaCodec slot limit '
        '($_maxConcurrentControllers)',
        name: 'VideoPlayerWidget',
      );
      if (mounted && generation == _videoInitGeneration) {
        setState(() {
          _hasError = false;
          _isInitialized = false;
          _isDeferredWaitingForSlot = true;
        });
      }
      await _waitForControllerSlot(generation);
      return;
    }
    if (mounted && generation == _videoInitGeneration) {
      _isDeferredWaitingForSlot = false;
    }
    await _initializeVideoWithHeldSlot(generation);
  }

  Future<List<_PlayableVideoSource>> _playableSourcesForCandidate(
    String candidate,
  ) async {
    final normalized = candidate.trim();
    if (normalized.isEmpty) {
      return const <_PlayableVideoSource>[];
    }
    final sources = <_PlayableVideoSource>[];
    final seen = <String>{};
    final cachedPath = await ref
        .read(mediaDownloadCacheProvider)
        .getCachedFilePath(normalized);
    if (cachedPath != null && seen.add('cache:$cachedPath')) {
      sources.add(_PlayableVideoSource.cachedFile(cachedPath));
    }
    final networkUri = Uri.tryParse(normalized);
    if (_isNetworkVideoUri(networkUri) &&
        await _canUseNetworkVideoUri(networkUri!) &&
        seen.add(networkUri.toString())) {
      sources.add(_PlayableVideoSource.network(networkUri));
    }
    return sources;
  }

  bool _isNetworkVideoUri(Uri? uri) {
    if (uri == null || uri.host.isEmpty) {
      return false;
    }
    final scheme = uri.scheme.toLowerCase();
    return scheme == 'http' || scheme == 'https';
  }

  Future<bool> _canUseNetworkVideoUri(Uri uri) async {
    // 交付 URI 已在 MediaDeliveryResolver 边界校验为 HTTPS + 注入 origin。
    return uri.scheme.toLowerCase() == 'https' && uri.host.isNotEmpty;
  }

  Widget _buildVideoPlaceholder() {
    final thumbnailUrl = widget.thumbnailReference?.url ?? '';
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
                imageUrlCandidates: <String>[thumbnailUrl],
                cdnPreset: CdnImagePreset.cover,
                fit: BoxFit.cover,
                placeholder: const SizedBox.shrink(),
                errorWidget: const SizedBox.shrink(),
              ),
            ),
          ColoredBox(color: AppColors.black.withValues(alpha: 0.22)),
          // 聚焦自动播放（autoPlay）时显示加载转圈，避免与卡片层叠出第二个
          // 「播放三角」按钮；未自动播放时仍用播放三角作为点按查看提示。
          Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              if (widget.autoPlay)
                CupertinoActivityIndicator(
                  color: AppColors.white,
                  radius: AppSpacing.iconMedium / 2,
                )
              else
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
    final thumbnailUrl = widget.thumbnailReference?.url ?? '';
    return ColoredBox(
      color: AppColors.black,
      child: Stack(
        fit: StackFit.expand,
        children: [
          if (thumbnailUrl.isNotEmpty)
            AppCachedNetworkImage(
              imageUrl: thumbnailUrl,
              imageUrlCandidates: <String>[thumbnailUrl],
              cdnPreset: CdnImagePreset.cover,
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
    final failure =
        _playbackFailure ??
        MediaPlaybackFailure.fromKind(MediaCandidateFailureKind.other);
    return VideoPlaybackFailureOverlay(
      failure: failure,
      thumbnailReference: widget.thumbnailReference,
      retrying: _isRetrying,
      onRetry: failure.isRetryable
          ? () {
              unawaited(_retryPlayback());
            }
          : null,
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
      // deferred 等待槽位时仍展示标准 loading 占位，超时后走 _hasError。
      assert(!_isDeferredWaitingForSlot || !_hasError);
      return _buildCenteredVideoFrame(_buildVideoPlaceholder());
    }

    final player = widget.showControls
        ? Chewie(controller: _chewieController!)
        : VideoPlayer(_controller!);
    final surface = widget.overlayMode == VideoPlaybackOverlayMode.inlineFeed
        ? Stack(
            fit: StackFit.expand,
            children: [
              player,
              _InlineFeedPlaybackOverlay(session: _playbackSession),
            ],
          )
        : player;
    return KeyedSubtree(
      key: const ValueKey<String>('video-player-ready'),
      child: GestureDetector(
        onTap: widget.onTap,
        child: _buildCenteredVideoFrame(surface),
      ),
    );
  }
}

class _InlineFeedPlaybackOverlay extends StatelessWidget {
  const _InlineFeedPlaybackOverlay({required this.session});

  final VideoPlaybackSession session;

  static String _formatDuration(Duration duration) {
    final totalSeconds = duration.inSeconds.clamp(0, 359999);
    final minutes = totalSeconds ~/ 60;
    final seconds = totalSeconds % 60;
    return '$minutes:${seconds.toString().padLeft(2, '0')}';
  }

  @override
  Widget build(BuildContext context) {
    return IgnorePointer(
      child: AnimatedBuilder(
        animation: session,
        builder: (context, _) {
          final snapshot = session.snapshot;
          if (!snapshot.isInitialized || snapshot.duration <= Duration.zero) {
            return const SizedBox.shrink();
          }
          final expanded = snapshot.isScrubbing || !snapshot.isPlaying;
          final trackHeight = expanded
              ? AppSpacing.xs
              : AppSpacing.xs / AppSpacing.two;
          return Stack(
            fit: StackFit.expand,
            children: [
              Positioned(
                top: AppSpacing.intraGroupSm,
                right: AppSpacing.intraGroupSm,
                child: AnimatedOpacity(
                  duration: const Duration(milliseconds: 180),
                  opacity:
                      snapshot.controlsVisibility ==
                          VideoPlaybackControlsVisibility.hidden
                      ? 0
                      : 1,
                  child: Text(
                    _formatDuration(snapshot.duration),
                    key: const ValueKey<String>(
                      'home-video-transient-duration',
                    ),
                    style: TextStyle(
                      color: AppColors.white.withValues(alpha: 0.96),
                      fontSize: AppTypography.xxs,
                      fontWeight: AppTypography.semiBold,
                      shadows: <Shadow>[
                        Shadow(
                          color: AppColors.black.withValues(alpha: 0.38),
                          blurRadius: AppSpacing.xs,
                        ),
                      ],
                    ),
                  ),
                ),
              ),
              Positioned(
                left: AppSpacing.intraGroupSm,
                right: AppSpacing.intraGroupSm,
                bottom: AppSpacing.intraGroupSm,
                child: _InlinePlaybackTrack(
                  progress: snapshot.progress,
                  height: trackHeight,
                  expanded: expanded,
                ),
              ),
            ],
          );
        },
      ),
    );
  }
}

class _InlinePlaybackTrack extends StatelessWidget {
  const _InlinePlaybackTrack({
    required this.progress,
    required this.height,
    required this.expanded,
  });

  final double progress;
  final double height;
  final bool expanded;

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(AppSpacing.circularBorderRadius),
      child: SizedBox(
        height: height,
        child: DecoratedBox(
          decoration: BoxDecoration(
            color: AppColors.white.withValues(alpha: expanded ? 0.46 : 0.30),
          ),
          child: FractionallySizedBox(
            alignment: Alignment.centerLeft,
            widthFactor: progress.clamp(0.0, 1.0),
            child: DecoratedBox(
              decoration: BoxDecoration(
                color: AppColors.white.withValues(alpha: expanded ? 1 : 0.86),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _PlayableVideoSource {
  const _PlayableVideoSource._({
    required this.label,
    required this.createController,
  });

  factory _PlayableVideoSource.cachedFile(String path) {
    return _PlayableVideoSource._(
      label: 'cache',
      createController: () =>
          AppVideoPlayerControllerFactory.localFilePath(path),
    );
  }

  factory _PlayableVideoSource.network(Uri uri) {
    return _PlayableVideoSource._(
      label: 'network',
      createController: () => AppVideoPlayerControllerFactory.networkUri(uri),
    );
  }

  final String label;
  final VideoPlayerController Function() createController;
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
