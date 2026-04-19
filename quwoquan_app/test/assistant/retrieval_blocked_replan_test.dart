import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/contracts/answer_boundary_policy.dart';
import 'package:quwoquan_app/assistant/context/assembly/conversation_state_kernel.dart';
import 'package:quwoquan_app/assistant/context/assembly/evidence_evaluator.dart';
import 'package:quwoquan_app/assistant/contracts/aggregation_state.dart';
import 'package:quwoquan_app/assistant/contracts/context_assembly_result.dart';
import 'package:quwoquan_app/assistant/contracts/context_fill_contract.dart';
import 'package:quwoquan_app/assistant/contracts/dialogue_round_script.dart';
import 'package:quwoquan_app/assistant/contracts/intent_graph.dart';
import 'package:quwoquan_app/assistant/contracts/query_task_contract.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/contracts/slot_schema.dart';
import 'package:quwoquan_app/assistant/contracts/synthesis_readiness_result.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_tool_result_row.dart';
import 'package:quwoquan_app/assistant/session/assistant_session_manager.dart';
import 'package:quwoquan_app/assistant/infrastructure/assistant_model_runtime.dart';
import 'package:quwoquan_app/assistant/memory/assistant_memory_runtime.dart';
import 'package:quwoquan_app/assistant/orchestration/pipelines/assistant_pipeline_engine.dart';
import 'package:quwoquan_app/assistant/orchestration/state/execution_phase_snapshot.dart';
import 'package:quwoquan_app/assistant/protocol/trace_events.dart';
import 'package:quwoquan_app/assistant/protocol/run_request.dart';
import 'package:quwoquan_app/assistant/reasoning/runtime/react_runtime.dart';
import 'package:quwoquan_app/assistant/skill/domain/skill_manifest.dart';
import 'package:quwoquan_app/assistant/tool/runtime/tool_registry.dart';

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

class _StaticEnvelopeProvider implements AssistantLlmProvider {
  _StaticEnvelopeProvider(this.synthesisEnvelopeText);

  final String synthesisEnvelopeText;
  int callCount = 0;

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
    if (templateId == 'synthesizer.final_answer') {
      callCount += 1;
      return AssistantModelOutput(text: synthesisEnvelopeText);
    }
    return const AssistantModelOutput(text: '');
  }
}

ExecutionPhaseSnapshot _buildExecutionSnapshot(Map<String, dynamic> raw) {
  final dialogueRoundScript = raw['dialogueRoundScript'] is Map
      ? DialogueRoundScript(
          domainId:
              (raw['dialogueRoundScript'] as Map)['domainId']?.toString() ?? '',
          enabled:
              (raw['dialogueRoundScript'] as Map)['enabled'] == true,
          currentStateId:
              (raw['dialogueRoundScript'] as Map)['currentStateId']
                  ?.toString() ??
              '',
          detectedEvent:
              (raw['dialogueRoundScript'] as Map)['detectedEvent']
                  ?.toString() ??
              '',
          suggestedNextStateId:
              (raw['dialogueRoundScript'] as Map)['suggestedNextStateId']
                  ?.toString() ??
              '',
          nextStateCandidates:
              ((raw['dialogueRoundScript'] as Map)['nextStateCandidates']
                      as List?)
                  ?.map((item) => item.toString())
                  .toList(growable: false) ??
              const <String>[],
          requiredFieldsForNextState:
              ((raw['dialogueRoundScript'] as Map)['requiredFieldsForNextState']
                      as List?)
                  ?.map((item) => item.toString())
                  .toList(growable: false) ??
              const <String>[],
          totalSubTotalRequired:
              (raw['dialogueRoundScript'] as Map)['totalSubTotalRequired'] ==
              true,
          optionalEnrichment:
              (raw['dialogueRoundScript'] as Map)['optionalEnrichment'] == true,
          maxQuestionsPerTurn:
              ((raw['dialogueRoundScript'] as Map)['maxQuestionsPerTurn']
                      as num?)
                  ?.toInt() ??
              0,
          hardFailCodes:
              ((raw['dialogueRoundScript'] as Map)['hardFailCodes'] as List?)
                  ?.map((item) => item.toString())
                  .toList(growable: false) ??
              const <String>[],
          passCriteriaRound:
              ((raw['dialogueRoundScript'] as Map)['passCriteriaRound'] as Map?)
                      ?.cast<String, dynamic>() ??
                  const <String, dynamic>{},
          statePromptExcerpt:
              (raw['dialogueRoundScript'] as Map)['statePromptExcerpt']
                  ?.toString() ??
              '',
          stateMachineExcerpt:
              (raw['dialogueRoundScript'] as Map)['stateMachineExcerpt']
                  ?.toString() ??
              '',
          routingCatalogVersion:
              (raw['dialogueRoundScript'] as Map)['routingCatalogVersion']
                  ?.toString() ??
              '',
          eventCatalogVersion:
              (raw['dialogueRoundScript'] as Map)['eventCatalogVersion']
                  ?.toString() ??
              '',
        )
      : const DialogueRoundScript();

  return ExecutionPhaseSuccess(
    runId: (raw['runId'] as String?)?.trim() ?? '',
    traceId: (raw['traceId'] as String?)?.trim() ?? '',
    runStartAt: DateTime(2026, 4, 9, 10, 0, 0),
    sessionId: (raw['sessionId'] as String?)?.trim() ?? '',
    latestUserQuery: (raw['latestUserQuery'] as String?)?.trim() ?? '',
    domainId: (raw['domainId'] as String?)?.trim() ?? '',
    contextAssembly: raw['contextAssembly'] is ContextAssemblyResult
        ? raw['contextAssembly'] as ContextAssemblyResult
        : raw['contextAssembly'] is Map
        ? ContextAssemblyResult.fromJson(
            (raw['contextAssembly'] as Map).cast<String, dynamic>(),
          )
        : const ContextAssemblyResult(),
    intentGraph: raw['intentGraph'] is IntentGraph
        ? raw['intentGraph'] as IntentGraph
        : raw['intentGraph'] is Map
        ? IntentGraph.fromJson((raw['intentGraph'] as Map).cast<String, dynamic>())
        : const IntentGraph(
            userGoal: '',
            problemShape: ProblemShape.singleSkill,
            primarySkill: '',
          ),
    dialogueRoundScript: raw['dialogueRoundScript'] is DialogueRoundScript
        ? raw['dialogueRoundScript'] as DialogueRoundScript
        : dialogueRoundScript,
    domainCatalog: (raw['domainCatalog'] as List?)
            ?.map((item) => item.toString())
            .toList(growable: false) ??
        const <String>[],
    domainCatalogVersion: (raw['domainCatalogVersion'] as String?)?.trim() ?? '',
    allowedToolNames: (raw['allowedToolNames'] as List?)
            ?.map((item) => item.toString())
            .toList(growable: false) ??
        const <String>[],
    executionShell: raw['executionShell'] is SkillExecutionShell
        ? raw['executionShell'] as SkillExecutionShell
        : raw['executionShell'] is Map
        ? SkillExecutionShell.fromJson(
            (raw['executionShell'] as Map).cast<String, dynamic>(),
          )
        : const SkillExecutionShell(),
    previousSlotState: raw['previousSlotState'] is SlotStateSnapshot
        ? raw['previousSlotState'] as SlotStateSnapshot
        : raw['previousSlotState'] is Map
        ? SlotStateSnapshot.fromJson(
            (raw['previousSlotState'] as Map).cast<String, dynamic>(),
          )
        : const SlotStateSnapshot(),
    retrievalPolicy: (raw['retrievalPolicy'] as Map?)
            ?.cast<String, dynamic>() ??
        const <String, dynamic>{},
    answerBoundaryPolicy: raw['answerBoundaryPolicy'] is AnswerBoundaryPolicy
        ? raw['answerBoundaryPolicy'] as AnswerBoundaryPolicy
        : raw['answerBoundaryPolicy'] is Map
        ? AnswerBoundaryPolicy.fromJson(
            (raw['answerBoundaryPolicy'] as Map).cast<String, dynamic>(),
          )
        : const AnswerBoundaryPolicy(),
    understandingSnapshot: (raw['understandingSnapshot'] as Map?)
            ?.cast<String, dynamic>() ??
        const <String, dynamic>{},
    templateVariables: (raw['templateVariables'] as Map?)
            ?.cast<String, dynamic>() ??
        const <String, dynamic>{},
    messages: (raw['messages'] as List?)
            ?.whereType<Map>()
            .map((item) => item.cast<String, dynamic>())
            .toList(growable: false) ??
        const <Map<String, dynamic>>[],
    synthTemplateVersion:
        (raw['synthTemplateVersion'] as String?)?.trim() ?? '',
    fusionSynthTemplateVersion:
        (raw['fusionSynthTemplateVersion'] as String?)?.trim() ?? '',
    phaseOneResult: raw['phaseOneResult'] is ReactRuntimeResult
        ? raw['phaseOneResult'] as ReactRuntimeResult
        : const ReactRuntimeResult(finalText: '', traces: []),
    synthesisReadiness: raw['synthesisReadiness'] is SynthesisReadinessResult
        ? raw['synthesisReadiness'] as SynthesisReadinessResult
        : const SynthesisReadinessResult(),
    evidenceLedger: const <EvidenceLedgerEntry>[],
    evidenceEvaluation: raw['evidenceEvaluation'] is EvidenceEvaluationResult
        ? raw['evidenceEvaluation'] as EvidenceEvaluationResult
        : const EvidenceEvaluationResult(),
    toolResults: const <AssistantToolResultRow>[],
    supplementalTraces: (raw['supplementalTraces'] as List?)
            ?.whereType<AssistantTraceEvent>()
            .toList(growable: false) ??
        const <AssistantTraceEvent>[],
  );
}

const String _phaseOneRenderableBlockedEnvelope =
    '{"contractId":"assistant_turn","messageKind":"answer","phaseId":"answering","actionCode":"compose_answer","reasonCode":"need_more_evidence","decision":{"nextAction":"answer"},"userMarkdown":"## 初步结论\\n\\n- 先给你一版受限答案。","result":{"text":"先给你一版受限答案。","summary":"先给你一版受限答案。","interpretation":"bounded_answer"},"selfCheck":{"goalSatisfied":true,"constraintSatisfied":true,"safetyBoundarySatisfied":true,"failedItems":[]},"diagnostics":{"emergedTags":[],"failedChecks":[],"parseStatus":"","notes":[]}}';

const String _synthesisRenderableReplanEnvelope =
    '{"contractId":"assistant_turn","messageKind":"answer","phaseId":"answering","actionCode":"compose_answer","reasonCode":"need_more_evidence","decision":{"nextAction":"replan"},"userMarkdown":"根据当前预报，深圳明天可能下雨，但我还要继续补查更稳的来源。","result":{"text":"根据当前预报，深圳明天可能下雨，但我还要继续补查更稳的来源。","summary":"当前仍需继续补查","interpretation":"bounded_answer"},"selfCheck":{"goalSatisfied":true,"constraintSatisfied":true,"safetyBoundarySatisfied":true,"failedItems":[]},"diagnostics":{"emergedTags":[],"failedChecks":[],"parseStatus":"","notes":[]}}';

void main() {
  group('Retrieval blocked replan guard', () {
    test('kernel 在 needExpansion 时优先 replan 而不是 bounded answer', () {
      const kernel = ConversationStateKernel();
      final decision = kernel.evaluate(
        domainId: 'weather',
        problemClass: ProblemClass.realtimeInfo.wireName,
        intentGraph: const IntentGraph(
          userGoal: '判断是否需要继续补查天气证据',
          problemShape: ProblemShape.singleSkill,
          primarySkill: 'weather',
          problemClass: ProblemClass.realtimeInfo,
          requiresExternalEvidence: true,
        ),
        queryTasks: const <QueryTask>[
          QueryTask(
            id: 'weather_today',
            query: '深圳 天气 实时',
            dimension: QueryTaskDimension.currentState,
          ),
        ],
        dialogueRoundScript: const DialogueRoundScript(domainId: 'weather'),
        aggregationState: const AggregationState(
          canGivePartialAnswer: true,
          needExpansion: true,
        ),
        answerPayload: <String, dynamic>{
          'decision': <String, dynamic>{'nextAction': 'answer'},
          'messageKind': 'answer',
          'result': <String, dynamic>{
            'text': '先给你一版受限答案。',
            'interpretation': 'bounded_answer',
          },
        },
        previousSlotState: const SlotStateSnapshot(domainId: 'weather'),
        evidenceEvaluation: const EvidenceEvaluationResult(
          entries: <EvidenceLedgerEntry>[
            EvidenceLedgerEntry(evidenceId: 'evidence_1'),
          ],
          status: EvidenceStatus.retry,
          passed: false,
          evidenceRequired: true,
          coveredDimensions: <String>['current_state'],
          missingDimensions: <String>['risk_boundaries'],
          summary: '还缺风险边界维度。',
        ),
        slotSchema: const SlotSchema(
          requiredSlots: <String>[],
          optionalSlots: <String>[],
          carryOver: true,
          stateId: 'weather',
          nextStateId: 'weather_answer',
        ),
      );

      expect(decision.nextActionType, AssistantNextAction.toolCall);
      expect(decision.finalAnswerModeType, FinalAnswerMode.replan);
      expect(decision.finalAnswerReady, isFalse);
    });

    test('renderable blocked + replanTask 会继续 formal synthesis 而不是 shortcut', () async {
      final tempDir = await Directory.systemTemp.createTemp(
        'assistant_retrieval_replan_guard_',
      );
      final provider = _StaticEnvelopeProvider(_synthesisRenderableReplanEnvelope);
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

      try {
        final response = await owner.synthesizeBridge(
          const AssistantRunRequest(
            sessionId: 'renderable_blocked_with_replan',
            messages: <AssistantRunMessage>[
              AssistantRunMessage(role: 'user', content: '明天深圳会下雨吗？'),
            ],
          ),
          executionSnapshot: _buildExecutionSnapshot(<String, dynamic>{
            'runId': 'run_renderable_blocked_with_replan',
            'traceId': 'trace_renderable_blocked_with_replan',
            'sessionId': 'renderable_blocked_with_replan',
            'latestUserQuery': '明天深圳会下雨吗？',
            'domainId': 'weather',
            'contextAssembly': const ContextAssemblyResult(),
            'intentGraph': const IntentGraph(
              userGoal: '判断明天深圳是否会下雨',
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
            'answerBoundaryPolicy': const <String, dynamic>{},
            'templateVariables': const <String, dynamic>{},
            'messages': const <Map<String, dynamic>>[
              <String, dynamic>{'role': 'user', 'content': '明天深圳会下雨吗？'},
            ],
            'synthTemplateVersion': 'test',
            'phaseOneResult': const ReactRuntimeResult(
              finalText: _phaseOneRenderableBlockedEnvelope,
              traces: <AssistantTraceEvent>[],
            ),
            'synthesisReadiness': const SynthesisReadinessResult(
              ready: false,
              reason: 'freshness_pending',
              replanTask: ContextFillTask(
                fillType: ContextFillType.replan,
                targetSlot: ContextTargetSlot.realtimeEvidence,
                reason: '当前还要继续补齐更稳的天气来源。',
                generatedQueryConditions: <String>['深圳 2026-04-10 天气预报'],
                scopeExpansionPolicy:
                    ContextScopeExpansionPolicy.expandTimeWindow,
              ),
            ),
            'supplementalTraces': const <AssistantTraceEvent>[],
            'understandingSnapshot': const <String, dynamic>{
              'userFacingSummary': '我先确认明天深圳的降雨概率。',
            },
            'retrievalProcessing': const <String, dynamic>{
              'processingSummary': '当前证据还不够稳，需要继续补查。',
            },
            'blockedProcessStepId': ProcessStepId.retrievalProcessing.wireName,
            'blockedProcessMessage': '当前证据仍需补齐。',
          }),
        );

        final routing =
            (response.structuredResponse['phaseOneRoutingDiagnostics'] as Map?)
                ?.cast<String, dynamic>() ??
            const <String, dynamic>{};
        final decision =
            (response.structuredResponse['conversationStateDecision'] as Map?)
                ?.cast<String, dynamic>() ??
            const <String, dynamic>{};

        expect(provider.callCount, greaterThan(0));
        expect(routing['route'], equals('formal_synthesis'));
        expect(decision['nextAction'], equals('tool_call'));
        expect(decision['finalAnswerMode'], equals('replan'));
      } finally {
        if (await tempDir.exists()) {
          await tempDir.delete(recursive: true);
        }
      }
    });
  });
}
