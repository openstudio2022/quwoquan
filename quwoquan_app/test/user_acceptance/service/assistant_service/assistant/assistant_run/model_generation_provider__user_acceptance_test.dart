library;

import 'package:patrol/patrol.dart';
import '../../../../../support/runtime/patrol/patrol_test_support.dart';

import '../../../../../support/runtime/patrol/assistant_provider_journey_support.dart';

void main() {
  patrolTest(
    '真实模型生成返回指定答案',
    tags: const ['user-acceptance', 'assistant', 'provider', 'model'],
    skip: !kRunPatrolAcceptance,
    ($) => runAssistantProviderJourney(
      $,
      prompt: '请只回复 QWQ-MODEL-READY，不要添加其他文字。',
      expectedAnswerFragment: 'QWQ-MODEL-READY',
    ),
  );
}
