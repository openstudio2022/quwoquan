import 'dart:io';

import 'package:quwoquan_app/assistant/contracts/assistant_journey.dart';
import 'package:quwoquan_app/assistant/contracts/retrieval_outcome.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/conversation/orchestration/session_manager.dart';
import 'package:quwoquan_app/assistant/memory/assistant_memory_runtime.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/finalize_runner.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_display_state_projection.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_process_timeline.dart';
import 'package:quwoquan_app/assistant/protocol/persisted_assistant_turn.dart';
import 'package:quwoquan_app/assistant/protocol/run_request.dart';
import 'package:quwoquan_app/assistant/protocol/run_response.dart';
import 'package:test/test.dart';

class _InMemoryVectorStore implements AssistantVectorStore {
  final List<VectorMemoryItem> _items = <VectorMemoryItem>[];

  @override
  Future<void> upsert(VectorMemoryItem item) async {
    _items.removeWhere((existing) => existing.id == item.id);
    _items.add(item);
  }

  @override
  Future<List<VectorMemoryItem>> search(
    List<double> queryVector, {
    int limit = 5,
  }) async {
    return _items.take(limit).toList(growable: false);
  }
}

AssistantRunResponse _buildFinalizeResponse({required bool includeAnswer}) {
  const answerText = '这是一版受限答案。';
  const blockedReason = '当前证据时效性不满足要求，还不能直接 fully 放行。';
  const understandingSnapshot = RunArtifactsUnderstandingSnapshot(
    userFacingSummary: '我先确认你想追的是昨天盘面的原因。',
    intentSummary: '我会先锁定对应交易日，再核对盘面主线。',
  );
  const retrievalProcessing = RetrievalProcessingSnapshot(
    processingSummary: '当前证据时效性还不够稳定。',
  );
  const answerProcessing = RunArtifactsAnswerProcessing(
    readinessSummary: blockedReason,
    retrieveMoreReason: blockedReason,
  );
  final journey = AssistantJourney(
    stages: <AssistantJourneyStage>[
      const AssistantJourneyStage(
        stageId: JourneyStageId.analyze,
        status: JourneyStageStatus.completed,
        order: 0,
        summary: '我先确认你想追的是昨天盘面的原因。',
      ),
      AssistantJourneyStage(
        stageId: JourneyStageId.search,
        status: includeAnswer
            ? JourneyStageStatus.blocked
            : JourneyStageStatus.active,
        order: 1,
        summary: '我会先锁定对应交易日，再核对盘面主线。',
      ),
    ],
    entries: const <AssistantJourneyEntry>[
      AssistantJourneyEntry(
        entryId: 'journey.analyze',
        stageId: JourneyStageId.analyze,
        kind: JourneyEntryKind.narrative,
        status: JourneyStageStatus.completed,
        order: 0,
        headline: '我先确认你想追的是昨天盘面的原因。',
      ),
    ],
    readiness: AssistantJourneyReadiness(finalAnswerReady: false),
  );
  final processTimeline = <ProcessTimelineFrame>[
    buildProcessTimelineFrame(
      stepId: ProcessStepId.understanding,
      status: JourneyStageStatus.completed,
      headline: understandingSnapshot.userFacingSummary,
      understandingSnapshot: understandingSnapshot,
    ),
    buildProcessTimelineFrame(
      stepId: ProcessStepId.retrievalDesign,
      status: JourneyStageStatus.completed,
      headline: understandingSnapshot.intentSummary,
      detail: '执行检索：2026-04-07 A股 大涨 原因',
    ),
    buildProcessTimelineFrame(
      stepId: ProcessStepId.retrievalProcessing,
      status: JourneyStageStatus.blocked,
      headline: retrievalProcessing.processingSummary,
      retrievalProcessing: retrievalProcessing,
    ),
    if (includeAnswer)
      buildProcessTimelineFrame(
        stepId: ProcessStepId.answerOrganization,
        status: JourneyStageStatus.completed,
        headline: '先给你一版受限答案。',
        answerProcessing: answerProcessing,
      ),
  ];
  final baseDisplayState = buildAssistantDisplayState(
    processTimeline: processTimeline,
    understandingSnapshot: understandingSnapshot,
    retrievalProcessing: retrievalProcessing,
    answerProcessing: answerProcessing,
    finalAnswerReady: false,
  );
  final displayState = AssistantDisplayState(
    process: baseDisplayState.process,
    answer: includeAnswer
        ? const AssistantAnswerDisplayState(
            summary: blockedReason,
            blocks: <AssistantAnswerDisplayBlock>[
              AssistantAnswerDisplayBlock(
                blockId: 'answer_markdown',
                kind: DisplayBlockKind.markdown,
                body: answerText,
              ),
            ],
          )
        : const AssistantAnswerDisplayState(),
  );
  final runArtifacts = RunArtifacts(
    machineEnvelope: 'retrieval_processing_blocked',
    displayMarkdown: includeAnswer ? answerText : '',
    displayPlainText: includeAnswer ? answerText : '',
    displayState: displayState,
    journey: journey,
    processTimeline: processTimeline,
    understandingSnapshot: understandingSnapshot,
    answerProcessing: answerProcessing,
    historicalThinkingSnapshot: const RunArtifactsHistoricalThinkingSnapshot(),
    retrievalProcessing: retrievalProcessing,
    evidenceLedger: const <EvidenceLedgerEntry>[],
    answerEvidenceBindings: const <AnswerEvidenceBinding>[],
    slotState: const SlotStateSnapshot(domainId: 'assistant'),
    answerDecision: const RunArtifactsAnswerDecisionPartitioned(),
    diagnostics: const RunArtifactsDiagnosticsPartitioned(),
  );
  return AssistantRunResponse(
    finalText: 'retrieval_processing_blocked',
    traces: const [],
    degraded: true,
    structuredResponse: <String, dynamic>{
      'runArtifacts': runArtifacts.toJson(),
      assistantDisplayStateField: displayState.toJson(),
      assistantProcessTimelineField: processTimeline
          .map((item) => item.toJson())
          .toList(growable: false),
      assistantUnderstandingSnapshotField: understandingSnapshot.toJson(),
      assistantRetrievalProcessingField: retrievalProcessing.toJson(),
      assistantAnswerProcessingField: answerProcessing.toJson(),
      assistantAnswerGateDecisionField: <String, dynamic>{
        'eligible': false,
        'finalAnswerReady': false,
        'reasonCode': 'freshness_unsatisfied',
        'reason': blockedReason,
        'nextAction': 'answer',
        'answerEligibility': 'blocked',
        'renderable': includeAnswer,
        'retrievalReady': false,
        'terminalPayloadComplete': true,
        'degraded': false,
        'incomplete': false,
      },
    },
  );
}

AssistantRunResponse _buildStructuredOnlyFinalizeResponse({
  required bool includeAnswer,
}) {
  final base = _buildFinalizeResponse(includeAnswer: includeAnswer);
  final structured = <String, dynamic>{...base.structuredResponse}
    ..remove('runArtifacts');
  if (includeAnswer) {
    structured[assistantDisplayMarkdownField] = '这是一版受限答案。';
    structured[assistantDisplayPlainTextField] = '这是一版受限答案。';
  }
  return AssistantRunResponse(
    finalText: base.finalText,
    traces: base.traces,
    runId: base.runId,
    traceId: base.traceId,
    degraded: base.degraded,
    errorCode: base.errorCode,
    structuredResponse: structured,
    profileUpdateProposal: base.profileUpdateProposal,
  );
}

void main() {
  late Directory tempDir;

  setUp(() async {
    tempDir = await Directory.systemTemp.createTemp(
      'assistant_finalize_runner_',
    );
  });

  tearDown(() async {
    if (await tempDir.exists()) {
      await tempDir.delete(recursive: true);
    }
  });

  test(
    'degraded 但 renderable 的 canonical answer 会被写入 session 并保留顶层状态',
    () async {
      final storagePath = '${tempDir.path}/sessions.json';
      final sessionManager = AssistantSessionManager(storagePath: storagePath);
      await sessionManager.load();
      final runner = FinalizeRunner(
        sessionManager: sessionManager,
        memoryRepository: AssistantMemoryRepository(_InMemoryVectorStore()),
        buildObservabilityPayload: ({required response, required request}) =>
            <String, dynamic>{},
      );
      final request = const AssistantRunRequest(
        sessionId: 'renderable_bounded',
        messages: <AssistantRunMessage>[
          AssistantRunMessage(role: 'user', content: '昨天A股为什么大涨'),
        ],
      );

      await runner.finalize(
        request,
        executionSnapshot: <String, dynamic>{
          'sessionId': 'renderable_bounded',
          'latestUserQuery': '昨天A股为什么大涨',
          'elapsedMs': 2300,
        },
        response: _buildFinalizeResponse(includeAnswer: true),
      );

      final messages = sessionManager.getOrCreateSession('renderable_bounded');
      expect(messages, hasLength(1));
      final message = messages.single;
      expect(message[assistantDisplayMarkdownField], equals('这是一版受限答案。'));
      expect(message[assistantDisplayStateField], isA<Map<String, dynamic>>());
      expect(message[assistantProcessTimelineField], isA<List<dynamic>>());
      expect(
        ((message['runArtifacts'] as Map?)?.cast<String, dynamic>() ??
            const <String, dynamic>{})[assistantDisplayStateField],
        isA<Map<String, dynamic>>(),
      );

      final reloadedManager = AssistantSessionManager(storagePath: storagePath);
      await reloadedManager.load();
      final reloaded = reloadedManager.getOrCreateSession('renderable_bounded');
      expect(reloaded, hasLength(1));
      expect(
        resolvePersistedAssistantDisplayPlainText(reloaded.single),
        equals('这是一版受限答案。'),
      );
    },
  );

  test('structured-only canonical turn 也会被持久化并在 reload 后恢复', () async {
    final storagePath = '${tempDir.path}/sessions.json';
    final sessionManager = AssistantSessionManager(storagePath: storagePath);
    await sessionManager.load();
    final runner = FinalizeRunner(
      sessionManager: sessionManager,
      memoryRepository: AssistantMemoryRepository(_InMemoryVectorStore()),
      buildObservabilityPayload: ({required response, required request}) =>
          <String, dynamic>{},
    );
    const request = AssistantRunRequest(
      sessionId: 'structured_only_turn',
      messages: <AssistantRunMessage>[
        AssistantRunMessage(role: 'user', content: '昨天A股为什么大涨'),
      ],
    );

    await runner.finalize(
      request,
      executionSnapshot: <String, dynamic>{
        'sessionId': 'structured_only_turn',
        'latestUserQuery': '昨天A股为什么大涨',
        'elapsedMs': 2100,
      },
      response: _buildStructuredOnlyFinalizeResponse(includeAnswer: true),
    );

    final messages = sessionManager.getOrCreateSession('structured_only_turn');
    expect(messages, hasLength(1));
    final message = messages.single;
    expect(message[assistantDisplayMarkdownField], equals('这是一版受限答案。'));
    expect(message[assistantDisplayStateField], isA<Map<String, dynamic>>());
    expect(message[assistantProcessTimelineField], isA<List<dynamic>>());
    expect(
      ((message['runArtifacts'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{})[assistantDisplayStateField],
      isA<Map<String, dynamic>>(),
    );

    final reloadedManager = AssistantSessionManager(storagePath: storagePath);
    await reloadedManager.load();
    final reloaded = reloadedManager.getOrCreateSession('structured_only_turn');
    expect(reloaded, hasLength(1));
    final reloadedMessage = reloaded.single;
    expect(
      resolvePersistedAssistantDisplayPlainText(reloadedMessage),
      equals('这是一版受限答案。'),
    );
    expect(
      resolvePersistedAssistantDisplayState(reloadedMessage).process.blocks,
      isNotEmpty,
    );
    expect(
      resolvePersistedAssistantProcessTimeline(reloadedMessage),
      isNotEmpty,
    );
  });

  test('process-only blocked turn 在 append save load 后仍能回放流程状态', () async {
    final storagePath = '${tempDir.path}/sessions.json';
    final sessionManager = AssistantSessionManager(storagePath: storagePath);
    await sessionManager.load();
    final runner = FinalizeRunner(
      sessionManager: sessionManager,
      memoryRepository: AssistantMemoryRepository(_InMemoryVectorStore()),
      buildObservabilityPayload: ({required response, required request}) =>
          <String, dynamic>{},
    );
    final request = const AssistantRunRequest(
      sessionId: 'process_only_blocked',
      messages: <AssistantRunMessage>[
        AssistantRunMessage(role: 'user', content: '昨天A股为什么大涨'),
      ],
    );

    await runner.finalize(
      request,
      executionSnapshot: <String, dynamic>{
        'sessionId': 'process_only_blocked',
        'latestUserQuery': '昨天A股为什么大涨',
        'elapsedMs': 1800,
      },
      response: _buildFinalizeResponse(includeAnswer: false),
    );

    final reloadedManager = AssistantSessionManager(storagePath: storagePath);
    await reloadedManager.load();
    final messages = reloadedManager.getOrCreateSession('process_only_blocked');
    expect(messages, hasLength(1));
    final message = messages.single;
    expect(resolvePersistedAssistantDisplayPlainText(message), isEmpty);
    expect(resolvePersistedAssistantProcessTimeline(message), isNotEmpty);
    expect(
      resolvePersistedAssistantDisplayState(message).process.blocks,
      isNotEmpty,
    );
  });

  test('string 版 understanding resolutionItems 会在 finalize 后被规范持久化', () async {
    final storagePath = '${tempDir.path}/sessions.json';
    final sessionManager = AssistantSessionManager(storagePath: storagePath);
    await sessionManager.load();
    final runner = FinalizeRunner(
      sessionManager: sessionManager,
      memoryRepository: AssistantMemoryRepository(_InMemoryVectorStore()),
      buildObservabilityPayload: ({required response, required request}) =>
          <String, dynamic>{},
    );
    const request = AssistantRunRequest(
      sessionId: 'string_resolution_items',
      messages: <AssistantRunMessage>[
        AssistantRunMessage(role: 'user', content: '昨天A股为什么大涨'),
      ],
    );

    final response = AssistantRunResponse(
      finalText: '昨天（2026年4月9日）A股上涨与情绪修复有关。',
      traces: const [],
      structuredResponse: <String, dynamic>{
        'contractId': 'assistant_turn',
        'messageKind': 'answer',
        'phaseId': 'answering',
        'actionCode': 'compose_answer',
        'reasonCode': 'need_more_evidence',
        'reasonShort': '先保留已确认部分。',
        'decision': const <String, dynamic>{'nextAction': 'answer'},
        'userMarkdown': '昨天（2026年4月9日）A股上涨与情绪修复有关。',
        assistantUnderstandingSnapshotField: <String, dynamic>{
          'userFacingSummary': '我先把相对时间和市场范围落清。',
          'resolutionItems': <String>[
            '时间锚点：昨天已对齐到2026年4月9日。',
            '地理锚点：默认按中国股市/A股理解。',
          ],
        },
        assistantAnswerProcessingField: const <String, dynamic>{
          'readinessSummary': '这版先给出已确认部分。',
        },
      },
    );

    await runner.finalize(
      request,
      executionSnapshot: <String, dynamic>{
        'sessionId': 'string_resolution_items',
        'latestUserQuery': '昨天A股为什么大涨',
        'elapsedMs': 1900,
      },
      response: response,
    );

    final message = sessionManager
        .getOrCreateSession('string_resolution_items')
        .single;
    final understanding = RunArtifactsUnderstandingSnapshot.fromJson(
      (message[assistantUnderstandingSnapshotField] as Map)
          .cast<String, dynamic>(),
    );
    final displayState = resolvePersistedAssistantDisplayState(message);

    expect(understanding.resolutionItems, hasLength(2));
    expect(understanding.resolutionItems.first.title, equals('时间锚点'));
    expect(
      displayState.process.blocks.any(
        (block) => block.blockId == 'understanding_resolution_items',
      ),
      isFalse,
      reason: 'resolution items 信息已融入 summary 叙事，不应有独立列表块',
    );
  });
}
