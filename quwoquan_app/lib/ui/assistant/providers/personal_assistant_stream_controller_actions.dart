// ASSISTANT_WEAK_TYPE: EXTENSION_MAP — presentation action payload 与 runArtifacts 是协议开放 JSON。
part of 'personal_assistant_stream_controller.dart';

extension PersonalAssistantRunActions on PersonalAssistantStreamController {
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
    if (action.operation ==
        AssistantApiMetadata.setAssistantPreferenceOperation) {
      return action.objectTypeRef == 'assistant_preference_candidate' &&
          action.objectId.trim().isNotEmpty &&
          action.intentId.trim().isNotEmpty &&
          action.requiresConfirmation &&
          _memoryConfirmation(action) != null;
    }
    final decision = (action.payload['decision'] as String?)?.trim() ?? '';
    final continuationToken =
        (action.payload['continuationToken'] as String?)?.trim() ?? '';
    final validDeviceAction =
        decision != 'approved' || _calendarReminderRequest(action) != null;
    return action.operation ==
            AssistantApiMetadata.continueAssistantToolUseOperation &&
        action.objectTypeRef == 'assistant_tool_use' &&
        action.objectId.trim().isNotEmpty &&
        action.intentId.trim().isNotEmpty &&
        (decision == 'approved' || decision == 'rejected') &&
        continuationToken.isNotEmpty &&
        validDeviceAction;
  }

  Future<void> handlePresentationAction({
    required String runId,
    required AssistantActionIntentWire action,
  }) async {
    final normalizedRunId = runId.trim();
    if (normalizedRunId.isEmpty || !canHandlePresentationAction(action)) {
      developer.log(
        'assistant presentation action rejected',
        name: 'assistant.presentation',
        error: <String, Object>{
          'operation': action.operation,
          'intentId': action.intentId,
        },
      );
      return;
    }
    final requestedDecision = (action.payload['decision'] as String).trim();
    try {
      if (action.operation ==
          AssistantApiMetadata.setAssistantPreferenceOperation) {
        final candidate = _memoryConfirmation(action)!;
        if (candidate.decision == 'approved') {
          await _actionsRef
              .read(assistantPreferenceFactFacetProvider)
              .setAssistantPreference(
                scope: AssistantPreferenceScope.longTerm,
                kind: candidate.kind,
                value: candidate.value,
                sourceType: AssistantPreferenceSourceType.sessionConfirmed,
                sourceSessionId: candidate.sourceSessionId,
                confirmed: true,
              );
        }
        return;
      }
      final continuationToken = (action.payload['continuationToken'] as String)
          .trim();
      var decision = requestedDecision;
      AssistantDeviceActionExecutionReceipt? executionReceipt;
      if (requestedDecision == 'approved') {
        final reminder = _calendarReminderRequest(action)!;
        final capabilities = _actionsRef.read(platformCapabilitiesProvider);
        final result = capabilities.calendarWrite
            ? await _actionsRef
                  .read(assistantDeviceActionBridgeProvider)
                  .createCalendarReminder(reminder)
            : const AssistantDeviceActionResult(
                status: AssistantDeviceActionStatus.unavailable,
              );
        executionReceipt = _calendarExecutionReceipt(reminder, result);
        if (!result.created) {
          decision = 'rejected';
          _actionsState = _actionsState.copyWith(
            errorMessage: AssistantText.assistantDeviceActionUnavailable,
            retryAvailable: false,
          );
        }
      }
      final run = await _actionsRef
          .read(assistantRunControlFacetProvider)
          .continueAssistantToolUse(
            runId: normalizedRunId,
            toolUseId: action.objectId.trim(),
            commandRequestId:
                'continue-${action.intentId}-${const Uuid().v4()}',
            decision: decision,
            continuationToken: continuationToken,
            executionReceipt: executionReceipt,
          );
      _actionsState = _actionsState.copyWith(runStatus: run.status);
      if (decision == 'approved') {
        await _watchContinuedRun(normalizedRunId);
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

  AssistantCalendarReminderRequest? _calendarReminderRequest(
    AssistantActionIntentWire action,
  ) {
    final rawAction = action.payload['deviceAction'];
    if (rawAction is! Map || rawAction['kind'] != 'calendar_create_reminder') {
      return null;
    }
    final idempotencyKey =
        (rawAction['idempotencyKey'] as String?)?.trim() ?? '';
    final rawInput = rawAction['input'];
    if (idempotencyKey.isEmpty || rawInput is! Map) {
      return null;
    }
    final title = (rawInput['title'] as String?)?.trim() ?? '';
    final startsAtRaw = (rawInput['startsAt'] as String?)?.trim() ?? '';
    final startsAt = DateTime.tryParse(startsAtRaw);
    final durationMinutes =
        (rawInput['durationMinutes'] as num?)?.toInt() ?? 60;
    final reminderMinutes =
        (rawInput['reminderMinutes'] as num?)?.toInt() ?? 10;
    final notes = (rawInput['notes'] as String?)?.trim() ?? '';
    if (title.isEmpty ||
        title.runes.length > 200 ||
        startsAt == null ||
        durationMinutes < 1 ||
        durationMinutes > 1440 ||
        reminderMinutes < 0 ||
        reminderMinutes > 10080 ||
        notes.runes.length > 2000) {
      return null;
    }
    return AssistantCalendarReminderRequest(
      idempotencyKey: idempotencyKey,
      title: title,
      startsAt: startsAt,
      durationMinutes: durationMinutes,
      reminderMinutes: reminderMinutes,
      notes: notes,
    );
  }

  ({
    AssistantPreferenceKind kind,
    String value,
    String sourceSessionId,
    String decision,
  })?
  _memoryConfirmation(AssistantActionIntentWire action) {
    final decision = (action.payload['decision'] as String?)?.trim() ?? '';
    final value = (action.payload['value'] as String?)?.trim() ?? '';
    final sourceSessionId =
        (action.payload['sourceSessionId'] as String?)?.trim() ?? '';
    final rawKind = (action.payload['kind'] as String?)?.trim() ?? '';
    if ((decision != 'approved' && decision != 'rejected') ||
        value.isEmpty ||
        value.runes.length > 500 ||
        sourceSessionId.isEmpty ||
        rawKind.isEmpty) {
      return null;
    }
    final kind = parseAssistantPreferenceKind(rawKind);
    if (!const <AssistantPreferenceKind>{
      AssistantPreferenceKind.frequentLocations,
      AssistantPreferenceKind.familyTerms,
      AssistantPreferenceKind.dietaryRestrictions,
      AssistantPreferenceKind.travelPreferences,
    }.contains(kind)) {
      return null;
    }
    return (
      kind: kind,
      value: value,
      sourceSessionId: sourceSessionId,
      decision: decision,
    );
  }

  AssistantDeviceActionExecutionReceipt _calendarExecutionReceipt(
    AssistantCalendarReminderRequest request,
    AssistantDeviceActionResult result,
  ) {
    final (outcome, failureCode) = switch (result.status) {
      AssistantDeviceActionStatus.created => ('completed', null),
      AssistantDeviceActionStatus.unavailable => (
        'unavailable',
        'ASSISTANT.SYSTEM.device_action_unavailable',
      ),
      AssistantDeviceActionStatus.denied => (
        'denied',
        'ASSISTANT.USER.device_action_permission_denied',
      ),
      AssistantDeviceActionStatus.failed => (
        'failed',
        'ASSISTANT.SYSTEM.device_action_failed',
      ),
    };
    return AssistantDeviceActionExecutionReceipt(
      actionKind: 'calendar_create_reminder',
      idempotencyKey: request.idempotencyKey,
      outcome: outcome,
      executedAt: DateTime.now().toUtc().toIso8601String(),
      deviceObjectId: result.deviceObjectId.trim().isEmpty
          ? null
          : result.deviceObjectId.trim(),
      failureCode: failureCode,
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
