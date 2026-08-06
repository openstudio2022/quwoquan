import 'package:quwoquan_app/service/assistant_service/assistant/assistant_session/application/public/assistant_session_ports.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_turn_view/application/public/assistant_turn_query.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/application/public/assistant_run_ports.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/application/public/assistant_session_run_facade.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

class InMemoryAssistantSearchRunFacet implements AssistantSearchRunFacade {
  @override
  Future<AssistantRunTerminalSnapshotView> executeAssistantSearch({
    required String query,
    required String sessionClientRequestId,
    required String runClientRequestId,
    SearchIntensity searchIntensity = SearchIntensity.medium,
    AssistantContextSnapshot? contextSnapshot,
  }) async {
    final trimmedQuery = query.trim();
    return AssistantRunTerminalSnapshotView(
      answerText: trimmedQuery.isEmpty
          ? '小趣搜会结合圈子讨论结果和已有公开内容，为你梳理当前最相关的线索。'
          : '小趣搜正在整理“$trimmedQuery”的公开线索，会优先总结当前最相关的话题、圈子讨论与内容方向。',
      processes: const <AssistantRunVisibleProcessView>[],
    );
  }
}

class InMemoryAssistantCreationRunCommandWriter
    implements AssistantCreationRunCommandWriter {
  @override
  Future<AssistantRunEnvelopeWire> startCreationRun({
    required String sessionId,
    required String clientRequestId,
    required AssistantCreationRunIntent intent,
    AssistantContextSnapshot? contextSnapshot,
  }) async {
    return AssistantRunEnvelopeWire(
      runId: 'arn_mock_creation_${clientRequestId.trim()}',
      sessionId: sessionId,
      goal: <String?>[
        intent.draftTitle,
        intent.draftSummary,
        intent.bodyDigest,
      ].whereType<String>().join(' ').trim(),
      traceId: 'trace_mock_creation_${clientRequestId.trim()}',
      createdAt: DateTime.now().toUtc().toIso8601String(),
    );
  }
}

class InMemoryAssistantSessionRunFacade implements AssistantSessionRunFacade {
  @override
  Future<AssistantSessionWire> createAssistantSession({
    String summary = '',
    required String clientRequestId,
  }) async {
    final now = DateTime.now().toUtc().toIso8601String();
    return AssistantSessionWire(
      sessionId: 'asn_mock_personal_assistant',
      userId: 'mock-user',
      summary: summary,
      createdAt: now,
      updatedAt: now,
    );
  }

  @override
  Future<AssistantSessionListView> listAssistantSessions({
    int limit = kAssistantSessionListDefaultLimit,
    String cursor = '',
  }) async => const AssistantSessionListView(items: <AssistantSessionWire>[]);

  @override
  Future<AssistantSessionWire> getAssistantSession({
    required String sessionId,
  }) async {
    final now = DateTime.now().toUtc().toIso8601String();
    return AssistantSessionWire(
      sessionId: sessionId,
      userId: 'mock-user',
      createdAt: now,
      updatedAt: now,
    );
  }

  @override
  Future<AssistantTurnListView> listSessionTurns({
    required String sessionId,
    int limit = kAssistantTurnListDefaultLimit,
    String cursor = '',
  }) async => const AssistantTurnListView(items: <AssistantTurnSummaryView>[]);

  @override
  Future<AssistantRunEnvelopeWire> startAssistantRun({
    required String sessionId,
    required String text,
    required String clientRequestId,
    String turnType = 'user',
    String skillId = '',
    String domainId = '',
    List<AssistantIntersectionEvidenceRef> intersectionEvidenceRefs =
        const <AssistantIntersectionEvidenceRef>[],
  }) async {
    return AssistantRunEnvelopeWire(
      runId: 'arn_mock_personal_assistant',
      sessionId: sessionId,
      goal: text,
      traceId: 'trace_mock_personal_assistant',
      createdAt: DateTime.now().toUtc().toIso8601String(),
    );
  }

  @override
  Future<AssistantRunEnvelopeWire> getAssistantRun({
    required String runId,
  }) async => AssistantRunEnvelopeWire(
    runId: runId,
    sessionId: 'asn_mock_personal_assistant',
    traceId: 'trace_mock_personal_assistant',
    createdAt: DateTime.now().toUtc().toIso8601String(),
  );

  @override
  Future<AssistantRunEnvelopeWire> cancelAssistantRun({
    required String runId,
    required String commandRequestId,
  }) async => AssistantRunEnvelopeWire(
    runId: runId,
    sessionId: 'asn_mock_personal_assistant',
    traceId: 'trace_mock_personal_assistant',
    createdAt: DateTime.now().toUtc().toIso8601String(),
  );

  @override
  Stream<AssistantStreamEventWire> watchAssistantRunEvents({
    required String runId,
    String lastEventId = '',
  }) async* {
    final createdAt = DateTime.now().toUtc().toIso8601String();
    yield AssistantStreamEventWire(
      schema: 'assistant_stream_event',
      eventId: '$runId:run_started',
      sessionId: 'asn_mock_personal_assistant',
      runId: runId,
      seq: 1,
      eventType: AssistantStreamEventType.runStarted,
      payload: const <String, dynamic>{'status': 'running', 'restarted': false},
      createdAt: createdAt,
    );
    yield AssistantStreamEventWire(
      schema: 'assistant_stream_event',
      eventId: '$runId:process_replace',
      sessionId: 'asn_mock_personal_assistant',
      runId: runId,
      seq: 2,
      eventType: AssistantStreamEventType.processReplace,
      payload: const <String, dynamic>{'processes': <Object?>[]},
      createdAt: createdAt,
    );
    yield AssistantStreamEventWire(
      schema: 'assistant_stream_event',
      eventId: '$runId:searching',
      sessionId: 'asn_mock_personal_assistant',
      runId: runId,
      seq: 3,
      eventType: AssistantStreamEventType.processAppend,
      payload: const <String, dynamic>{
        'process': <String, dynamic>{
          'processId': 'searching',
          'scope': 'skill',
          'stage': 'searching',
          'status': 'completed',
          'order': 1,
          'summary': '已完成可用信息的核对。',
          'toolName': 'web_search',
        },
      },
      createdAt: createdAt,
    );
    yield AssistantStreamEventWire(
      schema: 'assistant_stream_event',
      eventId: '$runId:answer_delta',
      sessionId: 'asn_mock_personal_assistant',
      runId: runId,
      seq: 4,
      eventType: AssistantStreamEventType.answerDelta,
      payload: const <String, dynamic>{'text': '找私助 mock stream 已接通。'},
      createdAt: createdAt,
    );
    yield AssistantStreamEventWire(
      schema: 'assistant_stream_event',
      eventId: '$runId:completed',
      sessionId: 'asn_mock_personal_assistant',
      runId: runId,
      seq: 5,
      eventType: AssistantStreamEventType.completed,
      payload: const <String, dynamic>{
        'status': 'completed',
        'finalAnswer': '找私助 mock stream 已接通。',
      },
      createdAt: createdAt,
    );
  }
}

class InMemoryAssistantRunControlFacet implements AssistantRunControlFacet {
  InMemoryAssistantRunControlFacet({
    InMemoryAssistantSessionRunFacade? sessionRun,
  }) : sessionRun = sessionRun ?? InMemoryAssistantSessionRunFacade();

  final InMemoryAssistantSessionRunFacade sessionRun;

  @override
  Future<AssistantRunEnvelopeWire> pauseAssistantRun({
    required String runId,
    required String commandRequestId,
    String reason = '',
  }) => sessionRun.getAssistantRun(runId: runId);

  @override
  Future<AssistantRunEnvelopeWire> resumeAssistantRun({
    required String runId,
    required String commandRequestId,
  }) => sessionRun.getAssistantRun(runId: runId);

  @override
  Future<AssistantRunEnvelopeWire> steerAssistantRun({
    required String runId,
    required String commandRequestId,
    required String instruction,
  }) => sessionRun.getAssistantRun(runId: runId);

  @override
  Future<AssistantToolApprovalResult> approveAssistantToolUse({
    required String runId,
    required String toolInvocationId,
    required String commandRequestId,
    required String decision,
    required String approvalPermit,
    String? installationId,
    String? deviceId,
  }) async => AssistantToolApprovalResult(
    runId: runId,
    state: decision == 'approved' ? 'executing' : 'cancelled',
  );

  @override
  Future<AssistantRunEnvelopeWire> submitDeviceActionReceipt({
    required String runId,
    required String toolInvocationId,
    required String commandRequestId,
    required AssistantDeviceActionExecutionReceipt receipt,
  }) => sessionRun.getAssistantRun(runId: runId);
}
