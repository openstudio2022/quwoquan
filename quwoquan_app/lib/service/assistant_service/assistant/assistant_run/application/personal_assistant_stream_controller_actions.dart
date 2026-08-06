// ASSISTANT_WEAK_TYPE: EXTENSION_MAP — runArtifacts 是协议开放 JSON。
part of 'personal_assistant_stream_controller.dart';

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
    try {
      final intent = _actionIntentConsumer.consume(
        action,
        expectedRunId: normalizedRunId,
      );
      switch (intent.kind) {
        case 'ApproveTool':
          await _approveToolIntent(intent.approveTool!);
        case 'ExecuteDeviceAction':
          await _executeDeviceActionIntent(intent.executeDeviceAction!);
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
      _actionsState = _actionsState.copyWith(
        errorMessage: runtimeErrorDisplayMessage(error),
        errorFailure: runtimeFailureFromError(error),
        retryAvailable: false,
      );
    }
  }

  Future<void> _approveToolIntent(AssistantApproveToolIntentWire intent) async {
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
    _actionsState = _actionsState.copyWith(runStatus: result.state);
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
      );
      return;
    }
    await _watchContinuedRun(intent.runId.trim());
  }

  Future<void> _executeDeviceActionIntent(
    AssistantExecuteDeviceActionIntentWire intent,
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
        failureCode: 'ASSISTANT.SYSTEM.device_action_unavailable',
      );
    } else {
      try {
        execution = await executor.execute(intent);
      } on Object {
        execution = AssistantDeviceActionExecutionResult(
          outcome: 'failed',
          executedAt: DateTime.now().toUtc(),
          failureCode: 'ASSISTANT.SYSTEM.device_action_failed',
        );
      }
    }
    final canonicalFailureCode = switch (execution.outcome) {
      'completed' => null,
      'unavailable' => 'ASSISTANT.SYSTEM.device_action_unavailable',
      'denied' => 'ASSISTANT.USER.device_action_permission_denied',
      'failed' => 'ASSISTANT.SYSTEM.device_action_failed',
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
    _actionsState = _actionsState.copyWith(runStatus: run.status);
    await _watchContinuedRun(intent.runId.trim());
  }

  Future<void> _watchContinuedRun(String runId) async {
    final repository = _actionsRef.read(assistantSessionRunFacetProvider);
    AssistantAnswerTranscriptRow? assistantRow;
    for (final row
        in _actionsState.transcript.whereType<AssistantAnswerTranscriptRow>()) {
      if (row.anchor.runId == runId) {
        assistantRow = row;
      }
    }
    if (assistantRow == null) {
      return;
    }
    var lastSeq = _actionsState.events.fold<int>(
      0,
      (maximum, event) => event.seq > maximum ? event.seq : maximum,
    );
    var answer = _actionsState.answer;
    var processSummary = _actionsState.processSummary;
    var presentationDocument = _presentationDocumentFromRow(assistantRow);
    final presentationProjection = AssistantPresentationStreamProjection();
    if (presentationDocument != null &&
        presentationDocument.committedAt.isNotEmpty) {
      presentationProjection.seedCommitted(presentationDocument);
    }
    final events = <AssistantStreamEventWire>[..._actionsState.events];
    var transcript = <AssistantTranscriptTimelineRow>[
      ..._actionsState.transcript,
    ];
    var runStatus = _actionsState.runStatus;
    var terminalObserved = false;
    _actionsState = _actionsState.copyWith(running: true);
    await for (final event in repository.watchAssistantRunEvents(
      runId: runId,
      lastEventId: lastSeq.toString(),
    )) {
      if (event.seq <= lastSeq) {
        continue;
      }
      lastSeq = event.seq;
      events.add(event);
      final streamEvent = AssistantRunStreamEvent.fromWire(event);
      if (streamEvent.type ==
              AssistantRunStreamEventType.presentationSnapshot ||
          streamEvent.type == AssistantRunStreamEventType.presentationPatch ||
          streamEvent.type == AssistantRunStreamEventType.presentationCommit) {
        presentationDocument = presentationProjection.apply(event);
      }
      answer = _projectAnswer(answer, streamEvent);
      processSummary = _projectProcessSummary(
        processSummary,
        streamEvent,
        elapsedMs: processSummary.elapsedMs,
      );
      if (streamEvent.runStatus.isNotEmpty) {
        runStatus = streamEvent.runStatus;
      } else if (streamEvent.type == AssistantRunStreamEventType.completed) {
        runStatus = 'completed';
      } else if (streamEvent.type == AssistantRunStreamEventType.failed) {
        runStatus = 'failed';
      } else if (streamEvent.type == AssistantRunStreamEventType.cancelled) {
        runStatus = 'cancelled';
      }
      terminalObserved = terminalObserved || streamEvent.type.isTerminal;
      transcript = _upsertAssistantTranscript(
        transcript,
        assistantRow.id,
        text: answer,
        runId: runId,
        traceId: assistantRow.anchor.traceId,
        sourceQuery: assistantRow.anchor.sourceQuery,
        eventType: event.eventType.wireName,
        streaming: !streamEvent.type.isTerminal,
        processSummary: processSummary,
        presentationDocument: presentationDocument,
      );
      _actionsState = _actionsState.copyWith(
        running: !terminalObserved,
        runStatus: runStatus,
        answer: answer,
        transcript: transcript,
        processSummary: processSummary,
        events: List<AssistantStreamEventWire>.unmodifiable(events),
        answerGateOpen: _actionsState.answerGateOpen || answer.isNotEmpty,
      );
    }
    if (!terminalObserved) {
      throw const FormatException(
        'Continued AssistantRun stream ended without a terminal event',
      );
    }
  }

  AssistantPresentationDocumentWire? _presentationDocumentFromRow(
    AssistantAnswerTranscriptRow row,
  ) {
    final raw = row.runArtifacts['presentationDocument'];
    if (raw is! Map) {
      return null;
    }
    return AssistantPresentationDocumentWire.fromJson(
      raw.cast<String, dynamic>(),
    );
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
