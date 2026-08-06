library;

import 'package:patrol/patrol.dart';
import '../../../../../support/runtime/patrol/patrol_test_support.dart';

import '../../../../../support/runtime/patrol/assistant_provider_journey_support.dart';

void main() {
  patrolTest(
    '真实公共搜索结果进入助手答案',
    tags: const ['user-acceptance', 'assistant', 'provider', 'search'],
    skip: !kRunPatrolAcceptance,
    ($) => runAssistantProviderJourney(
      $,
      prompt: '请打开公开 HTTPS 页面 https://example.com ，仅根据读到的网页内容说明页面标题，并附可回查引用。',
      expectedAnswerFragment: 'Example Domain',
      expectedCitationHost: 'example.com',
    ),
  );
}
