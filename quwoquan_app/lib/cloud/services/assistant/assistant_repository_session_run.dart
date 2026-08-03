part of 'assistant_repository.dart';

/// Assistant session、run lifecycle 与 SSE 的 generated-client 单轨 Facet。
mixin _RemoteAssistantSessionRun on _RemoteAssistantRepositoryBase
    implements AssistantSessionRunFacet, AssistantRunControlFacet {
  @override
  Future<AssistantSessionWire> createAssistantSession({
    String summary = '',
    required String clientRequestId,
  }) async {
    return _createAssistantSession(
      summary: summary,
      clientRequestId: clientRequestId,
    );
  }

  Future<AssistantSessionWire> _createAssistantSession({
    required String summary,
    required String clientRequestId,
    bool networkSurface = false,
  }) {
    final requestId = _requireAssistantCommandRequestId(
      clientRequestId,
      operation:
          AppCloudOperationIds.assistantAssistantSessionCreateAssistantSession,
    );
    return _core.createSession(
      summary: summary,
      clientRequestId: requestId,
      networkSurface: networkSurface,
    );
  }

  @override
  Future<AssistantSessionWire> getAssistantSession({
    required String sessionId,
  }) {
    return _core.getSession(sessionId: sessionId);
  }

  @override
  Future<AssistantSessionListPage> listAssistantSessions({
    int limit = kAssistantListPageDefaultLimit,
    String cursor = '',
  }) async {
    final page = await _core.listSessions(limit: limit, cursor: cursor);
    return AssistantSessionListPage(
      items: page.items,
      nextCursor: page.nextCursor ?? '',
    );
  }

  @override
  Future<AssistantTurnListView> listSessionTurns({
    required String sessionId,
    int limit = kAssistantListPageDefaultLimit,
    String cursor = '',
  }) {
    return _core.listTurns(sessionId: sessionId, limit: limit, cursor: cursor);
  }

  @override
  Future<AssistantRunEnvelopeWire> cancelAssistantRun({
    required String runId,
    required String commandRequestId,
  }) {
    return _core.cancelRun(
      runId: runId,
      idempotencyKey: _requireAssistantCommandRequestId(
        commandRequestId,
        operation: AppCloudOperationIds.assistantAssistantRunCancelAssistantRun,
      ),
    );
  }

  @override
  Future<AssistantRunEnvelopeWire> pauseAssistantRun({
    required String runId,
    required String commandRequestId,
    String reason = '',
  }) {
    return _core.pauseRun(
      runId: runId,
      reason: reason,
      idempotencyKey: _requireAssistantCommandRequestId(
        commandRequestId,
        operation: AppCloudOperationIds.assistantAssistantRunPauseAssistantRun,
      ),
    );
  }

  @override
  Future<AssistantRunEnvelopeWire> resumeAssistantRun({
    required String runId,
    required String commandRequestId,
  }) {
    return _core.resumeRun(
      runId: runId,
      idempotencyKey: _requireAssistantCommandRequestId(
        commandRequestId,
        operation: AppCloudOperationIds.assistantAssistantRunResumeAssistantRun,
      ),
    );
  }

  @override
  Future<AssistantRunEnvelopeWire> steerAssistantRun({
    required String runId,
    required String commandRequestId,
    required String instruction,
  }) {
    return _core.steerRun(
      runId: runId,
      instruction: instruction,
      idempotencyKey: _requireAssistantCommandRequestId(
        commandRequestId,
        operation: AppCloudOperationIds.assistantAssistantRunSteerAssistantRun,
      ),
    );
  }

  @override
  Future<AssistantRunEnvelopeWire> continueAssistantToolUse({
    required String runId,
    required String toolUseId,
    required String commandRequestId,
    required String decision,
    required String continuationToken,
    AssistantDeviceActionExecutionReceipt? executionReceipt,
  }) {
    return _core.continueToolUse(
      request: AssistantContinueToolUseRequest(
        runId: runId,
        toolUseId: toolUseId,
        decision: decision,
        continuationToken: continuationToken,
        executionReceipt: executionReceipt,
      ),
      idempotencyKey: _requireAssistantCommandRequestId(
        commandRequestId,
        operation:
            AppCloudOperationIds.assistantAssistantRunContinueAssistantToolUse,
      ),
    );
  }

  @override
  Future<AssistantRunEnvelopeWire> startAssistantRun({
    required String sessionId,
    required String text,
    required String clientRequestId,
    List<AssistantIntersectionEvidenceRef> intersectionEvidenceRefs =
        const <AssistantIntersectionEvidenceRef>[],
  }) async {
    final run = await _startAssistantRunIntent(
      sessionId: sessionId,
      clientRequestId: clientRequestId,
      intent: AssistantRunIntent(
        kind: AssistantRunIntentKind.answer,
        answer: AssistantAnswerRunIntent(text: text.trim()),
      ),
      contextSnapshot: intersectionEvidenceRefs.isEmpty
          ? null
          : AssistantContextSnapshot(
              intersectionEvidenceRefs:
                  List<AssistantIntersectionEvidenceRef>.unmodifiable(
                    intersectionEvidenceRefs,
                  ),
            ),
    );
    _debugAssistantRepository(
      'run decoded sessionId=${run.sessionId} runId=${run.runId} traceId=${run.traceId}',
    );
    return run;
  }

  @override
  Future<AssistantRunEnvelopeWire> getAssistantRun({required String runId}) {
    return _core.getRun(runId: runId);
  }

  @override
  Stream<AssistantStreamEventWire> watchAssistantRunEvents({
    required String runId,
    String lastEventId = '',
  }) {
    return _watchAssistantRunEvents(runId: runId, lastEventId: lastEventId);
  }

  Stream<AssistantStreamEventWire> _watchAssistantRunEvents({
    required String runId,
    required String lastEventId,
    bool networkSurface = false,
  }) {
    return _core.watchRunEvents(
      runId: runId,
      resumeToken: lastEventId,
      networkSurface: networkSurface,
    );
  }
}
