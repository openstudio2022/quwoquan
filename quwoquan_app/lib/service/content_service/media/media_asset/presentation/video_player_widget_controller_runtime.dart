part of 'video_player_widget.dart';

extension _VideoPlayerWidgetControllerRuntime on _VideoPlayerWidgetState {
  bool _acquireControllerSlot() {
    if (_holdingControllerSlot) {
      return false;
    }
    if (_VideoPlayerWidgetState._activeControllerCount >=
        _VideoPlayerWidgetState._maxConcurrentControllers) {
      return false;
    }
    _VideoPlayerWidgetState._activeControllerCount += 1;
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
    if (_VideoPlayerWidgetState._activeControllerCount > 0) {
      _VideoPlayerWidgetState._activeControllerCount -= 1;
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
      await Future<void>.delayed(_VideoPlayerWidgetState._slotRetryInterval);
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
            identity: _playbackCandidateIdentity(candidate, widget),
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
}
