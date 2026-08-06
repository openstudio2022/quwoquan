// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/spec.md#sit-001
library;

import 'package:patrol/patrol.dart';
import '../../../../../support/runtime/patrol/patrol_test_support.dart';

import '../../../../../support/runtime/patrol/assistant_provider_journey_support.dart';

void main() {
  patrolTest(
    '真实天气 Provider 返回北京天气',
    tags: const ['user-acceptance', 'assistant', 'provider', 'weather'],
    skip: !kRunPatrolAcceptance,
    ($) => runAssistantProviderJourney(
      $,
      prompt: '请查询北京当前天气，答案中必须包含城市名北京。',
      expectedAnswerFragment: '北京',
    ),
  );
}
