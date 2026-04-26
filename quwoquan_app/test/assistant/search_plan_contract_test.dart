import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/domain/conversation/conversation.dart';

void main() {
  group('search plan contract', () {
    test('normalizeList 将 label/dimension 收口为 typed contract', () {
      final plans = SearchPlanItem.normalizeList(<Object>[
        <String, dynamic>{
          'id': 'tradeoffs',
          'query': 'A 和 B 区别',
          'label': '关键取舍',
          'dimension': '关键取舍',
          'answerShape': 'comparison',
          'freshnessNeed': 'recent',
        },
      ]);

      expect(plans, hasLength(1));
      expect(plans.first.dimension, SearchPlanDimension.tradeoffs);
      expect(plans.first.dimensionCode, 'tradeoffs');
      expect(plans.first.answerShape, AnswerShape.comparison);
      expect(plans.first.freshnessNeed, FreshnessNeed.recent);
      expect(plans.first.toJson()['dimensionLabel'], '关键取舍');
    });

    test('支持 authorityDomains 与 freshnessHoursMax roundtrip', () {
      final plan = SearchPlanItem.fromJson(<String, dynamic>{
        'id': 'weather_now',
        'query': '深圳天气 实时',
        'label': '当前状态',
        'dimension': 'current_state',
        'authorityDomains': <String>['weather.com.cn', 'cma.cn'],
        'freshnessHoursMax': 1,
      });

      expect(plan.authorityDomains, <String>['weather.com.cn', 'cma.cn']);
      expect(plan.freshnessHoursMax, 1);
      expect(plan.toJson()['authorityDomains'], <String>[
        'weather.com.cn',
        'cma.cn',
      ]);
      expect(plan.toJson()['freshnessHoursMax'], 1);
    });

    test('unknown dimension 保持安全默认值', () {
      final plan = SearchPlanItem.fromJson(<String, dynamic>{
        'query': '随便查一下',
        'dimension': '未定义维度',
      });

      expect(plan.dimension, SearchPlanDimension.unknown);
      expect(plan.toJson().containsKey('dimension'), isFalse);
    });
  });
}
