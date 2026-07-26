library;

import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/core/testing/patrol_test_support.dart';

import 'provider_journey_support.dart';

void main() {
  patrolTest(
    '真实模型生成返回指定答案',
    tags: const ['t4', 'assistant', 'provider', 'model'],
    skip: !kRunPatrolT4,
    ($) => runAssistantProviderJourney(
      $,
      prompt: '请只回复 QWQ-MODEL-READY，不要添加其他文字。',
      expectedAnswerFragment: 'QWQ-MODEL-READY',
    ),
  );
}
