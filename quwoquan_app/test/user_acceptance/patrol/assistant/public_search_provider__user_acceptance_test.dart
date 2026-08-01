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
      prompt: '请打开公开 HTTPS 页面 https://example.com ，仅根据读到的网页内容说明页面标题，并附可回查引用。',
      expectedAnswerFragment: 'Example Domain',
      expectedCitationHost: 'example.com',
    ),
  );
}
