library;

import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/core/testing/patrol_test_support.dart';

import 'provider_journey_support.dart';

void main() {
  patrolTest(
    '真实公共搜索结果进入助手答案',
    tags: const ['t4', 'assistant', 'provider', 'search'],
    skip: !kRunPatrolT4,
    ($) => runAssistantProviderJourney(
      $,
      prompt: '请搜索 OpenAI 官方网站，并在答案中明确写出 OpenAI。',
      expectedAnswerFragment: 'OpenAI',
    ),
  );
}
