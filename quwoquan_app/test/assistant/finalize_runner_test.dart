import 'dart:io';

import 'package:quwoquan_app/assistant/contracts/assistant_journey.dart';
import 'package:quwoquan_app/assistant/contracts/answer_boundary_policy.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_tool_result_row.dart';
import 'package:quwoquan_app/assistant/contracts/context_assembly_result.dart';
import 'package:quwoquan_app/assistant/contracts/dialogue_round_script.dart';
import 'package:quwoquan_app/assistant/contracts/orchestrator_state_contract.dart';
import 'package:quwoquan_app/assistant/context/assembly/evidence_evaluator.dart';
import 'package:quwoquan_app/assistant/contracts/retrieval_outcome.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/contracts/synthesis_readiness_result.dart';
import 'package:quwoquan_app/assistant/contracts/system_context_envelope.dart';
import 'package:quwoquan_app/assistant/contracts/task_graph_contract.dart';
import 'package:quwoquan_app/assistant/contracts/turn_synthesis_state_contract.dart';
import 'package:quwoquan_app/assistant/contracts/understanding_result_contract.dart';
import 'package:quwoquan_app/assistant/session/assistant_session_manager.dart';
import 'package:quwoquan_app/assistant/memory/assistant_memory_runtime.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/finalize_runner.dart';
import 'package:quwoquan_app/assistant/orchestration/state/execution_phase_snapshot.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_display_state_projection.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_process_timeline.dart';
import 'package:quwoquan_app/assistant/protocol/persisted_assistant_turn.dart';
import 'package:quwoquan_app/assistant/protocol/run_request.dart';
import 'package:quwoquan_app/assistant/protocol/run_response.dart';
import 'package:quwoquan_app/assistant/protocol/trace_events.dart';
import 'package:quwoquan_app/assistant/reasoning/runtime/react_runtime.dart';
import 'package:quwoquan_app/assistant/skill/domain/skill_manifest.dart';
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

const UnderstandingResult _aShareUnderstandingResult = UnderstandingResult(
  intents: <IntentNode>[
    IntentNode(
      intentId: 'intent_a_share_jump',
      intentType: 'assistant.market_explain',
      goal: '查昨天A股为什么大涨',
      requiresEvidence: true,
    ),
  ],
);

const TaskGraph _aShareTaskGraph = TaskGraph();

ExecutionPhaseSnapshot _buildExecutionSnapshot({
  required String sessionId,
  required String latestUserQuery,
  required String runId,
  required String traceId,
}) {
  return ExecutionPhaseSuccess(
    runId: runId,
    traceId: traceId,
    runStartAt: DateTime(2026, 4, 9, 10, 0, 0),
    sessionId: sessionId,
    latestUserQuery: latestUserQuery,
    domainId: 'assistant',
    contextAssembly: const ContextAssemblyResult(),
    understandingResult: _aShareUnderstandingResult,
    taskGraph: _aShareTaskGraph,
    orchestratorState: const ConversationOrchestratorState(),
    turnSynthesisState: const TurnSynthesisState(),
    dialogueRoundScript: const DialogueRoundScript(),
    domainCatalog: const <String>[],
    domainCatalogVersion: '',
    allowedToolNames: const <String>[],
    executionShell: const SkillExecutionShell(),
    previousSlotState: const SlotStateSnapshot(),
    retrievalPolicy: const <String, dynamic>{},
    answerBoundaryPolicy: const AnswerBoundaryPolicy(),
    understandingSnapshot: const <String, dynamic>{},
    templateVariables: const <String, dynamic>{},
    messages: const <Map<String, dynamic>>[],
    synthTemplateVersion: '',
    fusionSynthTemplateVersion: '',
    phaseOneResult: const ReactRuntimeResult(finalText: '', traces: []),
    synthesisReadiness: const SynthesisReadinessResult(),
    evidenceLedger: const <EvidenceLedgerEntry>[],
    evidenceEvaluation: const EvidenceEvaluationResult(),
    toolResults: const <AssistantToolResultRow>[],
    supplementalTraces: const <AssistantTraceEvent>[],
  );
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
      'subagentRuns': <Map<String, dynamic>>[
        <String, dynamic>{
          'version': 'subagent_result',
          'subagentId': 'weather_verify',
          'domainId': 'weather',
          'status': 'success',
          'goal': '核验深圳天气',
          'mode': 'qa',
          'problemClass': 'realtime_info',
          'shell': const <String, dynamic>{},
          'stopPolicy': 'balanced',
          'searchIntensity': 'medium',
          'providerPolicy': '',
          'freshnessHoursMax': 6,
          'answerThreshold': 0.7,
          'summary': '深圳天气适合出门。',
          'userMarkdown': '深圳天气适合出门。',
          'result': <String, dynamic>{
            'text': '深圳天气适合出门。',
            'nextAction': 'answer',
          },
          'answerReady': true,
          'references': <Map<String, dynamic>>[
            <String, dynamic>{
              'title': '深圳天气',
              'url': 'https://example.com/weather',
              'source': 'web_search',
            },
          ],
          'acceptedEvidence': <Map<String, dynamic>>[
            <String, dynamic>{
              'title': '深圳天气',
              'url': 'https://example.com/weather',
              'source': 'web_search',
            },
          ],
          'rejectedEvidence': const <Map<String, dynamic>>[],
          'nextAction': 'answer',
          'missingSlots': const <String>[],
          'failureReason': '',
          'toolCallCount': 1,
          'modelCallCount': 1,
          'totalTokens': 120,
          'maxTokensPerCall': 120,
          'tokenSource': 'usage',
          'tokenSampleCount': 1,
          'inputTokens': 80,
          'outputTokens': 40,
          'usageLedger': const <Map<String, dynamic>>[],
        },
      ],
      'uiTimeline': <Map<String, dynamic>>[
        <String, dynamic>{
          'event': 'subagent_progress',
          'subagentId': 'weather_verify',
          'status': 'success',
          'summary': '深圳天气适合出门。',
          'acceptedEvidenceCount': 1,
          'failureReason': '',
          'nextAction': 'answer',
        },
      ],
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

AssistantRunResponse _buildHistoryFinalizeResponse() {
  final base = _buildFinalizeResponse(includeAnswer: true);
  final structured = Map<String, dynamic>.from(base.structuredResponse);
  structured['sessionSummary'] = '本轮已经把天气与出行结论收束完成。';
  structured['skillSynthesis'] = <String, dynamic>{
    'input': <String, dynamic>{
      'userQuery': '深圳明天适合出门吗',
      'routeNarrative': 'weather primary',
      'selectedTargets': <Map<String, dynamic>>[
        <String, dynamic>{
          'skillId': 'weather',
          'role': 'primary',
          'priority': 1,
          'reason': '天气查询',
        },
        <String, dynamic>{
          'skillId': 'travel',
          'role': 'supporting',
          'priority': 2,
          'reason': '出行建议',
        },
      ],
      'skillResults': <Map<String, dynamic>>[
        <String, dynamic>{
          'skillId': 'weather',
          'role': 'primary',
          'status': 'complete',
          'summary': '深圳明天适合出门。',
          'acceptedEvidence': <Map<String, dynamic>>[
            <String, dynamic>{
              'title': '深圳天气预报',
              'source': 'test',
              'snippet': '明天晴到多云。',
            },
          ],
          'rejectedEvidence': const <Map<String, dynamic>>[],
          'missingSlots': const <String>[],
          'failureReason': '',
          'answerReady': true,
          'nextAction': 'answer',
        },
        <String, dynamic>{
          'skillId': 'travel',
          'role': 'supporting',
          'status': 'pending',
          'summary': '还需要确认具体出发时间。',
          'acceptedEvidence': const <Map<String, dynamic>>[],
          'rejectedEvidence': const <Map<String, dynamic>>[],
          'missingSlots': <String>['date'],
          'failureReason': 'missing_date',
          'answerReady': false,
          'nextAction': 'ask_user',
        },
      ],
      'pendingClarifications': const <String>['出发日期'],
      'sessionSummary': '本轮已经把天气与出行结论收束完成。',
    },
    'output': <String, dynamic>{
      'answerMarkdown': '深圳明天适合出门。',
      'followUpSuggestions': <String>['如果要出门，我可以继续帮你看路线。'],
      'partialCompletionState': 'partial',
      'unresolvedSkills': <String>['travel'],
      'nextAction': 'answer',
      'summary': '本轮已经把天气与出行结论收束完成。',
    },
  };
  structured['sessionPreferenceFacts'] = <Map<String, dynamic>>[
    <String, dynamic>{
      'factId': 'session_pref_1',
      'scope': 'session',
      'key': 'city',
      'value': '深圳',
      'source': 'test',
      'createdAt': '2026-04-09T10:00:00Z',
    },
  ];
  structured['longTermPreferenceFacts'] = <Map<String, dynamic>>[
    <String, dynamic>{
      'factId': 'long_term_pref_1',
      'scope': 'long_term',
      'key': 'weather',
      'value': '喜欢简洁结论',
      'source': 'test',
      'createdAt': '2026-04-09T10:00:00Z',
    },
  ];
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
        executionSnapshot: _buildExecutionSnapshot(
          sessionId: 'renderable_bounded',
          latestUserQuery: '昨天A股为什么大涨',
          runId: 'renderable_bounded_run',
          traceId: 'renderable_bounded_trace',
        ),
        response: _buildFinalizeResponse(includeAnswer: true),
      );

      final messages = sessionManager.getOrCreateSession('renderable_bounded');
      expect(messages, hasLength(1));
      final message = messages.single;
      expect(message[assistantDisplayMarkdownField], equals('这是一版受限答案。'));
      expect(message[assistantDisplayStateField], isA<Map<String, dynamic>>());
      expect(message[assistantProcessTimelineField], isA<List<dynamic>>());
      expect(message.containsKey('subagentRuns'), isFalse);
      expect(message.containsKey('uiTimeline'), isFalse);
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
      executionSnapshot: _buildExecutionSnapshot(
        sessionId: 'structured_only_turn',
        latestUserQuery: '昨天A股为什么大涨',
        runId: 'structured_only_turn_run',
        traceId: 'structured_only_turn_trace',
      ),
      response: _buildStructuredOnlyFinalizeResponse(includeAnswer: true),
    );

    final messages = sessionManager.getOrCreateSession('structured_only_turn');
    expect(messages, hasLength(1));
    final message = messages.single;
    expect(message[assistantDisplayMarkdownField], equals('这是一版受限答案。'));
    expect(message[assistantDisplayStateField], isA<Map<String, dynamic>>());
    expect(message[assistantProcessTimelineField], isA<List<dynamic>>());
    expect(message.containsKey('subagentRuns'), isFalse);
    expect(message.containsKey('uiTimeline'), isFalse);
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

  test('finalize 会持久化 typed mainline contracts 供后续 UI 与回放读取', () async {
    final storagePath = '${tempDir.path}/sessions_typed.json';
    final sessionManager = AssistantSessionManager(storagePath: storagePath);
    await sessionManager.load();
    final runner = FinalizeRunner(
      sessionManager: sessionManager,
      memoryRepository: AssistantMemoryRepository(_InMemoryVectorStore()),
      buildObservabilityPayload: ({required response, required request}) =>
          <String, dynamic>{},
    );
    const request = AssistantRunRequest(
      sessionId: 'typed_mainline_turn',
      messages: <AssistantRunMessage>[
        AssistantRunMessage(role: 'user', content: '深圳明天天气怎么样'),
      ],
    );
    const typedSystemContext = SystemContextEnvelope(
      time: SystemTimeContext(
        referenceNowIso: '2026-04-21T08:00:00Z',
        timezone: 'Asia/Shanghai',
        locale: 'zh-CN',
      ),
      location: SystemLocationContext(
        countryCode: 'CN',
        adminAreaLevel1: 'Guangdong',
        adminAreaLevel2: 'Shenzhen',
        formattedAddress: 'Guangdong Shenzhen',
      ),
    );
    const typedUnderstandingResult = UnderstandingResult(
      intents: <IntentNode>[
        IntentNode(
          intentId: 'intent_weather',
          intentType: 'weather.retrieve',
          goal: '查询深圳明天天气',
          requiresEvidence: true,
        ),
      ],
      dialogueTransitionDecision: DialogueTransitionDecision(
        nextTurnMode: NextTurnMode.continueExecution,
      ),
    );
    const typedTaskGraph = TaskGraph(
      tasks: <TaskNode>[
        TaskNode(
          taskId: 'task_weather_search',
          intentId: 'intent_weather',
          toolName: 'web_search',
          toolArgs: TaskToolArgs(<String, Object?>{'query': '深圳 明天天气'}),
          status: TaskStatus.completed,
          output: TaskOutput(<String, Object?>{'provider': 'serpapi'}),
        ),
      ],
    );
    const typedOrchestratorState = ConversationOrchestratorState(
      completedTaskIds: <String>['task_weather_search'],
      interactionDirective: InteractionDirective(
        kind: InteractionDirectiveKind.finalAnswer,
        intentId: 'intent_weather',
        message: '可以输出最终答案',
      ),
    );
    const typedSynthesisState = TurnSynthesisState(
      interactionDirective: InteractionDirective(
        kind: InteractionDirectiveKind.finalAnswer,
        intentId: 'intent_weather',
        message: '整理最终回答',
      ),
      completedIntentIds: <String>['intent_weather'],
    );

    final response = AssistantRunResponse(
      finalText: '深圳明天多云，气温 24 到 29 度。',
      traces: const [],
      structuredResponse: <String, dynamic>{
        'contractId': 'assistant_turn',
        'messageKind': 'answer',
        'decision': const <String, dynamic>{'nextAction': 'answer'},
        'userMarkdown': '深圳明天多云，气温 24 到 29 度。',
        assistantDisplayStateField: const <String, dynamic>{
          'answer': <String, dynamic>{
            'summary': '深圳明天多云，气温 24 到 29 度。',
            'blocks': <Map<String, dynamic>>[
              <String, dynamic>{
                'blockId': 'answer_markdown',
                'kind': 'markdown',
                'body': '深圳明天多云，气温 24 到 29 度。',
              },
            ],
          },
        },
        assistantSystemContextEnvelopeField: typedSystemContext.toJson(),
        assistantUnderstandingResultField: typedUnderstandingResult.toJson(),
        assistantTaskGraphField: typedTaskGraph.toJson(),
        assistantOrchestratorStateField: typedOrchestratorState.toJson(),
        assistantTurnSynthesisStateField: typedSynthesisState.toJson(),
      },
    );

    await runner.finalize(
      request,
      executionSnapshot: _buildExecutionSnapshot(
        sessionId: 'typed_mainline_turn',
        latestUserQuery: '深圳明天天气怎么样',
        runId: 'typed_mainline_turn_run',
        traceId: 'typed_mainline_turn_trace',
      ),
      response: response,
    );

    final message = sessionManager
        .getOrCreateSession('typed_mainline_turn')
        .single;
    expect(
      message[assistantSystemContextEnvelopeField],
      isA<Map<String, dynamic>>(),
    );
    expect(
      message[assistantUnderstandingResultField],
      isA<Map<String, dynamic>>(),
    );
    expect(message[assistantTaskGraphField], isA<Map<String, dynamic>>());
    expect(
      message[assistantOrchestratorStateField],
      isA<Map<String, dynamic>>(),
    );
    expect(
      message[assistantTurnSynthesisStateField],
      isA<Map<String, dynamic>>(),
    );

    expect(
      resolvePersistedAssistantSystemContextEnvelope(
        message,
      ).location.adminAreaLevel2,
      'Shenzhen',
    );
    expect(
      resolvePersistedAssistantUnderstandingResult(
        message,
      ).intents.single.intentType,
      'weather.retrieve',
    );
    expect(
      resolvePersistedAssistantTaskGraph(message).tasks.single.toolName,
      'web_search',
    );
    expect(
      resolvePersistedAssistantOrchestratorState(
        message,
      ).interactionDirective.kind,
      InteractionDirectiveKind.finalAnswer,
    );
    expect(
      resolvePersistedAssistantTurnSynthesisState(message).completedIntentIds,
      <String>['intent_weather'],
    );
  });

  test('finalize 会把 skill 历史态写入 session metadata 并保留挂起状态', () async {
    final storagePath = '${tempDir.path}/sessions_history.json';
    final sessionManager = AssistantSessionManager(storagePath: storagePath);
    await sessionManager.load();
    final runner = FinalizeRunner(
      sessionManager: sessionManager,
      memoryRepository: AssistantMemoryRepository(_InMemoryVectorStore()),
      buildObservabilityPayload: ({required response, required request}) =>
          <String, dynamic>{},
    );
    const request = AssistantRunRequest(
      sessionId: 'history_session',
      messages: <AssistantRunMessage>[
        AssistantRunMessage(role: 'user', content: '深圳明天适合出门吗'),
      ],
    );

    await runner.finalize(
      request,
      executionSnapshot: _buildExecutionSnapshot(
        sessionId: 'history_session',
        latestUserQuery: '深圳明天适合出门吗',
        runId: 'history_session_run',
        traceId: 'history_session_trace',
      ),
      response: _buildHistoryFinalizeResponse(),
    );

    final historyState = sessionManager.historyStateOf('history_session');
    expect(historyState.sessionSummary, contains('天气与出行结论'));
    expect(historyState.completedSkillSummaries, hasLength(1));
    expect(historyState.completedSkillSummaries.single.skillId, 'weather');
    expect(historyState.pendingSkillStates, hasLength(1));
    expect(historyState.pendingSkillStates.single.skillId, 'travel');
    expect(historyState.userPreferences, hasLength(2));

    final reloadedManager = AssistantSessionManager(storagePath: storagePath);
    await reloadedManager.load();
    final reloadedHistoryState = reloadedManager.historyStateOf(
      'history_session',
    );
    expect(reloadedHistoryState.sessionSummary, contains('天气与出行结论'));
    expect(reloadedHistoryState.completedSkillSummaries, hasLength(1));
    expect(reloadedHistoryState.pendingSkillStates, hasLength(1));
    expect(reloadedHistoryState.userPreferences, hasLength(2));
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
      executionSnapshot: _buildExecutionSnapshot(
        sessionId: 'process_only_blocked',
        latestUserQuery: '昨天A股为什么大涨',
        runId: 'process_only_blocked_run',
        traceId: 'process_only_blocked_trace',
      ),
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
      executionSnapshot: _buildExecutionSnapshot(
        sessionId: 'string_resolution_items',
        latestUserQuery: '昨天A股为什么大涨',
        runId: 'string_resolution_items_run',
        traceId: 'string_resolution_items_trace',
      ),
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
