import 'package:quwoquan_app/cloud/runtime/generated/assistant/assistant_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef AssistantInvocationContextFactory =
    CloudOperationInvocationContext Function(
      String clientPageId, {
      String? idempotencyKey,
      bool networkSurface,
    });

/// Assistant 对话核心的唯一 generated-client Remote owner。
///
/// Session、Run、SSE、Entry、Task、PageContext 与 Preference 全部经同一
/// ContractGraph 生成 facade；此处不拥有 path、HTTP、JSON decoder 或重试策略。
final class RemoteAssistantCoreAdapter {
  const RemoteAssistantCoreAdapter({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final AssistantInvocationContextFactory invocationContext;

  Future<AssistantSessionWire> createSession({
    required String summary,
    required String clientRequestId,
    bool networkSurface = false,
  }) {
    return client.assistantAssistantSessionCreateAssistantSession(
      AssistantCreateSessionRequest(
        summary: summary.trim().isEmpty ? null : summary.trim(),
        clientRequestId: clientRequestId,
      ),
      context: invocationContext(
        AssistantRequestPageIds.createAssistantSession,
        idempotencyKey: clientRequestId,
        networkSurface: networkSurface,
      ),
    );
  }

  Future<AssistantSessionWire> getSession({required String sessionId}) {
    return client.assistantAssistantSessionGetAssistantSession(
      AssistantSessionByIdQuery(sessionId: sessionId),
      context: invocationContext(AssistantRequestPageIds.getAssistantSession),
    );
  }

  Future<AssistantSessionListView> listSessions({
    required int limit,
    required String cursor,
  }) {
    return client.assistantAssistantSessionListAssistantSessions(
      AssistantSessionListQuery(limit: limit, cursor: cursor),
      context: invocationContext(AssistantRequestPageIds.listAssistantSessions),
    );
  }

  Future<AssistantTurnListView> listTurns({
    required String sessionId,
    required int limit,
    required String cursor,
  }) {
    return client.assistantAssistantTurnViewListSessionTurns(
      AssistantTurnListQuery(
        sessionId: sessionId,
        limit: limit,
        cursor: cursor.trim().isEmpty ? null : cursor.trim(),
      ),
      context: invocationContext(AssistantRequestPageIds.listSessionTurns),
    );
  }

  Future<AssistantRunEnvelopeWire> startRun({
    required AssistantStartRunRequest request,
    required String idempotencyKey,
    bool networkSurface = false,
  }) {
    return client.assistantAssistantRunStartAssistantRun(
      request,
      context: invocationContext(
        AssistantRequestPageIds.startAssistantRun,
        idempotencyKey: idempotencyKey,
        networkSurface: networkSurface,
      ),
    );
  }

  Future<AssistantRunEnvelopeWire> getRun({
    required String runId,
    bool networkSurface = false,
  }) {
    return client.assistantAssistantRunGetAssistantRun(
      AssistantRunByIdQuery(runId: runId),
      context: invocationContext(
        AssistantRequestPageIds.getAssistantRun,
        networkSurface: networkSurface,
      ),
    );
  }

  Future<AssistantRunEnvelopeWire> cancelRun({
    required String runId,
    required String idempotencyKey,
  }) {
    return client.assistantAssistantRunCancelAssistantRun(
      AssistantRunCommandRequest(runId: runId),
      context: invocationContext(
        AssistantRequestPageIds.cancelAssistantRun,
        idempotencyKey: idempotencyKey,
      ),
    );
  }

  Future<AssistantRunEnvelopeWire> pauseRun({
    required String runId,
    required String reason,
    required String idempotencyKey,
  }) {
    return client.assistantAssistantRunPauseAssistantRun(
      AssistantPauseRunRequest(
        runId: runId,
        reason: reason.trim().isEmpty ? null : reason.trim(),
      ),
      context: invocationContext(
        AssistantRequestPageIds.pauseAssistantRun,
        idempotencyKey: idempotencyKey,
      ),
    );
  }

  Future<AssistantRunEnvelopeWire> resumeRun({
    required String runId,
    required String idempotencyKey,
  }) {
    return client.assistantAssistantRunResumeAssistantRun(
      AssistantRunCommandRequest(runId: runId),
      context: invocationContext(
        AssistantRequestPageIds.resumeAssistantRun,
        idempotencyKey: idempotencyKey,
      ),
    );
  }

  Future<AssistantRunEnvelopeWire> steerRun({
    required String runId,
    required String instruction,
    required String idempotencyKey,
  }) {
    return client.assistantAssistantRunSteerAssistantRun(
      AssistantSteerRunRequest(runId: runId, instruction: instruction),
      context: invocationContext(
        AssistantRequestPageIds.steerAssistantRun,
        idempotencyKey: idempotencyKey,
      ),
    );
  }

  Future<AssistantRunEnvelopeWire> continueToolUse({
    required AssistantContinueToolUseRequest request,
    required String idempotencyKey,
  }) {
    return client.assistantAssistantRunContinueAssistantToolUse(
      request,
      context: invocationContext(
        AssistantRequestPageIds.continueAssistantToolUse,
        idempotencyKey: idempotencyKey,
      ),
    );
  }

  Stream<AssistantStreamEventWire> watchRunEvents({
    required String runId,
    required String resumeToken,
    bool networkSurface = false,
  }) {
    return client.assistantAssistantRunStreamAssistantRunEvents(
      AssistantRunEventStreamQuery(
        runId: runId,
        resumeToken: resumeToken.trim().isEmpty ? null : resumeToken.trim(),
      ),
      context: invocationContext(
        AssistantRequestPageIds.streamAssistantRunEvents,
        networkSurface: networkSurface,
      ),
    );
  }

  Future<PageContextReceipt> reportPageContext(PageContextSnapshot snapshot) {
    return client.assistantPageContextReportPageContext(
      ReportPageContextCommand(contextSnapshot: snapshot),
      context: invocationContext(AssistantRequestPageIds.reportPageContext),
    );
  }

  Future<AssistantEntryResponse> getEntry({
    required AssistantEntryQuery query,
  }) {
    return client.assistantAssistantEntryViewGetAssistantEntry(
      query,
      context: invocationContext(AssistantRequestPageIds.getAssistantEntry),
    );
  }

  Future<AssistantTaskSlice> listTasks({
    required int limit,
    required String? status,
  }) {
    return client.assistantAssistantTaskViewListAssistantTasks(
      ListAssistantTasksQuery(limit: limit, status: status),
      context: invocationContext(AssistantRequestPageIds.listAssistantTasks),
    );
  }

  Future<AssistantPreference> setPreference(
    SetAssistantPreferenceRequest request,
  ) {
    return client.assistantAssistantPreferenceSetAssistantPreference(
      request,
      context: invocationContext(
        AssistantRequestPageIds.setAssistantPreference,
      ),
    );
  }

  Future<AssistantPreferenceListView> listPreferences(
    ListAssistantPreferencesQuery query,
  ) {
    return client.assistantAssistantPreferenceListAssistantPreferences(
      query,
      context: invocationContext(
        AssistantRequestPageIds.listAssistantPreferences,
      ),
    );
  }

  Future<AssistantPreference> revokePreference(String preferenceId) {
    return client.assistantAssistantPreferenceRevokeAssistantPreference(
      AssistantPreferenceByIdRequest(preferenceId: preferenceId),
      context: invocationContext(
        AssistantRequestPageIds.revokeAssistantPreference,
      ),
    );
  }

  Future<AssistantPreference> restorePreference(String preferenceId) {
    return client.assistantAssistantPreferenceRestoreAssistantPreference(
      AssistantPreferenceByIdRequest(preferenceId: preferenceId),
      context: invocationContext(
        AssistantRequestPageIds.restoreAssistantPreference,
      ),
    );
  }
}
