import 'dart:convert';
import 'dart:io';

import 'package:quwoquan_app/assistant/contracts/answer_boundary_policy.dart';
import 'package:quwoquan_app/assistant/contracts/context_assembly_result.dart';
import 'package:quwoquan_app/assistant/contracts/dialogue_round_script.dart';
import 'package:quwoquan_app/assistant/contracts/intent_graph.dart';
import 'package:quwoquan_app/assistant/contracts/query_task_contract.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/contracts/synthesis_readiness_result.dart';
import 'package:quwoquan_app/assistant/conversation/orchestration/session_manager.dart';
import 'package:quwoquan_app/assistant/infrastructure/assistant_model_runtime.dart';
import 'package:quwoquan_app/assistant/memory/assistant_memory_runtime.dart';
import 'package:quwoquan_app/assistant/orchestration/local_phase_execution_owner.dart';
import 'package:quwoquan_app/assistant/protocol/trace_events.dart';
import 'package:quwoquan_app/assistant/protocol/run_request.dart';
import 'package:quwoquan_app/assistant/reasoning/runtime/react_runtime.dart';
import 'package:quwoquan_app/assistant/skill/domain/skill_manifest.dart';
import 'package:quwoquan_app/assistant/tool/runtime/tool_registry.dart';
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

const String _phaseOneRenderableBlockedEnvelope =
    '{"contractId":"assistant_turn","messageKind":"answer","phaseId":"answering","actionCode":"compose_answer","reasonCode":"need_more_evidence","decision":{"nextAction":"answer"},"userMarkdown":"## 初步结论\\n\\n- 先给你一版受限答案。","result":{"text":"先给你一版受限答案。","summary":"先给你一版受限答案。","interpretation":"bounded_answer"},"selfCheck":{"goalSatisfied":true,"constraintSatisfied":true,"safetyBoundarySatisfied":true,"failedItems":[]},"diagnostics":{"emergedTags":[],"failedChecks":[],"parseStatus":"","notes":[]}}';

const String _phaseOneProgressOnlyEnvelope =
    '{"contractId":"assistant_turn","messageKind":"progress","phaseId":"understanding","actionCode":"frame_problem","reasonCode":"align_goal","decision":{"nextAction":"tool_call"},"userMarkdown":"我先确认今天的天气情况，再看是否需要外套。","selfCheck":{"goalSatisfied":true,"constraintSatisfied":true,"safetyBoundarySatisfied":true,"failedItems":[]},"diagnostics":{"emergedTags":[],"failedChecks":[],"parseStatus":"","notes":[]}}';

const String _synthesisWeatherAnswerEnvelope =
    '{"contractId":"assistant_turn","messageKind":"answer","phaseId":"answering","actionCode":"compose_answer","reasonCode":"evidence_ready","decision":{"nextAction":"answer"},"userMarkdown":"深圳今天气温约24-28°C，体感偏暖，带一件薄外套更稳妥。","result":{"text":"深圳今天气温约24-28°C，体感偏暖，带一件薄外套更稳妥。","summary":"深圳今天偏暖，薄外套更稳妥","interpretation":"bounded_answer"},"selfCheck":{"goalSatisfied":true,"constraintSatisfied":true,"safetyBoundarySatisfied":true,"failedItems":[]},"diagnostics":{"emergedTags":[],"failedChecks":[],"parseStatus":"","notes":[]}}';

const String _synthesisRenderableReplanEnvelope =
    '{"contractId":"assistant_turn","messageKind":"answer","phaseId":"answering","actionCode":"compose_answer","reasonCode":"need_more_evidence","decision":{"nextAction":"replan"},"userMarkdown":"根据当前预报，深圳明天有降雨概率，建议带伞和薄外套。","result":{"text":"根据当前预报，深圳明天有降雨概率，建议带伞和薄外套。","summary":"深圳明天可能下雨，带伞和薄外套更稳妥","interpretation":"bounded_answer"},"selfCheck":{"goalSatisfied":true,"constraintSatisfied":true,"safetyBoundarySatisfied":true,"failedItems":[]},"diagnostics":{"emergedTags":[],"failedChecks":[],"parseStatus":"","notes":[]}}';

const String _synthesisStructuredDecisionEnvelope =
    '{"contractId":"assistant_turn","messageKind":"answer","phaseId":"answering","actionCode":"compose_answer","reasonCode":"bounded_ready","decision":{"nextAction":"answer"},"answerGateAssessment":{"canAnswerNow":true,"answerMode":"bounded_answer","replanNeeded":false,"replanReason":"","convergenceStatus":"improving","attemptsUsed":1,"maxAttempts":2},"retrievalProcessing":{"processingSummary":"围绕明天深圳天气，已经接纳了能直接支撑判断的线索。","acceptedDocumentCount":2,"acceptedReferences":[{"title":"深圳天气预报","url":"https://weather.example.com/shenzhen","source":"weather.example.com","snippet":"2026-04-10 深圳有降雨概率，气温偏暖。"}]},"answerProcessing":{"readinessSummary":"这版会先给出是否需要带伞，再补一条穿衣建议。","keyFacts":["降雨概率偏高","气温偏暖"],"missingDimensions":[],"retrieveMoreReason":""},"userMarkdown":"深圳明天有降雨概率，建议带伞，薄外套即可。","result":{"text":"深圳明天有降雨概率，建议带伞，薄外套即可。","summary":"深圳明天可能下雨，建议带伞","interpretation":"bounded_answer"},"selfCheck":{"goalSatisfied":true,"constraintSatisfied":true,"safetyBoundarySatisfied":true,"failedItems":[]},"diagnostics":{"emergedTags":[],"failedChecks":[],"parseStatus":"","notes":[]}}';

class _TemplateResponseProvider implements AssistantLlmProvider {
  _TemplateResponseProvider({
    required this.synthesisEnvelopeText,
    this.streamedDelta = '',
  });

  final String synthesisEnvelopeText;
  final String streamedDelta;
  int callCount = 0;
  Map<String, dynamic> lastSynthesisTemplateVariables =
      const <String, dynamic>{};

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
    callCount += 1;
    if (templateId == 'synthesizer.final_answer') {
      lastSynthesisTemplateVariables = Map<String, dynamic>.from(
        templateVariables,
      );
      if (streamedDelta.trim().isNotEmpty) {
        onDelta?.call(streamedDelta);
      }
      return AssistantModelOutput(text: synthesisEnvelopeText);
    }
    return const AssistantModelOutput(text: '');
  }
}

void main() {
  late Directory tempDir;

  setUp(() async {
    tempDir = await Directory.systemTemp.createTemp(
      'assistant_renderable_blocked_',
    );
  });

  tearDown(() async {
    if (await tempDir.exists()) {
      await tempDir.delete(recursive: true);
    }
  });

  test(
    'retrieval blocked 但已有 renderable answer 时，不再回退为 retrieval_processing_blocked fallback',
    () async {
      final owner = LocalPhaseExecutionOwner(
        ReactRuntime(
          llmProvider: const HeuristicLocalLlmProvider(),
          toolRegistry: AssistantToolRegistry(),
        ),
        sessionManager: AssistantSessionManager(
          storagePath: '${tempDir.path}/sessions.json',
        ),
        memoryRepository: AssistantMemoryRepository(_InMemoryVectorStore()),
      );
      final request = const AssistantRunRequest(
        sessionId: 'renderable_blocked_synthesis',
        messages: <AssistantRunMessage>[
          AssistantRunMessage(role: 'user', content: '昨天A股为什么大涨'),
        ],
      );

      final response = await owner.synthesizeBridge(
        request,
        executionSnapshot: <String, dynamic>{
          'runId': 'run_renderable_blocked_synthesis',
          'traceId': 'trace_renderable_blocked_synthesis',
          'sessionId': 'renderable_blocked_synthesis',
          'latestUserQuery': '昨天A股为什么大涨',
          'domainId': 'fallback_general_search',
          'contextAssembly': const ContextAssemblyResult(),
          'intentGraph': const IntentGraph(
            userGoal: '解释昨天A股为什么大涨',
            problemShape: ProblemShape.singleSkill,
            primarySkill: 'fallback_general_search',
            problemClass: ProblemClass.realtimeInfo,
            freshnessNeed: FreshnessNeed.recent,
            requiresExternalEvidence: true,
            queryTasks: <QueryTask>[
              QueryTask(
                id: 'market_jump',
                query: '2026-04-07 A股 大涨 原因',
                dimension: QueryTaskDimension.latestSignal,
              ),
            ],
          ),
          'dialogueRoundScript': const DialogueRoundScript(
            domainId: 'fallback_general_search',
          ),
          'domainCatalog': const <String>['fallback_general_search'],
          'domainCatalogVersion': 'test',
          'executionShell': const SkillExecutionShell(),
          'previousSlotState': const SlotStateSnapshot(
            domainId: 'fallback_general_search',
          ),
          'retrievalPolicy': const <String, dynamic>{},
          'answerBoundaryPolicy': const AnswerBoundaryPolicy(
            evidenceRequired: false,
            allowBoundedAnswer: true,
          ).toJson(),
          'templateVariables': const <String, dynamic>{},
          'messages': const <Map<String, dynamic>>[
            <String, dynamic>{'role': 'user', 'content': '昨天A股为什么大涨'},
          ],
          'synthTemplateVersion': 'test',
          'phaseOneResult': const ReactRuntimeResult(
            finalText: _phaseOneRenderableBlockedEnvelope,
            traces: <AssistantTraceEvent>[],
          ),
          'synthesisReadiness': const SynthesisReadinessResult(
            ready: false,
            reason: 'freshness_pending',
          ),
          'supplementalTraces': const <AssistantTraceEvent>[],
          'understandingSnapshot': const <String, dynamic>{
            'userFacingSummary': '我先确认你想追的是昨天盘面的原因。',
            'queryDesignSummary': '我会先锁定对应交易日，再核对盘面主线。',
            'queryGroups': <Map<String, dynamic>>[
              <String, dynamic>{
                'dimension': '交易日确认',
                'queries': <String>['2026-04-07 A股 大涨 原因'],
                'why': '先把相对时间落成具体日期。',
              },
            ],
          },
          'retrievalProcessing': const <String, dynamic>{
            'processingSummary': '当前证据时效性还不够稳定。',
          },
          'blockedProcessStepId': ProcessStepId.retrievalProcessing.wireName,
          'blockedProcessMessage': '当前证据时效性不满足要求，还不能直接成答。',
        },
      );
      expect(
        response.finalText,
        isNot(contains('retrieval_processing_blocked')),
      );
      expect(response.answerGateDecision.renderable, isTrue);
      expect(response.displayMarkdown, contains('先给你一版受限答案'));
      expect(response.displayState.answer.blocks, isNotEmpty);
      expect(
        ((response.structuredResponse['phaseOneRoutingDiagnostics'] as Map?)
            ?.cast<String, dynamic>())?['route'],
        equals('retrieval_blocked_renderable'),
      );
    },
  );

  test(
    'retrieval blocked 且 phase one 只有过程文本时，仍继续 formal synthesis 生成答案',
    () async {
      final provider = _TemplateResponseProvider(
        synthesisEnvelopeText: _synthesisWeatherAnswerEnvelope,
        streamedDelta: '深圳今天气温约24-28°C，体感偏暖，带一件薄外套更稳妥。',
      );
      final owner = LocalPhaseExecutionOwner(
        ReactRuntime(
          llmProvider: provider,
          toolRegistry: AssistantToolRegistry(),
        ),
        sessionManager: AssistantSessionManager(
          storagePath: '${tempDir.path}/sessions.json',
        ),
        memoryRepository: AssistantMemoryRepository(_InMemoryVectorStore()),
      );
      final request = const AssistantRunRequest(
        sessionId: 'blocked_but_synthesizable_weather',
        messages: <AssistantRunMessage>[
          AssistantRunMessage(role: 'user', content: '深圳今天天气怎么样？需要带外套吗？'),
        ],
      );

      final response = await owner.synthesizeBridge(
        request,
        executionSnapshot: <String, dynamic>{
          'runId': 'run_blocked_but_synthesizable_weather',
          'traceId': 'trace_blocked_but_synthesizable_weather',
          'sessionId': 'blocked_but_synthesizable_weather',
          'latestUserQuery': '深圳今天天气怎么样？需要带外套吗？',
          'domainId': 'weather',
          'contextAssembly': const ContextAssemblyResult(),
          'intentGraph': const IntentGraph(
            userGoal: '了解深圳今天的天气并判断是否需要带外套',
            problemShape: ProblemShape.singleSkill,
            primarySkill: 'weather',
            problemClass: ProblemClass.realtimeInfo,
            freshnessNeed: FreshnessNeed.realtime,
            requiresExternalEvidence: true,
            queryTasks: <QueryTask>[
              QueryTask(
                id: 'weather_today',
                query: '深圳 2026-04-09 实时天气',
                dimension: QueryTaskDimension.currentState,
                timeScope: 'today',
                timePoint: '2026-04-09',
                timezone: 'Asia/Shanghai',
              ),
            ],
          ),
          'dialogueRoundScript': const DialogueRoundScript(domainId: 'weather'),
          'domainCatalog': const <String>['weather'],
          'domainCatalogVersion': 'test',
          'executionShell': const SkillExecutionShell(),
          'previousSlotState': const SlotStateSnapshot(domainId: 'weather'),
          'retrievalPolicy': const <String, dynamic>{},
          'answerBoundaryPolicy': const AnswerBoundaryPolicy(
            evidenceRequired: false,
            allowBoundedAnswer: true,
          ).toJson(),
          'templateVariables': const <String, dynamic>{},
          'messages': const <Map<String, dynamic>>[
            <String, dynamic>{'role': 'user', 'content': '深圳今天天气怎么样？需要带外套吗？'},
          ],
          'synthTemplateVersion': 'test',
          'phaseOneResult': const ReactRuntimeResult(
            finalText: _phaseOneProgressOnlyEnvelope,
            traces: <AssistantTraceEvent>[],
          ),
          'synthesisReadiness': const SynthesisReadinessResult(
            ready: true,
            reason: 'ok',
          ),
          'supplementalTraces': const <AssistantTraceEvent>[],
          'understandingSnapshot': const <String, dynamic>{
            'userFacingSummary': '我先确认今天深圳的实时天气，再判断是否需要外套。',
            'queryDesignSummary': '我会先看实时温度和体感，再给穿衣建议。',
          },
          'retrievalProcessing': const <String, dynamic>{
            'processingSummary': '当前证据还不够稳定，但已能进入整理答案。',
          },
          'blockedProcessStepId': ProcessStepId.retrievalProcessing.wireName,
          'blockedProcessMessage': '当前证据时效性还不够稳，但可以先整理已确认部分。',
        },
      );

      expect(
        response.finalText,
        isNot(contains('retrieval_processing_blocked')),
      );
      expect(response.displayMarkdown, contains('薄外套'));
      expect(
        ((response.structuredResponse['phaseOneRoutingDiagnostics'] as Map?)
            ?.cast<String, dynamic>())?['route'],
        equals('formal_synthesis'),
      );
      expect(provider.callCount, greaterThan(0));
    },
  );

  test(
    'renderable replan answer 会被规范成 answer，不再把 replan 暴露为最终 nextAction',
    () async {
      final provider = _TemplateResponseProvider(
        synthesisEnvelopeText: _synthesisRenderableReplanEnvelope,
        streamedDelta: '根据当前预报，深圳明天有降雨概率，建议带伞和薄外套。',
      );
      final owner = LocalPhaseExecutionOwner(
        ReactRuntime(
          llmProvider: provider,
          toolRegistry: AssistantToolRegistry(),
        ),
        sessionManager: AssistantSessionManager(
          storagePath: '${tempDir.path}/sessions.json',
        ),
        memoryRepository: AssistantMemoryRepository(_InMemoryVectorStore()),
      );
      final request = const AssistantRunRequest(
        sessionId: 'renderable_replan_answer',
        messages: <AssistantRunMessage>[
          AssistantRunMessage(role: 'user', content: '明天会下雨吗，要带伞还是外套？'),
        ],
      );

      final response = await owner.synthesizeBridge(
        request,
        executionSnapshot: <String, dynamic>{
          'runId': 'run_renderable_replan_answer',
          'traceId': 'trace_renderable_replan_answer',
          'sessionId': 'renderable_replan_answer',
          'latestUserQuery': '明天会下雨吗，要带伞还是外套？',
          'domainId': 'weather',
          'contextAssembly': const ContextAssemblyResult(),
          'intentGraph': const IntentGraph(
            userGoal: '判断明天是否下雨以及要带伞还是外套',
            problemShape: ProblemShape.singleSkill,
            primarySkill: 'weather',
            problemClass: ProblemClass.realtimeInfo,
            freshnessNeed: FreshnessNeed.recent,
            requiresExternalEvidence: true,
            queryTasks: <QueryTask>[
              QueryTask(
                id: 'weather_tomorrow',
                query: '深圳 2026-04-10 天气预报',
                dimension: QueryTaskDimension.currentState,
                timeScope: 'year_month_day',
                timePoint: '2026-04-10',
                timezone: 'Asia/Shanghai',
              ),
            ],
          ),
          'dialogueRoundScript': const DialogueRoundScript(domainId: 'weather'),
          'domainCatalog': const <String>['weather'],
          'domainCatalogVersion': 'test',
          'executionShell': const SkillExecutionShell(),
          'previousSlotState': const SlotStateSnapshot(domainId: 'weather'),
          'retrievalPolicy': const <String, dynamic>{},
          'answerBoundaryPolicy': const AnswerBoundaryPolicy(
            evidenceRequired: false,
            allowBoundedAnswer: true,
          ).toJson(),
          'templateVariables': const <String, dynamic>{},
          'messages': const <Map<String, dynamic>>[
            <String, dynamic>{'role': 'user', 'content': '明天会下雨吗，要带伞还是外套？'},
          ],
          'synthTemplateVersion': 'test',
          'phaseOneResult': const ReactRuntimeResult(
            finalText: '',
            traces: <AssistantTraceEvent>[],
          ),
          'synthesisReadiness': const SynthesisReadinessResult(
            ready: true,
            reason: 'ok',
          ),
          'supplementalTraces': const <AssistantTraceEvent>[],
          'understandingSnapshot': const <String, dynamic>{
            'userFacingSummary': '我先确认明天的降雨概率和温度，再判断带伞还是外套。',
            'queryDesignSummary': '我会先看明天降水与气温，再给出出行建议。',
          },
          'retrievalProcessing': const <String, dynamic>{
            'processingSummary': '已经拿到首轮天气证据，可以开始整理答案。',
          },
        },
      );

      final decision =
          (response.structuredResponse['conversationStateDecision'] as Map?)
              ?.cast<String, dynamic>() ??
          const <String, dynamic>{};
      expect(response.displayMarkdown, contains('带伞和薄外套'));
      expect(decision['nextAction'], equals('answer'));
      expect(decision['finalAnswerMode'], isNot(equals('replan')));
    },
  );

  test(
    '显式 answerGateAssessment 与 searchIterationState 会透传到 synthesis 结果',
    () async {
      final provider = _TemplateResponseProvider(
        synthesisEnvelopeText: _synthesisStructuredDecisionEnvelope,
        streamedDelta: '深圳明天有降雨概率，建议带伞，薄外套即可。',
      );
      final owner = LocalPhaseExecutionOwner(
        ReactRuntime(
          llmProvider: provider,
          toolRegistry: AssistantToolRegistry(),
        ),
        sessionManager: AssistantSessionManager(
          storagePath: '${tempDir.path}/sessions.json',
        ),
        memoryRepository: AssistantMemoryRepository(_InMemoryVectorStore()),
      );
      final request = const AssistantRunRequest(
        sessionId: 'structured_gate_assessment',
        maxIterations: 2,
        messages: <AssistantRunMessage>[
          AssistantRunMessage(role: 'user', content: '明天深圳天气怎么样，要不要带伞？'),
        ],
      );

      final response = await owner.synthesizeBridge(
        request,
        executionSnapshot: <String, dynamic>{
          'runId': 'run_structured_gate_assessment',
          'traceId': 'trace_structured_gate_assessment',
          'sessionId': 'structured_gate_assessment',
          'latestUserQuery': '明天深圳天气怎么样，要不要带伞？',
          'domainId': 'weather',
          'contextAssembly': const ContextAssemblyResult(),
          'intentGraph': const IntentGraph(
            userGoal: '判断明天深圳天气以及是否需要带伞',
            problemShape: ProblemShape.singleSkill,
            primarySkill: 'weather',
            problemClass: ProblemClass.realtimeInfo,
            freshnessNeed: FreshnessNeed.recent,
            requiresExternalEvidence: true,
            queryTasks: <QueryTask>[
              QueryTask(
                id: 'weather_tomorrow',
                query: '深圳 2026-04-10 天气 预报',
                dimension: QueryTaskDimension.currentState,
              ),
            ],
          ),
          'dialogueRoundScript': const DialogueRoundScript(domainId: 'weather'),
          'domainCatalog': const <String>['weather'],
          'domainCatalogVersion': 'test',
          'executionShell': const SkillExecutionShell(),
          'previousSlotState': const SlotStateSnapshot(domainId: 'weather'),
          'retrievalPolicy': const <String, dynamic>{},
          'answerBoundaryPolicy': const AnswerBoundaryPolicy(
            evidenceRequired: true,
            allowBoundedAnswer: true,
          ).toJson(),
          'templateVariables': const <String, dynamic>{},
          'messages': const <Map<String, dynamic>>[
            <String, dynamic>{'role': 'user', 'content': '明天深圳天气怎么样，要不要带伞？'},
          ],
          'synthTemplateVersion': 'test',
          'phaseOneResult': const ReactRuntimeResult(
            finalText: '',
            traces: <AssistantTraceEvent>[],
          ),
          'synthesisReadiness': const SynthesisReadinessResult(
            ready: true,
            reason: 'ok',
          ),
          'supplementalTraces': const <AssistantTraceEvent>[],
          'understandingSnapshot': const <String, dynamic>{
            'userFacingSummary': '我先确认明天深圳的降雨概率和温度，再判断是否需要带伞。',
            'queryDesignSummary': '先看明天降雨与温度，再给出出行建议。',
          },
          'retrievalProcessing': const <String, dynamic>{
            'processingSummary': '已经拿到首轮天气候选，可以整理答案。',
            'acceptedReferences': <Map<String, dynamic>>[
              <String, dynamic>{
                'title': '深圳天气预报',
                'url': 'https://weather.example.com/shenzhen',
                'source': 'weather.example.com',
                'snippet': '2026-04-10 深圳有降雨概率，气温偏暖。',
              },
            ],
          },
        },
      );

      final conversationStateDecision =
          (response.structuredResponse['conversationStateDecision'] as Map?)
              ?.cast<String, dynamic>();
      expect(conversationStateDecision, isNotNull);
      expect(conversationStateDecision!['nextAction'], equals('answer'));
      expect(
        response.structuredResponse['finalAnswerMode'],
        equals('bounded_answer'),
      );
      expect(response.displayMarkdown, contains('建议带伞'));
      expect(provider.callCount, greaterThan(0));

      final searchIterationState =
          jsonDecode(
                (provider.lastSynthesisTemplateVariables['searchIterationState']
                        as String?) ??
                    '{}',
              )
              as Map<String, dynamic>;
      expect(searchIterationState['maxIterations'], greaterThan(0));
      expect(searchIterationState['currentIteration'], 1);
      final rounds =
          (searchIterationState['rounds'] as List?)
              ?.whereType<Map>()
              .map((item) => item.cast<String, dynamic>())
              .toList(growable: false) ??
          const <Map<String, dynamic>>[];
      expect(rounds, isNotEmpty);
      final roundTasks =
          (rounds.first['queryTasks'] as List?)
              ?.whereType<Map>()
              .map((item) => item.cast<String, dynamic>())
              .toList(growable: false) ??
          const <Map<String, dynamic>>[];
      expect(roundTasks, isNotEmpty);
      expect(roundTasks.first['query'], equals('深圳 2026-04-10 天气 预报'));
    },
  );
}
