import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/personal_assistant/engine/default_processing/baseline_kernel.dart';

void main() {
  group('BaselineKernel bootstrap', () {
    const kernel = BaselineKernel();

    test('天气问题可产出稳定 problem frame', () {
      final frame = kernel.frame('深圳天气怎么样');

      expect(frame.primaryDomainId, equals('weather'));
      expect(frame.problemClass, equals('realtime_info'));
      expect(frame.city, equals('深圳'));
      expect(frame.toIntentPayload()['queryNormalization'], containsPair('city', '深圳'));
    });

    test('住宿规划可产出多 queryTasks 检索计划', () {
      final plan = kernel.buildRetrievalPlan(
        '深圳住宿怎么选',
        const <String>['web_search'],
      );

      expect(plan, isNotNull);
      expect(plan!.calls.single.name, equals('web_search'));
      final queryTasks =
          (plan.calls.single.arguments['queryTasks'] as List?)
              ?.whereType<Map>()
              .toList(growable: false) ??
          const <Map>[];
      expect(queryTasks.length, equals(3));
    });

    test('普通问答在有 web_search 时退回单路默认检索', () {
      final plan = kernel.buildRetrievalPlan(
        '帮我了解下深圳博物馆开放时间',
        const <String>['web_search'],
      );

      expect(plan, isNotNull);
      expect(plan!.calls.single.arguments['query'], contains('深圳博物馆开放时间'));
    });
  });
}
