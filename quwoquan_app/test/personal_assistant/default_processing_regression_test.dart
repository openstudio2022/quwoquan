import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/personal_assistant/contracts/aggregation_state.dart';
import 'package:quwoquan_app/personal_assistant/contracts/assistant_turn_contract.dart';
import 'package:quwoquan_app/personal_assistant/contracts/dialogue_round_script.dart';
import 'package:quwoquan_app/personal_assistant/contracts/planner_contracts.dart';
import 'package:quwoquan_app/personal_assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/personal_assistant/engine/conversation_state_kernel.dart';
import 'package:quwoquan_app/personal_assistant/engine/default_processing/evidence_evaluator.dart';
import 'package:quwoquan_app/personal_assistant/engine/default_processing/problem_framer.dart';
import 'package:quwoquan_app/personal_assistant/engine/default_processing/retrieval_planner.dart';

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
      expect(
        travelPlan.blockingDimensions,
        contains('候选范围'),
      );

      expect(wildlifePlan, isNotNull);
      expect(
        wildlifePlan!.queryTasks.map((item) => item.id).toList(),
        containsAll(<String>['key_facts', 'decision_threshold']),
      );
      expect(
        wildlifePlan.blockingDimensions,
        isNotEmpty,
      );
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
      expect(result.missingDimensions, contains('最新变化'));
    });

    test('ConversationStateKernel 对 bounded_answer 不再阻塞成答', () {
      final kernel = ConversationStateKernel(problemFramer: framer);
      final slotSchema = kernel.defaultSlotSchema(
        domainId: 'fallback_general_search',
        problemClass: 'evidence_lookup',
        dialogueRoundScript: _dialogueScript(),
      );
      final decision = kernel.evaluate(
        query: '土拨鼠观赏最佳时间',
        domainId: 'fallback_general_search',
        problemClass: 'evidence_lookup',
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
