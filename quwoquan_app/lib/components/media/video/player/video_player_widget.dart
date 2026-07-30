import 'dart:async';
import 'dart:developer' as developer;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:video_player/video_player.dart';
import 'package:chewie/chewie.dart';

import 'package:quwoquan_app/core/media/media_candidate_failure.dart';
import 'package:quwoquan_app/core/di/runtime_observability_dependencies.dart';
import 'package:quwoquan_app/core/media/adaptive_video_delivery.dart';
import 'package:quwoquan_app/core/media/media_delivery_reference.dart';
import 'package:quwoquan_app/core/media/media_load_failure_cache.dart';
import 'package:quwoquan_app/core/media/media_playback_failure.dart';
import 'package:quwoquan_app/core/platform/platform_target.dart';
import 'package:quwoquan_app/core/platform/video_native_playback_signals.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/services/app_request_wait_controller.dart';
import 'package:quwoquan_app/core/telemetry/app_telemetry_reporter.dart';
import 'package:quwoquan_app/core/trackers/page_lifecycle_observability.dart';
import 'package:quwoquan_app/cloud/runtime/generated/ops/app_telemetry_catalog.g.dart';
import 'package:quwoquan_app/components/media/video/player/video_playback_session.dart';
import 'package:quwoquan_app/components/media/video/player/video_playback_timeline.dart';
import 'package:quwoquan_app/components/media/video/player/video_player_support.dart';
import 'package:quwoquan_app/components/media/video/player/video_player_surface_builder.dart';

part 'video_player_widget_api.dart';
part 'video_player_widget_presentation.dart';

/// 当前 controller 创建时的候选事实。
///
/// 运行时错误不得用变化中的 flag 重算。
final class _ActiveVideoCandidateSnapshot {
  const _ActiveVideoCandidateSnapshot({
    required this.generation,
    required this.index,
    required this.count,
    required this.identity,
    required this.url,
    required this.isAdaptive,
  });

  final int generation;
  final int index;
  final int count;
  final String identity;
  final String url;
  final bool isAdaptive;

  bool get canFallbackToProgressive => isAdaptive && index < count - 1;
}

class _VideoPlayerWidgetState extends ConsumerState<VideoPlayerWidget>
    with WidgetsBindingObserver {
  /// Soft cap on concurrent ExoPlayer/MediaCodec instances (OEM hard-decode slots).
  static int _activeControllerCount = 0;
  static const int _maxConcurrentControllers = 2;
  static const Duration _slotRetryInterval = Duration(milliseconds: 250);
  static const Duration _compactProgressDelay = Duration(milliseconds: 300);
  static const Duration _sourceSwitchTailSafety = Duration(milliseconds: 500);

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
  final AppRequestWaitController _initializationWaitController =
      AppRequestWaitController();
  Timer? _compactProgressTimer;
  bool _showCompactProgress = false;
  bool _isInitializationSlow = false;
  bool _forceProgressiveForCurrentDelivery = false;
  _ActiveVideoCandidateSnapshot? _activeCandidateSnapshot;
  Duration? _pendingSourceSwitchPosition;
  late final ProviderSubscription<bool> _adaptivePlaybackFlagSubscription;

  VideoPlaybackSession get _playbackSession =>
      widget.playbackSession ?? _ownedPlaybackSession;

  List<MediaDeliveryReference> _deliveryCandidatesFor(
    VideoPlayerWidget value, {
    bool? featureEnabled,
  }) {
    return AdaptiveVideoDeliverySet(
      progressive: value.deliveryReference,
      adaptive: value.adaptiveDeliveryReference,
      adaptiveDescriptorVersion: value.adaptiveDescriptorVersion,
    ).candidates(
      featureEnabled:
          featureEnabled ??
          ref.read(
            contentFeatureFlagProvider(hlsCmafAdaptivePlaybackFeatureFlag),
          ),
      capabilities: ref.read(platformCapabilitiesProvider),
    );
  }

  String _deliveryCandidateIdentity(
    VideoPlayerWidget value, {
    bool? featureEnabled,
  }) => _deliveryCandidatesFor(
    value,
    featureEnabled: featureEnabled,
  ).map((candidate) => candidate.cacheIdentity).join(' -> ');

  @override
  void initState() {
    super.initState();
    _telemetryRecorder = ref.read(appTelemetryReporterProvider);
    _ownedPlaybackSession = VideoPlaybackSession(
      onNativeSignal: ref
          .read(runtimeDiagnosticsProvider)
          .recordNativeMediaSignal,
    );
    _adaptivePlaybackFlagSubscription = ref.listenManual<bool>(
      contentFeatureFlagProvider(hlsCmafAdaptivePlaybackFeatureFlag),
      (previous, next) {
        if (previous == null || previous == next) {
          return;
        }
        final previousIdentity = _deliveryCandidateIdentity(
          widget,
          featureEnabled: previous,
        );
        final nextCandidates = _deliveryCandidatesFor(
          widget,
          featureEnabled: next,
        );
        final nextIdentity = nextCandidates
            .map((candidate) => candidate.cacheIdentity)
            .join(' -> ');
        if (previousIdentity == nextIdentity) {
          return;
        }
        // HLS/CMAF 是 runtime-overridable 增强链。灰度关闭必须让当前实例
        // 回到同资产 progressive，而不能等 Widget 重建或 App 重启；重新开启
        // 时也要清除本次 delivery 的临时 fallback 记忆再重选候选。
        _forceProgressiveForCurrentDelivery = false;
        if (_activeCandidateSnapshot?.identity ==
            nextCandidates.first.cacheIdentity) {
          return;
        }
        _scheduleControllerLifecycleSync(
          sourceChanged: true,
          preserveSourcePosition: true,
        );
      },
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
    if (_deliveryCandidateIdentity(widget) !=
        _deliveryCandidateIdentity(oldWidget)) {
      _forceProgressiveForCurrentDelivery = false;
      _pendingSourceSwitchPosition = null;
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

  void _scheduleControllerLifecycleSync({
    required bool sourceChanged,
    bool preserveSourcePosition = false,
  }) {
    final generation = ++_controllerLifecycleSyncGeneration;
    final expectedCandidates = _deliveryCandidatesFor(widget);
    final expectedIdentity = expectedCandidates
        .map((candidate) => candidate.cacheIdentity)
        .join(' -> ');
    final expectedPrimaryIdentity = expectedCandidates.first.cacheIdentity;
    final shouldInitialize = widget.initialize;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted ||
          generation != _controllerLifecycleSyncGeneration ||
          expectedIdentity != _deliveryCandidateIdentity(widget) ||
          shouldInitialize != widget.initialize) {
        return;
      }
      if (shouldInitialize &&
          sourceChanged &&
          _controller != null &&
          _activeCandidateSnapshot?.identity == expectedPrimaryIdentity) {
        return;
      }
      // attach/detach 会同步通知 PlaybackSession 的 AnimatedBuilder；
      // didUpdateWidget 的 build 阶段不能直接释放或重建 controller。
      if (shouldInitialize) {
        if (sourceChanged) {
          unawaited(
            _replaceVideoController(
              preserveSourcePosition: preserveSourcePosition,
            ),
          );
        } else {
          unawaited(_initializeVideo());
        }
        return;
      }
      _pendingSourceSwitchPosition = null;
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
    _initializationWaitController.dispose();
    _adaptivePlaybackFlagSubscription.close();
    _pendingSourceSwitchPosition = null;
    _automaticPlaybackSyncGeneration += 1;
    _controllerLifecycleSyncGeneration += 1;
    WidgetsBinding.instance.removeObserver(this);
    unawaited(_disposeActiveControllers());
    _ownedPlaybackSession.dispose();
    super.dispose();
  }

  void _invalidateVideoInitialization() {
    _videoInitGeneration += 1;
    _initializationWaitController.cancel();
    _compactProgressTimer?.cancel();
    _compactProgressTimer = null;
    _showCompactProgress = false;
    _isInitializationSlow = false;
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
    _activeCandidateSnapshot = null;
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
      await Future<void>.delayed(_slotRetryInterval);
    }
  }

  /// Slot already acquired; continue initialization without re-acquiring.
  Future<void> _initializeVideoWithHeldSlot(
    int generation,
    int? slotLeaseId,
  ) async {
    final candidates = _deliveryCandidatesFor(widget);
    final adaptiveCandidateIdentity =
        widget.adaptiveDeliveryReference?.cacheIdentity;
    final firstCandidateIndex =
        _forceProgressiveForCurrentDelivery && candidates.length > 1
        ? candidates.length - 1
        : 0;
    final startupStopwatch = Stopwatch()..start();
    final observedFailures = <MediaCandidateFailureKind>[];
    var retainControllerSlot = false;
    try {
      for (
        var index = firstCandidateIndex;
        index < candidates.length;
        index++
      ) {
        final candidate = candidates[index];
        final candidateUrl = candidate.url;
        List<PlayableVideoSource> sources;
        try {
          sources = await _playableSourcesForCandidate(candidateUrl);
        } catch (error, stackTrace) {
          if (!mounted || generation != _videoInitGeneration) {
            return;
          }
          final kind = _classifyPlaybackFailure(error, candidateUrl);
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
          VideoSeekSettleEvidenceCapability? seekSettleEvidenceCapability;
          try {
            final controllerHandle = source.createController();
            controller = controllerHandle.controller;
            nativePlaybackSignals = controllerHandle.nativePlaybackSignals;
            seekSettleEvidenceCapability =
                controllerHandle.seekSettleEvidenceCapability;
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
              // video_player 2.11 leaves its private creating completer pending
              // when native create throws; awaiting dispose() then never exits
              // and prevents the next delivery candidate from running. A
              // never-created controller owns no native player. The factory
              // disables the plugin lifecycle observer because this widget
              // already owns lifecycle pause/resume, so abandoning this shell
              // cannot retain a WidgetsBinding observer.
              final nativePlayerWasCreated =
                  // video_player 未公开“native create 是否完成”的生产 getter；
                  // 这里只读插件自身的生命周期哨兵，避免对未创建实例 await dispose。
                  // ignore: invalid_use_of_visible_for_testing_member
                  controller.playerId !=
                  // ignore: invalid_use_of_visible_for_testing_member
                  VideoPlayerController.kUninitializedPlayerId;
              if (nativePlayerWasCreated) {
                await _disposeControllerAndReleaseSlot(
                  controller,
                  releaseSlot: false,
                  slotLeaseId: slotLeaseId,
                );
              }
            }
            if (identical(_initializingController, controller)) {
              _initializingController = null;
            }
            if (!mounted || generation != _videoInitGeneration) {
              return;
            }
            final kind = _classifyPlaybackFailure(error, candidateUrl);
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
          final candidateSnapshot = _ActiveVideoCandidateSnapshot(
            generation: generation,
            index: index,
            count: candidates.length,
            identity: candidate.cacheIdentity,
            url: candidateUrl,
            isAdaptive:
                adaptiveCandidateIdentity != null &&
                candidate.cacheIdentity == adaptiveCandidateIdentity,
          );
          _controller = controller;
          _activeCandidateSnapshot = candidateSnapshot;
          _chewieController = chewieController;
          _nativePlaybackSignals = nativePlaybackSignals;
          retainControllerSlot = true;
          _finishInitializationWait();
          _attachControllerErrorListener(
            controller,
            candidateSnapshot: candidateSnapshot,
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
            synchronizeAutomaticPlayback: _pendingSourceSwitchPosition == null,
          );
          await _restoreSourceSwitchPosition(
            controller,
            generation: generation,
            evidenceCapability: seekSettleEvidenceCapability,
          );
          if (!mounted || generation != _videoInitGeneration) {
            return;
          }
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
    required _ActiveVideoCandidateSnapshot candidateSnapshot,
    required String source,
  }) {
    _detachControllerErrorListener();
    _reportedNativeErrorGeneration = null;
    void listener() {
      if (!mounted ||
          candidateSnapshot.generation != _videoInitGeneration ||
          !identical(_controller, controller) ||
          !identical(_activeCandidateSnapshot, candidateSnapshot) ||
          !controller.value.hasError ||
          _reportedNativeErrorGeneration == candidateSnapshot.generation) {
        return;
      }
      _reportedNativeErrorGeneration = candidateSnapshot.generation;
      final description = controller.value.errorDescription?.trim();
      unawaited(
        _handleNativePlaybackError(
          controller: controller,
          candidateSnapshot: candidateSnapshot,
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
    required _ActiveVideoCandidateSnapshot candidateSnapshot,
    required String source,
    required Object error,
    required StackTrace stackTrace,
  }) async {
    if (!mounted ||
        candidateSnapshot.generation != _videoInitGeneration ||
        !identical(_controller, controller) ||
        !identical(_activeCandidateSnapshot, candidateSnapshot) ||
        _hasError) {
      return;
    }
    final kind = _classifyPlaybackFailure(error, candidateSnapshot.url);
    _logCandidateFailure(
      index: candidateSnapshot.index,
      candidateCount: candidateSnapshot.count,
      source: source,
      kind: kind,
      error: error,
      stackTrace: stackTrace,
    );
    final canFallbackToProgressive = candidateSnapshot.canFallbackToProgressive;
    if (canFallbackToProgressive) {
      _captureSourceSwitchPosition();
    }
    await _disposeActiveControllers(
      qoeResult: 'failure',
      qoeFailureCode: kind.name,
    );
    if (!mounted || candidateSnapshot.generation != _videoInitGeneration) {
      return;
    }
    if (canFallbackToProgressive) {
      _forceProgressiveForCurrentDelivery = true;
      setState(() {
        _isInitialized = false;
        _hasError = false;
        _playbackFailure = null;
      });
      await _initializeVideo();
      return;
    }
    _reportPlaybackFailure(
      MediaPlaybackFailure.fromKind(
        kind,
        candidatesTried: candidateSnapshot.index + 1,
      ),
    );
    _pendingSourceSwitchPosition = null;
  }

  void _reportPlaybackFailure(MediaPlaybackFailure failure) {
    _finishInitializationWait();
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
      _showCompactProgress = false;
      _isInitializationSlow = false;
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
                seekEvidenceSource: AppTelemetryValueSeekEvidenceSource
                    .controllerCommandCompletion,
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

  void _captureSourceSwitchPosition() {
    final value = _controller?.value;
    if (value == null || !value.isInitialized) {
      _pendingSourceSwitchPosition = null;
      return;
    }
    final position = value.position;
    final duration = value.duration;
    _pendingSourceSwitchPosition =
        position > Duration.zero &&
            (duration <= Duration.zero || position < duration)
        ? position
        : null;
  }

  Future<VideoSourceSwitchSeekResult?> _restoreSourceSwitchPosition(
    VideoPlayerController controller, {
    required int generation,
    required VideoSeekSettleEvidenceCapability evidenceCapability,
  }) async {
    final pending = _pendingSourceSwitchPosition;
    if (pending == null) {
      return null;
    }
    _pendingSourceSwitchPosition = null;
    final duration = controller.value.duration;
    var target = pending;
    if (duration > Duration.zero && pending >= duration) {
      target = duration - _sourceSwitchTailSafety;
    }
    if (target <= Duration.zero) {
      return null;
    }
    final result = await _playbackSession.restoreSourceSwitchPosition(
      target,
      evidenceCapability: evidenceCapability,
    );
    if (!mounted ||
        generation != _videoInitGeneration ||
        !identical(_controller, controller)) {
      return result;
    }
    return result;
  }

  Future<void> _replaceVideoController({
    bool preserveSourcePosition = false,
  }) async {
    if (preserveSourcePosition) {
      _captureSourceSwitchPosition();
    } else {
      _pendingSourceSwitchPosition = null;
    }
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
    _forceProgressiveForCurrentDelivery = false;
    _pendingSourceSwitchPosition = null;
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
    _beginInitializationWait(generation);
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

  void _beginInitializationWait(int videoGeneration) {
    _compactProgressTimer?.cancel();
    _showCompactProgress = false;
    _isInitializationSlow = false;
    _initializationWaitController.start(
      mode: AppRequestWaitMode.foreground,
      onSlow: (_) {
        if (!mounted || videoGeneration != _videoInitGeneration) return;
        setState(() => _isInitializationSlow = true);
      },
      onTimeout: (_) {
        if (!mounted || videoGeneration != _videoInitGeneration) return;
        _videoInitGeneration += 1;
        _compactProgressTimer?.cancel();
        _compactProgressTimer = null;
        final slotLeaseId = _controllerSlotLeaseId;
        _releaseControllerSlot(leaseId: slotLeaseId);
        unawaited(
          _disposeActiveControllers(
            qoeResult: 'failure',
            qoeFailureCode:
                MediaCandidateFailureKind.initializationTimeout.name,
          ),
        );
        _reportPlaybackFailure(
          MediaPlaybackFailure.fromKind(
            MediaCandidateFailureKind.initializationTimeout,
          ),
        );
      },
    );
    _compactProgressTimer = Timer(_compactProgressDelay, () {
      if (!mounted || videoGeneration != _videoInitGeneration) return;
      setState(() => _showCompactProgress = true);
    });
  }

  void _finishInitializationWait() {
    _compactProgressTimer?.cancel();
    _compactProgressTimer = null;
    _initializationWaitController.complete(
      _initializationWaitController.generation,
    );
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
    final networkUri = Uri.tryParse(normalized);
    final isAdaptiveManifest =
        networkUri != null && networkUri.path.toLowerCase().endsWith('.m3u8');
    // HLS/CMAF 是多对象交付，单文件下载缓存会把 master manifest 脱离相对
    // variant/segment 上下文；adaptive 候选只交给原生网络播放器。
    if (!isAdaptiveManifest) {
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
    }
    if (_isNetworkVideoUri(networkUri) &&
        await _canUseNetworkVideoUri(networkUri!) &&
        seen.add(networkUri.toString())) {
      sources.add(
        PlayableVideoSource.network(
          networkUri,
          formatHint: isAdaptiveManifest ? VideoFormat.hls : null,
        ),
      );
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
