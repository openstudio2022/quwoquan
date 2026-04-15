import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/contracts/answer_boundary_policy.dart';
import 'package:quwoquan_app/assistant/contracts/aggregation_state.dart';
import 'package:quwoquan_app/assistant/contracts/conversation_state_decision.dart';
import 'package:quwoquan_app/assistant/contracts/retrieval_outcome.dart';
import 'package:quwoquan_app/assistant/domain/conversation/conversation.dart';
import 'package:quwoquan_app/assistant/context/assembly/conversation_state_kernel.dart';
import 'package:quwoquan_app/assistant/context/assembly/evidence_evaluator.dart';
import 'package:quwoquan_app/assistant/reasoning/planner/problem_framer.dart';
import 'package:quwoquan_app/assistant/reasoning/planner/retrieval_planner.dart';
import 'package:quwoquan_app/assistant/reasoning/runtime/answer_gate_resolver.dart';

void main() {
  group('Default processing regression', () {
    const framer = DefaultProblemFramer();
    const planner = DefaultRetrievalPlanner();
    const evaluator = DefaultEvidenceEvaluator();

    test('多方案探索问题走通用 options_exploration 合同', () {
      final frame = framer.frame(
        '如果把九寨沟方向考虑进去，多给我几个备选方案',
        intentPayload: const <String, dynamic>{
          'queryIntent': 'options_exploration',
          'problemClass': 'complex_reasoning',
          'answerShape': 'options',
          'requiresExternalEvidence': true,
        },
      );

      expect(frame.queryIntent, 'options_exploration');
      expect(frame.problemClass, 'complex_reasoning');
      expect(frame.answerShape, 'options');
      expect(frame.city, '九寨沟');
    });

    test('需要依据判断的问题走通用 evidence_lookup 合同', () {
      final frame = framer.frame(
        '土拨鼠观赏最佳时间',
        intentPayload: const <String, dynamic>{
          'problemClass': 'evidence_lookup',
          'requiresExternalEvidence': true,
        },
      );

      expect(frame.problemClass, 'evidence_lookup');
      expect(frame.requiresExternalEvidence, isTrue);
      expect(frame.city, isEmpty, reason: '不应再用危险兜底把前 2~4 个汉字误判成城市');
    });

    test('检索规划使用通用 queryTask id，而不是垂类专属维度名', () {
      final travelPlan = planner.plan(
        frame: framer.frame(
          '如果把九寨沟方向考虑进去，多给我几个备选方案',
          intentPayload: const <String, dynamic>{
            'problemClass': 'complex_reasoning',
            'answerShape': 'options',
            'requiresExternalEvidence': true,
          },
        ),
        availableTools: const <String>['web_search'],
      );
      final wildlifePlan = planner.plan(
        frame: framer.frame(
          '土拨鼠观赏最佳时间',
          intentPayload: const <String, dynamic>{
            'problemClass': 'evidence_lookup',
            'answerShape': 'decision_ready',
            'requiresExternalEvidence': true,
          },
        ),
        availableTools: const <String>['web_search'],
      );

      expect(travelPlan, isNotNull);
      expect(
        travelPlan!.queryTasks.map((item) => item.id).toList(),
        containsAll(<String>['candidate_space', 'fit_scenarios', 'risks']),
      );
      expect(travelPlan.blockingDimensions, contains('候选范围'));

      expect(wildlifePlan, isNotNull);
      expect(
        wildlifePlan!.queryTasks.map((item) => item.id).toList(),
        containsAll(<String>['key_facts', 'decision_threshold']),
      );
      expect(wildlifePlan.blockingDimensions, isNotEmpty);
    });

    test('检索规划在 search 可用时优先 search 且默认 mode=result', () {
      final plan = planner.plan(
        frame: framer.frame(
          '摄影入门需要准备什么？',
          intentPayload: const <String, dynamic>{
            'problemClass': 'evidence_lookup',
            'requiresExternalEvidence': true,
          },
        ),
        availableTools: const <String>['search', 'web_search'],
      );

      expect(plan, isNotNull);
      expect(plan!.calls, isNotEmpty);
      expect(plan.calls.first.name, equals('search'));
      expect(plan.calls.first.arguments['mode'], equals('result'));
      expect(plan.calls.first.arguments['query'], isNotEmpty);
    });

    test('证据评估可把未满配的资料判为 bounded', () {
      final result = evaluator.evaluate(
        ledger: const <EvidenceLedgerEntry>[
          EvidenceLedgerEntry(
            evidenceId: 'a',
            dimension: '关键事实',
            queryTaskId: 'key_facts',
            title: '季节资料',
            url: 'https://example.com/season',
            sourceTier: 'authority',
            authorityScore: 0.92,
            relevanceScore: 0.88,
            freshnessHours: 24,
          ),
          EvidenceLedgerEntry(
            evidenceId: 'b',
            dimension: '判断条件',
            queryTaskId: 'decision_threshold',
            title: '时段资料',
            url: 'https://example.com/daytime',
            sourceTier: 'authority',
            authorityScore: 0.91,
            relevanceScore: 0.84,
            freshnessHours: 12,
          ),
        ],
        evidenceRequired: true,
        authorityRequired: true,
        freshnessHoursMax: 72,
        blockingDimensions: const <String>['关键事实', '判断条件', '最新变化'],
      );

      expect(result.status, EvidenceStatus.bounded);
      expect(result.passed, isFalse);
      expect(
        result.missingDimensions,
        contains(QueryTaskDimension.latestSignal.wireName),
      );
    });

    test('ConversationStateKernel 对 bounded_answer 不再阻塞成答', () {
      const kernel = ConversationStateKernel();
      final slotSchema = kernel.defaultSlotSchema(
        domainId: 'fallback_general_search',
        problemClass: 'evidence_lookup',
        dialogueRoundScript: _dialogueScript(),
      );
      final decision = kernel.evaluate(
        domainId: 'fallback_general_search',
        problemClass: 'evidence_lookup',
        intentGraph: const IntentGraph(
          userGoal: '土拨鼠观赏最佳时间',
          problemShape: ProblemShape.singleSkill,
          primarySkill: 'fallback_general_search',
          problemClass: ProblemClass.evidenceLookup,
          requiresExternalEvidence: true,
        ),
        queryTasks: const <QueryTask>[],
        dialogueRoundScript: _dialogueScript(),
        aggregationState: const AggregationState(
          canGivePartialAnswer: true,
          finalAnswerReady: true,
        ),
        answerPayload: const <String, dynamic>{
          'decision': <String, dynamic>{'nextAction': 'answer'},
        },
        previousSlotState: const SlotStateSnapshot(),
        evidenceEvaluation: const EvidenceEvaluationResult(
          status: EvidenceStatus.bounded,
          evidenceRequired: true,
          entries: <EvidenceLedgerEntry>[
            EvidenceLedgerEntry(
              evidenceId: 'a',
              title: '季节资料',
              url: 'https://example.com',
            ),
          ],
        ),
        slotSchema: slotSchema,
      );

      expect(decision.nextAction, AssistantNextAction.answer);
      expect(decision.finalAnswerMode, FinalAnswerMode.boundedAnswer);
      expect(decision.finalAnswerReady, isTrue);
      expect(decision.answerEligibility, AnswerEligibility.eligible);
    });

    test('ConversationStateKernel 在零证据 bounded 状态下必须回到 replan', () {
      const kernel = ConversationStateKernel();
      final slotSchema = kernel.defaultSlotSchema(
        domainId: 'finance_consumer',
        problemClass: 'evidence_lookup',
        dialogueRoundScript: _dialogueScript(),
      );
      final decision = kernel.evaluate(
        domainId: 'finance_consumer',
        problemClass: 'evidence_lookup',
        intentGraph: const IntentGraph(
          userGoal: 'A股大涨原因',
          problemShape: ProblemShape.singleSkill,
          primarySkill: 'finance_consumer',
          problemClass: ProblemClass.evidenceLookup,
          requiresExternalEvidence: true,
          mustVerifyClaims: true,
        ),
        queryTasks: const <QueryTask>[
          QueryTask(
            id: 'stock_reason',
            query: 'A股大涨原因',
            dimension: QueryTaskDimension.latestSignal,
          ),
        ],
        dialogueRoundScript: _dialogueScript(),
        aggregationState: const AggregationState(
          canGivePartialAnswer: false,
          finalAnswerReady: false,
        ),
        answerPayload: const <String, dynamic>{
          'decision': <String, dynamic>{'nextAction': 'answer'},
        },
        previousSlotState: const SlotStateSnapshot(),
        evidenceEvaluation: const EvidenceEvaluationResult(
          status: EvidenceStatus.bounded,
          evidenceRequired: true,
          passed: false,
          entries: <EvidenceLedgerEntry>[],
          missingDimensions: <String>['latest_signal'],
        ),
        slotSchema: slotSchema,
      );

      expect(decision.nextAction, AssistantNextAction.toolCall);
      expect(decision.finalAnswerMode, FinalAnswerMode.replan);
      expect(decision.finalAnswerReady, isFalse);
      expect(decision.answerEligibility, AnswerEligibility.blocked);
    });

    test('bounded_answer 展示不再复用阻塞式 freshness 文案', () {
      const resolver = AnswerGateResolver();
      final decision = resolver.resolve(
        retrievalOutcome: const RetrievalOutcome(
          evidenceRequired: true,
          authorityRequired: true,
          freshnessRequired: true,
          hasToolResult: true,
          referenceCount: 2,
          authoritySatisfied: true,
          freshnessKnown: true,
          freshnessSatisfied: false,
          terminalPayloadComplete: true,
        ),
        conversationStateDecision: const ConversationStateDecision(
          nextAction: AssistantNextAction.answer,
          finalAnswerMode: FinalAnswerMode.boundedAnswer,
          answerEligibility: AnswerEligibility.blocked,
          finalAnswerReady: false,
        ),
        renderableAnswer: true,
      );

      expect(decision.reasonCode, equals('freshness_unsatisfied'));
      expect(decision.reason, equals('已基于当前可确认信息整理答案，如需补齐最新变化可继续补查。'));
    });
  });
}

DialogueRoundScript _dialogueScript() {
  return const DialogueRoundScript(
    domainId: 'fallback_general_search',
    enabled: true,
    currentStateId: 'S0',
    detectedEvent: 'qa',
    suggestedNextStateId: 'S1',
    nextStateCandidates: <String>['S1'],
    requiredFieldsForNextState: <String>[],
    totalSubTotalRequired: false,
    optionalEnrichment: true,
    maxQuestionsPerTurn: 2,
    hardFailCodes: <String>[],
    passCriteriaRound: <String, dynamic>{},
    statePromptExcerpt: '',
    stateMachineExcerpt: '',
    routingCatalogVersion: 'test',
    eventCatalogVersion: 'test',
  );
}
