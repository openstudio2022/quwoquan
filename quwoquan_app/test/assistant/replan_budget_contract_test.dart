import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/protocol/run_request.dart';

void main() {
  group('AssistantRunRequest replan budget', () {
    test('default budget stays at normal 2 stages + max 3 requery rounds', () {
      const request = AssistantRunRequest(
        messages: <AssistantRunMessage>[
          AssistantRunMessage(role: 'user', content: '昨天A股为什么大涨'),
        ],
      );

      expect(
        request.totalModelStageBudget,
        AssistantRunRequest.defaultTotalModelStageBudget,
      );
      expect(
        request.plannerStageBudget,
        AssistantRunRequest.defaultNormalModelStageBudget - 1,
      );
      expect(request.answerStageBudget, 4);
      expect(
        request.maxRequeryRounds,
        AssistantRunRequest.defaultMaxRequeryRounds,
      );
    });

    test('custom total budget still derives answer-stage and requery budgets', () {
      const request = AssistantRunRequest(
        maxIterations: 4,
        messages: <AssistantRunMessage>[
          AssistantRunMessage(role: 'user', content: '明天深圳天气怎么样'),
        ],
      );

      expect(request.totalModelStageBudget, 4);
      expect(request.answerStageBudget, 3);
      expect(request.maxRequeryRounds, 2);
    });

    test('gateway body without explicit budget falls back to total 5', () {
      final request = AssistantRunRequest.fromGatewayBody(<String, dynamic>{
        'messages': <Map<String, dynamic>>[
          <String, dynamic>{'role': 'user', 'content': '明天深圳天气怎么样'},
        ],
      });

      expect(request.totalModelStageBudget, 5);
      expect(request.answerStageBudget, 4);
      expect(request.maxRequeryRounds, 3);
    });
  });
}
