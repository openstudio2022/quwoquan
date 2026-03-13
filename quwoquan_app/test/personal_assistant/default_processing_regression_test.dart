import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/personal_assistant/contracts/aggregation_state.dart';
import 'package:quwoquan_app/personal_assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/personal_assistant/engine/conversation_state_kernel.dart';
import 'package:quwoquan_app/personal_assistant/engine/default_processing/evidence_evaluator.dart';
import 'package:quwoquan_app/personal_assistant/engine/default_processing/problem_framer.dart';
import 'package:quwoquan_app/personal_assistant/engine/default_processing/retrieval_planner.dart';
import 'package:quwoquan_app/personal_assistant/engine/dialogue_state_runtime.dart';

void main() {
  group('Default processing regression', () {
    const framer = DefaultProblemFramer();
    const planner = DefaultRetrievalPlanner();
    const evaluator = DefaultEvidenceEvaluator();

    test('真实住宿追问会被识别为九寨沟方向备选方案问题', () {
      final frame = framer.frame('如果把九寨沟方向考虑进去，多给我几个备选方案');

      expect(frame.queryIntent, 'travelAlternativeOptions');
      expect(frame.problemClass, 'complex_reasoning');
      expect(frame.city, '九寨沟');
    });

    test('真实观赏问题会被识别为土拨鼠观赏时间问题', () {
      final frame = framer.frame('土拨鼠观赏最佳时间');

      expect(frame.queryIntent, 'wildlifeBestTime');
      expect(frame.problemClass, 'evidence_lookup');
      expect(frame.city, isEmpty, reason: '不应再用危险兜底把前 2~4 个汉字误判成城市');
    });

    test('检索规划会为两类真实问题生成专属维度', () {
      final travelPlan = planner.plan(
        frame: framer.frame('如果把九寨沟方向考虑进去，多给我几个备选方案'),
        availableTools: const <String>['web_search'],
      );
      final wildlifePlan = planner.plan(
        frame: framer.frame('土拨鼠观赏最佳时间'),
        availableTools: const <String>['web_search'],
      );

      expect(travelPlan, isNotNull);
      expect(
        travelPlan!.queryTasks.map((item) => item['dimension']).toList(),
        containsAll(<String>['候选路线', '适用条件', '关键取舍']),
      );
      expect(
        travelPlan.blockingDimensions,
        containsAll(<String>['候选路线', '适用条件']),
      );

      expect(wildlifePlan, isNotNull);
      expect(
        wildlifePlan!.queryTasks.map((item) => item['dimension']).toList(),
        containsAll(<String>['季节窗口', '日内时段', '天气条件']),
      );
      expect(
        wildlifePlan.blockingDimensions,
        containsAll(<String>['季节窗口', '日内时段', '天气条件']),
      );
    });

    test('证据评估可把未满配的资料判为 bounded', () {
      final result = evaluator.evaluate(
        ledger: const <EvidenceLedgerEntry>[
          EvidenceLedgerEntry(
            evidenceId: 'a',
            dimension: '季节窗口',
            queryTaskId: 'wildlife_season',
            title: '季节资料',
            url: 'https://example.com/season',
            sourceTier: 'authority',
            authorityScore: 0.92,
            relevanceScore: 0.88,
            freshnessHours: 24,
          ),
          EvidenceLedgerEntry(
            evidenceId: 'b',
            dimension: '日内时段',
            queryTaskId: 'wildlife_daytime',
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
        blockingDimensions: const <String>['季节窗口', '日内时段', '天气条件'],
      );

      expect(result.status, 'bounded');
      expect(result.passed, isFalse);
      expect(result.missingDimensions, contains('天气条件'));
    });

    test('ConversationStateKernel 对 bounded_answer 不再阻塞成答', () {
      final kernel = ConversationStateKernel(problemFramer: framer);
      final slotSchema = kernel.defaultSlotSchema(
        query: '土拨鼠观赏最佳时间',
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
          status: 'bounded',
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

      expect(decision.nextAction, 'answer');
      expect(decision.finalAnswerMode, 'bounded_answer');
      expect(decision.finalAnswerReady, isTrue);
      expect(decision.answerEligibility, 'eligible');
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
