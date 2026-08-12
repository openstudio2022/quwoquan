// spec_ref: specs/feature-tree/runtime/runtime-external-integration/provider-adapter-conformance-suite/spec.md#gwt-002
library;

import 'package:patrol/patrol.dart';
import '../../../../../support/runtime/patrol/patrol_test_support.dart';

import '../../../../../support/runtime/patrol/assistant_provider_journey_support.dart';

void main() {
  patrolTest(
    '真实行情 Provider 返回 AAPL 行情',
    tags: const ['user-acceptance', 'assistant', 'provider', 'finance'],
    skip: !kRunPatrolAcceptance,
    ($) => runAssistantProviderJourney(
      $,
      prompt: '请查询 AAPL 最新行情，答案中必须包含股票代码 AAPL。',
      expectedAnswerFragment: 'AAPL',
    ),
  );
}
