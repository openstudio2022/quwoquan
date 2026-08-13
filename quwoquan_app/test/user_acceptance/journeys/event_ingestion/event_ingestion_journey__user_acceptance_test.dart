/// 分工声明（防「空壳绿灯」误读）：本旅程的角色是**事件触发器**——在真实
/// production Remote 会话下执行创作入口动作，产生行为事件流量；事件是否
/// 真实落入观测管道由绑定它的 ES provider conformance runner
/// （`ext_obs_elasticsearch_provider_conformance.py`）在服务侧断言。
/// 本用例自身承诺的是：动作旅程不产生错误终态且首页壳可恢复。
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/runtime/testing/test_keys.dart';
import '../../../support/runtime/patrol/patrol_test_support.dart';

import '../../../support/runtime/patrol/home_create_entry.dart';

void main() {
  patrolTest(
    'ops_event_ingestion_journey',
    tags: ['user-acceptance', 'ops', 'event'],
    skip: !kRunPatrolAcceptance,
    config: PatrolTesterConfig(visibleTimeout: const Duration(seconds: 10)),
    ($) async {
      await launchPatrolAppOnce($);

      // 创作入口已迁移到底部导航「+」（DiscoveryPage 已不在主导航）。
      await openCreateActionSheet($);

      await $(TestKeys.createActionWrite).tap();
      await $(
        TestKeys.createPage,
      ).waitUntilVisible(timeout: const Duration(seconds: 10));

      expect($(TestKeys.createCloseButton).visible, isTrue);
      await $(TestKeys.createCloseButton).tap();
      await waitForHomeShell($);
    },
  );
}
