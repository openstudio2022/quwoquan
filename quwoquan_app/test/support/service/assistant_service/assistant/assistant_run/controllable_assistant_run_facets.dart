import 'dart:async';

import 'package:quwoquan_app/service/assistant_service/assistant/assistant_session/application/public/assistant_history.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/page_context/application/public/assistant_open_context.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import 'assistant_facets_typed_double.dart';

/// 不读取历史的 AssistantRun 对象级替身；供 controller focused LC 共同复用。
final class EmptyAssistantHistoryLoader implements AssistantHistoryLoader {
  const EmptyAssistantHistoryLoader();

  @override
  Future<AssistantHistorySnapshot?> load({
    required String personaId,
    String sessionId = '',
  }) async => null;
}

/// 从 canonical generated wire 构造测试事件，不复制 wire schema 或 decoder。
AssistantStreamEventWire assistantRunStreamEventFixture({
  required int seq,
  required String eventType,
  Map<String, dynamic> payload = const <String, dynamic>{},
  RuntimeFailureWire? runtimeFailure,
  String runId = 'arn_test_personal',
  String sessionId = 'asn_test_personal',
}) {
  final wirePayload = <String, dynamic>{...payload};
  if (eventType == 'completed' &&
      !wirePayload.containsKey('finalAnswer') &&
      wirePayload['text'] is String) {
    wirePayload['finalAnswer'] = wirePayload['text'];
  }
  return AssistantStreamEventWire(
    schema: 'assistant_stream_event',
    eventId: 'evt_$seq',
    sessionId: sessionId,
    runId: runId,
    seq: seq,
    eventType: parseAssistantStreamEventTypeStrict(eventType),
    payload: wirePayload,
    runtimeFailure: runtimeFailure,
    createdAt: '2026-04-29T00:00:00Z',
  );
}

AssistantStreamEventWire _eventForRun(
  AssistantStreamEventWire event,
  String runId,
) {
  if (event.runId == runId) {
    return event;
  }
  return AssistantStreamEventWire(
    schema: event.schema,
    eventId: event.eventId,
    sessionId: event.sessionId,
    runId: runId,
    seq: event.seq,
    eventType: event.eventType,
    payload: event.payload,
    runtimeFailure: event.runtimeFailure,
    createdAt: event.createdAt,
  );
}

/// Controller LC 的唯一可控 Assistant Facet 替身。
///
/// 它扩展现有 [InMemoryAssistantFacets]，同时被综合 controller LC 与并发 focused
/// LC 消费；禁止在单个测试文件中再复制另一套 Run fake。
final class ControllableAssistantRunFacets extends InMemoryAssistantFacets {
  ControllableAssistantRunFacets({
    required this.events,
    this.approvalDevicePermit,
    this.eventStream,
    this.getRunResult,
  });

  final List<AssistantStreamEventWire> events;
  final AssistantDeviceActionPermit? approvalDevicePermit;
  final Stream<AssistantStreamEventWire>? eventStream;
  AssistantRunEnvelopeWire? getRunResult;
  Object? steerError;
  int steerFailuresAfterAcceptRemaining = 0;
  Completer<AssistantRunEnvelopeWire>? steerResponseCompleter;
  final Map<String, Completer<AssistantRunEnvelopeWire>> getRunCompleters =
      <String, Completer<AssistantRunEnvelopeWire>>{};
  final Map<String, AssistantRunEnvelopeWire> getRunResults =
      <String, AssistantRunEnvelopeWire>{};
  final Map<String, Stream<AssistantStreamEventWire>> eventStreamsByRunId =
      <String, Stream<AssistantStreamEventWire>>{};
  final List<String> streamResumeTokens = <String>[];
  final List<String> steerInstructions = <String>[];
  final List<String> steerCommandRequestIds = <String>[];
  int _turnCounter = 0;
  int createSessionFailuresRemaining = 0;
  int startRunFailuresRemaining = 0;
  bool failPageContextReport = false;
  final List<String> createdSessionRequestIds = <String>[];
  final List<String> startedRunClientRequestIds = <String>[];
  final List<String> callOrder = <String>[];
  final List<String> reportedPageContextActions = <String>[];
  AssistantOpenContext? reportedPageContext;

  @override
  Future<PageContextReceipt> reportPageContext({
    required AssistantOpenContext context,
    String? userAction,
  }) async {
    callOrder.add('reportPageContext');
    reportedPageContext = context;
    reportedPageContextActions.add(userAction ?? '');
    if (failPageContextReport) {
      throw StateError('page context unavailable (test)');
    }
    return PageContextReceipt(
      accepted: true,
      contextKey: 'ctx_test',
      expiresAt: '2026-08-02T12:05:00Z',
    );
  }

  /// 记录单轨学习事实 command；可按 eventId 模拟失败以覆盖重试语义。
  final List<AssistantLearningFactAppendCommand> learningFacts =
      <AssistantLearningFactAppendCommand>[];
  bool failLearningFactAppend = false;
  final Set<String> rejectedLearningFactIds = <String>{};

  @override
  Future<AssistantLearningFactReceipt> appendUserFact({
    required AssistantLearningFactAppendCommand request,
  }) async {
    learningFacts.add(request);
    if (failLearningFactAppend ||
        rejectedLearningFactIds.contains(request.eventId)) {
      throw StateError('learning append unavailable (test)');
    }
    return AssistantLearningFactReceipt(
      eventId: request.eventId,
      accepted: true,
      deduplicated: false,
      appendSequence: learningFacts.length,
      payloadDigest:
          '0000000000000000000000000000000000000000000000000000000000000000',
      recordedAt: DateTime.now().toUtc().toIso8601String(),
    );
  }

  @override
  Future<AssistantSessionWire> createAssistantSession({
    String summary = '',
    required String clientRequestId,
  }) async {
    createdSessionRequestIds.add(clientRequestId);
    if (createSessionFailuresRemaining > 0) {
      createSessionFailuresRemaining -= 1;
      throw StateError('assistant session unavailable (test)');
    }
    return const AssistantSessionWire(
      sessionId: 'asn_test_personal',
      userId: 'user_test',
      createdAt: '2026-04-29T00:00:00Z',
      updatedAt: '2026-04-29T00:00:00Z',
    );
  }

  /// 记录 StartAssistantRun 提交文本（regenerate 合同断言消费）。
  final List<String> startedRunTexts = <String>[];
  List<AssistantIntersectionEvidenceRef> startedIntersectionEvidenceRefs =
      const <AssistantIntersectionEvidenceRef>[];

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
    callOrder.add('startAssistantRun');
    _turnCounter += 1;
    startedRunTexts.add(text);
    startedRunClientRequestIds.add(clientRequestId);
    startedIntersectionEvidenceRefs =
        List<AssistantIntersectionEvidenceRef>.unmodifiable(
          intersectionEvidenceRefs,
        );
    if (startRunFailuresRemaining > 0) {
      startRunFailuresRemaining -= 1;
      throw StateError('assistant start unavailable (test)');
    }
    return AssistantRunEnvelopeWire(
      runId: _turnCounter == 1
          ? 'arn_test_personal'
          : 'arn_test_personal_$_turnCounter',
      sessionId: sessionId,
      goal: text,
      traceId: 'trace_test',
      createdAt: '2026-04-29T00:00:00Z',
    );
  }

  @override
  Future<AssistantRunEnvelopeWire> getAssistantRun({
    required String runId,
  }) async {
    final completer = getRunCompleters[runId];
    if (completer != null) {
      return completer.future;
    }
    final result = getRunResults[runId];
    if (result != null) {
      return result;
    }
    return getRunResult ?? super.getAssistantRun(runId: runId);
  }

  @override
  Future<AssistantRunEnvelopeWire> steerAssistantRun({
    required String runId,
    required String commandRequestId,
    required String instruction,
  }) async {
    steerInstructions.add(instruction);
    steerCommandRequestIds.add(commandRequestId);
    final responseCompleter = steerResponseCompleter;
    if (responseCompleter != null) {
      return responseCompleter.future;
    }
    if (steerFailuresAfterAcceptRemaining > 0) {
      steerFailuresAfterAcceptRemaining -= 1;
      throw StateError('steer response lost after acceptance (test)');
    }
    final error = steerError;
    if (error != null) {
      throw error;
    }
    return AssistantRunEnvelopeWire(
      runId: runId,
      sessionId: 'asn_test_personal',
      status: 'executing',
      traceId: 'trace_test',
      createdAt: '2026-04-29T00:00:00Z',
    );
  }

  /// 记录 CancelAssistantRun 调用（stopGeneration 合同断言消费）。
  final List<String> cancelledRunIds = <String>[];
  final List<
    ({
      String runId,
      String toolInvocationId,
      String decision,
      String approvalPermit,
    })
  >
  approvedToolUses = [];
  final List<
    ({
      String runId,
      String toolInvocationId,
      AssistantDeviceActionExecutionReceipt receipt,
    })
  >
  deviceReceipts = [];

  @override
  Future<AssistantRunEnvelopeWire> cancelAssistantRun({
    required String runId,
    required String commandRequestId,
  }) async {
    cancelledRunIds.add(runId);
    return AssistantRunEnvelopeWire(
      runId: runId,
      sessionId: 'asn_test_personal',
      status: 'cancelled',
      traceId: 'trace_test',
      createdAt: '2026-04-29T00:00:00Z',
    );
  }

  @override
  Future<AssistantToolApprovalResult> approveAssistantToolUse({
    required String runId,
    required String toolInvocationId,
    required String commandRequestId,
    required String decision,
    required String approvalPermit,
    String? installationId,
    String? deviceId,
  }) async {
    approvedToolUses.add((
      runId: runId,
      toolInvocationId: toolInvocationId,
      decision: decision,
      approvalPermit: approvalPermit,
    ));
    return AssistantToolApprovalResult(
      runId: runId,
      state: decision == 'approved' ? 'executing' : 'cancelled',
      deviceActionPermit: decision == 'approved' ? approvalDevicePermit : null,
    );
  }

  @override
  Future<AssistantRunEnvelopeWire> submitDeviceActionReceipt({
    required String runId,
    required String toolInvocationId,
    required String commandRequestId,
    required AssistantDeviceActionExecutionReceipt receipt,
  }) async {
    deviceReceipts.add((
      runId: runId,
      toolInvocationId: toolInvocationId,
      receipt: receipt,
    ));
    return AssistantRunEnvelopeWire(
      runId: runId,
      sessionId: 'asn_test_personal',
      status: 'executing',
      traceId: 'trace_test',
      createdAt: '2026-04-29T00:00:00Z',
    );
  }

  @override
  Stream<AssistantStreamEventWire> watchAssistantRunEvents({
    required String runId,
    String lastEventId = '',
  }) async* {
    streamResumeTokens.add(lastEventId);
    final configuredStream = eventStreamsByRunId[runId] ?? eventStream;
    if (configuredStream != null) {
      yield* configuredStream;
      return;
    }
    if (lastEventId.isNotEmpty && events.isEmpty) {
      yield assistantRunStreamEventFixture(
        seq: (int.tryParse(lastEventId) ?? 0) + 1,
        eventType: 'completed',
        runId: runId,
        payload: <String, dynamic>{
          'status': 'completed',
          'finalAnswer': '设备上的系统日程已创建。',
        },
      );
      return;
    }
    for (final event in events) {
      yield _eventForRun(event, runId);
    }
  }
}
