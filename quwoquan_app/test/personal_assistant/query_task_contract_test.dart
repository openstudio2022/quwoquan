import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/personal_assistant/contracts/query_task_contract.dart';
import 'package:quwoquan_app/personal_assistant/contracts/runtime_enums.dart';

void main() {
  group('query task contract', () {
    test('normalizeList 将 legacy label/dimension 收口为 typed contract', () {
      final tasks = QueryTask.normalizeList(<Object>[
        <String, dynamic>{
          'id': 'tradeoffs',
          'query': 'A 和 B 区别',
          'label': '关键取舍',
          'dimension': '关键取舍',
          'answerShape': 'comparison',
          'freshnessNeed': 'recent',
        },
      ]);

      expect(tasks, hasLength(1));
      expect(tasks.first.dimension, QueryTaskDimension.tradeoffs);
      expect(tasks.first.dimensionCode, 'tradeoffs');
      expect(tasks.first.answerShape, AnswerShape.comparison);
      expect(tasks.first.freshnessNeed, FreshnessNeed.recent);
      expect(tasks.first.toJson()['dimensionLabel'], '关键取舍');
    });

    test('unknown dimension 保持安全默认值', () {
      final task = QueryTask.fromJson(<String, dynamic>{
        'query': '随便查一下',
        'dimension': '未定义维度',
      });

      expect(task.dimension, QueryTaskDimension.unknown);
      expect(task.toJson().containsKey('dimension'), isFalse);
    });
  });
}
