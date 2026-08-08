// ASSISTANT_WEAK_TYPE: EXTENSION_MAP — runArtifacts 是协议开放 JSON。
part of 'personal_assistant_stream_controller.dart';

const Set<String> _assistantTerminalRunStatuses = <String>{
  'completed',
  'failed',
  'cancelled',
};

bool _isAssistantTerminalRunStatus(String status) =>
    _assistantTerminalRunStatuses.contains(status.trim().toLowerCase());

extension PersonalAssistantRunActions on PersonalAssistantStreamController {
  Future<String?> resolvePresentationMedia(
    AssistantPresentationMediaRefWire media,
  ) async {
    try {
      final uri = await _actionsRef
          .read(assistantPresentationMediaResolverProvider)
          .resolve(mediaAssetId: media.mediaAssetId);
      return uri.toString();
    } catch (error, stackTrace) {
      developer.log(
        'assistant presentation media resolution rejected',
        name: 'assistant.presentation',
        error: error,
        stackTrace: stackTrace,
      );
      return null;
    }
  }

  /// 停止当前生成：发送 CancelAssistantRun 命令；SSE 会以
  /// cancelled 终态事件结束流，send() 收尾时落停止态。
  Future<void> stopGeneration() async {
    final runId = _actionsState.runId.trim();
    if (runId.isEmpty || !_actionsState.running) {
      return;
    }
    try {
      await _actionsRef
          .read(assistantSessionRunFacetProvider)
          .cancelAssistantRun(
            runId: runId,
            commandRequestId: 'cancel-${const Uuid().v4()}',
          );
    } catch (error, stackTrace) {
      developer.log(
        'assistant cancel run failed runId=$runId',
        name: 'personal_assistant',
        error: error,
        stackTrace: stackTrace,
      );
    }
  }

  Future<void> pauseCurrentRun() async {
    final runId = _actionsState.runId.trim();
    if (runId.isEmpty ||
        !_actionsState.running ||
        _actionsState.runStatus == 'paused') {
      return;
    }
    try {
      final run = await _actionsRef
          .read(assistantRunControlFacetProvider)
          .pauseAssistantRun(
            runId: runId,
            commandRequestId: 'pause-${const Uuid().v4()}',
            reason: 'user_requested',
          );
      _actionsState = _actionsState.copyWith(runStatus: run.status);
    } catch (error) {
      _actionsState = _actionsState.copyWith(
        errorMessage: runtimeErrorDisplayMessage(error),
        errorFailure: runtimeFailureFromError(error),
        retryAvailable: false,
      );
    }
  }

  Future<void> resumeCurrentRun() async {
    final runId = _actionsState.runId.trim();
    if (runId.isEmpty ||
        !_actionsState.running ||
        _actionsState.runStatus != 'paused') {
      return;
    }
    try {
      final run = await _actionsRef
          .read(assistantRunControlFacetProvider)
          .resumeAssistantRun(
            runId: runId,
            commandRequestId: 'resume-${const Uuid().v4()}',
          );
      _actionsState = _actionsState.copyWith(runStatus: run.status);
    } catch (error) {
      _actionsState = _actionsState.copyWith(
        errorMessage: runtimeErrorDisplayMessage(error),
        errorFailure: runtimeFailureFromError(error),
        retryAvailable: false,
      );
    }
  }

  bool canHandlePresentationAction(AssistantActionIntentWire action) {
    try {
      final intent = _actionIntentConsumer.inspect(action);
      return switch (intent.kind) {
        'ApproveTool' => true,
        'ExecuteDeviceAction' => _canHandleDeviceActionIntent(
          intent.executeDeviceAction!,
        ),
        'Navigate' =>
          _actionsRef
              .read(assistantNavigateIntentHandlerProvider)
              .canNavigate(intent.navigate!),
        'ProvideInput' =>
          _actionsRef
              .read(assistantProvideInputIntentHandlerProvider)
              .canProvideInput(intent.provideInput!),
        _ => false,
      };
    } on AssistantActionIntentRejected {
      return false;
    }
  }

  bool _canHandleDeviceActionIntent(
    AssistantExecuteDeviceActionIntentWire intent,
  ) {
    final binding = _actionsRef.read(deviceCalendarLocalBindingProvider);
    return binding.isComplete &&
        binding.installationId.trim() == intent.installationId.trim() &&
        binding.deviceId.trim() == intent.deviceId.trim() &&
        _actionsRef
            .read(assistantDeviceActionExecutorProvider)
            .canExecute(intent);
  }

  Future<void> handlePresentationAction({
    required String runId,
    required AssistantActionIntentWire action,
  }) async {
    final normalizedRunId = runId.trim();
    if (normalizedRunId.isEmpty) {
      developer.log(
        'assistant presentation action rejected',
        name: 'assistant.presentation',
        error: <String, Object>{
          'kind': action.kind,
          'intentId': action.intentId,
          'reason': 'missing_run_id',
        },
      );
      return;
    }
    final capturedGeneration = _captureCurrentRunGeneration(normalizedRunId);
    try {
      final intent = _actionIntentConsumer.consume(
        action,
        expectedRunId: normalizedRunId,
      );
      switch (intent.kind) {
        case 'ApproveTool':
          if (capturedGeneration == null) {
            throw const AssistantActionIntentRejected(
              AssistantActionIntentRejection.targetMismatch,
            );
          }
          await _approveToolIntent(intent.approveTool!, capturedGeneration);
        case 'ExecuteDeviceAction':
          if (capturedGeneration == null) {
            throw const AssistantActionIntentRejected(
              AssistantActionIntentRejection.targetMismatch,
            );
          }
          await _executeDeviceActionIntent(
            intent.executeDeviceAction!,
            capturedGeneration,
          );
        case 'Navigate':
          final navigate = intent.navigate!;
          final handler = _actionsRef.read(
            assistantNavigateIntentHandlerProvider,
          );
          if (!handler.canNavigate(navigate)) {
            throw const AssistantActionIntentRejected(
              AssistantActionIntentRejection.invalidShape,
            );
          }
          await handler.navigate(navigate);
        case 'ProvideInput':
          final provideInput = intent.provideInput!;
          final handler = _actionsRef.read(
            assistantProvideInputIntentHandlerProvider,
          );
          if (!handler.canProvideInput(provideInput)) {
            throw const AssistantActionIntentRejected(
              AssistantActionIntentRejection.invalidShape,
            );
          }
          await handler.provideInput(provideInput);
      }
    } catch (error, stackTrace) {
      developer.log(
        'assistant presentation action failed',
        name: 'assistant.presentation',
        error: error,
        stackTrace: stackTrace,
      );
      final stillCurrent = capturedGeneration == null
          ? _actionsState.runId.trim() == normalizedRunId
          : _isRunStreamGenerationCurrent(
              capturedGeneration,
              runId: normalizedRunId,
            );
      if (stillCurrent) {
        _actionsState = _actionsState.copyWith(
          errorMessage: runtimeErrorDisplayMessage(error),
          errorFailure: runtimeFailureFromError(error),
          retryAvailable: false,
        );
      }
    }
  }

  Future<void> _approveToolIntent(
    AssistantApproveToolIntentWire intent,
    _AssistantRunStreamGeneration capturedGeneration,
  ) async {
    final binding = _actionsRef.read(deviceCalendarLocalBindingProvider);
    final result = await _actionsRef
        .read(assistantRunControlFacetProvider)
        .approveAssistantToolUse(
          runId: intent.runId.trim(),
          toolInvocationId: intent.toolInvocationId.trim(),
          commandRequestId: 'approve-${const Uuid().v4()}',
          decision: intent.decision,
          approvalPermit: intent.approvalPermit,
          installationId: binding.isComplete ? binding.installationId : null,
          deviceId: binding.isComplete ? binding.deviceId : null,
        );
    if (result.runId.trim() != intent.runId.trim()) {
      throw const AssistantActionIntentRejected(
        AssistantActionIntentRejection.targetMismatch,
      );
    }
    if (_isRunStreamGenerationCurrent(
      capturedGeneration,
      runId: intent.runId.trim(),
    )) {
      _actionsState = _actionsState.copyWith(runStatus: result.state);
    }
    if (intent.decision == 'rejected') {
      return;
    }

    final permit = result.deviceActionPermit;
    if (permit != null) {
      final permitExpiresAt = DateTime.tryParse(permit.expiresAt);
      if (permit.runId.trim() != intent.runId.trim() ||
          permit.toolInvocationId.trim() != intent.toolInvocationId.trim() ||
          permit.capability.trim() != intent.capability.trim() ||
          permit.inputDigest.trim() != intent.inputDigest.trim() ||
          !binding.isComplete ||
          permit.installationId.trim() != binding.installationId.trim() ||
          permit.deviceId.trim() != binding.deviceId.trim() ||
          permitExpiresAt == null ||
          !permitExpiresAt.toUtc().isAfter(DateTime.now().toUtc())) {
        throw const AssistantActionIntentRejected(
          AssistantActionIntentRejection.targetMismatch,
        );
      }
      await _executeDeviceActionIntent(
        AssistantExecuteDeviceActionIntentWire(
          runId: permit.runId,
          toolInvocationId: permit.toolInvocationId,
          installationId: permit.installationId,
          deviceId: permit.deviceId,
          capability: permit.capability,
          inputDigest: permit.inputDigest,
          idempotencyKey: permit.idempotencyKey,
          deviceActionPermit: permit.permit,
        ),
        capturedGeneration,
      );
      return;
    }
    await _continueRunAfterAction(intent.runId.trim(), capturedGeneration);
  }

  Future<void> _executeDeviceActionIntent(
    AssistantExecuteDeviceActionIntentWire intent,
    _AssistantRunStreamGeneration capturedGeneration,
  ) async {
    _actionIntentConsumer.validateDeviceActionIntent(intent);
    final binding = _actionsRef.read(deviceCalendarLocalBindingProvider);
    if (!binding.isComplete ||
        binding.installationId.trim() != intent.installationId.trim() ||
        binding.deviceId.trim() != intent.deviceId.trim()) {
      throw const AssistantActionIntentRejected(
        AssistantActionIntentRejection.targetMismatch,
      );
    }
    final claimKey = intent.idempotencyKey.trim();
    if (!_claimedDeviceActionKeys.add(claimKey)) {
      throw const AssistantActionIntentRejected(
        AssistantActionIntentRejection.replay,
      );
    }

    final executor = _actionsRef.read(assistantDeviceActionExecutorProvider);
    AssistantDeviceActionExecutionResult execution;
    if (!executor.canExecute(intent)) {
      execution = AssistantDeviceActionExecutionResult(
        outcome: 'unavailable',
        executedAt: DateTime.now().toUtc(),
        failureCode: AssistantErrorCode.deviceActionUnavailable.code,
      );
    } else {
      try {
        execution = await executor.execute(intent);
      } on Object {
        execution = AssistantDeviceActionExecutionResult(
          outcome: 'failed',
          executedAt: DateTime.now().toUtc(),
          failureCode: AssistantErrorCode.deviceActionFailed.code,
        );
      }
    }
    final canonicalFailureCode = switch (execution.outcome) {
      'completed' => null,
      'unavailable' => AssistantErrorCode.deviceActionUnavailable.code,
      'denied' => AssistantErrorCode.deviceActionPermissionDenied.code,
      'failed' => AssistantErrorCode.deviceActionFailed.code,
      _ => throw const FormatException(
        'Device action executor returned an unsupported outcome',
      ),
    };
    final executorFailureCode = execution.failureCode?.trim() ?? '';
    if (executorFailureCode.isNotEmpty &&
        executorFailureCode != canonicalFailureCode) {
      throw const FormatException(
        'Device action executor returned a non-canonical failure code',
      );
    }

    final run = await _actionsRef
        .read(assistantRunControlFacetProvider)
        .submitDeviceActionReceipt(
          runId: intent.runId.trim(),
          toolInvocationId: intent.toolInvocationId.trim(),
          commandRequestId: claimKey,
          receipt: AssistantDeviceActionExecutionReceipt(
            installationId: intent.installationId.trim(),
            deviceId: intent.deviceId.trim(),
            capability: intent.capability.trim(),
            inputDigest: intent.inputDigest.trim(),
            permit: intent.deviceActionPermit.trim(),
            idempotencyKey: claimKey,
            outcome: execution.outcome,
            executedAt: execution.executedAt.toUtc(),
            deviceObjectId: execution.deviceObjectId?.trim().isEmpty ?? true
                ? null
                : execution.deviceObjectId!.trim(),
            failureCode: canonicalFailureCode,
          ),
        );
    if (run.runId.trim() != intent.runId.trim()) {
      throw const AssistantActionIntentRejected(
        AssistantActionIntentRejection.targetMismatch,
      );
    }
    if (_isRunStreamGenerationCurrent(
      capturedGeneration,
      runId: intent.runId.trim(),
    )) {
      _actionsState = _actionsState.copyWith(runStatus: run.status);
      await _continueRunAfterAction(intent.runId.trim(), capturedGeneration);
    }
  }

  Future<void> refreshManagementSummary() async {
    if (!_actionsRef.mounted || _actionsState.managementSummaryLoading) {
      return;
    }
    _actionsState = _actionsState.copyWith(managementSummaryLoading: true);
    try {
      final unread = await _actionsRef
          .read(appMessageQueryProvider)
          .getUnreadCount(GetAppMessageUnreadCountQuery());
      if (!_actionsRef.mounted) {
        return;
      }
      _actionsState = _actionsState.copyWith(
        appMessageUnreadCount: unread.unreadCount,
        managementSummaryLoading: false,
      );
    } catch (error, stackTrace) {
      final domainCode = error is CloudException
          ? (error.domainErrorCode?.code ?? error.code ?? '')
          : '';
      developer.log(
        'assistant unread-count degraded (code=$domainCode)',
        name: 'personal_assistant',
        error: error,
        stackTrace: stackTrace,
      );
      if (_actionsRef.mounted) {
        _actionsState = _actionsState.copyWith(managementSummaryLoading: false);
      }
    }
  }
}
