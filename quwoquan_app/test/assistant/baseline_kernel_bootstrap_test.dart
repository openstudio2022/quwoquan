import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/reasoning/runtime/baseline_kernel.dart';

void main() {
  group('BaselineKernel bootstrap', () {
    const kernel = BaselineKernel();

    test('实时问题可产出稳定通用 problem frame', () {
      final frame = kernel.frame(
        '深圳市天气怎么样',
        intentPayload: const <String, dynamic>{
          'problemClass': 'realtime_info',
          'requiresExternalEvidence': true,
        },
      );

      expect(frame.primaryDomainId, equals('fallback_general_search'));
      expect(frame.problemClass, equals('realtime_info'));
      expect(frame.city, equals('深圳市'));
      expect(
        frame.toIntentPayload()['queryNormalization'],
        containsPair('city', '深圳市'),
      );
    });

    test('多方案问题可产出多 queryTasks 检索计划', () {
      final plan = kernel.buildRetrievalPlan(
        '深圳住宿怎么选',
        const <String>['web_search'],
        intentPayload: const <String, dynamic>{
          'problemClass': 'complex_reasoning',
          'answerShape': 'options',
          'requiresExternalEvidence': true,
        },
      );

      expect(plan, isNotNull);
      expect(plan!.calls.single.name, equals('web_search'));
      final queryTasks =
          (plan.calls.single.arguments['queryTasks'] as List?)
              ?.whereType<Map>()
              .toList(growable: false) ??
          const <Map>[];
      expect(queryTasks.length, equals(3));
      expect(
        queryTasks.map((task) => task['id']).toList(),
        containsAll(<String>['candidate_space', 'fit_scenarios', 'risks']),
      );
    });

    test('普通问答在有 web_search 时退回单路默认检索', () {
      final plan = kernel.buildRetrievalPlan(
        '帮我了解下深圳博物馆开放时间',
        const <String>['web_search'],
        intentPayload: const <String, dynamic>{
          'problemClass': 'simple_qa',
          'requiresExternalEvidence': true,
        },
      );

      expect(plan, isNotNull);
      expect(plan!.calls.single.arguments['query'], contains('深圳博物馆开放时间'));
    });
  });
}
