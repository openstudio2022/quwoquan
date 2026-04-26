import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_plan_view.dart';
import 'package:quwoquan_app/assistant/contracts/task_graph_contract.dart';
import 'package:quwoquan_app/assistant/contracts/understanding_result_contract.dart';
import 'package:quwoquan_app/assistant/domain/conversation/conversation.dart';

void main() {
  group('Typed planning contracts', () {
    test('UnderstandingResult + TaskGraph materialize AssistantPlanView', () {
      final understanding = UnderstandingResult.fromJson(
        const <String, dynamic>{
          'intents': <Map<String, dynamic>>[
            <String, dynamic>{
              'intentId': 'intent_weather',
              'intentType': 'weather.lookup',
              'goal': '查看深圳天气并规划旅游',
              'entityRefs': <Map<String, dynamic>>[
                <String, dynamic>{
                  'entityType': 'city',
                  'canonicalKey': 'shenzhen',
                  'displayText': '深圳',
                },
              ],
              'requiresEvidence': true,
            },
            <String, dynamic>{
              'intentId': 'intent_travel',
              'intentType': 'travel.plan',
              'goal': '结合天气补充旅游建议',
            },
          ],
        },
      );
      final taskGraph = TaskGraph.fromJson(
        const <String, dynamic>{
          'tasks': <Map<String, dynamic>>[
            <String, dynamic>{
              'taskId': 'task_weather',
              'intentId': 'intent_weather',
              'toolName': 'web_search',
              'toolArgs': <String, dynamic>{
                'searchPlans': <Map<String, dynamic>>[
                  <String, dynamic>{
                    'id': 'weather_latest',
                    'query': '深圳 今天 天气 预报',
                    'dimension': 'latest_signal',
                    'entityRefs': <String>['深圳'],
                    'authorityDomains': <String>['weather.cma.cn'],
                    'freshnessHoursMax': 1,
                  },
                ],
              },
            },
          ],
        },
      );

      final planView = assistantPlanViewFromTypedMainline(
        understandingResult: understanding,
        taskGraph: taskGraph,
      );
      final searchPlans = searchPlansFromTaskGraph(taskGraph);

      expect(planView, isNotNull);
      expect(planView!.primarySkill, 'weather');
      expect(planView.problemShape, ProblemShape.multiSkill);
      expect(planView.problemClass, ProblemClass.realtimeInfo);
      expect(planView.entityRefs, <String>['深圳']);
      expect(planView.requiresExternalEvidence, isTrue);
      expect(searchPlans.single.dimension, SearchPlanDimension.latestSignal);
      expect(searchPlans.single.authorityDomains, <String>['weather.cma.cn']);
    });

    test('SearchPlanItem preserves typed retrieval fields', () {
      final plan = SearchPlanItem.fromJson(
        const <String, dynamic>{
          'id': 'candidate_space',
          'query': '深圳住宿 推荐 区域',
          'dimension': 'candidate_space',
          'entityRefs': <String>['深圳'],
          'negativeKeywords': <String>['广告'],
          'freshnessHoursMax': 24,
          'answerShape': 'options',
          'freshnessNeed': 'recent',
        },
      );

      expect(plan.dimension, SearchPlanDimension.candidateSpace);
      expect(plan.entityRefs, <String>['深圳']);
      expect(plan.negativeKeywords, <String>['广告']);
      expect(plan.freshnessHoursMax, 24);
      expect(plan.answerShape, AnswerShape.options);
      expect(plan.freshnessNeed, FreshnessNeed.recent);
      expect(plan.toJson()['entityRefs'], <String>['深圳']);
    });
  });
}
