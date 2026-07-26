library;

import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/core/testing/patrol_test_support.dart';

import 'provider_journey_support.dart';

void main() {
  patrolTest(
    '真实行情 Provider 返回 AAPL 行情',
    tags: const ['t4', 'assistant', 'provider', 'finance'],
    skip: !kRunPatrolT4,
    ($) => runAssistantProviderJourney(
      $,
      prompt: '请查询 AAPL 最新行情，答案中必须包含股票代码 AAPL。',
      expectedAnswerFragment: 'AAPL',
    ),
  );
}
