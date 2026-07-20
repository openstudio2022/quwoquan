import 'dart:async';
import 'dart:developer' as developer;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:video_player/video_player.dart';
import 'package:chewie/chewie.dart';

import 'package:quwoquan_app/core/media/media_candidate_failure.dart';
import 'package:quwoquan_app/core/di/runtime_observability_dependencies.dart';
import 'package:quwoquan_app/core/media/media_delivery_reference.dart';
import 'package:quwoquan_app/core/media/media_load_failure_cache.dart';
import 'package:quwoquan_app/core/media/media_playback_failure.dart';
import 'package:quwoquan_app/core/platform/platform_target.dart';
import 'package:quwoquan_app/core/platform/video_native_playback_signals.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/telemetry/app_telemetry_reporter.dart';
import 'package:quwoquan_app/core/trackers/page_lifecycle_observability.dart';
import 'package:quwoquan_app/cloud/runtime/generated/ops/app_telemetry_catalog.g.dart';
import 'package:quwoquan_app/components/media/video/player/video_playback_session.dart';
import 'package:quwoquan_app/components/media/video/player/video_playback_timeline.dart';
import 'package:quwoquan_app/components/media/video/player/video_player_support.dart';
import 'package:quwoquan_app/components/media/video/player/video_player_surface_builder.dart';

part 'video_player_widget_api.dart';

class _VideoPlayerWidgetState extends ConsumerState<VideoPlayerWidget>
    with WidgetsBindingObserver {
  /// Soft cap on concurrent ExoPlayer/MediaCodec instances (OEM hard-decode slots).
  static int _activeControllerCount = 0;
  static const int _maxConcurrentControllers = 2;
  static const Duration _slotWaitTimeout = Duration(seconds: 8);
  static const Duration _slotRetryInterval = Duration(milliseconds: 250);

  VideoPlayerController? _controller;
  ChewieController? _chewieController;
  late final AppTelemetryRecorder _telemetryRecorder;
  bool _isInitialized = false;
  bool _hasError = false;
  bool _isDeferredWaitingForSlot = false;
  bool _isRetrying = false;
  MediaPlaybackFailure? _playbackFailure;
  int _videoInitGeneration = 0;
  int _automaticPlaybackSyncGeneration = 0;
  int _controllerLifecycleSyncGeneration = 0;
  bool _holdingControllerSlot = false;
  int _nextControllerSlotLeaseId = 0;
  int? _controllerSlotLeaseId;
  VoidCallback? _controllerErrorListener;
  int? _reportedNativeErrorGeneration;
  bool _qoeReportedForController = false;
  bool _appIsForeground = true;
  Stream<VideoNativePlaybackSignal>? _nativePlaybackSignals;
  late final VideoPlaybackSession _ownedPlaybackSession;
  VideoPlayerController? _initializingController;
  VideoPlayerController? _disposingController;
  Future<void>? _controllerDisposalFuture;

  VideoPlaybackSession get _playbackSession =>
      widget.playbackSession ?? _ownedPlaybackSession;

  @override
  void initState() {
    super.initState();
    _telemetryRecorder = ref.read(appTelemetryReporterProvider);
    _ownedPlaybackSession = VideoPlaybackSession(
      onNativeSignal: ref
          .read(runtimeDiagnosticsProvider)
          .recordNativeMediaSignal,
    );
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
          nativeSignals: _nativePlaybackSignals,
        );
      }
      _scheduleAutomaticPlaybackEligibilitySync();
      widget.onPlaybackSessionCreated?.call(_playbackSession);
    }
    if (widget.verifiedDuration != oldWidget.verifiedDuration) {
      _playbackSession.setVerifiedDuration(widget.verifiedDuration);
    }
    if (widget.deliveryReference.cacheIdentity !=
        oldWidget.deliveryReference.cacheIdentity) {
      _scheduleControllerLifecycleSync(sourceChanged: true);
      return;
    }
    if (widget.initialize != oldWidget.initialize) {
      _scheduleControllerLifecycleSync(sourceChanged: false);
      return;
    }
    if (widget.autoPlay != oldWidget.autoPlay) {
      _scheduleAutomaticPlaybackEligibilitySync();
    }
  }

  void _scheduleAutomaticPlaybackEligibilitySync() {
    final generation = ++_automaticPlaybackSyncGeneration;
    final session = _playbackSession;
    final eligible = widget.autoPlay;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted ||
          generation != _automaticPlaybackSyncGeneration ||
          !identical(session, _playbackSession)) {
        return;
      }
      // setAutomaticPlaybackEligible 可能同步 pause/play 并通知监听者；
      // didUpdateWidget 正处于 build 阶段，必须等当前帧结束后再触发。
      session.setAutomaticPlaybackEligible(eligible);
    });
  }

  void _scheduleControllerLifecycleSync({required bool sourceChanged}) {
    final generation = ++_controllerLifecycleSyncGeneration;
    final expectedIdentity = widget.deliveryReference.cacheIdentity;
    final shouldInitialize = widget.initialize;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted ||
          generation != _controllerLifecycleSyncGeneration ||
          expectedIdentity != widget.deliveryReference.cacheIdentity ||
          shouldInitialize != widget.initialize) {
        return;
      }
      // attach/detach 会同步通知 PlaybackSession 的 AnimatedBuilder；
      // didUpdateWidget 的 build 阶段不能直接释放或重建 controller。
      if (shouldInitialize) {
        if (sourceChanged) {
          unawaited(_replaceVideoController());
        } else {
          unawaited(_initializeVideo());
        }
        return;
      }
      _invalidateVideoInitialization();
      unawaited(_disposeActiveControllers());
      setState(() {
        _isInitialized = false;
        _hasError = false;
        _playbackFailure = null;
      });
    });
  }

  @override
  void dispose() {
    _invalidateVideoInitialization();
    _automaticPlaybackSyncGeneration += 1;
    _controllerLifecycleSyncGeneration += 1;
    WidgetsBinding.instance.removeObserver(this);
    unawaited(_disposeActiveControllers());
    _ownedPlaybackSession.dispose();
    super.dispose();
  }

  void _invalidateVideoInitialization() {
    _videoInitGeneration += 1;
  }

  Future<void> _disposeActiveControllers({
    String qoeResult = 'success',
    String? qoeFailureCode,
  }) {
    _detachControllerErrorListener();
    final activeController = _controller;
    final controller = activeController ?? _initializingController;
    final slotLeaseId = _controllerSlotLeaseId;
    if (activeController != null) {
      final effectiveEvidence = _playbackSession
          .takeEffectivePlaybackEvidence();
      if (effectiveEvidence.qualifies) {
        widget.onEffectivePlayback?.call(effectiveEvidence);
      }
      _reportPlaybackQoe(result: qoeResult, failReasonCode: qoeFailureCode);
      _playbackSession.detach(activeController);
    }
    _chewieController?.dispose();
    _chewieController = null;
    _controller = null;
    if (identical(_initializingController, controller)) {
      _initializingController = null;
    }
    _nativePlaybackSignals = null;
    _isInitialized = false;
    _isDeferredWaitingForSlot = false;
    _isRetrying = false;
    if (controller == null) {
      final pendingDisposal = _controllerDisposalFuture;
      if (_disposingController != null && pendingDisposal != null) {
        return pendingDisposal;
      }
      // source lookup 尚未触及原生 decoder，取消时可立即归还该代际的槽位；
      // 初始化任务 finally 携带同一 lease，不能误释放后续新控制器的槽位。
      _releaseControllerSlot(leaseId: slotLeaseId);
      return Future<void>.value();
    }
    return _disposeControllerAndReleaseSlot(
      controller,
      slotLeaseId: slotLeaseId,
    );
  }

  Future<void> _disposeControllerAndReleaseSlot(
    VideoPlayerController controller, {
    bool releaseSlot = true,
    int? slotLeaseId,
  }) {
    final pending = _controllerDisposalFuture;
    if (identical(_disposingController, controller) && pending != null) {
      return pending;
    }
    _disposingController = controller;
    late final Future<void> disposal;
    disposal = Future<void>.sync(() async {
      try {
        await controller.dispose();
      } catch (error, stackTrace) {
        developer.log(
          'video controller disposal failed',
          name: 'VideoPlayerWidget',
          error: error,
          stackTrace: stackTrace,
        );
      } finally {
        if (identical(_disposingController, controller)) {
          _disposingController = null;
          _controllerDisposalFuture = null;
        }
        if (releaseSlot) {
          _releaseControllerSlot(leaseId: slotLeaseId);
        }
      }
    });
    _controllerDisposalFuture = disposal;
    return disposal;
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
      return false;
    }
    if (_activeControllerCount >= _maxConcurrentControllers) {
      return false;
    }
    _activeControllerCount += 1;
    _holdingControllerSlot = true;
    _controllerSlotLeaseId = ++_nextControllerSlotLeaseId;
    return true;
  }

  void _releaseControllerSlot({int? leaseId}) {
    if (!_holdingControllerSlot ||
        (leaseId != null && _controllerSlotLeaseId != leaseId)) {
      return;
    }
    _holdingControllerSlot = false;
    _controllerSlotLeaseId = null;
    if (_activeControllerCount > 0) {
      _activeControllerCount -= 1;
    }
  }

  Future<void> _waitForControllerSlot(int generation) async {
    final deadline = DateTime.now().add(_slotWaitTimeout);
    while (mounted && generation == _videoInitGeneration) {
      if (_acquireControllerSlot()) {
        final slotLeaseId = _controllerSlotLeaseId;
        if (mounted && generation == _videoInitGeneration) {
          setState(() {
            _isDeferredWaitingForSlot = false;
          });
          await _initializeVideoWithHeldSlot(generation, slotLeaseId);
        } else {
          _releaseControllerSlot(leaseId: slotLeaseId);
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
  Future<void> _initializeVideoWithHeldSlot(
    int generation,
    int? slotLeaseId,
  ) async {
    final candidates = <String>[widget.deliveryReference.url];
    final startupStopwatch = Stopwatch()..start();
    final observedFailures = <MediaCandidateFailureKind>[];
    var retainControllerSlot = false;
    try {
      for (var index = 0; index < candidates.length; index++) {
        final candidate = candidates[index];
        List<PlayableVideoSource> sources;
        try {
          sources = await _playableSourcesForCandidate(candidate);
        } catch (error, stackTrace) {
          if (!mounted || generation != _videoInitGeneration) {
            return;
          }
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
          Stream<VideoNativePlaybackSignal>? nativePlaybackSignals;
          try {
            final controllerHandle = source.createController();
            controller = controllerHandle.controller;
            nativePlaybackSignals = controllerHandle.nativePlaybackSignals;
            _initializingController = controller;
            await controller.initialize();
            if (!mounted || generation != _videoInitGeneration) {
              await _disposeControllerAndReleaseSlot(
                controller,
                slotLeaseId: slotLeaseId,
              );
              if (identical(_initializingController, controller)) {
                _initializingController = null;
              }
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
            if (controller != null) {
              await _disposeControllerAndReleaseSlot(
                controller,
                releaseSlot: false,
                slotLeaseId: slotLeaseId,
              );
            }
            if (identical(_initializingController, controller)) {
              _initializingController = null;
            }
            if (!mounted || generation != _videoInitGeneration) {
              return;
            }
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

          if (identical(_initializingController, controller)) {
            _initializingController = null;
          }
          _controller = controller;
          _chewieController = chewieController;
          _nativePlaybackSignals = nativePlaybackSignals;
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
            nativeSignals: nativePlaybackSignals,
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
      if (!retainControllerSlot && _disposingController == null) {
        _releaseControllerSlot(leaseId: slotLeaseId);
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
    await _disposeActiveControllers(
      qoeResult: 'failure',
      qoeFailureCode: kind.name,
    );
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
                effectivePlaybackMs: 0,
                seekCount: 0,
                seekFailureCount: 0,
                seekCommandMaxMs: 0,
                seekSettleMaxMs: 0,
                seekEvidenceSource: 'controller_command_completion',
                devicePlatform: platformWireName(currentAppPlatform),
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
      _telemetryRecorder.record(
        AppTelemetryPayload.videoPlaybackQoe(
          readyMs: summary.readyMs,
          rebufferCount: summary.rebufferCount,
          rebufferMs: summary.rebufferMs,
          effectivePlaybackMs: summary.effectivePlaybackMs,
          seekCount: summary.seekCount,
          seekFailureCount: summary.seekFailureCount,
          seekCommandMaxMs: summary.seekCommandMaxMs,
          seekSettleMaxMs: summary.seekSettleMaxMs,
          seekEvidenceSource: summary.seekEvidenceSource,
          devicePlatform: platformWireName(currentAppPlatform),
          playbackMode: summary.playbackMode,
          ttffMs: summary.ttffMs,
          droppedFrames: summary.droppedFrames,
          processedVideoFrames: summary.processedVideoFrames,
          audioUnderrunCount: summary.audioUnderrunCount,
          rendererMode: summary.rendererMode,
          decoderQueueMode: summary.decoderQueueMode,
          decoderFallbackEnabled: summary.decoderFallbackEnabled,
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
    _invalidateVideoInitialization();
    final disposal = _disposeActiveControllers();
    if (mounted) {
      setState(() {
        _isInitialized = false;
        _hasError = false;
        _playbackFailure = null;
      });
    }
    await disposal;
    if (!mounted || !widget.initialize) {
      return;
    }
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
    await _initializeVideoWithHeldSlot(generation, _controllerSlotLeaseId);
  }

  Future<List<PlayableVideoSource>> _playableSourcesForCandidate(
    String candidate,
  ) async {
    final normalized = candidate.trim();
    if (normalized.isEmpty) {
      return const <PlayableVideoSource>[];
    }
    final sources = <PlayableVideoSource>[];
    final seen = <String>{};
    String? cachedPath;
    try {
      cachedPath = await ref
          .read(mediaDownloadCacheProvider)
          .getCachedFilePath(normalized);
    } catch (error, stackTrace) {
      developer.log(
        'cached video source lookup failed; continue with delivery URI',
        name: 'VideoPlayerWidget',
        error: error,
        stackTrace: stackTrace,
      );
    }
    if (cachedPath != null && seen.add('cache:$cachedPath')) {
      sources.add(PlayableVideoSource.cachedFile(cachedPath));
    }
    final networkUri = Uri.tryParse(normalized);
    if (_isNetworkVideoUri(networkUri) &&
        await _canUseNetworkVideoUri(networkUri!) &&
        seen.add(networkUri.toString())) {
      sources.add(PlayableVideoSource.network(networkUri));
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
    return VideoPlayerSurfaceBuilder.buildPlaceholder(
      thumbnailReference: widget.thumbnailReference,
      autoPlay: widget.autoPlay,
    );
  }

  Widget _buildDeferredWidget() {
    return VideoPlayerSurfaceBuilder.buildDeferred(
      thumbnailReference: widget.thumbnailReference,
    );
  }

  Widget _buildErrorWidget() {
    final failure =
        _playbackFailure ??
        MediaPlaybackFailure.fromKind(MediaCandidateFailureKind.other);
    return VideoPlayerSurfaceBuilder.buildFailure(
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
    return VideoPlayerSurfaceBuilder.buildCenteredFrame(
      aspectRatio: _resolvedAspectRatio,
      child: child,
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
              InlineFeedPlaybackOverlay(session: _playbackSession),
            ],
          )
        : player;
    return KeyedSubtree(
      key: const ValueKey<String>('video-player-ready'),
      child: AnimatedBuilder(
        animation: _playbackSession,
        builder: (context, child) {
          final nativeSeekSettledTarget =
              _playbackSession.nativeSeekSettledTarget;
          return Stack(
            fit: StackFit.passthrough,
            children: [
              child!,
              if (_playbackSession.hasNativeFirstFrameEvidence)
                const Positioned.fill(
                  child: IgnorePointer(
                    child: SizedBox(
                      key: ValueKey<String>('video-player-native-first-frame'),
                    ),
                  ),
                ),
              if (nativeSeekSettledTarget != null)
                Positioned.fill(
                  child: IgnorePointer(
                    child: SizedBox(
                      key: ValueKey<String>(
                        'video-player-native-seek-settled-'
                        '${nativeSeekSettledTarget.inMilliseconds}',
                      ),
                    ),
                  ),
                ),
            ],
          );
        },
        child: GestureDetector(
          onTap: widget.onTap,
          child: _buildCenteredVideoFrame(surface),
        ),
      ),
    );
  }
}
