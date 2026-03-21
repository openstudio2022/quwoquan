import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/orchestration/local_phase_execution_owner.dart'
    as phase_owner;
import 'package:quwoquan_app/assistant/contracts/aggregation_state.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_journey.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_turn_contract.dart';
import 'package:quwoquan_app/assistant/contracts/context_continuity_policy.dart';
import 'package:quwoquan_app/assistant/contracts/intent_graph.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/contracts/synthesis_readiness_result.dart';
import 'package:quwoquan_app/assistant/context/assembly/evidence_evaluator.dart';
import 'package:quwoquan_app/assistant/context/assembly/context_orchestrator.dart';
import 'package:quwoquan_app/assistant/context/assembly/recall_coordinator.dart';
import 'package:quwoquan_app/assistant/infrastructure/assistant_model_runtime.dart';
import 'package:quwoquan_app/assistant/memory/assistant_memory_runtime.dart';
import 'package:quwoquan_app/assistant/orchestration/answer_outcome_resolver.dart';
import 'package:quwoquan_app/assistant/orchestration/assistant_orchestration_runtime.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/phase.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/phase_orchestrator.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/bootstrap_phase.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/finalize_phase.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/synthesis_phase.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/phase_types.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/retrieval_design_phase.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/understand_phase.dart';
import 'package:quwoquan_app/assistant/orchestration/state/agent_execution_state.dart';
import 'package:quwoquan_app/assistant/protocol/trace_events.dart';
import 'package:quwoquan_app/assistant/protocol/run_request.dart';
import 'package:quwoquan_app/assistant/protocol/run_response.dart';
import 'package:quwoquan_app/assistant/protocol/persisted_assistant_turn.dart';
import 'package:quwoquan_app/assistant/contracts/conversation_state_decision.dart';
import 'package:quwoquan_app/assistant/reasoning/planner/mode_decider.dart';
import 'package:quwoquan_app/assistant/reasoning/routing/domain_router.dart';
import 'package:quwoquan_app/assistant/skill/domain/skill_manifest.dart';
import 'package:quwoquan_app/assistant/template_runtime/assistant_template_runtime.dart';
import 'package:quwoquan_app/assistant/tools/assistant_tool_runtime.dart';
import 'package:quwoquan_app/assistant/tool/schema/tool_schema.dart';

bool _isFinalAnswerTemplate(String templateId) =>
    templateId == 'synthesizer.final_answer';

bool _hasSubagentRuns(Map<String, dynamic> templateVariables) =>
    templateVariables['subagentRuns'] != null;

void main() {
  group('orchestration phase owner', () {
    test('bootstrap phase 应产出 bootstrapContext 与 contextAssembly', () async {
      final tempDir = await Directory.systemTemp.createTemp(
        'assistant_bootstrap_phase_',
      );
      addTearDown(() async {
        if (await tempDir.exists()) {
          await tempDir.delete(recursive: true);
        }
      });
      final phase = BootstrapPhase(
        runtime: ReactRuntime(
          llmProvider: const HeuristicLocalLlmProvider(),
          toolRegistry: AssistantToolRegistry(),
        ),
        sessionManager: AssistantSessionManager(
          storagePath: '${tempDir.path}/sessions.json',
        ),
        memoryRepository: AssistantMemoryRepository(
          ObjectBoxVectorStore(storagePath: '${tempDir.path}/memory.json'),
        ),
        contextOrchestrator: const PersonalAssistantContextOrchestrator(),
        templateCatalogRuntime: TemplateCatalogRuntime(),
        domainRouter: AssistantDomainRouter(),
        recallCoordinator: RecallCoordinator(),
      );
      final request = AssistantRunRequest(
        sessionId: 'bootstrap_owner',
        messages: const <AssistantRunMessage>[
          AssistantRunMessage(role: 'user', content: '请帮我看看深圳天气'),
        ],
        contextScopeHint: const <String, dynamic>{
          'runArtifacts': <String, dynamic>{
            'machineEnvelope': '',
            'displayMarkdown': '',
            'displayPlainText': '',
            'journey': <String, dynamic>{},
            'evidenceLedger': <Map<String, dynamic>>[],
            'answerEvidenceBindings': <Map<String, dynamic>>[],
            'slotState': <String, dynamic>{
              'domainId': 'weather',
              'slotValues': <String, dynamic>{},
              'missingSlots': <String>['date'],
            },
            'answerDecision': <String, dynamic>{},
            'diagnostics': <String, dynamic>{},
          },
        },
      );

      final result = await phase.run(
        PhaseInput(
          request: request,
          state: const AgentExecutionState(),
          runId: 'run_bootstrap',
          traceId: 'trace_bootstrap',
        ),
      );

      expect(result.state, isNotNull);
      expect(result.state!.bootstrapContext, isNotNull);
      expect(result.state!.bootstrapContext!.sessionId, 'bootstrap_owner');
      expect(result.state!.bootstrapContext!.latestUserQuery, '请帮我看看深圳天气');
      expect(result.state!.bootstrapContext!.skillCatalog, isNotEmpty);
      expect(
        result.state!.bootstrapContext!.skillCatalog,
        contains('- weather:'),
      );
      expect(
        result.state!.bootstrapContext!.skillCatalog,
        contains('- fallback_general_search:'),
      );
      expect(result.state!.contextAssembly, isNotNull);
      expect(result.state!.previousRunArtifacts, isNotNull);
      expect(
        result.state!.previousRunArtifacts!.slotState.missingSlots,
        <String>['date'],
      );
    });

    test('bootstrap phase 应保留上一轮意图与回答摘要', () async {
      final tempDir = await Directory.systemTemp.createTemp(
        'assistant_bootstrap_continuity_',
      );
      addTearDown(() async {
        if (await tempDir.exists()) {
          await tempDir.delete(recursive: true);
        }
      });
      final sessionManager = AssistantSessionManager(
        storagePath: '${tempDir.path}/sessions.json',
      );
      await sessionManager.load();
      final previousIntentGraph = IntentGraph(
        userGoal: '给九寨沟行程做备选路线',
        problemShape: ProblemShape.singleSkill,
        primarySkill: 'travel',
        problemClass: ProblemClass.complexReasoning,
        answerShape: AnswerShape.options,
        entityAnchors: const <String>['九寨沟'],
        contextSlots: const <String, dynamic>{'destination': '九寨沟'},
      );
      const previousJourney = AssistantJourney(
        stages: <AssistantJourneyStage>[
          AssistantJourneyStage(
            stageId: JourneyStageId.answer,
            status: JourneyStageStatus.completed,
            order: 3,
            summary: '已完成路线整理',
          ),
        ],
        summary: '已深度思考，处理3篇文档，耗时4秒',
        readiness: AssistantJourneyReadiness(finalAnswerReady: true),
      );
      sessionManager.appendMessage(
        sessionId: 'bootstrap_continuity_owner',
        role: 'assistant',
        content: '上轮已经给出九寨沟的多条备选路线。',
        metadata: <String, dynamic>{
          ...buildPersistedAssistantTurnFields(
            journey: previousJourney,
            displayMarkdown: '上轮推荐了九寨沟方向三条路线。',
            displayPlainText: '上轮推荐了九寨沟方向三条路线。',
            followupPrompt: '',
            actionHints: const <String>[],
            elapsedMs: 4000,
          ),
          'intentGraph': previousIntentGraph.toJson(),
        },
      );
      await sessionManager.save();
      final phase = BootstrapPhase(
        runtime: ReactRuntime(
          llmProvider: const HeuristicLocalLlmProvider(),
          toolRegistry: AssistantToolRegistry(),
        ),
        sessionManager: sessionManager,
        memoryRepository: AssistantMemoryRepository(
          ObjectBoxVectorStore(storagePath: '${tempDir.path}/memory.json'),
        ),
        contextOrchestrator: const PersonalAssistantContextOrchestrator(),
        templateCatalogRuntime: TemplateCatalogRuntime(),
        domainRouter: AssistantDomainRouter(),
        recallCoordinator: RecallCoordinator(),
      );
      const request = AssistantRunRequest(
        sessionId: 'bootstrap_continuity_owner',
        messages: <AssistantRunMessage>[
          AssistantRunMessage(role: 'user', content: '如果我只有4天，优先哪条路线？'),
        ],
      );

      final result = await phase.run(
        const PhaseInput(
          request: request,
          state: AgentExecutionState(),
          runId: 'run_bootstrap_continuity',
          traceId: 'trace_bootstrap_continuity',
        ),
      );

      expect(result.state!.bootstrapContext?.previousIntentGraph, isNotNull);
      expect(
        result.state!.bootstrapContext?.previousIntentGraph?.primarySkill,
        'travel',
      );
      expect(
        result.state!.bootstrapContext?.previousAnswerSummary,
        contains('九寨沟'),
      );
    });

    test('understand phase 应产出 intent graph 并写入 state', () async {
      final phase = UnderstandPhase();
      final request = AssistantRunRequest(
        messages: const <AssistantRunMessage>[
          AssistantRunMessage(role: 'user', content: '深圳天气怎么样'),
        ],
        contextScopeHint: <String, dynamic>{
          'problemClass': 'realtime_info',
          'requiresExternalEvidence': true,
          'authorityDomains': <String>['weather.com.cn', 'cma.cn'],
          'freshnessHoursMax': 1,
        },
      );

      final result = await phase.run(
        PhaseInput(
          request: request,
          state: const AgentExecutionState(),
          runId: 'run_1',
          traceId: 'trace_1',
        ),
      );

      expect(result.state, isNotNull);
      expect(result.state!.intentGraph, isNotNull);
      expect(
        result.state!.intentGraph!.problemClass,
        ProblemClass.realtimeInfo,
      );
      expect(result.state!.intentGraph!.authorityDomains, <String>[
        'weather.com.cn',
        'cma.cn',
      ]);
      expect(result.state!.intentGraph!.freshnessHoursMax, 1);
      expect(result.state!.dialogueRoundScript, isNotNull);
      expect(
        result.state!.executionPreparation?.domainId,
        result.state!.intentGraph!.primarySkill,
      );
    });

    test('understand phase 模型路径可兼容字符串形式 contextEnvelope', () async {
      final phase = UnderstandPhase(
        runtime: ReactRuntime(
          llmProvider: const HeuristicLocalLlmProvider(),
          toolRegistry: AssistantToolRegistry(),
        ),
      );
      final request = AssistantRunRequest(
        sessionId: 'understand_runtime_context_envelope',
        messages: const <AssistantRunMessage>[
          AssistantRunMessage(role: 'user', content: '如果把九寨沟方向考虑进去，多给我几个备选方案'),
        ],
      );
      final bootstrapContext = AssistantBootstrapContext(
        sessionId: 'understand_runtime_context_envelope',
        latestUserQuery: '如果把九寨沟方向考虑进去，多给我几个备选方案',
        historySummary: '上一轮刚讨论过川西主线。',
        recalledTexts: const <String>['用户更关注路线与住宿备选。'],
      );

      final result = await phase.run(
        PhaseInput(
          request: request,
          state: AgentExecutionState(bootstrapContext: bootstrapContext),
          runId: 'run_understand_runtime_context_envelope',
          traceId: 'trace_understand_runtime_context_envelope',
        ),
      );

      expect(result.state, isNotNull);
      expect(result.state!.intentGraph, isNotNull);
      expect(result.state!.dialogueRoundScript, isNotNull);
      expect(result.state!.executionPreparation, isNotNull);
    });

    test('understand phase 应优先恢复 root-level typed intent graph', () async {
      final phase = UnderstandPhase(
        runtime: ReactRuntime(
          llmProvider: const _RootLevelIntentGraphUnderstandLlm(),
          toolRegistry: AssistantToolRegistry(),
        ),
      );
      const request = AssistantRunRequest(
        sessionId: 'understand_root_level_typed_intent',
        messages: <AssistantRunMessage>[
          AssistantRunMessage(role: 'user', content: '深圳周末天气适合出门吗'),
        ],
      );

      final result = await phase.run(
        PhaseInput(
          request: request,
          state: const AgentExecutionState(),
          runId: 'run_understand_root_level_typed_intent',
          traceId: 'trace_understand_root_level_typed_intent',
        ),
      );

      expect(result.state!.intentGraph, isNotNull);
      expect(result.state!.intentGraph!.primarySkill, 'weather');
      expect(
        result.state!.intentGraph!.problemClass,
        ProblemClass.realtimeInfo,
      );
      expect(result.state!.intentGraph!.entityAnchors, contains('深圳'));
      expect(result.state!.intentGraph!.queryTasks, hasLength(1));
      expect(
        result.state!.intentGraph!.queryTasks.first.authorityDomains,
        contains('weather.cma.cn'),
      );
      expect(result.state!.queryTasks, hasLength(1));
    });

    test('understand phase 应合并 continuity 输入并继承上一轮意图骨架', () async {
      final phase = UnderstandPhase(
        runtime: ReactRuntime(
          llmProvider: const _ContinuityAwareUnderstandLlm(),
          toolRegistry: AssistantToolRegistry(),
        ),
      );
      const previousIntentGraph = IntentGraph(
        userGoal: '给九寨沟行程做备选路线',
        problemShape: ProblemShape.singleSkill,
        primarySkill: 'travel',
        problemClass: ProblemClass.complexReasoning,
        answerShape: AnswerShape.options,
        freshnessNeed: FreshnessNeed.recent,
        requiresExternalEvidence: true,
        entityAnchors: <String>['九寨沟'],
        contextSlots: <String, dynamic>{'destination': '九寨沟'},
        globalConstraints: <String, dynamic>{'mode': 'qa'},
      );
      final bootstrapContext = AssistantBootstrapContext(
        sessionId: 'understand_continuity_owner',
        latestUserQuery: '如果我只有4天，优先哪条路线？',
        historySummary: '上一轮刚讨论过九寨沟多条备选路线。',
        previousIntentGraph: previousIntentGraph,
        previousAnswerSummary: '上轮推荐了九寨沟方向三条路线。',
        contextContinuityPolicy: const ContextContinuityPolicy(
          continuityMode: ContextContinuityMode.explicitFollowUp,
          explicitContinuation: true,
          referenceQueries: <String>['给九寨沟行程做备选路线'],
        ),
        continuityOverrideSlots: const <String, dynamic>{'durationDays': 4},
      );
      final previousRunArtifacts = parseRunArtifacts(<String, dynamic>{
        'machineEnvelope': '',
        'displayMarkdown': '',
        'displayPlainText': '',
        'journey': <String, dynamic>{},
        'evidenceLedger': <Map<String, dynamic>>[],
        'answerEvidenceBindings': <Map<String, dynamic>>[],
        'slotState': <String, dynamic>{
          'domainId': 'travel',
          'slotValues': <String, dynamic>{
            'destination': <String, dynamic>{
              'slotId': 'destination',
              'status': 'filled',
              'value': '九寨沟',
              'source': 'previous_answer',
            },
          },
          'missingSlots': <String>[],
        },
        'answerDecision': <String, dynamic>{},
        'diagnostics': <String, dynamic>{},
      });
      const request = AssistantRunRequest(
        sessionId: 'understand_continuity_owner',
        messages: <AssistantRunMessage>[
          AssistantRunMessage(role: 'user', content: '如果我只有4天，优先哪条路线？'),
        ],
      );

      final result = await phase.run(
        PhaseInput(
          request: request,
          state: AgentExecutionState(
            bootstrapContext: bootstrapContext,
            previousRunArtifacts: previousRunArtifacts,
          ),
          runId: 'run_understand_continuity',
          traceId: 'trace_understand_continuity',
        ),
      );

      expect(result.state!.intentGraph, isNotNull);
      expect(result.state!.intentGraph!.primarySkill, 'travel');
      expect(result.state!.intentGraph!.contextSlots['destination'], '九寨沟');
      expect(
        (result.state!.intentGraph!.contextSlots['overrideSlots']
            as Map?)?['durationDays'],
        4,
      );
      expect(
        (result.state!.intentGraph!.contextSlots['continuity']
            as Map?)?['mode'],
        'explicit_follow_up',
      );
      expect(
        result.state!.intentGraph!.globalConstraints['previousAnswerSummary'],
        contains('九寨沟'),
      );
    });

    test('retrieval design phase 应产出 queryTasks 并回写 intent graph', () async {
      final phase = RetrievalDesignPhase(
        runtime: ReactRuntime(
          llmProvider: const _RetrievalDesignPlanLlm(),
          toolRegistry: AssistantToolRegistry(),
        ),
      );
      final intentGraph = IntentGraph(
        userGoal: '深圳住宿怎么选',
        problemShape: ProblemShape.singleSkill,
        primarySkill: 'fallback_general_search',
        problemClass: ProblemClass.complexReasoning,
        answerShape: AnswerShape.options,
        requiresExternalEvidence: true,
        authorityDomains: const <String>['gov.cn'],
        freshnessHoursMax: 24,
      );
      final request = AssistantRunRequest(
        messages: const <AssistantRunMessage>[
          AssistantRunMessage(role: 'user', content: '深圳住宿怎么选'),
        ],
      );

      final result = await phase.run(
        PhaseInput(
          request: request,
          state: AgentExecutionState(intentGraph: intentGraph),
          runId: 'run_2',
          traceId: 'trace_2',
        ),
      );

      final queryTasks = result.state!.queryTasks;
      expect(queryTasks, hasLength(3));
      expect(
        queryTasks.map((item) => item.id),
        containsAll(<String>['candidate_space', 'fit_scenarios', 'risks']),
      );
      expect(
        queryTasks.every((item) => item.authorityDomains.contains('gov.cn')),
        isTrue,
      );
      expect(queryTasks.every((item) => item.freshnessHoursMax == 24), isTrue);
      expect(result.state!.intentGraph!.queryTasks, hasLength(3));
      expect(result.state!.executionPreparation, isNotNull);
      expect(
        result.state!.executionPreparation!.domainId,
        result.state!.intentGraph!.primarySkill,
      );
      expect(
        result.state!.executionPreparation!.executionShell.problemClass,
        isNotEmpty,
      );
    });

    test(
      'retrieval design phase 应产出启发式 typed queryTasks',
      () async {
        final phase = RetrievalDesignPhase(
          runtime: ReactRuntime(
            llmProvider: const _ToolCallQueryTasksRetrievalDesignLlm(),
            toolRegistry: AssistantToolRegistry(),
          ),
        );
        const intentGraph = IntentGraph(
          userGoal: '深圳周末天气适合出门吗',
          problemShape: ProblemShape.singleSkill,
          primarySkill: 'weather',
          problemClass: ProblemClass.realtimeInfo,
          answerShape: AnswerShape.decisionReady,
          freshnessNeed: FreshnessNeed.recent,
          requiresExternalEvidence: true,
          entityAnchors: <String>['深圳'],
          authorityDomains: <String>['weather.cma.cn'],
          freshnessHoursMax: 6,
        );
        const request = AssistantRunRequest(
          messages: <AssistantRunMessage>[
            AssistantRunMessage(role: 'user', content: '深圳周末天气适合出门吗'),
          ],
        );

        final result = await phase.run(
          PhaseInput(
            request: request,
            state: const AgentExecutionState(intentGraph: intentGraph),
            runId: 'run_retrieval_tool_call_query_tasks',
            traceId: 'trace_retrieval_tool_call_query_tasks',
          ),
        );

        expect(result.state!.queryTasks, hasLength(2));
        expect(
          result.state!.queryTasks.map((item) => item.id),
          containsAll(<String>['key_facts', 'decision_threshold']),
        );
        expect(
          result.state!.queryTasks.every(
            (item) => item.authorityDomains.contains('weather.cma.cn'),
          ),
          isTrue,
        );
        expect(
          result.state!.queryTasks.every((item) => item.freshnessHoursMax == 6),
          isTrue,
        );
        expect(result.state!.intentGraph!.queryTasks, hasLength(2));
      },
    );

    test('retrieval design phase 应消费 continuity 输入补全 query task 语义', () async {
      final phase = RetrievalDesignPhase(
        runtime: ReactRuntime(
          llmProvider: const _ToolCallQueryTasksRetrievalDesignLlm(),
          toolRegistry: AssistantToolRegistry(),
        ),
      );
      const previousIntentGraph = IntentGraph(
        userGoal: '给九寨沟行程做备选路线',
        problemShape: ProblemShape.singleSkill,
        primarySkill: 'travel',
        problemClass: ProblemClass.complexReasoning,
        answerShape: AnswerShape.options,
        freshnessNeed: FreshnessNeed.recent,
        requiresExternalEvidence: true,
        entityAnchors: <String>['九寨沟'],
        negativeKeywords: <String>['购物团'],
        contextSlots: <String, dynamic>{'destination': '九寨沟'},
        authorityDomains: <String>['gov.cn'],
        freshnessHoursMax: 24,
      );
      final bootstrapContext = AssistantBootstrapContext(
        sessionId: 'retrieval_continuity_owner',
        latestUserQuery: '如果我只有4天，优先哪条路线？',
        previousIntentGraph: previousIntentGraph,
        previousAnswerSummary: '上轮推荐了九寨沟方向三条路线。',
        contextContinuityPolicy: const ContextContinuityPolicy(
          continuityMode: ContextContinuityMode.explicitFollowUp,
          explicitContinuation: true,
          referenceQueries: <String>['给九寨沟行程做备选路线'],
        ),
        continuityOverrideSlots: const <String, dynamic>{'durationDays': 4},
      );
      const intentGraph = IntentGraph(
        userGoal: '4天优先哪条路线',
        problemShape: ProblemShape.singleSkill,
        primarySkill: 'travel',
        problemClass: ProblemClass.complexReasoning,
        answerShape: AnswerShape.options,
        freshnessNeed: FreshnessNeed.recent,
        requiresExternalEvidence: true,
        entityAnchors: <String>['九寨沟'],
        negativeKeywords: <String>['购物团'],
        contextSlots: <String, dynamic>{
          'destination': '九寨沟',
          'overrideSlots': <String, dynamic>{'durationDays': 4},
        },
        authorityDomains: <String>['gov.cn'],
        freshnessHoursMax: 24,
      );
      final previousRunArtifacts = parseRunArtifacts(<String, dynamic>{
        'machineEnvelope': '',
        'displayMarkdown': '',
        'displayPlainText': '',
        'journey': <String, dynamic>{},
        'evidenceLedger': <Map<String, dynamic>>[],
        'answerEvidenceBindings': <Map<String, dynamic>>[],
        'slotState': <String, dynamic>{
          'domainId': 'travel',
          'slotValues': <String, dynamic>{
            'destination': <String, dynamic>{
              'slotId': 'destination',
              'status': 'filled',
              'value': '九寨沟',
              'source': 'previous_answer',
            },
          },
          'missingSlots': <String>[],
        },
        'answerDecision': <String, dynamic>{},
        'diagnostics': <String, dynamic>{},
      });
      const request = AssistantRunRequest(
        sessionId: 'retrieval_continuity_owner',
        messages: <AssistantRunMessage>[
          AssistantRunMessage(role: 'user', content: '如果我只有4天，优先哪条路线？'),
        ],
      );

      final result = await phase.run(
        PhaseInput(
          request: request,
          state: AgentExecutionState(
            bootstrapContext: bootstrapContext,
            intentGraph: intentGraph,
            previousRunArtifacts: previousRunArtifacts,
          ),
          runId: 'run_retrieval_continuity',
          traceId: 'trace_retrieval_continuity',
        ),
      );

      expect(result.state!.queryTasks, isNotEmpty);
      expect(
        result.state!.queryTasks.every(
          (item) => item.entityAnchors.contains('九寨沟'),
        ),
        isTrue,
      );
      expect(
        result.state!.queryTasks.every(
          (item) => item.answerShape == AnswerShape.options,
        ),
        isTrue,
      );
      expect(
        result.state!.queryTasks.every(
          (item) => item.freshnessNeed == FreshnessNeed.recent,
        ),
        isTrue,
      );
    });

    test('synthesis phase 应从 pendingResponse 回灌 run artifacts', () async {
      final tempDir = await Directory.systemTemp.createTemp(
        'assistant_synthesis_phase_',
      );
      addTearDown(() async {
        if (await tempDir.exists()) {
          await tempDir.delete(recursive: true);
        }
      });
      final phase = SynthesisPhase(
        phase_owner.LocalPhaseExecutionOwner(
          ReactRuntime(
            llmProvider: const HeuristicLocalLlmProvider(),
            toolRegistry: AssistantToolRegistry(),
          ),
          sessionManager: AssistantSessionManager(
            storagePath: '${tempDir.path}/sessions.json',
          ),
          memoryRepository: AssistantMemoryRepository(
            ObjectBoxVectorStore(storagePath: '${tempDir.path}/memory.json'),
          ),
        ),
      );
      final pendingResponse = AssistantRunResponse(
        finalText: '{"ok":true}',
        traces: const [],
        structuredResponse: const <String, dynamic>{
          'aggregationState': <String, dynamic>{
            'allSkillsReady': true,
            'finalAnswerReady': true,
            'finalAnswerMode': 'full',
            'answerOwner': 'chat',
          },
          'synthesisReadiness': <String, dynamic>{
            'ready': true,
            'reason': 'evidence grounded',
          },
          'evidenceEvaluation': <String, dynamic>{
            'coverageScore': 1.0,
            'authorityScore': 0.92,
            'relevanceScore': 0.88,
            'freshnessHours': 1,
            'status': 'full',
            'passed': true,
            'authoritySatisfied': true,
            'freshnessSatisfied': true,
            'evidenceRequired': true,
            'coveredDimensions': <String>['realtime_fact'],
            'coveredQueryTaskIds': <String>['weather_now'],
            'blockingDimensions': <String>[],
            'missingDimensions': <String>[],
            'summary': '证据账完整。',
          },
          'conversationStateDecision': <String, dynamic>{
            'nextAction': 'answer',
            'finalAnswerMode': 'full',
            'answerEligibility': 'ready',
            'slotState': <String, dynamic>{
              'domainId': 'chat',
              'slotValues': <String, dynamic>{
                'city': <String, dynamic>{
                  'slotId': 'city',
                  'status': 'filled',
                  'value': '深圳',
                  'source': 'tool_result',
                },
              },
              'missingSlots': <String>[],
            },
            'missingCriticalSlots': <String>[],
            'askUser': <String, dynamic>{},
            'qualityGates': <String, dynamic>{
              'structureSafe': true,
              'taskSafe': true,
              'evidenceSafe': true,
              'renderSafe': true,
            },
            'finalAnswerReady': true,
          },
          'runArtifacts': <String, dynamic>{
            'machineEnvelope': '',
            'displayMarkdown': '你好',
            'displayPlainText': '你好',
            'journey': <String, dynamic>{},
            'evidenceLedger': <Map<String, dynamic>>[
              <String, dynamic>{
                'evidenceId': 'ev_weather_1',
                'domainId': 'chat',
                'dimension': 'realtime_fact',
                'dimensionLabel': '实时事实',
                'queryTaskId': 'weather_now',
                'title': '深圳天气预报 - 中国气象局',
                'url': 'https://weather.cma.cn/shenzhen',
                'sourceHost': 'weather.cma.cn',
                'sourceTier': 'official',
                'freshnessHours': 1,
                'authorityScore': 0.92,
                'relevanceScore': 0.88,
                'slotContributions': <String, dynamic>{'city': '深圳'},
                'snippet': '深圳当前天气晴。',
                'retrievedAt': '2026-03-16T10:00:00.000Z',
              },
            ],
            'answerEvidenceBindings': <Map<String, dynamic>>[
              <String, dynamic>{
                'bindingId': 'bind_weather_1',
                'label': '[1]',
                'claim': '深圳当前天气晴。',
                'evidenceId': 'ev_weather_1',
                'url': 'https://weather.cma.cn/shenzhen',
                'title': '深圳天气预报 - 中国气象局',
                'source': '中国气象局',
                'snippet': '深圳当前天气晴。',
              },
            ],
            'slotState': <String, dynamic>{
              'domainId': 'chat',
              'slotValues': <String, dynamic>{
                'city': <String, dynamic>{
                  'slotId': 'city',
                  'status': 'filled',
                  'value': '深圳',
                  'source': 'tool_result',
                  'confidence': 0.98,
                  'evidenceIds': <String>['ev_weather_1'],
                },
              },
              'missingSlots': <String>[],
            },
            'answerDecision': <String, dynamic>{},
            'diagnostics': <String, dynamic>{},
            'domainPolicyBundle': <String, dynamic>{
              'domainId': 'chat',
              'retrievalPolicy': <String, dynamic>{'authorityRequired': true},
            },
          },
        },
      );

      final result = await phase.run(
        PhaseInput(
          request: AssistantRunRequest(messages: const <AssistantRunMessage>[]),
          state: AgentExecutionState(pendingResponse: pendingResponse),
          runId: 'run_synth',
          traceId: 'trace_synth',
        ),
      );

      expect(result.state!.previousRunArtifacts, isNotNull);
      expect(result.state!.previousRunArtifacts!.displayPlainText, '你好');
      expect(result.state!.aggregationState, isNotNull);
      expect(result.state!.aggregationState!.finalAnswerReady, isTrue);
      expect(result.state!.synthesisReadiness?.ready, isTrue);
      expect(result.state!.evidenceLedger, hasLength(1));
      expect(result.state!.answerEvidenceBindings, hasLength(1));
      expect(result.state!.evidenceEvaluation, isNotNull);
      expect(result.state!.evidenceEvaluation!.entries, hasLength(1));
      expect(result.state!.evidenceEvaluation!.status, EvidenceStatus.full);
      expect(result.state!.slotState?.slotValueOf('city')?.value, '深圳');
      expect(
        result.state!.slotState?.slotValueOf('city')?.evidenceIds,
        <String>['ev_weather_1'],
      );
      expect(
        result.state!.conversationStateDecision?.nextActionType,
        AssistantNextAction.answer,
      );
      expect(result.state!.domainPolicyBundle?.domainId, 'chat');
    });

    test('synthesis phase 应通过 draft seam 物化 pendingResponse', () async {
      final tempDir = await Directory.systemTemp.createTemp(
        'assistant_synthesis_draft_phase_',
      );
      addTearDown(() async {
        if (await tempDir.exists()) {
          await tempDir.delete(recursive: true);
        }
      });
      final toolRegistry = AssistantToolRegistry()
        ..register(_SynthesisDraftWeatherSearchTool());
      final loop = phase_owner.LocalPhaseExecutionOwner(
        ReactRuntime(
          llmProvider: _SynthesisDraftWeatherLlm(),
          toolRegistry: toolRegistry,
        ),
        sessionManager: AssistantSessionManager(
          storagePath: '${tempDir.path}/sessions.json',
        ),
        memoryRepository: AssistantMemoryRepository(
          ObjectBoxVectorStore(storagePath: '${tempDir.path}/memory.json'),
        ),
      );
      const request = AssistantRunRequest(
        sessionId: 'synthesis_draft_owner',
        messages: <AssistantRunMessage>[
          AssistantRunMessage(role: 'user', content: '深圳天气怎么样'),
        ],
        contextScopeHint: <String, dynamic>{
          'problemClass': 'realtime_info',
          'requiresExternalEvidence': true,
        },
      );
      final snapshot = await loop.executeBridge(
        request,
        runId: 'run_synthesis_draft_owner',
        traceId: 'trace_synthesis_draft_owner',
      );

      expect(snapshot['shortCircuitResponse'], isNull);

      final result = await SynthesisPhase(loop).run(
        PhaseInput(
          request: request,
          state: AgentExecutionState(executionBridgeSnapshot: snapshot),
          runId: 'run_synthesis_draft_owner',
          traceId: 'trace_synthesis_draft_owner',
        ),
      );

      expect(result.state!.synthesisDraft, isNotNull);
      expect(result.state!.pendingResponse, isNotNull);
      expect(result.state!.pendingResponse!.runArtifacts, isNotNull);
      expect(result.state!.pendingResponse!.displayMarkdown.trim(), isNotEmpty);
      expect(result.state!.previousRunArtifacts, isNotNull);
      expect(result.state!.evidenceLedger, isNotEmpty);
      expect(result.state!.conversationStateDecision?.finalAnswerReady, isTrue);
    });

    test('synthesis phase 在 phase-one 已成答时应跳过 synthesis', () async {
      final tempDir = await Directory.systemTemp.createTemp(
        'assistant_phase_one_direct_answer_',
      );
      addTearDown(() async {
        if (await tempDir.exists()) {
          await tempDir.delete(recursive: true);
        }
      });
      final llm = _PhaseOneDirectAnswerLlm();
      final loop = phase_owner.LocalPhaseExecutionOwner(
        ReactRuntime(llmProvider: llm, toolRegistry: AssistantToolRegistry()),
        sessionManager: AssistantSessionManager(
          storagePath: '${tempDir.path}/sessions.json',
        ),
        memoryRepository: AssistantMemoryRepository(
          ObjectBoxVectorStore(storagePath: '${tempDir.path}/memory.json'),
        ),
      );
      final fallbackDomainId = AssistantDomainRouter().fallbackDomainId;
      final prepared = AssistantExecutionPreparation(
        domainId: fallbackDomainId,
        modeDecision: const ModeDecision(
          mode: AgentMode.singleAgent,
          reason: 'phase_one_direct_answer_test',
        ),
        skillName: 'General Direct Answer',
        skillInstructionMarkdown: '请直接输出最终答案。',
        executionShell: const SkillExecutionShell(
          problemClass: 'simple_qa',
          maxIterations: 1,
          toolBudget: 0,
          variantBudget: 0,
          reflectionBudget: 0,
          freshnessHoursMax: 720,
        ),
        plannerTemplateVersion: 'direct_answer_planner_v1',
        postcheckTemplateVersion: 'direct_answer_postcheck_v1',
        synthTemplateVersion: 'direct_answer_synth_v1',
        fusionSynthTemplateVersion: 'direct_answer_fusion_v1',
      );
      final request = AssistantRunRequest(
        sessionId: 'phase_one_direct_answer_owner',
        messages: const <AssistantRunMessage>[
          AssistantRunMessage(role: 'user', content: '请用一句话解释牛顿第一定律'),
        ],
        contextScopeHint: <String, dynamic>{
          'precomputedIntentGraph': const IntentGraph(
            userGoal: '一句话解释牛顿第一定律',
            problemShape: ProblemShape.singleSkill,
            primarySkill: '',
            problemClass: ProblemClass.simpleQa,
            answerShape: AnswerShape.directAnswer,
            requiresExternalEvidence: false,
          ).toJson(),
          'precomputedExecutionPreparation': prepared.toJson(),
        },
      );

      final snapshot = await loop.executeBridge(
        request,
        runId: 'run_phase_one_direct_answer_owner',
        traceId: 'trace_phase_one_direct_answer_owner',
      );

      final result = await SynthesisPhase(loop).run(
        PhaseInput(
          request: request,
          state: AgentExecutionState(executionBridgeSnapshot: snapshot),
          runId: 'run_phase_one_direct_answer_owner',
          traceId: 'trace_phase_one_direct_answer_owner',
        ),
      );

      expect(result.state!.synthesisDraft, isNotNull);
      expect(
        result.state!.synthesisDraft!.templateVersionUsed,
        'phase_one_direct_answer',
      );
      expect(llm.phaseOneCallCount, 1);
      expect(llm.synthesisCallCount, 0);
      expect(result.state!.pendingResponse, isNotNull);
      expect(
        result.state!.pendingResponse!.displayMarkdown,
        contains('牛顿第一定律'),
      );
      expect(
        result.state!.conversationStateDecision?.nextActionType,
        AssistantNextAction.answer,
      );
      final uiUsageStats =
          result.state!.pendingResponse!.structuredResponse['uiUsageStats']
              as Map<String, dynamic>;
      expect(uiUsageStats['modelCallCount'], 1);
    });

    test(
      'execute bridge 应在 gap-fill retry 后重算 readiness 并继续 direct answer',
      () async {
        final tempDir = await Directory.systemTemp.createTemp(
          'assistant_phase_one_gap_fill_direct_answer_',
        );
        addTearDown(() async {
          if (await tempDir.exists()) {
            await tempDir.delete(recursive: true);
          }
        });
        final llm = _PhaseOneGapFillThenDirectAnswerLlm();
        final toolRegistry = AssistantToolRegistry()
          ..register(_SynthesisDraftWeatherSearchTool());
        final loop = phase_owner.LocalPhaseExecutionOwner(
          ReactRuntime(llmProvider: llm, toolRegistry: toolRegistry),
          sessionManager: AssistantSessionManager(
            storagePath: '${tempDir.path}/sessions.json',
          ),
          memoryRepository: AssistantMemoryRepository(
            ObjectBoxVectorStore(storagePath: '${tempDir.path}/memory.json'),
          ),
        );
        final prepared = AssistantExecutionPreparation(
          domainId: 'weather',
          modeDecision: const ModeDecision(
            mode: AgentMode.singleAgent,
            reason: 'gap_fill_readiness_recompute_test',
          ),
          skillName: 'Weather QA',
          skillInstructionMarkdown: '先拿到实时证据，再直接整理为最终答案。',
          allowedToolNames: const <String>['web_search'],
          executionShell: const SkillExecutionShell(
            problemClass: 'realtime_info',
            maxIterations: 3,
            toolBudget: 1,
            variantBudget: 0,
            reflectionBudget: 0,
            freshnessHoursMax: 6,
          ),
          plannerTemplateVersion: 'gap_fill_direct_planner_v1',
          postcheckTemplateVersion: 'gap_fill_direct_postcheck_v1',
          synthTemplateVersion: 'gap_fill_direct_synth_v1',
          fusionSynthTemplateVersion: 'gap_fill_direct_fusion_v1',
        );
        final request = AssistantRunRequest(
          sessionId: 'phase_one_gap_fill_direct_answer_owner',
          messages: const <AssistantRunMessage>[
            AssistantRunMessage(role: 'user', content: '深圳今天适合出门吗？'),
          ],
          contextScopeHint: <String, dynamic>{
            'precomputedIntentGraph': const IntentGraph(
              userGoal: '判断深圳今天是否适合出门',
              problemShape: ProblemShape.singleSkill,
              primarySkill: 'weather',
              problemClass: ProblemClass.realtimeInfo,
              answerShape: AnswerShape.directAnswer,
              freshnessNeed: FreshnessNeed.realtime,
              mustVerifyClaims: true,
              requiresExternalEvidence: true,
              entityAnchors: <String>['深圳'],
              authorityDomains: <String>['weather.cma.cn', 'cma.cn'],
              freshnessHoursMax: 1,
            ).toJson(),
            'precomputedExecutionPreparation': prepared.toJson(),
          },
        );

        final snapshot = await loop.executeBridge(
          request,
          runId: 'run_phase_one_gap_fill_direct_answer_owner',
          traceId: 'trace_phase_one_gap_fill_direct_answer_owner',
        );

        final readiness =
            snapshot['synthesisReadiness'] as SynthesisReadinessResult;
        final boundary = snapshot['answerBoundaryPolicy'];
        expect((boundary as dynamic).requireToolResultBeforeSynthesis, isTrue);
        expect(readiness.ready, isTrue);
        expect(llm.initialPlannerCallCount, 1);
        expect(llm.postcheckToolCallCount, 1);
        expect(llm.postcheckAnswerCallCount, 1);

        final result = await SynthesisPhase(loop).run(
          PhaseInput(
            request: request,
            state: AgentExecutionState(executionBridgeSnapshot: snapshot),
            runId: 'run_phase_one_gap_fill_direct_answer_owner',
            traceId: 'trace_phase_one_gap_fill_direct_answer_owner',
          ),
        );

        expect(
          result.state!.synthesisDraft!.templateVersionUsed,
          'phase_one_direct_answer',
        );
        expect(llm.synthesisCallCount, 0);
        expect(
          result.state!.pendingResponse!.displayMarkdown,
          contains('深圳今天适合出门'),
        );
        final uiUsageStats =
            result.state!.pendingResponse!.structuredResponse['uiUsageStats']
                as Map<String, dynamic>;
        expect(uiUsageStats['modelCallCount'], 3);
      },
    );

    test('synthesis phase 应恢复非结构化 phase-one answer 并跳过 synthesis', () async {
      final tempDir = await Directory.systemTemp.createTemp(
        'assistant_phase_one_plain_markdown_',
      );
      addTearDown(() async {
        if (await tempDir.exists()) {
          await tempDir.delete(recursive: true);
        }
      });
      final llm = _PhaseOnePlainMarkdownAnswerLlm();
      final loop = phase_owner.LocalPhaseExecutionOwner(
        ReactRuntime(llmProvider: llm, toolRegistry: AssistantToolRegistry()),
        sessionManager: AssistantSessionManager(
          storagePath: '${tempDir.path}/sessions.json',
        ),
        memoryRepository: AssistantMemoryRepository(
          ObjectBoxVectorStore(storagePath: '${tempDir.path}/memory.json'),
        ),
      );
      final fallbackDomainId = AssistantDomainRouter().fallbackDomainId;
      final prepared = AssistantExecutionPreparation(
        domainId: fallbackDomainId,
        modeDecision: const ModeDecision(
          mode: AgentMode.singleAgent,
          reason: 'phase_one_plain_markdown_recovery_test',
        ),
        skillName: 'General Direct Answer',
        skillInstructionMarkdown: '若本轮已能直接回答，就直接给出最终答复。',
        executionShell: const SkillExecutionShell(
          problemClass: 'simple_qa',
          maxIterations: 1,
          toolBudget: 0,
          variantBudget: 0,
          reflectionBudget: 0,
          freshnessHoursMax: 720,
        ),
        plannerTemplateVersion: 'plain_markdown_planner_v1',
        postcheckTemplateVersion: 'plain_markdown_postcheck_v1',
        synthTemplateVersion: 'plain_markdown_synth_v1',
        fusionSynthTemplateVersion: 'plain_markdown_fusion_v1',
      );
      final request = AssistantRunRequest(
        sessionId: 'phase_one_plain_markdown_owner',
        messages: const <AssistantRunMessage>[
          AssistantRunMessage(role: 'user', content: '一句话说明什么是惯性'),
        ],
        contextScopeHint: <String, dynamic>{
          'precomputedIntentGraph': const IntentGraph(
            userGoal: '一句话说明什么是惯性',
            problemShape: ProblemShape.singleSkill,
            primarySkill: '',
            problemClass: ProblemClass.simpleQa,
            answerShape: AnswerShape.directAnswer,
            requiresExternalEvidence: false,
            entityAnchors: <String>['惯性'],
          ).toJson(),
          'precomputedExecutionPreparation': prepared.toJson(),
        },
      );

      final snapshot = await loop.executeBridge(
        request,
        runId: 'run_phase_one_plain_markdown_owner',
        traceId: 'trace_phase_one_plain_markdown_owner',
      );

      final result = await SynthesisPhase(loop).run(
        PhaseInput(
          request: request,
          state: AgentExecutionState(executionBridgeSnapshot: snapshot),
          runId: 'run_phase_one_plain_markdown_owner',
          traceId: 'trace_phase_one_plain_markdown_owner',
        ),
      );

      expect(
        result.state!.synthesisDraft!.templateVersionUsed,
        'phase_one_direct_answer',
      );
      expect(llm.phaseOneCallCount, 1);
      expect(llm.synthesisCallCount, 0);
      expect(result.state!.pendingResponse!.displayPlainText, contains('惯性'));
      final diagnostics =
          result
                  .state!
                  .pendingResponse!
                  .structuredResponse['phaseOneRoutingDiagnostics']
              as Map<String, dynamic>;
      expect(diagnostics['phaseOneRecoveryApplied'], isTrue);
      expect(diagnostics['rawDirectAnswerReason'], 'phase_one_not_structured');
    });

    test('synthesis phase 应恢复非契约 phase-one json 并跳过 synthesis', () async {
      final tempDir = await Directory.systemTemp.createTemp(
        'assistant_phase_one_non_contract_json_',
      );
      addTearDown(() async {
        if (await tempDir.exists()) {
          await tempDir.delete(recursive: true);
        }
      });
      final llm = _PhaseOneNonContractJsonAnswerLlm();
      final loop = phase_owner.LocalPhaseExecutionOwner(
        ReactRuntime(llmProvider: llm, toolRegistry: AssistantToolRegistry()),
        sessionManager: AssistantSessionManager(
          storagePath: '${tempDir.path}/sessions.json',
        ),
        memoryRepository: AssistantMemoryRepository(
          ObjectBoxVectorStore(storagePath: '${tempDir.path}/memory.json'),
        ),
      );
      final fallbackDomainId = AssistantDomainRouter().fallbackDomainId;
      final prepared = AssistantExecutionPreparation(
        domainId: fallbackDomainId,
        modeDecision: const ModeDecision(
          mode: AgentMode.singleAgent,
          reason: 'phase_one_non_contract_json_recovery_test',
        ),
        skillName: 'General Direct Answer',
        skillInstructionMarkdown: '若本轮已能直接回答，就直接给出最终答复。',
        executionShell: const SkillExecutionShell(
          problemClass: 'simple_qa',
          maxIterations: 1,
          toolBudget: 0,
          variantBudget: 0,
          reflectionBudget: 0,
          freshnessHoursMax: 720,
        ),
        plannerTemplateVersion: 'non_contract_planner_v1',
        postcheckTemplateVersion: 'non_contract_postcheck_v1',
        synthTemplateVersion: 'non_contract_synth_v1',
        fusionSynthTemplateVersion: 'non_contract_fusion_v1',
      );
      final request = AssistantRunRequest(
        sessionId: 'phase_one_non_contract_json_owner',
        messages: const <AssistantRunMessage>[
          AssistantRunMessage(role: 'user', content: '一句话解释光合作用'),
        ],
        contextScopeHint: <String, dynamic>{
          'precomputedIntentGraph': const IntentGraph(
            userGoal: '一句话解释光合作用',
            problemShape: ProblemShape.singleSkill,
            primarySkill: '',
            problemClass: ProblemClass.simpleQa,
            answerShape: AnswerShape.directAnswer,
            requiresExternalEvidence: false,
            entityAnchors: <String>['光合作用'],
          ).toJson(),
          'precomputedExecutionPreparation': prepared.toJson(),
        },
      );

      final snapshot = await loop.executeBridge(
        request,
        runId: 'run_phase_one_non_contract_json_owner',
        traceId: 'trace_phase_one_non_contract_json_owner',
      );

      final result = await SynthesisPhase(loop).run(
        PhaseInput(
          request: request,
          state: AgentExecutionState(executionBridgeSnapshot: snapshot),
          runId: 'run_phase_one_non_contract_json_owner',
          traceId: 'trace_phase_one_non_contract_json_owner',
        ),
      );

      expect(
        result.state!.synthesisDraft!.templateVersionUsed,
        'phase_one_direct_answer',
      );
      expect(llm.phaseOneCallCount, 1);
      expect(llm.synthesisCallCount, 0);
      expect(result.state!.pendingResponse!.displayPlainText, contains('光合作用'));
      final diagnostics =
          result
                  .state!
                  .pendingResponse!
                  .structuredResponse['phaseOneRoutingDiagnostics']
              as Map<String, dynamic>;
      expect(diagnostics['phaseOneRecoveryApplied'], isTrue);
      expect(
        diagnostics['rawDirectAnswerReason'],
        'phase_one_not_contract_turn',
      );
    });

    test(
      'synthesis phase 应在连续追问场景下走 phase-one answer repair 而非 formal synthesis',
      () async {
        final tempDir = await Directory.systemTemp.createTemp(
          'assistant_phase_one_followup_answer_repair_',
        );
        addTearDown(() async {
          if (await tempDir.exists()) {
            await tempDir.delete(recursive: true);
          }
        });
        final llm = _PhaseOneFollowupDirectAnswerRepairLlm();
        final loop = phase_owner.LocalPhaseExecutionOwner(
          ReactRuntime(llmProvider: llm, toolRegistry: AssistantToolRegistry()),
          sessionManager: AssistantSessionManager(
            storagePath: '${tempDir.path}/sessions.json',
          ),
          memoryRepository: AssistantMemoryRepository(
            ObjectBoxVectorStore(storagePath: '${tempDir.path}/memory.json'),
          ),
        );
        final fallbackDomainId = AssistantDomainRouter().fallbackDomainId;
        final prepared = AssistantExecutionPreparation(
          domainId: fallbackDomainId,
          modeDecision: const ModeDecision(
            mode: AgentMode.singleAgent,
            reason: 'phase_one_followup_answer_repair_test',
          ),
          skillName: 'Travel Follow-up Answer',
          skillInstructionMarkdown: '延续上一轮时，若已能回答就直接给出最终答复。',
          executionShell: const SkillExecutionShell(
            problemClass: 'simple_qa',
            maxIterations: 1,
            toolBudget: 0,
            variantBudget: 0,
            reflectionBudget: 0,
            freshnessHoursMax: 72,
          ),
          plannerTemplateVersion: 'followup_repair_planner_v1',
          postcheckTemplateVersion: 'followup_repair_postcheck_v1',
          synthTemplateVersion: 'followup_repair_synth_v1',
          fusionSynthTemplateVersion: 'followup_repair_fusion_v1',
        );
        const previousIntentGraph = IntentGraph(
          userGoal: '给九寨沟行程做备选路线',
          problemShape: ProblemShape.singleSkill,
          primarySkill: 'travel',
          problemClass: ProblemClass.complexReasoning,
          answerShape: AnswerShape.options,
          requiresExternalEvidence: false,
          entityAnchors: <String>['九寨沟'],
        );
        final request = AssistantRunRequest(
          sessionId: 'phase_one_followup_answer_repair_owner',
          messages: const <AssistantRunMessage>[
            AssistantRunMessage(role: 'user', content: '如果我只有4天，优先哪条路线？'),
          ],
          contextScopeHint: <String, dynamic>{
            'precomputedBootstrap': <String, dynamic>{
              'sessionId': 'phase_one_followup_answer_repair_owner',
              'latestUserQuery': '如果我只有4天，优先哪条路线？',
              'historySummary': '上一轮刚讨论过九寨沟多条备选路线。',
              'previousIntentGraph': previousIntentGraph.toJson(),
              'previousAnswerSummary': '上轮推荐了九寨沟方向三条路线。',
              'contextContinuityPolicy': const ContextContinuityPolicy(
                continuityMode: ContextContinuityMode.explicitFollowUp,
                explicitContinuation: true,
                referenceQueries: <String>['给九寨沟行程做备选路线'],
              ).toJson(),
              'continuityOverrideSlots': const <String, dynamic>{
                'durationDays': 4,
              },
            },
            'precomputedIntentGraph': const IntentGraph(
              userGoal: '4天优先哪条路线',
              problemShape: ProblemShape.singleSkill,
              primarySkill: '',
              problemClass: ProblemClass.simpleQa,
              answerShape: AnswerShape.directAnswer,
              requiresExternalEvidence: false,
              entityAnchors: <String>['九寨沟'],
              contextSlots: <String, dynamic>{
                'destination': '九寨沟',
                'continuity': <String, dynamic>{'mode': 'explicit_follow_up'},
                'overrideSlots': <String, dynamic>{'durationDays': 4},
              },
            ).toJson(),
            'precomputedExecutionPreparation': prepared.toJson(),
          },
        );

        final snapshot = await loop.executeBridge(
          request,
          runId: 'run_phase_one_followup_answer_repair_owner',
          traceId: 'trace_phase_one_followup_answer_repair_owner',
        );

        final result = await SynthesisPhase(loop).run(
          PhaseInput(
            request: request,
            state: AgentExecutionState(executionBridgeSnapshot: snapshot),
            runId: 'run_phase_one_followup_answer_repair_owner',
            traceId: 'trace_phase_one_followup_answer_repair_owner',
          ),
        );

        final diagnostics =
            result
                    .state!
                    .pendingResponse!
                    .structuredResponse['phaseOneRoutingDiagnostics']
                as Map<String, dynamic>;
        expect(
          result.state!.synthesisDraft!.templateVersionUsed,
          'phase_one_direct_answer',
        );
        expect(llm.phaseOneCallCount, 1);
        expect(llm.repairCallCount, 1);
        expect(llm.synthesisCallCount, 0);
        expect(
          result.state!.pendingResponse!.displayPlainText,
          contains('九寨沟'),
        );
        expect(diagnostics['route'], 'phase_one_direct_answer');
        expect(
          diagnostics['rawDirectAnswerReason'],
          'phase_one_not_structured',
        );
        expect(diagnostics['phaseOneRecoveryApplied'], isFalse);
        expect(diagnostics['phaseOneModelRepairApplied'], isTrue);
      },
    );

    test(
      'synthesis phase 在连续追问且已有检索痕迹时仍可走 phase-one answer repair',
      () async {
        final tempDir = await Directory.systemTemp.createTemp(
          'assistant_phase_one_followup_answer_repair_with_execution_',
        );
        addTearDown(() async {
          if (await tempDir.exists()) {
            await tempDir.delete(recursive: true);
          }
        });
        final llm = _PhaseOneFollowupDirectAnswerRepairLlm();
        final loop = phase_owner.LocalPhaseExecutionOwner(
          ReactRuntime(llmProvider: llm, toolRegistry: AssistantToolRegistry()),
          sessionManager: AssistantSessionManager(
            storagePath: '${tempDir.path}/sessions.json',
          ),
          memoryRepository: AssistantMemoryRepository(
            ObjectBoxVectorStore(storagePath: '${tempDir.path}/memory.json'),
          ),
        );
        final fallbackDomainId = AssistantDomainRouter().fallbackDomainId;
        final prepared = AssistantExecutionPreparation(
          domainId: fallbackDomainId,
          modeDecision: const ModeDecision(
            mode: AgentMode.singleAgent,
            reason: 'phase_one_followup_answer_repair_with_execution_test',
          ),
          skillName: 'Travel Follow-up Answer',
          skillInstructionMarkdown: '延续上一轮时，若已能回答就直接给出最终答复。',
          executionShell: const SkillExecutionShell(
            problemClass: 'simple_qa',
            maxIterations: 1,
            toolBudget: 0,
            variantBudget: 0,
            reflectionBudget: 0,
            freshnessHoursMax: 72,
          ),
          plannerTemplateVersion: 'followup_repair_planner_v1',
          postcheckTemplateVersion: 'followup_repair_postcheck_v1',
          synthTemplateVersion: 'followup_repair_synth_v1',
          fusionSynthTemplateVersion: 'followup_repair_fusion_v1',
        );
        const previousIntentGraph = IntentGraph(
          userGoal: '给九寨沟行程做备选路线',
          problemShape: ProblemShape.singleSkill,
          primarySkill: 'travel',
          problemClass: ProblemClass.complexReasoning,
          answerShape: AnswerShape.options,
          requiresExternalEvidence: false,
          entityAnchors: <String>['九寨沟'],
        );
        final request = AssistantRunRequest(
          sessionId: 'phase_one_followup_answer_repair_with_execution_owner',
          messages: const <AssistantRunMessage>[
            AssistantRunMessage(role: 'user', content: '如果我只有4天，优先哪条路线？'),
          ],
          contextScopeHint: <String, dynamic>{
            'precomputedBootstrap': <String, dynamic>{
              'sessionId':
                  'phase_one_followup_answer_repair_with_execution_owner',
              'latestUserQuery': '如果我只有4天，优先哪条路线？',
              'historySummary': '上一轮刚讨论过九寨沟多条备选路线。',
              'previousIntentGraph': previousIntentGraph.toJson(),
              'previousAnswerSummary': '上轮推荐了九寨沟方向三条路线。',
              'contextContinuityPolicy': const ContextContinuityPolicy(
                continuityMode: ContextContinuityMode.explicitFollowUp,
                explicitContinuation: true,
                referenceQueries: <String>['给九寨沟行程做备选路线'],
              ).toJson(),
              'continuityOverrideSlots': const <String, dynamic>{
                'durationDays': 4,
              },
            },
            'precomputedIntentGraph': const IntentGraph(
              userGoal: '4天优先哪条路线',
              problemShape: ProblemShape.singleSkill,
              primarySkill: '',
              problemClass: ProblemClass.simpleQa,
              answerShape: AnswerShape.directAnswer,
              requiresExternalEvidence: false,
              entityAnchors: <String>['九寨沟'],
              contextSlots: <String, dynamic>{
                'destination': '九寨沟',
                'continuity': <String, dynamic>{'mode': 'explicit_follow_up'},
                'overrideSlots': <String, dynamic>{'durationDays': 4},
              },
            ).toJson(),
            'precomputedExecutionPreparation': prepared.toJson(),
          },
        );

        final snapshot = await loop.executeBridge(
          request,
          runId: 'run_phase_one_followup_answer_repair_with_execution_owner',
          traceId: 'trace_phase_one_followup_answer_repair_with_execution_owner',
        );
        final phaseOneResult =
            snapshot['phaseOneResult'] as ReactRuntimeResult;
        snapshot['phaseOneResult'] = ReactRuntimeResult(
          finalText: phaseOneResult.finalText,
          traces: <AssistantTraceEvent>[
            ...phaseOneResult.traces,
            AssistantTraceEvent(
              type: AssistantTraceEventType.searchCompleted,
              message: 'follow-up evidence checked',
              timestamp: DateTime.now(),
              data: const <String, dynamic>{
                'references': <Map<String, dynamic>>[
                  <String, dynamic>{
                    'title': '九寨沟景区公告',
                    'url': 'https://example.com/jiuzhaigou',
                    'source': '官方',
                  },
                ],
              },
            ),
          ],
          degraded: phaseOneResult.degraded,
          failureCode: phaseOneResult.failureCode,
        );

        final result = await SynthesisPhase(loop).run(
          PhaseInput(
            request: request,
            state: AgentExecutionState(executionBridgeSnapshot: snapshot),
            runId: 'run_phase_one_followup_answer_repair_with_execution_owner',
            traceId:
                'trace_phase_one_followup_answer_repair_with_execution_owner',
          ),
        );

        final diagnostics =
            result
                    .state!
                    .pendingResponse!
                    .structuredResponse['phaseOneRoutingDiagnostics']
                as Map<String, dynamic>;
        expect(
          result.state!.synthesisDraft!.templateVersionUsed,
          'phase_one_direct_answer',
        );
        expect(llm.phaseOneCallCount, 1);
        expect(llm.repairCallCount, 1);
        expect(llm.synthesisCallCount, 0);
        expect(
          result.state!.pendingResponse!.displayPlainText,
          contains('九寨沟'),
        );
        expect(diagnostics['route'], 'phase_one_direct_answer');
        expect(diagnostics['phaseOneExecutionSignalsPresent'], isTrue);
        expect(diagnostics['phaseOneContinuationCarryover'], isTrue);
        expect(diagnostics['allowPhaseOneContractRepair'], isTrue);
        expect(diagnostics['phaseOneRecoveryApplied'], isFalse);
        expect(diagnostics['phaseOneModelRepairApplied'], isTrue);
      },
    );

    test(
      'synthesis phase 应允许 direct-answer shortcut 覆盖 derived secondary-skill subagent fallback',
      () async {
        final tempDir = await Directory.systemTemp.createTemp(
          'assistant_phase_one_secondary_skill_repair_',
        );
        addTearDown(() async {
          if (await tempDir.exists()) {
            await tempDir.delete(recursive: true);
          }
        });
        final llm = _PhaseOneDerivedSecondarySkillRepairLlm();
        final loop = phase_owner.LocalPhaseExecutionOwner(
          ReactRuntime(llmProvider: llm, toolRegistry: AssistantToolRegistry()),
          sessionManager: AssistantSessionManager(
            storagePath: '${tempDir.path}/sessions.json',
          ),
          memoryRepository: AssistantMemoryRepository(
            ObjectBoxVectorStore(storagePath: '${tempDir.path}/memory.json'),
          ),
        );
        final fallbackDomainId = AssistantDomainRouter().fallbackDomainId;
        final prepared = AssistantExecutionPreparation(
          domainId: fallbackDomainId,
          modeDecision: const ModeDecision(
            mode: AgentMode.singleAgent,
            reason: 'phase_one_secondary_skill_repair_test',
          ),
          skillName: 'Travel Follow-up Answer',
          skillInstructionMarkdown: '如果本轮信息已经够答，就直接给最终答复。',
          executionShell: const SkillExecutionShell(
            problemClass: 'simple_qa',
            maxIterations: 1,
            toolBudget: 0,
            variantBudget: 0,
            reflectionBudget: 0,
            freshnessHoursMax: 72,
          ),
          plannerTemplateVersion: 'secondary_skill_repair_planner_v1',
          postcheckTemplateVersion: 'secondary_skill_repair_postcheck_v1',
          synthTemplateVersion: 'secondary_skill_repair_synth_v1',
          fusionSynthTemplateVersion: 'secondary_skill_repair_fusion_v1',
        );
        final request = AssistantRunRequest(
          sessionId: 'phase_one_secondary_skill_repair_owner',
          messages: const <AssistantRunMessage>[
            AssistantRunMessage(role: 'user', content: '如果我只有4天，优先哪条路线？'),
          ],
          contextScopeHint: <String, dynamic>{
            'precomputedIntentGraph': const IntentGraph(
              userGoal: '4天优先哪条路线',
              problemShape: ProblemShape.singleSkill,
              primarySkill: 'travel',
              problemClass: ProblemClass.simpleQa,
              answerShape: AnswerShape.directAnswer,
              requiresExternalEvidence: false,
              secondarySkills: <String>['travel_transport'],
              entityAnchors: <String>['九寨沟'],
              contextSlots: <String, dynamic>{
                'destination': '九寨沟',
                'durationDays': 4,
              },
            ).toJson(),
            'precomputedExecutionPreparation': prepared.toJson(),
          },
        );

        final snapshot = await loop.executeBridge(
          request,
          runId: 'run_phase_one_secondary_skill_repair_owner',
          traceId: 'trace_phase_one_secondary_skill_repair_owner',
        );

        final result = await SynthesisPhase(loop).run(
          PhaseInput(
            request: request,
            state: AgentExecutionState(executionBridgeSnapshot: snapshot),
            runId: 'run_phase_one_secondary_skill_repair_owner',
            traceId: 'trace_phase_one_secondary_skill_repair_owner',
          ),
        );

        final diagnostics =
            result
                    .state!
                    .pendingResponse!
                    .structuredResponse['phaseOneRoutingDiagnostics']
                as Map<String, dynamic>;
        expect(
          result.state!.synthesisDraft!.templateVersionUsed,
          'phase_one_direct_answer',
        );
        expect(llm.phaseOneCallCount, 1);
        expect(llm.repairCallCount, 0);
        expect(llm.subagentCallCount, 0);
        expect(llm.synthesisCallCount, 0);
        expect(result.state!.pendingResponse!.displayPlainText, contains('4天'));
        expect(diagnostics['route'], 'phase_one_direct_answer');
        expect(diagnostics['phaseOneDerivedSkillRunPlanCount'], 1);
        expect(diagnostics['phaseOneSkillRunPlanCount'], 0);
        expect(diagnostics['phaseOneSkillRunPlanSource'], 'none');
        expect(diagnostics['phaseOneRecoveryApplied'], isTrue);
        expect(diagnostics['phaseOneModelRepairApplied'], isFalse);
      },
    );

    test('synthesis phase 应兼容无待执行动作的 progress/tool_call 成答', () async {
      final tempDir = await Directory.systemTemp.createTemp(
        'assistant_phase_one_progress_answer_',
      );
      addTearDown(() async {
        if (await tempDir.exists()) {
          await tempDir.delete(recursive: true);
        }
      });
      final llm = _PhaseOneProgressAnswerLlm();
      final loop = phase_owner.LocalPhaseExecutionOwner(
        ReactRuntime(llmProvider: llm, toolRegistry: AssistantToolRegistry()),
        sessionManager: AssistantSessionManager(
          storagePath: '${tempDir.path}/sessions.json',
        ),
        memoryRepository: AssistantMemoryRepository(
          ObjectBoxVectorStore(storagePath: '${tempDir.path}/memory.json'),
        ),
      );
      final fallbackDomainId = AssistantDomainRouter().fallbackDomainId;
      final prepared = AssistantExecutionPreparation(
        domainId: fallbackDomainId,
        modeDecision: const ModeDecision(
          mode: AgentMode.singleAgent,
          reason: 'phase_one_progress_answer_compat_test',
        ),
        skillName: 'General Direct Answer',
        skillInstructionMarkdown: '若本轮已能直接回答，就直接给出最终答复。',
        executionShell: const SkillExecutionShell(
          problemClass: 'simple_qa',
          maxIterations: 1,
          toolBudget: 0,
          variantBudget: 0,
          reflectionBudget: 0,
          freshnessHoursMax: 720,
        ),
        plannerTemplateVersion: 'progress_answer_planner_v1',
        postcheckTemplateVersion: 'progress_answer_postcheck_v1',
        synthTemplateVersion: 'progress_answer_synth_v1',
        fusionSynthTemplateVersion: 'progress_answer_fusion_v1',
      );
      final request = AssistantRunRequest(
        sessionId: 'phase_one_progress_answer_owner',
        messages: const <AssistantRunMessage>[
          AssistantRunMessage(role: 'user', content: '一句话说明惯性'),
        ],
        contextScopeHint: <String, dynamic>{
          'precomputedIntentGraph': const IntentGraph(
            userGoal: '一句话说明惯性',
            problemShape: ProblemShape.singleSkill,
            primarySkill: '',
            problemClass: ProblemClass.simpleQa,
            answerShape: AnswerShape.directAnswer,
            requiresExternalEvidence: false,
            entityAnchors: <String>['惯性'],
          ).toJson(),
          'precomputedExecutionPreparation': prepared.toJson(),
        },
      );

      final snapshot = await loop.executeBridge(
        request,
        runId: 'run_phase_one_progress_answer_owner',
        traceId: 'trace_phase_one_progress_answer_owner',
      );

      final result = await SynthesisPhase(loop).run(
        PhaseInput(
          request: request,
          state: AgentExecutionState(executionBridgeSnapshot: snapshot),
          runId: 'run_phase_one_progress_answer_owner',
          traceId: 'trace_phase_one_progress_answer_owner',
        ),
      );

      expect(
        result.state!.synthesisDraft!.templateVersionUsed,
        'phase_one_direct_answer',
      );
      expect(llm.phaseOneCallCount, 1);
      expect(llm.synthesisCallCount, 0);
      final diagnostics =
          result
                  .state!
                  .pendingResponse!
                  .structuredResponse['phaseOneRoutingDiagnostics']
              as Map<String, dynamic>;
      expect(
        diagnostics['rawDirectAnswerReason'],
        'phase_one_compat_direct_answer',
      );
      expect(
        diagnostics['directAnswerReason'],
        'phase_one_compat_direct_answer',
      );
      expect(result.state!.pendingResponse!.displayPlainText, contains('惯性'));
    });

    test(
      'synthesis phase 应忽略同域 tentative subagent plan 并继续 direct answer',
      () async {
        final tempDir = await Directory.systemTemp.createTemp(
          'assistant_phase_one_tentative_subagent_',
        );
        addTearDown(() async {
          if (await tempDir.exists()) {
            await tempDir.delete(recursive: true);
          }
        });
        final llm = _PhaseOneTentativeSubagentPlanLlm();
        final loop = phase_owner.LocalPhaseExecutionOwner(
          ReactRuntime(llmProvider: llm, toolRegistry: AssistantToolRegistry()),
          sessionManager: AssistantSessionManager(
            storagePath: '${tempDir.path}/sessions.json',
          ),
          memoryRepository: AssistantMemoryRepository(
            ObjectBoxVectorStore(storagePath: '${tempDir.path}/memory.json'),
          ),
        );
        final fallbackDomainId = AssistantDomainRouter().fallbackDomainId;
        final prepared = AssistantExecutionPreparation(
          domainId: fallbackDomainId,
          modeDecision: const ModeDecision(
            mode: AgentMode.singleAgent,
            reason: 'tentative_subagent_should_not_block_direct_answer',
          ),
          skillName: 'General Direct Answer',
          skillInstructionMarkdown: '若已能直接回答，就直接回答。',
          executionShell: const SkillExecutionShell(
            problemClass: 'simple_qa',
            maxIterations: 1,
            toolBudget: 0,
            variantBudget: 0,
            reflectionBudget: 0,
            freshnessHoursMax: 720,
          ),
          plannerTemplateVersion: 'tentative_planner_v1',
          postcheckTemplateVersion: 'tentative_postcheck_v1',
          synthTemplateVersion: 'tentative_synth_v1',
          fusionSynthTemplateVersion: 'tentative_fusion_v1',
        );
        final request = AssistantRunRequest(
          sessionId: 'phase_one_tentative_subagent_owner',
          messages: const <AssistantRunMessage>[
            AssistantRunMessage(role: 'user', content: '一句话说明惯性'),
          ],
          contextScopeHint: <String, dynamic>{
            'precomputedIntentGraph': const IntentGraph(
              userGoal: '一句话说明惯性',
              problemShape: ProblemShape.singleSkill,
              primarySkill: '',
              problemClass: ProblemClass.simpleQa,
              answerShape: AnswerShape.directAnswer,
              requiresExternalEvidence: false,
            ).toJson(),
            'precomputedExecutionPreparation': prepared.toJson(),
          },
        );

        final snapshot = await loop.executeBridge(
          request,
          runId: 'run_phase_one_tentative_subagent_owner',
          traceId: 'trace_phase_one_tentative_subagent_owner',
        );

        final result = await SynthesisPhase(loop).run(
          PhaseInput(
            request: request,
            state: AgentExecutionState(executionBridgeSnapshot: snapshot),
            runId: 'run_phase_one_tentative_subagent_owner',
            traceId: 'trace_phase_one_tentative_subagent_owner',
          ),
        );

        expect(
          result.state!.synthesisDraft!.templateVersionUsed,
          'phase_one_direct_answer',
        );
        expect(llm.phaseOneCallCount, 1);
        expect(llm.subagentCallCount, 0);
        expect(llm.synthesisCallCount, 0);
        expect(result.state!.pendingResponse!.displayPlainText, contains('惯性'));
        final uiUsageStats =
            result.state!.pendingResponse!.structuredResponse['uiUsageStats']
                as Map<String, dynamic>;
        expect(uiUsageStats['modelCallCount'], 1);
      },
    );

    test(
      'synthesis phase 在存在真实 subagent plan 时应跳过 pre-fusion synthesis',
      () async {
        final tempDir = await Directory.systemTemp.createTemp(
          'assistant_phase_one_subagent_owner_',
        );
        addTearDown(() async {
          if (await tempDir.exists()) {
            await tempDir.delete(recursive: true);
          }
        });
        final llm = _PhaseOneSubagentFusionLlm();
        final loop = phase_owner.LocalPhaseExecutionOwner(
          ReactRuntime(llmProvider: llm, toolRegistry: AssistantToolRegistry()),
          sessionManager: AssistantSessionManager(
            storagePath: '${tempDir.path}/sessions.json',
          ),
          memoryRepository: AssistantMemoryRepository(
            ObjectBoxVectorStore(storagePath: '${tempDir.path}/memory.json'),
          ),
        );
        const request = AssistantRunRequest(
          sessionId: 'phase_one_subagent_owner',
          messages: <AssistantRunMessage>[
            AssistantRunMessage(role: 'user', content: '帮我同时比较路线和住宿取舍'),
          ],
          contextScopeHint: <String, dynamic>{
            'precomputedIntentGraph': <String, dynamic>{
              'userGoal': '比较路线和住宿取舍',
              'problemShape': 'single_skill',
              'primarySkill': 'travel',
              'problemClass': 'complex_reasoning',
              'answerShape': 'options',
              'requiresExternalEvidence': false,
            },
            'precomputedExecutionPreparation': <String, dynamic>{
              'domainId': 'travel',
              'modeDecision': <String, dynamic>{
                'mode': 'singleAgent',
                'reason': 'phase_one_subagent_plan_owner_test',
                'subagentCount': 1,
                'budgetMultiplier': 1.0,
              },
              'skillName': 'Travel Planner',
              'skillInstructionMarkdown': '先给主答，再按需要拆子任务。',
              'skillPersona': '',
              'allowedToolNames': <String>[],
              'executionShell': <String, dynamic>{
                'problemClass': 'complex_reasoning',
                'maxIterations': 2,
                'toolBudget': 0,
                'variantBudget': 0,
                'reflectionBudget': 0,
                'freshnessHoursMax': 72,
              },
              'plannerTemplateVersion': 'subagent_owner_planner_v1',
              'postcheckTemplateVersion': 'subagent_owner_postcheck_v1',
              'synthTemplateVersion': 'subagent_owner_synth_v1',
              'fusionSynthTemplateVersion': 'subagent_owner_fusion_v1',
              'previousSlotState': <String, dynamic>{},
            },
          },
        );

        final snapshot = await loop.executeBridge(
          request,
          runId: 'run_phase_one_subagent_owner',
          traceId: 'trace_phase_one_subagent_owner',
        );

        final result = await SynthesisPhase(loop).run(
          PhaseInput(
            request: request,
            state: AgentExecutionState(executionBridgeSnapshot: snapshot),
            runId: 'run_phase_one_subagent_owner',
            traceId: 'trace_phase_one_subagent_owner',
          ),
        );

        expect(result.state!.synthesisDraft, isNotNull);
        expect(
          result.state!.synthesisDraft!.templateVersionUsed,
          'subagent_owner_synth_v1',
        );
        expect(llm.phaseOneCallCount, 1);
        expect(llm.subagentCallCount, 1);
        expect(llm.synthesisCallCount, 1);
        expect(
          result.state!.pendingResponse!.displayMarkdown,
          contains('路线优先'),
        );
        final uiUsageStats =
            result.state!.pendingResponse!.structuredResponse['uiUsageStats']
                as Map<String, dynamic>;
        expect(uiUsageStats['modelCallCount'], 3);
      },
    );

    test('synthesis phase 应优先消费 typed answer outcome snapshot', () async {
      final tempDir = await Directory.systemTemp.createTemp(
        'assistant_synthesis_answer_outcome_',
      );
      addTearDown(() async {
        if (await tempDir.exists()) {
          await tempDir.delete(recursive: true);
        }
      });
      final phase = SynthesisPhase(
        phase_owner.LocalPhaseExecutionOwner(
          ReactRuntime(
            llmProvider: const HeuristicLocalLlmProvider(),
            toolRegistry: AssistantToolRegistry(),
          ),
          sessionManager: AssistantSessionManager(
            storagePath: '${tempDir.path}/sessions.json',
          ),
          memoryRepository: AssistantMemoryRepository(
            ObjectBoxVectorStore(storagePath: '${tempDir.path}/memory.json'),
          ),
        ),
      );
      const slotState = SlotStateSnapshot(
        domainId: 'travel',
        slotValues: <String, SlotValueSnapshot>{
          'destination': SlotValueSnapshot(
            slotId: 'destination',
            status: SlotValueStatus.confirmed,
            value: '九寨沟',
            source: 'answer_outcome',
            evidenceIds: <String>['ev_jzg_1'],
          ),
        },
        missingSlots: <String>[],
      );
      const evidenceEntry = EvidenceLedgerEntry(
        evidenceId: 'ev_jzg_1',
        domainId: 'travel',
        dimension: 'candidate_options',
        dimensionLabel: '备选方案',
        queryTaskId: 'route_candidates',
        title: '九寨沟经典路线建议',
        url: 'https://example.com/jzg',
        source: '示例旅行站',
        sourceHost: 'example.com',
        sourceTier: 'authority',
        freshnessHours: 12,
        authorityScore: 0.92,
        relevanceScore: 0.95,
        slotContributions: <String, dynamic>{'destination': '九寨沟'},
        snippet: '4天九寨沟经典路线建议。',
        retrievedAt: '2026-03-16T00:00:00.000Z',
      );
      const evidenceBinding = AnswerEvidenceBinding(
        bindingId: 'bind_jzg_1',
        label: '来源1',
        claim: '4天优先经典路线',
        evidenceId: 'ev_jzg_1',
        url: 'https://example.com/jzg',
        title: '九寨沟经典路线建议',
        source: '示例旅行站',
        snippet: '4天九寨沟经典路线建议。',
      );
      final answerOutcome = AnswerOutcomeSnapshot(
        slotState: slotState,
        evidenceLedger: const <EvidenceLedgerEntry>[evidenceEntry],
        answerEvidenceBindings: const <AnswerEvidenceBinding>[evidenceBinding],
        evidenceEvaluation: const EvidenceEvaluationResult(
          entries: <EvidenceLedgerEntry>[evidenceEntry],
          coverageScore: 0.9,
          authorityScore: 0.92,
          relevanceScore: 0.95,
          freshnessHours: 12,
          status: EvidenceStatus.full,
          passed: true,
          authoritySatisfied: true,
          freshnessSatisfied: true,
          evidenceRequired: true,
          coveredDimensions: <String>['candidate_options'],
          coveredQueryTaskIds: <String>['route_candidates'],
          summary: '证据已经足够支持最终答复。',
        ),
        aggregationState: const AggregationState(
          allSkillsReady: true,
          canGivePartialAnswer: false,
          finalAnswerReady: true,
          finalAnswerMode: FinalAnswerMode.full,
          answerOwner: 'travel_primary',
        ),
        synthesisReadiness: const SynthesisReadinessResult(
          ready: true,
          reason: 'typed_answer_outcome_ready',
        ),
        conversationStateDecision: const ConversationStateDecision(
          nextAction: AssistantNextAction.answer,
          finalAnswerMode: FinalAnswerMode.full,
          answerEligibility: AnswerEligibility.eligible,
          slotState: slotState,
          missingCriticalSlots: <String>[],
          askUser: AssistantTurnAskUser(),
          qualityGates: QualityGatesDto(
            structureSafe: true,
            taskSafe: true,
            evidenceSafe: true,
            renderSafe: true,
          ),
          finalAnswerReady: true,
        ),
        domainPolicyBundle: const DomainPolicyBundle(
          domainId: 'travel',
          retrievalPolicy: <String, dynamic>{
            'authorityDomains': <String>['example.com'],
          },
        ),
        journey: const AssistantJourney(
          stages: <AssistantJourneyStage>[
            AssistantJourneyStage(
              stageId: JourneyStageId.answer,
              status: JourneyStageStatus.completed,
              order: 3,
              summary: '答案已准备好',
            ),
          ],
          entries: <AssistantJourneyEntry>[
            AssistantJourneyEntry(
              entryId: 'journey.answer.ready',
              stageId: JourneyStageId.answer,
              kind: JourneyEntryKind.narrative,
              status: JourneyStageStatus.completed,
              order: 0,
              headline: '答案已准备好',
              detail: '正在整理答案',
            ),
          ],
        ),
      );
      final pendingResponse = AssistantRunResponse(
        finalText: '最终答案',
        traces: const [],
        structuredResponse: <String, dynamic>{
          'answerOutcome': answerOutcome.toJson(),
          'aggregationState': const <String, dynamic>{
            'finalAnswerReady': false,
            'finalAnswerMode': 'retry',
          },
          'synthesisReadiness': const <String, dynamic>{
            'ready': false,
            'reason': 'legacy_fallback_should_not_win',
          },
          'conversationStateDecision': const <String, dynamic>{
            'nextAction': 'retry',
            'finalAnswerMode': 'retry',
            'answerEligibility': 'blocked',
            'missingCriticalSlots': <String>['date'],
            'finalAnswerReady': false,
          },
        },
      );

      final result = await phase.run(
        PhaseInput(
          request: const AssistantRunRequest(
            messages: <AssistantRunMessage>[
              AssistantRunMessage(role: 'user', content: '如果我只有4天，优先哪条路线？'),
            ],
          ),
          state: AgentExecutionState(
            pendingResponse: pendingResponse,
            synthesisReadiness: const SynthesisReadinessResult(
              ready: false,
              reason: 'fallback_state',
            ),
          ),
          runId: 'run_answer_outcome_snapshot',
          traceId: 'trace_answer_outcome_snapshot',
        ),
      );

      expect(result.state!.slotState?.domainId, 'travel');
      expect(
        result.state!.slotState?.slotValueOf('destination')?.evidenceIds,
        <String>['ev_jzg_1'],
      );
      expect(result.state!.evidenceLedger, hasLength(1));
      expect(result.state!.answerEvidenceBindings, hasLength(1));
      expect(result.state!.evidenceEvaluation?.passed, isTrue);
      expect(result.state!.aggregationState?.finalAnswerReady, isTrue);
      expect(
        result.state!.conversationStateDecision?.nextActionType,
        AssistantNextAction.answer,
      );
      expect(result.state!.synthesisReadiness?.ready, isTrue);
      expect(
        result.state!.synthesisReadiness?.reason,
        'typed_answer_outcome_ready',
      );
      expect(result.state!.domainPolicyBundle?.domainId, 'travel');
      expect(result.state!.journey.entries, hasLength(1));
      expect(result.state!.journey.entries.single.detail, '正在整理答案');
    });

    test('execute bridge 应优先消费 typed execution preparation 输入', () async {
      final tempDir = await Directory.systemTemp.createTemp(
        'assistant_execution_preparation_owner_',
      );
      addTearDown(() async {
        if (await tempDir.exists()) {
          await tempDir.delete(recursive: true);
        }
      });
      final toolRegistry = AssistantToolRegistry()
        ..register(_SynthesisDraftWeatherSearchTool());
      final loop = phase_owner.LocalPhaseExecutionOwner(
        ReactRuntime(
          llmProvider: _SynthesisDraftWeatherLlm(),
          toolRegistry: toolRegistry,
        ),
        sessionManager: AssistantSessionManager(
          storagePath: '${tempDir.path}/sessions.json',
        ),
        memoryRepository: AssistantMemoryRepository(
          ObjectBoxVectorStore(storagePath: '${tempDir.path}/memory.json'),
        ),
      );
      const intentGraph = IntentGraph(
        userGoal: '查询深圳天气',
        problemShape: ProblemShape.singleSkill,
        primarySkill: 'weather',
        problemClass: ProblemClass.realtimeInfo,
        answerShape: AnswerShape.directAnswer,
        freshnessNeed: FreshnessNeed.recent,
        requiresExternalEvidence: true,
        authorityDomains: <String>['cma.cn'],
        freshnessHoursMax: 6,
      );
      final prepared = AssistantExecutionPreparation(
        domainId: 'weather',
        modeDecision: const ModeDecision(
          mode: AgentMode.singleAgent,
          reason: 'typed_owner_test',
        ),
        skillName: 'Typed Owner Skill',
        skillInstructionMarkdown: '## typed owner instruction',
        skillPersona: '## persona\ntyped',
        allowedToolNames: const <String>['web_search'],
        executionShell: const SkillExecutionShell(
          problemClass: 'realtime_info',
          maxIterations: 2,
          toolBudget: 1,
          variantBudget: 0,
          reflectionBudget: 0,
          freshnessHoursMax: 6,
        ),
        plannerTemplateVersion: 'typed_planner_v1',
        postcheckTemplateVersion: 'typed_postcheck_v1',
        synthTemplateVersion: 'typed_synth_v1',
        fusionSynthTemplateVersion: 'typed_fusion_v1',
        previousSlotState: const SlotStateSnapshot(
          domainId: 'weather',
          slotValues: <String, SlotValueSnapshot>{
            'city': SlotValueSnapshot(
              slotId: 'city',
              status: SlotValueStatus.confirmed,
              value: '深圳',
              source: 'typed_owner',
            ),
          },
          missingSlots: <String>[],
        ),
      );
      final request = AssistantRunRequest(
        sessionId: 'typed_execution_preparation_owner',
        messages: const <AssistantRunMessage>[
          AssistantRunMessage(role: 'user', content: '深圳天气怎么样'),
        ],
        contextScopeHint: <String, dynamic>{
          'precomputedIntentGraph': intentGraph.toJson(),
          'precomputedExecutionPreparation': prepared.toJson(),
        },
      );

      final snapshot = await loop.executeBridge(
        request,
        runId: 'run_typed_execution_preparation_owner',
        traceId: 'trace_typed_execution_preparation_owner',
      );

      expect(snapshot['shortCircuitResponse'], isNull);
      expect(snapshot['domainId'], 'weather');
      expect(snapshot['synthTemplateVersion'], 'typed_synth_v1');
      expect(
        (snapshot['executionShell'] as SkillExecutionShell).problemClass,
        'realtime_info',
      );
      expect(
        (snapshot['previousSlotState'] as SlotStateSnapshot)
            .slotValueOf('city')
            ?.value,
        '深圳',
      );
      expect(
        (snapshot['templateVariables']
            as Map<String, dynamic>)['domainSkillName'],
        'Typed Owner Skill',
      );
      expect(
        (snapshot['templateVariables']
            as Map<String, dynamic>)['domainSkillInstruction'],
        contains('typed owner instruction'),
      );
      expect(
        (snapshot['templateVariables']
            as Map<String, dynamic>)['availableTools'],
        <String>['web_search'],
      );
    });

    test('finalize phase 应返回 pendingResponse', () async {
      final tempDir = await Directory.systemTemp.createTemp(
        'assistant_finalize_phase_',
      );
      addTearDown(() async {
        if (await tempDir.exists()) {
          await tempDir.delete(recursive: true);
        }
      });
      final phase = FinalizePhase(
        phase_owner.LocalPhaseExecutionOwner(
          ReactRuntime(
            llmProvider: const HeuristicLocalLlmProvider(),
            toolRegistry: AssistantToolRegistry(),
          ),
          sessionManager: AssistantSessionManager(
            storagePath: '${tempDir.path}/sessions.json',
          ),
          memoryRepository: AssistantMemoryRepository(
            ObjectBoxVectorStore(storagePath: '${tempDir.path}/memory.json'),
          ),
        ),
      );
      final pendingResponse = AssistantRunResponse(
        finalText: 'final',
        traces: const [],
      );

      final result = await phase.run(
        PhaseInput(
          request: AssistantRunRequest(messages: const <AssistantRunMessage>[]),
          state: AgentExecutionState(pendingResponse: pendingResponse),
          runId: 'run_finalize',
          traceId: 'trace_finalize',
        ),
      );

      expect(result.response, isNotNull);
      expect((result.response as AssistantRunResponse).finalText, 'final');
    });

    test('phase orchestrator 应保留 finalize 输出的 response', () async {
      final orchestrator = PhaseOrchestrator(
        phases: const <Phase>[
          _StaticPhase(
            id: 'first',
            output: PhaseOutput(state: AgentExecutionState()),
          ),
          _StaticPhase(
            id: 'finalize',
            output: PhaseOutput(
              state: AgentExecutionState(),
              response: AssistantRunResponse(finalText: 'ok', traces: []),
            ),
          ),
        ],
      );

      final result = await orchestrator.run(
        const PhaseOrchestratorInput(
          request: AssistantRunRequest(messages: <AssistantRunMessage>[]),
          runId: 'run_orchestrator',
          traceId: 'trace_orchestrator',
        ),
      );

      expect(result.response, isNotNull);
      expect((result.response as AssistantRunResponse).finalText, 'ok');
    });
  });
}

class _StaticPhase implements Phase {
  const _StaticPhase({required this.id, required this.output});

  final String id;
  final PhaseOutput output;

  @override
  String get phaseId => id;

  @override
  Future<PhaseOutput> run(PhaseInput input) async => output;
}

class _RetrievalDesignPlanLlm implements AssistantLlmProvider {
  const _RetrievalDesignPlanLlm();

  @override
  Future<AssistantModelOutput> reason({
    required List<Map<String, dynamic>> messages,
    required List<String> availableTools,
    Map<String, dynamic> templateContext = const <String, dynamic>{},
    Map<String, dynamic> templateVariables = const <String, dynamic>{},
    String templateId = 'planner.global_plan',
    String templateVersion = '',
    String sessionId = '',
    String runId = '',
    String traceId = '',
    LlmCallOptions? callOptions,
    void Function(String delta)? onDelta,
  }) async {
    return AssistantModelOutput(
      text: jsonEncode(<String, dynamic>{
        'queryTasks': <Map<String, dynamic>>[
          <String, dynamic>{
            'id': 'candidate_space',
            'dimension': 'candidate_space',
            'label': '候选范围',
            'query': '深圳住宿 候选片区 酒店 民宿 公寓',
          },
          <String, dynamic>{
            'id': 'fit_scenarios',
            'dimension': 'fit_scenarios',
            'label': '适用场景',
            'query': '深圳住宿 通勤 景点 夜生活 亲子 商务 适合',
          },
          <String, dynamic>{
            'id': 'risks',
            'dimension': 'risk_boundaries',
            'label': '风险边界',
            'query': '深圳住宿 避坑 噪音 交通 拥堵 安全 风险',
          },
        ],
      }),
    );
  }
}

class _ContinuityAwareUnderstandLlm implements AssistantLlmProvider {
  const _ContinuityAwareUnderstandLlm();

  @override
  Future<AssistantModelOutput> reason({
    required List<Map<String, dynamic>> messages,
    required List<String> availableTools,
    Map<String, dynamic> templateContext = const <String, dynamic>{},
    Map<String, dynamic> templateVariables = const <String, dynamic>{},
    String templateId = 'planner.global_plan',
    String templateVersion = '',
    String sessionId = '',
    String runId = '',
    String traceId = '',
    LlmCallOptions? callOptions,
    void Function(String delta)? onDelta,
  }) async {
    return AssistantModelOutput(
      text: jsonEncode(<String, dynamic>{
        'intentGraph': <String, dynamic>{
          'userGoal': '4天优先哪条路线',
          'problemShape': 'single_skill',
          'primarySkill': '',
          'problemClass': 'complex_reasoning',
          'inferredMotive': '比较4天路线优先级',
          'answerShape': 'options',
          'requiresExternalEvidence': true,
          'contextSlots': <String, dynamic>{'durationDays': 4},
          'globalConstraints': <String, dynamic>{'mode': 'qa'},
        },
      }),
    );
  }
}

class _RootLevelIntentGraphUnderstandLlm implements AssistantLlmProvider {
  const _RootLevelIntentGraphUnderstandLlm();

  @override
  Future<AssistantModelOutput> reason({
    required List<Map<String, dynamic>> messages,
    required List<String> availableTools,
    Map<String, dynamic> templateContext = const <String, dynamic>{},
    Map<String, dynamic> templateVariables = const <String, dynamic>{},
    String templateId = 'planner.global_plan',
    String templateVersion = '',
    String sessionId = '',
    String runId = '',
    String traceId = '',
    LlmCallOptions? callOptions,
    void Function(String delta)? onDelta,
  }) async {
    return AssistantModelOutput(
      text: jsonEncode(<String, dynamic>{
        'userGoal': '判断深圳周末天气是否适合出门',
        'problemShape': 'single_skill',
        'primarySkill': 'weather',
        'problemClass': 'realtime_info',
        'inferredMotive': '判断深圳周末是否适合安排外出',
        'answerShape': 'decision_ready',
        'freshnessNeed': 'recent',
        'requiresExternalEvidence': true,
        'entityAnchors': <String>['深圳'],
        'queryNormalization': <String, dynamic>{
          'normalizedQuery': '深圳周末天气适合出门吗',
        },
        'queryTasks': <Map<String, dynamic>>[
          <String, dynamic>{
            'id': 'current_state',
            'dimension': 'current_state',
            'label': '当前天气',
            'query': '深圳 周末 天气 实况',
            'authorityDomains': <String>['weather.cma.cn'],
            'freshnessHoursMax': 1,
          },
        ],
        'contextSlots': <String, dynamic>{'city': '深圳'},
        'globalConstraints': <String, dynamic>{'mode': 'qa'},
      }),
    );
  }
}

class _ToolCallQueryTasksRetrievalDesignLlm implements AssistantLlmProvider {
  const _ToolCallQueryTasksRetrievalDesignLlm();

  @override
  Future<AssistantModelOutput> reason({
    required List<Map<String, dynamic>> messages,
    required List<String> availableTools,
    Map<String, dynamic> templateContext = const <String, dynamic>{},
    Map<String, dynamic> templateVariables = const <String, dynamic>{},
    String templateId = 'planner.global_plan',
    String templateVersion = '',
    String sessionId = '',
    String runId = '',
    String traceId = '',
    LlmCallOptions? callOptions,
    void Function(String delta)? onDelta,
  }) async {
    return AssistantModelOutput(
      text: jsonEncode(<String, dynamic>{
        'toolCalls': <Map<String, dynamic>>[
          <String, dynamic>{
            'toolName': 'web_search',
            'arguments': <String, dynamic>{
              'queryTasks': <Map<String, dynamic>>[
                <String, dynamic>{
                  'id': 'current_state',
                  'dimension': 'current_state',
                  'label': '当前状态',
                  'query': '深圳 周末 天气 实况',
                },
                <String, dynamic>{
                  'id': 'decision_threshold',
                  'dimension': 'decision_threshold',
                  'label': '出门阈值',
                  'query': '深圳 周末 天气 出门 适合 条件',
                },
              ],
            },
          },
        ],
      }),
    );
  }
}

Map<String, dynamic> _synthesisDraftIntentEnvelope() {
  return <String, dynamic>{
    'contractId': 'assistant_turn',
    'messageKind': 'progress',
    'phaseId': 'understanding',
    'actionCode': 'frame_problem',
    'reasonCode': 'align_goal',
    'reasonShort': '先聚焦用户目标，再决定如何获取资料。',
    'decision': const <String, dynamic>{
      'nextAction': 'answer',
      'confidence': 0.82,
      'reasoning': '先识别领域与问题类型',
    },
    'userMarkdown': '我先聚焦你的问题主线，再开始处理。',
    'result': const <String, dynamic>{
      'text': '',
      'summary': '进入理解阶段',
      'interpretation': '查询深圳实时天气',
    },
    'intentGraph': const <String, dynamic>{
      'userGoal': '查询深圳实时天气',
      'problemShape': 'single_skill',
      'primarySkill': 'weather',
      'problemClass': 'realtime_info',
      'inferredMotive': '查询深圳实时天气',
      'secondarySkills': <String>[],
      'contextSlots': <String, dynamic>{},
      'globalConstraints': <String, dynamic>{'mode': 'qa'},
      'clarificationNeeded': false,
    },
    'selfCheck': const <String, dynamic>{
      'goalSatisfied': true,
      'constraintSatisfied': true,
      'safetyBoundarySatisfied': true,
      'failedItems': <String>[],
    },
    'diagnostics': const <String, dynamic>{
      'emergedTags': <Map<String, dynamic>>[],
      'failedChecks': <String>[],
      'parseStatus': '',
      'notes': <String>[],
    },
  };
}

class _SynthesisDraftWeatherLlm implements AssistantLlmProvider {
  int _planCallCount = 0;

  @override
  Future<AssistantModelOutput> reason({
    required List<Map<String, dynamic>> messages,
    required List<String> availableTools,
    Map<String, dynamic> templateContext = const <String, dynamic>{},
    Map<String, dynamic> templateVariables = const <String, dynamic>{},
    String templateId = 'planner.global_plan',
    String templateVersion = '',
    String sessionId = '',
    String runId = '',
    String traceId = '',
    LlmCallOptions? callOptions,
    void Function(String delta)? onDelta,
  }) async {
    final isPlannerCall = templateId == 'planner.global_plan';
    final isSynthesisCall = _isFinalAnswerTemplate(templateId);
    final isIntentStage =
        templateId == 'planner.global_plan' && availableTools.isEmpty;

    if (!isPlannerCall && !isSynthesisCall) {
      return const AssistantModelOutput(text: '{"summary":"用户在查询深圳天气"}');
    }

    if (isIntentStage) {
      return AssistantModelOutput(
        text: jsonEncode(_synthesisDraftIntentEnvelope()),
      );
    }

    if (isPlannerCall) {
      _planCallCount += 1;
      if (_planCallCount == 1 && availableTools.contains('web_search')) {
        onDelta?.call('我先核对深圳今天的最新天气。');
        return AssistantModelOutput(
          text: jsonEncode(<String, dynamic>{
            'contractId': 'assistant_turn',
            'decision': <String, dynamic>{'nextAction': 'tool_call'},
            'toolCalls': const <Map<String, dynamic>>[
              <String, dynamic>{
                'toolName': 'web_search',
                'arguments': <String, dynamic>{
                  'query': '深圳天气实时数据',
                  'freshnessHoursMax': 6,
                  'provider': 'baidu',
                },
              },
            ],
            'reasonShort': '需要先查最新天气实况。',
          }),
          toolCalls: const <AssistantToolCall>[
            AssistantToolCall(
              name: 'web_search',
              arguments: <String, dynamic>{
                'query': '深圳天气实时数据',
                'freshnessHoursMax': 6,
                'provider': 'baidu',
              },
            ),
          ],
        );
      }
    }

    onDelta?.call('资料已经齐了，我来整理成最终答案。');
    return AssistantModelOutput(
      text: jsonEncode(<String, dynamic>{
        'contractId': 'assistant_turn',
        'decision': <String, dynamic>{'nextAction': 'answer'},
        'messageKind': 'answer',
        'userMarkdown': '## 深圳天气\n\n今天深圳天气晴朗，温度约25°C，适合轻装出门。',
        'result': const <String, dynamic>{
          'text': '今天深圳天气晴朗，温度约25°C。',
          'interpretation': '深圳当前天气概况',
        },
        'evidence': const <Map<String, dynamic>>[
          <String, dynamic>{
            'claim': '温度约25°C',
            'source': 'web_search',
            'confidence': 'high',
          },
        ],
        'reasoningBasis': const <Map<String, dynamic>>[],
        'selfCheck': const <String, dynamic>{
          'goalSatisfied': true,
          'constraintSatisfied': true,
          'safetyBoundarySatisfied': true,
          'failedItems': <String>[],
        },
        'diagnostics': const <String, dynamic>{
          'emergedTags': <Map<String, dynamic>>[],
          'failedChecks': <String>[],
          'parseStatus': '',
          'notes': <String>['资料已经齐了，我来整理成最终答案。'],
        },
        'modelSelfScore': const <String, dynamic>{
          'score': 94,
          'reason': '准确回答天气问题',
        },
        'toolCalls': const <dynamic>[],
      }),
    );
  }
}

class _PhaseOneDirectAnswerLlm implements AssistantLlmProvider {
  int phaseOneCallCount = 0;
  int synthesisCallCount = 0;

  @override
  Future<AssistantModelOutput> reason({
    required List<Map<String, dynamic>> messages,
    required List<String> availableTools,
    Map<String, dynamic> templateContext = const <String, dynamic>{},
    Map<String, dynamic> templateVariables = const <String, dynamic>{},
    String templateId = 'planner.global_plan',
    String templateVersion = '',
    String sessionId = '',
    String runId = '',
    String traceId = '',
    LlmCallOptions? callOptions,
    void Function(String delta)? onDelta,
  }) async {
    final isSynthesisCall = _isFinalAnswerTemplate(templateId);
    if (isSynthesisCall) {
      synthesisCallCount += 1;
      throw StateError('phase-one direct answer path should skip synthesis');
    }
    phaseOneCallCount += 1;
    onDelta?.call('这一问可以直接成答，我直接给出最终结论。');
    return AssistantModelOutput(
      text: jsonEncode(<String, dynamic>{
        'contractId': 'assistant_turn',
        'decision': const <String, dynamic>{'nextAction': 'answer'},
        'phaseId': 'answering',
        'actionCode': 'compose_answer',
        'reasonCode': 'evidence_ready',
        'userMarkdown': '牛顿第一定律：若不受外力作用，物体会保持静止或匀速直线运动。',
        'result': const <String, dynamic>{
          'text': '牛顿第一定律说明物体在不受外力时会保持原有运动状态。',
          'interpretation': '一句话解释牛顿第一定律',
        },
        'selfCheck': const <String, dynamic>{
          'goalSatisfied': true,
          'constraintSatisfied': true,
          'safetyBoundarySatisfied': true,
          'failedItems': <String>[],
        },
        'diagnostics': const <String, dynamic>{
          'emergedTags': <Map<String, dynamic>>[],
          'failedChecks': <String>[],
          'parseStatus': '',
          'notes': <String>['phase one direct answer'],
        },
        'modelSelfScore': const <String, dynamic>{
          'score': 96,
          'reason': 'simple_qa_direct_answer',
        },
      }),
    );
  }
}

class _PhaseOneGapFillThenDirectAnswerLlm implements AssistantLlmProvider {
  int initialPlannerCallCount = 0;
  int postcheckToolCallCount = 0;
  int postcheckAnswerCallCount = 0;
  int synthesisCallCount = 0;

  @override
  Future<AssistantModelOutput> reason({
    required List<Map<String, dynamic>> messages,
    required List<String> availableTools,
    Map<String, dynamic> templateContext = const <String, dynamic>{},
    Map<String, dynamic> templateVariables = const <String, dynamic>{},
    String templateId = 'planner.global_plan',
    String templateVersion = '',
    String sessionId = '',
    String runId = '',
    String traceId = '',
    LlmCallOptions? callOptions,
    void Function(String delta)? onDelta,
  }) async {
    final isSynthesisCall = _isFinalAnswerTemplate(templateId);
    if (isSynthesisCall) {
      synthesisCallCount += 1;
      throw StateError('gap-fill direct-answer path should skip synthesis');
    }

    if (templateId == 'planner.global_plan' && initialPlannerCallCount > 0) {
      if (postcheckToolCallCount == 0) {
        postcheckToolCallCount += 1;
        onDelta?.call('我补一条实时天气证据，再直接整理答案。');
        return AssistantModelOutput(
          text: jsonEncode(<String, dynamic>{
            'contractId': 'assistant_turn',
            'messageKind': 'progress',
            'phaseId': 'understanding',
            'actionCode': 'frame_problem',
            'reasonCode': 'align_goal',
            'reasonShort': '还差一条实时证据，我先补齐。',
            'decision': const <String, dynamic>{'nextAction': 'tool_call'},
            'toolCalls': const <Map<String, dynamic>>[
              <String, dynamic>{
                'toolName': 'web_search',
                'arguments': <String, dynamic>{
                  'query': '深圳 实时 天气 中国气象局',
                  'freshnessHoursMax': 6,
                },
              },
            ],
          }),
          toolCalls: const <AssistantToolCall>[
            AssistantToolCall(
              name: 'web_search',
              arguments: <String, dynamic>{
                'query': '深圳 实时 天气 中国气象局',
                'freshnessHoursMax': 6,
              },
            ),
          ],
        );
      }
      postcheckAnswerCallCount += 1;
      onDelta?.call('证据补齐，现在可以直接成答。');
      return AssistantModelOutput(
        text: jsonEncode(<String, dynamic>{
          'contractId': 'assistant_turn',
          'messageKind': 'answer',
          'phaseId': 'answering',
          'actionCode': 'compose_answer',
          'reasonCode': 'evidence_ready',
          'reasonShort': '实时证据已经补齐，可以直接回答。',
          'decision': const <String, dynamic>{'nextAction': 'answer'},
          'userMarkdown':
              '## 深圳今天适合出门\n\n今天深圳天气晴朗，气温大约 25°C，适合轻装出门；如果中午时段外出，注意补水和防晒。',
          'result': const <String, dynamic>{
            'text': '今天深圳天气晴朗，约25°C，适合出门。',
            'summary': '深圳今天适合轻装出门',
            'interpretation': '天气平稳，出行阻碍较小',
          },
          'evidence': const <Map<String, dynamic>>[
            <String, dynamic>{
              'evidenceId': 'ev_sz_weather_1',
              'title': '深圳天气预报 - 中国气象局',
              'source': '中国气象局',
              'url': 'https://weather.cma.cn/shenzhen',
              'snippet': '深圳今天晴，温度25°C。',
              'claim': '今天深圳晴朗，气温约25°C',
              'text': '深圳今天晴，温度25°C。',
            },
          ],
          'reasoningBasis': const <Map<String, dynamic>>[
            <String, dynamic>{
              'evidenceId': 'ev_sz_weather_1',
              'claim': '今天深圳适合出门',
              'text': '天气晴朗且温度舒适，适合正常出行。',
              'confidence': 0.91,
            },
          ],
          'selfCheck': const <String, dynamic>{
            'goalSatisfied': true,
            'constraintSatisfied': true,
            'safetyBoundarySatisfied': true,
            'failedItems': <String>[],
          },
          'diagnostics': const <String, dynamic>{
            'emergedTags': <Map<String, dynamic>>[],
            'failedChecks': <String>[],
            'parseStatus': '',
            'notes': <String>['gap fill complete'],
          },
          'modelSelfScore': const <String, dynamic>{
            'score': 92,
            'reason': 'realtime_weather_ready',
          },
        }),
      );
    }

    initialPlannerCallCount += 1;
    onDelta?.call('我先给你当前判断，但还缺一条实时证据。');
    return AssistantModelOutput(
      text: jsonEncode(<String, dynamic>{
        'contractId': 'assistant_turn',
        'messageKind': 'answer',
        'phaseId': 'answering',
        'actionCode': 'compose_answer',
        'reasonCode': 'evidence_ready',
        'reasonShort': '先给出初步判断，但还差实时核对。',
        'decision': const <String, dynamic>{'nextAction': 'answer'},
        'userMarkdown': '## 深圳今天适合出门\n\n从常规气候看，今天大概率适合出门，但我还没核对到最新实时天气。',
        'result': const <String, dynamic>{
          'text': '初步看今天适合出门，但还缺实时证据。',
          'summary': '先给初步判断',
          'interpretation': '仍需补一条实时天气证据',
        },
        'selfCheck': const <String, dynamic>{
          'goalSatisfied': true,
          'constraintSatisfied': true,
          'safetyBoundarySatisfied': true,
          'failedItems': <String>[],
        },
        'diagnostics': const <String, dynamic>{
          'emergedTags': <Map<String, dynamic>>[],
          'failedChecks': <String>[],
          'parseStatus': '',
          'notes': <String>['initial answer without evidence'],
        },
        'modelSelfScore': const <String, dynamic>{
          'score': 74,
          'reason': 'needs_realtime_evidence',
        },
      }),
    );
  }
}

class _PhaseOnePlainMarkdownAnswerLlm implements AssistantLlmProvider {
  int phaseOneCallCount = 0;
  int synthesisCallCount = 0;

  @override
  Future<AssistantModelOutput> reason({
    required List<Map<String, dynamic>> messages,
    required List<String> availableTools,
    Map<String, dynamic> templateContext = const <String, dynamic>{},
    Map<String, dynamic> templateVariables = const <String, dynamic>{},
    String templateId = 'planner.global_plan',
    String templateVersion = '',
    String sessionId = '',
    String runId = '',
    String traceId = '',
    LlmCallOptions? callOptions,
    void Function(String delta)? onDelta,
  }) async {
    final isSynthesisCall = _isFinalAnswerTemplate(templateId);
    if (isSynthesisCall) {
      synthesisCallCount += 1;
      throw StateError('plain markdown phase-one answer should skip synthesis');
    }
    phaseOneCallCount += 1;
    onDelta?.call('这一问我可以直接解释。');
    return const AssistantModelOutput(text: '惯性是物体保持原来静止或匀速直线运动状态的性质。');
  }
}

class _PhaseOneProgressAnswerLlm implements AssistantLlmProvider {
  int phaseOneCallCount = 0;
  int synthesisCallCount = 0;

  @override
  Future<AssistantModelOutput> reason({
    required List<Map<String, dynamic>> messages,
    required List<String> availableTools,
    Map<String, dynamic> templateContext = const <String, dynamic>{},
    Map<String, dynamic> templateVariables = const <String, dynamic>{},
    String templateId = 'planner.global_plan',
    String templateVersion = '',
    String sessionId = '',
    String runId = '',
    String traceId = '',
    LlmCallOptions? callOptions,
    void Function(String delta)? onDelta,
  }) async {
    final isSynthesisCall = _isFinalAnswerTemplate(templateId);
    if (isSynthesisCall) {
      synthesisCallCount += 1;
      throw StateError('progress answer compat path should skip synthesis');
    }
    phaseOneCallCount += 1;
    onDelta?.call('这一问我已经可以直接说明。');
    return AssistantModelOutput(
      text: jsonEncode(<String, dynamic>{
        'contractId': 'assistant_turn',
        'messageKind': 'progress',
        'decision': const <String, dynamic>{'nextAction': 'tool_call'},
        'userMarkdown': '惯性是物体保持原来静止或匀速直线运动状态的性质。',
        'result': const <String, dynamic>{
          'text': '惯性说明物体会保持原有运动状态。',
          'summary': '惯性是保持原有运动状态的性质',
        },
        'selfCheck': const <String, dynamic>{
          'goalSatisfied': true,
          'constraintSatisfied': true,
          'safetyBoundarySatisfied': true,
          'failedItems': <String>[],
        },
        'diagnostics': const <String, dynamic>{
          'emergedTags': <Map<String, dynamic>>[],
          'failedChecks': <String>[],
          'parseStatus': '',
          'notes': <String>['stale progress envelope'],
        },
        'modelSelfScore': const <String, dynamic>{
          'score': 85,
          'reason': 'compat_progress_answer',
        },
      }),
    );
  }
}

class _PhaseOneNonContractJsonAnswerLlm implements AssistantLlmProvider {
  int phaseOneCallCount = 0;
  int synthesisCallCount = 0;

  @override
  Future<AssistantModelOutput> reason({
    required List<Map<String, dynamic>> messages,
    required List<String> availableTools,
    Map<String, dynamic> templateContext = const <String, dynamic>{},
    Map<String, dynamic> templateVariables = const <String, dynamic>{},
    String templateId = 'planner.global_plan',
    String templateVersion = '',
    String sessionId = '',
    String runId = '',
    String traceId = '',
    LlmCallOptions? callOptions,
    void Function(String delta)? onDelta,
  }) async {
    final isSynthesisCall = _isFinalAnswerTemplate(templateId);
    if (isSynthesisCall) {
      synthesisCallCount += 1;
      throw StateError('non-contract phase-one json should skip synthesis');
    }
    phaseOneCallCount += 1;
    onDelta?.call('这一问我可以直接解释。');
    return AssistantModelOutput(
      text: jsonEncode(<String, dynamic>{
        'decision': const <String, dynamic>{'nextAction': 'answer'},
        'messageKind': 'answer',
        'userMarkdown': '光合作用是绿色植物利用阳光把二氧化碳和水转成有机物并释放氧气的过程。',
        'result': const <String, dynamic>{
          'text': '光合作用是植物把光能转为化学能并释放氧气的过程。',
          'summary': '植物利用阳光制造有机物',
        },
      }),
    );
  }
}

class _PhaseOneFollowupDirectAnswerRepairLlm implements AssistantLlmProvider {
  int phaseOneCallCount = 0;
  int repairCallCount = 0;
  int synthesisCallCount = 0;

  @override
  Future<AssistantModelOutput> reason({
    required List<Map<String, dynamic>> messages,
    required List<String> availableTools,
    Map<String, dynamic> templateContext = const <String, dynamic>{},
    Map<String, dynamic> templateVariables = const <String, dynamic>{},
    String templateId = 'planner.global_plan',
    String templateVersion = '',
    String sessionId = '',
    String runId = '',
    String traceId = '',
    LlmCallOptions? callOptions,
    void Function(String delta)? onDelta,
  }) async {
    final isSynthesisCall = _isFinalAnswerTemplate(templateId);
    if (isSynthesisCall) {
      synthesisCallCount += 1;
      return const AssistantModelOutput(
        text:
            '{"contractId":"assistant_turn","messageKind":"answer","phaseId":"answering","actionCode":"compose_answer","reasonCode":"evidence_ready","decision":{"nextAction":"answer"},"userMarkdown":"fallback synthesis answer","result":{"text":"fallback synthesis answer","summary":"fallback synthesis answer"}}',
      );
    }
    final isRepairCall =
        templateId == 'phase.output_contract.plan' &&
        messages.isNotEmpty &&
        messages.any(
          (message) =>
              (message['role'] as String?) == 'system' &&
              (message['content'] as String?)?.contains('<draft_answer>') ==
                  true,
        );
    if (isRepairCall) {
      repairCallCount += 1;
      expect(
        (templateVariables['continuityMode'] as String?) ?? '',
        equals('explicit_follow_up'),
      );
      expect(
        (templateVariables['previousAnswerSummary'] as String?) ?? '',
        contains('九寨沟'),
      );
      return AssistantModelOutput(
        text: jsonEncode(<String, dynamic>{
          'contractId': 'assistant_turn',
          'messageKind': 'answer',
          'phaseId': 'answering',
          'actionCode': 'compose_answer',
          'reasonCode': 'evidence_ready',
          'decision': const <String, dynamic>{'nextAction': 'answer'},
          'userMarkdown': '如果只有4天，九寨沟更推荐经典组合路线，行程紧凑且核心景点覆盖更完整。',
          'result': const <String, dynamic>{
            'text': '4天行程里，九寨沟优先经典组合路线，时间利用率最高。',
            'summary': '4天优先九寨沟经典组合路线',
          },
          'selfCheck': const <String, dynamic>{
            'goalSatisfied': true,
            'constraintSatisfied': true,
            'safetyBoundarySatisfied': true,
            'failedItems': <String>[],
          },
          'diagnostics': const <String, dynamic>{
            'emergedTags': <Map<String, dynamic>>[],
            'failedChecks': <String>[],
            'parseStatus': '',
            'notes': <String>['phase_one_followup_repair'],
          },
          'modelSelfScore': const <String, dynamic>{
            'score': 83,
            'reason': 'followup_answer_repaired',
          },
        }),
      );
    }
    phaseOneCallCount += 1;
    return const AssistantModelOutput(text: '如果只有4天，更推荐经典组合路线，时间利用率最高。');
  }
}

class _PhaseOneDerivedSecondarySkillRepairLlm implements AssistantLlmProvider {
  int phaseOneCallCount = 0;
  int repairCallCount = 0;
  int subagentCallCount = 0;
  int synthesisCallCount = 0;

  @override
  Future<AssistantModelOutput> reason({
    required List<Map<String, dynamic>> messages,
    required List<String> availableTools,
    Map<String, dynamic> templateContext = const <String, dynamic>{},
    Map<String, dynamic> templateVariables = const <String, dynamic>{},
    String templateId = 'planner.global_plan',
    String templateVersion = '',
    String sessionId = '',
    String runId = '',
    String traceId = '',
    LlmCallOptions? callOptions,
    void Function(String delta)? onDelta,
  }) async {
    final isSynthesisCall = _isFinalAnswerTemplate(templateId);
    if (isSynthesisCall) {
      synthesisCallCount += 1;
      throw StateError(
        'derived secondary-skill fallback should be bypassed by answer repair',
      );
    }
    if (templateVariables['subagentPlan'] != null) {
      subagentCallCount += 1;
      throw StateError(
        'derived secondary-skill fallback should not trigger subagent execution',
      );
    }
    final isRepairCall =
        templateId == 'phase.output_contract.plan' &&
        messages.any(
          (message) =>
              (message['role'] as String?) == 'system' &&
              (message['content'] as String?)?.contains('<draft_answer>') ==
                  true,
        );
    if (isRepairCall) {
      repairCallCount += 1;
      expect(
        (templateVariables['continuityMode'] as String?) ?? '',
        anyOf(equals(''), equals('unknown')),
      );
      return AssistantModelOutput(
        text: jsonEncode(<String, dynamic>{
          'contractId': 'assistant_turn',
          'messageKind': 'answer',
          'phaseId': 'answering',
          'actionCode': 'compose_answer',
          'reasonCode': 'evidence_ready',
          'decision': const <String, dynamic>{'nextAction': 'answer'},
          'userMarkdown': '如果只有4天，九寨沟更推荐经典高效路线，核心景点覆盖完整且时间利用率最高。',
          'result': const <String, dynamic>{
            'text': '4天优先走九寨沟经典高效路线，兼顾时间效率和景点覆盖。',
            'summary': '4天优先九寨沟经典高效路线',
          },
          'selfCheck': const <String, dynamic>{
            'goalSatisfied': true,
            'constraintSatisfied': true,
            'safetyBoundarySatisfied': true,
            'failedItems': <String>[],
          },
          'diagnostics': const <String, dynamic>{
            'emergedTags': <Map<String, dynamic>>[],
            'failedChecks': <String>[],
            'parseStatus': '',
            'notes': <String>['secondary_skill_fallback_repaired'],
          },
          'modelSelfScore': const <String, dynamic>{
            'score': 84,
            'reason': 'phase_one_repaired_before_secondary_skill_fallback',
          },
        }),
      );
    }
    phaseOneCallCount += 1;
    return const AssistantModelOutput(text: '如果只有4天，更推荐九寨沟经典高效路线，时间利用率最高。');
  }
}

class _PhaseOneTentativeSubagentPlanLlm implements AssistantLlmProvider {
  int phaseOneCallCount = 0;
  int subagentCallCount = 0;
  int synthesisCallCount = 0;

  @override
  Future<AssistantModelOutput> reason({
    required List<Map<String, dynamic>> messages,
    required List<String> availableTools,
    Map<String, dynamic> templateContext = const <String, dynamic>{},
    Map<String, dynamic> templateVariables = const <String, dynamic>{},
    String templateId = 'planner.global_plan',
    String templateVersion = '',
    String sessionId = '',
    String runId = '',
    String traceId = '',
    LlmCallOptions? callOptions,
    void Function(String delta)? onDelta,
  }) async {
    final isSynthesisCall = _isFinalAnswerTemplate(templateId);
    if (isSynthesisCall) {
      synthesisCallCount += 1;
      throw StateError(
        'tentative same-domain subagent plan should not trigger synthesis',
      );
    }
    if (templateVariables['subagentPlan'] != null) {
      subagentCallCount += 1;
      throw StateError(
        'tentative same-domain subagent plan should not trigger subagent execution',
      );
    }
    phaseOneCallCount += 1;
    return AssistantModelOutput(
      text: jsonEncode(<String, dynamic>{
        'contractId': 'assistant_turn',
        'decision': const <String, dynamic>{'nextAction': 'answer'},
        'messageKind': 'answer',
        'userMarkdown': '惯性：物体会保持原有的静止或匀速直线运动状态。',
        'result': const <String, dynamic>{
          'text': '惯性说明物体会保持当前运动状态。',
          'interpretation': '一句话说明惯性',
        },
        'subagentPlan': const <Map<String, dynamic>>[
          <String, dynamic>{
            'subagentId': 'tentative_same_domain',
            'domainId': 'fallback_general_search',
            'goal': '这个候选计划不应该被真正执行',
            'problemClass': 'simple_qa',
            'mode': 'qa',
            'maxIterations': 1,
            'toolBudget': 0,
          },
        ],
        'selfCheck': const <String, dynamic>{
          'goalSatisfied': true,
          'constraintSatisfied': true,
          'safetyBoundarySatisfied': true,
          'failedItems': <String>[],
        },
        'diagnostics': const <String, dynamic>{
          'emergedTags': <Map<String, dynamic>>[],
          'failedChecks': <String>[],
          'parseStatus': '',
        },
      }),
    );
  }
}

class _PhaseOneSubagentFusionLlm implements AssistantLlmProvider {
  int phaseOneCallCount = 0;
  int subagentCallCount = 0;
  int synthesisCallCount = 0;

  @override
  Future<AssistantModelOutput> reason({
    required List<Map<String, dynamic>> messages,
    required List<String> availableTools,
    Map<String, dynamic> templateContext = const <String, dynamic>{},
    Map<String, dynamic> templateVariables = const <String, dynamic>{},
    String templateId = 'planner.global_plan',
    String templateVersion = '',
    String sessionId = '',
    String runId = '',
    String traceId = '',
    LlmCallOptions? callOptions,
    void Function(String delta)? onDelta,
  }) async {
    final isSynthesisCall = _isFinalAnswerTemplate(templateId);
    if (isSynthesisCall) {
      synthesisCallCount += 1;
      if (!_hasSubagentRuns(templateVariables)) {
        throw StateError(
          'fusion synthesis should be identified by subagentRuns',
        );
      }
      if (subagentCallCount == 0) {
        throw StateError(
          'fusion synthesis must happen after subagent execution',
        );
      }
      return AssistantModelOutput(
        text: jsonEncode(<String, dynamic>{
          'contractId': 'assistant_turn',
          'decision': const <String, dynamic>{'nextAction': 'answer'},
          'messageKind': 'answer',
          'userMarkdown': '路线优先建议：先按经典主线走；住宿取舍建议：住在沟口附近更省时间。',
          'result': const <String, dynamic>{
            'text': '路线优先主线，住宿优先沟口附近。',
            'interpretation': '融合路线与住宿建议',
          },
          'selfCheck': const <String, dynamic>{
            'goalSatisfied': true,
            'constraintSatisfied': true,
            'safetyBoundarySatisfied': true,
            'failedItems': <String>[],
          },
          'diagnostics': const <String, dynamic>{
            'emergedTags': <Map<String, dynamic>>[],
            'failedChecks': <String>[],
            'parseStatus': '',
          },
        }),
      );
    }
    if (templateVariables['subagentPlan'] != null) {
      subagentCallCount += 1;
      return AssistantModelOutput(
        text: jsonEncode(<String, dynamic>{
          'contractId': 'assistant_turn',
          'decision': const <String, dynamic>{'nextAction': 'answer'},
          'messageKind': 'answer',
          'userMarkdown': '住宿建议：如果更看重效率，优先住沟口附近。',
          'result': const <String, dynamic>{
            'text': '沟口附近住宿能减少往返时间。',
            'interpretation': '住宿子任务结论',
          },
          'selfCheck': const <String, dynamic>{
            'goalSatisfied': true,
            'constraintSatisfied': true,
            'safetyBoundarySatisfied': true,
            'failedItems': <String>[],
          },
          'diagnostics': const <String, dynamic>{
            'emergedTags': <Map<String, dynamic>>[],
            'failedChecks': <String>[],
            'parseStatus': '',
          },
        }),
      );
    }
    phaseOneCallCount += 1;
    return AssistantModelOutput(
      text: jsonEncode(<String, dynamic>{
        'contractId': 'assistant_turn',
        'decision': const <String, dynamic>{'nextAction': 'answer'},
        'messageKind': 'answer',
        'userMarkdown': '路线先按经典主线安排，同时我会补一层住宿取舍建议。',
        'result': const <String, dynamic>{
          'text': '主线路线建议已形成，还需补充住宿取舍。',
          'interpretation': '主任务先给路线结论',
        },
        'subagentPlan': const <Map<String, dynamic>>[
          <String, dynamic>{
            'subagentId': 'hotel_tradeoff_1',
            'domainId': 'hotel',
            'goal': '补充住宿取舍建议',
            'problemClass': 'complex_reasoning',
            'mode': 'qa',
            'maxIterations': 1,
            'toolBudget': 0,
          },
        ],
        'selfCheck': const <String, dynamic>{
          'goalSatisfied': true,
          'constraintSatisfied': true,
          'safetyBoundarySatisfied': true,
          'failedItems': <String>[],
        },
        'diagnostics': const <String, dynamic>{
          'emergedTags': <Map<String, dynamic>>[],
          'failedChecks': <String>[],
          'parseStatus': '',
        },
      }),
    );
  }
}

class _SynthesisDraftWeatherSearchTool implements AssistantTool {
  @override
  String get name => 'web_search';

  @override
  String get description => '网络搜索';

  @override
  Future<AssistantToolResult> execute(Map<String, dynamic> arguments) async {
    return const AssistantToolResult(
      success: true,
      message: '搜索完成',
      data: <String, dynamic>{
        'provider': 'duckduckgo',
        'summary': '深圳今天天气晴朗，温度25°C',
        'totalReferences': 1,
        'references': <Map<String, dynamic>>[
          <String, dynamic>{
            'title': '深圳天气预报 - 中国气象局',
            'url': 'https://weather.cma.cn/shenzhen',
            'source': '中国气象局',
            'snippet': '深圳今天晴，温度25°C。',
          },
        ],
      },
    );
  }
}
