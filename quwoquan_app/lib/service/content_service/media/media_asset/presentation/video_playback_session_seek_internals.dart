part of 'video_playback_session.dart';

extension _VideoPlaybackSessionSeekInternals on VideoPlaybackSession {
  Future<_VideoSeekWaitResult> _waitForPhysicalSeekCommand({
    required VideoPlayerController controller,
    required Duration target,
    required Future<void> terminal,
    required _VideoSeekDeadline deadline,
  }) {
    final admission = _seekCommandAdmission;
    if (!admission.tryAcquire(controller)) {
      return Future<_VideoSeekWaitResult>.value(
        const _VideoSeekWaitResult.capacityExceeded(),
      );
    }
    final trackedCommand = Future<void>.sync(
      () => controller.seekTo(target),
    ).whenComplete(() => admission.release(controller));
    return _waitForSeekOperation(
      operation: trackedCommand,
      terminal: terminal,
      deadline: deadline,
    );
  }

  /// 所有 seek 平台调用共用同一个绝对 deadline 和 terminal 唤醒通道。
  ///
  /// 平台 Future 无法主动取消；deadline 或 epoch 终止后仍通过 [then] 消费迟到
  /// 的成功/失败，禁止它重新写入已经 supersede 的会话状态。
  Future<_VideoSeekWaitResult> _waitForSeekOperation({
    required Future<Object?> operation,
    required Future<void> terminal,
    required _VideoSeekDeadline deadline,
  }) {
    final remaining = deadline.remaining;
    if (remaining <= Duration.zero) {
      return Future<_VideoSeekWaitResult>.value(
        const _VideoSeekWaitResult.deadlineExceeded(),
      );
    }
    final operationResult = operation.then<_VideoSeekWaitResult>(
      _VideoSeekWaitResult.completed,
      onError: (Object error, StackTrace stackTrace) =>
          _VideoSeekWaitResult.failed(error, stackTrace),
    );
    final terminalResult = terminal.then<_VideoSeekWaitResult>(
      (_) => const _VideoSeekWaitResult.terminal(),
    );
    return Future.any<_VideoSeekWaitResult>(<Future<_VideoSeekWaitResult>>[
      operationResult,
      terminalResult,
    ]).timeout(
      remaining,
      onTimeout: () => const _VideoSeekWaitResult.deadlineExceeded(),
    );
  }

  Future<VideoSourceSwitchSeekResult> _waitForSourceSwitchPositionReadback({
    required VideoPlayerController controller,
    required int generation,
    required Duration target,
    required Duration tolerance,
    required _VideoSeekDeadline deadline,
    required Future<void> terminal,
    required VideoSeekSettleEvidenceCapability evidenceCapability,
  }) async {
    Duration? observedPosition;
    while (deadline.remaining > Duration.zero) {
      if (!identical(controller, _controller) || generation != _generation) {
        return _sourceSwitchSupersededResult(
          target: target,
          elapsedMs: deadline.elapsedMs,
          evidenceCapability: evidenceCapability,
        );
      }
      final readbackWait = await _waitForSeekOperation(
        operation: Future<Duration?>.sync(() => controller.position),
        terminal: terminal,
        deadline: deadline,
      );
      if (readbackWait.disposition == _VideoSeekWaitDisposition.terminal) {
        return _sourceSwitchSupersededResult(
          target: target,
          elapsedMs: deadline.elapsedMs,
          evidenceCapability: evidenceCapability,
        );
      }
      if (readbackWait.disposition == _VideoSeekWaitDisposition.failed) {
        developer.log(
          'video source-switch position readback unavailable',
          name: 'VideoPlaybackSession',
          error: readbackWait.error,
          stackTrace: readbackWait.stackTrace,
        );
        return VideoSourceSwitchSeekResult(
          outcome: VideoSourceSwitchSeekOutcome.settleUnsupported,
          target: target,
          observedPosition: observedPosition,
          elapsedMs: deadline.elapsedMs,
          evidenceCapability: evidenceCapability,
        );
      }
      if (readbackWait.disposition ==
          _VideoSeekWaitDisposition.deadlineExceeded) {
        break;
      }
      observedPosition = readbackWait.value as Duration?;
      if (observedPosition != null &&
          (observedPosition.inMilliseconds - target.inMilliseconds).abs() <=
              tolerance.inMilliseconds) {
        return VideoSourceSwitchSeekResult(
          outcome: VideoSourceSwitchSeekOutcome.positionReadbackSettled,
          target: target,
          observedPosition: observedPosition,
          elapsedMs: deadline.elapsedMs,
          evidenceCapability: evidenceCapability,
        );
      }
      final delayRemaining = deadline.remaining;
      if (delayRemaining <= Duration.zero) {
        break;
      }
      final delayWait = await _waitForSeekOperation(
        operation: Future<void>.delayed(
          delayRemaining <
                  VideoPlaybackSession._sourceSwitchReadbackPollInterval
              ? delayRemaining
              : VideoPlaybackSession._sourceSwitchReadbackPollInterval,
        ),
        terminal: terminal,
        deadline: deadline,
      );
      if (delayWait.disposition == _VideoSeekWaitDisposition.terminal) {
        return _sourceSwitchSupersededResult(
          target: target,
          elapsedMs: deadline.elapsedMs,
          evidenceCapability: evidenceCapability,
        );
      }
    }
    return VideoSourceSwitchSeekResult(
      outcome: VideoSourceSwitchSeekOutcome.settleUnsupported,
      target: target,
      observedPosition: observedPosition,
      elapsedMs: deadline.elapsedMs,
      evidenceCapability: evidenceCapability,
    );
  }

  VideoSourceSwitchSeekResult _sourceSwitchSupersededResult({
    required Duration target,
    required int elapsedMs,
    required VideoSeekSettleEvidenceCapability evidenceCapability,
  }) {
    return VideoSourceSwitchSeekResult(
      outcome: VideoSourceSwitchSeekOutcome.superseded,
      target: target,
      elapsedMs: elapsedMs,
      evidenceCapability: evidenceCapability,
    );
  }

  bool _completeSourceSwitchSeek({
    required int requestId,
    required int generation,
    required VideoSourceSwitchSeekResult result,
    bool notifyListeners = true,
  }) {
    if (!_isCurrentPendingSeek(requestId: requestId, generation: generation) ||
        _pendingSeekPurpose != _VideoSeekPurpose.sourceSwitch) {
      return false;
    }
    final completer = _pendingSourceSwitchSeekCompleter;
    _recordSourceSwitchSeekResult(
      result,
      generation: generation,
      notifyListeners: notifyListeners,
    );
    _clearPendingSeek(requestId: requestId);
    if (completer != null && !completer.isCompleted) {
      completer.complete(result);
    }
    return true;
  }

  void _recordSourceSwitchSeekResult(
    VideoSourceSwitchSeekResult result, {
    required int generation,
    bool notifyListeners = true,
  }) {
    _lastSourceSwitchSeekResult = result;
    _seekEvidenceSource = result.evidenceSource;
    if (result.countsAsFailure) {
      _seekFailureCount += 1;
    }
    if (result.outcome != VideoSourceSwitchSeekOutcome.commandTimedOut &&
        result.outcome !=
            VideoSourceSwitchSeekOutcome.commandCapacityExceeded &&
        result.outcome != VideoSourceSwitchSeekOutcome.commandFailed &&
        result.outcome != VideoSourceSwitchSeekOutcome.superseded) {
      _seekSettleMaxMs = result.elapsedMs > _seekSettleMaxMs
          ? result.elapsedMs
          : _seekSettleMaxMs;
    }
    if (result.isSettled) {
      _lastStablePosition = result.observedPosition ?? result.target;
      _runtimeFailure = null;
    } else if (result.outcome == VideoSourceSwitchSeekOutcome.commandTimedOut ||
        result.outcome ==
            VideoSourceSwitchSeekOutcome.commandCapacityExceeded ||
        result.outcome == VideoSourceSwitchSeekOutcome.commandFailed) {
      _runtimeFailure = _seekRuntimeFailure(
        generation,
        semanticReason: switch (result.outcome) {
          VideoSourceSwitchSeekOutcome.commandTimedOut =>
            'source_switch_seek_command_timeout',
          VideoSourceSwitchSeekOutcome.commandCapacityExceeded =>
            'source_switch_seek_command_capacity_exceeded',
          _ => 'source_switch_seek_command_failed',
        },
        evidenceSource: result.evidenceSource,
      );
    }
    _lastSeekLifecycleEvent = VideoSeekLifecycleEvent(
      phase: switch (result.outcome) {
        VideoSourceSwitchSeekOutcome.nativeSettled ||
        VideoSourceSwitchSeekOutcome.positionReadbackSettled =>
          VideoSeekLifecyclePhase.commandCompleted,
        VideoSourceSwitchSeekOutcome.nativeSettleTimedOut =>
          VideoSeekLifecyclePhase.settleTimedOut,
        VideoSourceSwitchSeekOutcome.settleUnsupported =>
          VideoSeekLifecyclePhase.settleUnsupported,
        VideoSourceSwitchSeekOutcome.commandTimedOut =>
          VideoSeekLifecyclePhase.commandTimedOut,
        VideoSourceSwitchSeekOutcome.commandCapacityExceeded =>
          VideoSeekLifecyclePhase.commandCapacityExceeded,
        VideoSourceSwitchSeekOutcome.commandFailed =>
          VideoSeekLifecyclePhase.failed,
        VideoSourceSwitchSeekOutcome.superseded =>
          VideoSeekLifecyclePhase.superseded,
      },
      target: result.target,
      generation: generation,
      elapsedMs: result.elapsedMs,
      hasNativeSettleEvidence:
          result.outcome == VideoSourceSwitchSeekOutcome.nativeSettled,
    );
    if (notifyListeners) {
      _notify();
    }
  }

  void _supersedePendingSeek({bool notifyListeners = true}) {
    final purpose = _pendingSeekPurpose;
    if (purpose == null) {
      return;
    }
    final target = _pendingSeekTarget;
    final generation = _pendingSeekGeneration;
    final requestId = _pendingSeekRequestId;
    if (target == null || generation == null || requestId == null) {
      _clearPendingSeek();
      return;
    }
    final startedAt = _pendingSeekStartedAt;
    final elapsedMs = startedAt == null
        ? 0
        : _now().difference(startedAt).inMilliseconds.clamp(0, 1 << 31).toInt();
    if (purpose == _VideoSeekPurpose.sourceSwitch) {
      final result = _sourceSwitchSupersededResult(
        target: target,
        elapsedMs: elapsedMs,
        evidenceCapability:
            _pendingSourceSwitchSeekEvidenceCapability ??
            VideoSeekSettleEvidenceCapability.positionReadbackOnly,
      );
      _completeSourceSwitchSeek(
        requestId: requestId,
        generation: generation,
        result: result,
        notifyListeners: notifyListeners,
      );
      return;
    }
    _lastSeekLifecycleEvent = VideoSeekLifecycleEvent(
      phase: VideoSeekLifecyclePhase.superseded,
      target: target,
      generation: generation,
      elapsedMs: elapsedMs,
      hasNativeSettleEvidence: false,
    );
    _clearPendingSeek(requestId: requestId);
    if (notifyListeners) {
      _notify();
    }
  }

  RuntimeFailure _seekRuntimeFailure(
    int generation, {
    String semanticReason = 'seek_command_failed',
    String evidenceSource =
        AppTelemetryValueSeekEvidenceSource.controllerCommandCompletion,
  }) {
    final errorCode = ContentErrorCode.mediaSeekFailed;
    return RuntimeFailure(
      code: errorCode.code,
      semanticReason: semanticReason,
      transportStatus: errorCode.httpStatus,
      origin: RuntimeFailureOrigin.localClient,
      kind: RuntimeFailureKind.unavailable,
      nature: RuntimeFailureNature.transient,
      location: const RuntimeFailureLocation(
        businessObject: 'content.post',
        functionModule: 'video_playback_seek',
      ),
      context: RuntimeFailureContext(
        attributes: <RuntimeContextAttribute>[
          RuntimeContextAttribute(
            key: 'sessionGeneration',
            value: generation.toString(),
          ),
          RuntimeContextAttribute(key: 'evidenceSource', value: evidenceSource),
        ],
      ),
      recovery: RuntimeRecoveryDirective(
        action: errorCode.recoveryAction,
        afterSeconds: errorCode.recoveryAfterSeconds,
      ),
    );
  }
}
