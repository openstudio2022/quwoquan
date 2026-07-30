// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/spec.md#sit-001
library;

import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/core/testing/patrol_test_support.dart';

import 'provider_journey_support.dart';

void main() {
  patrolTest(
    '真实天气 Provider 返回北京天气',
    tags: const ['t4', 'assistant', 'provider', 'weather'],
    skip: !kRunPatrolT4,
    ($) => runAssistantProviderJourney(
      $,
      prompt: '请查询北京当前天气，答案中必须包含城市名北京。',
      expectedAnswerFragment: '北京',
    ),
  );
}
