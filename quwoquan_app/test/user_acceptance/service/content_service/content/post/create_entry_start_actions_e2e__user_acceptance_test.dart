/// user_acceptance Patrol: 内容优先创作入口
///
/// 守护：底部导航「+」直达内容创作选项，不暴露无上下文活动入口。
///
/// 意图边界：本旅程验证创作入口的结构可达性与编辑器就绪（游客可见动作
/// 面板的登录门契约由 login-entry 合约测试承载），不依赖 feed 数据，
/// 因此没有非空列表断言——这是设计意图而非空页缺口。
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';

import '../../../../../support/runtime/patrol/patrol_test_support.dart';

import 'package:quwoquan_app/runtime/testing/test_keys.dart';

import '../../../../../support/runtime/patrol/home_create_entry.dart';

void main() {
  patrolTest(
    'create_entry_start_actions — 底部导航「+」内容优先且不暴露活动',
    tags: ['user-acceptance', 'content', 'create'],
    skip: !kRunPatrolAcceptance,
    config: PatrolTesterConfig(visibleTimeout: const Duration(seconds: 10)),
    ($) async {
      await launchPatrolAppOnce($);

      // 创作入口已迁移到底部导航「+」（DiscoveryPage 已不在主导航）。
      await openCreateActionSheet($);

      expect($(TestKeys.createActionGallery).visible, isTrue);
      expect($(TestKeys.createActionCapture).visible, isTrue);
      expect($(TestKeys.createActionWrite).visible, isTrue);
      // 「+」面板只承载内容创作三入口；活动发起已随行动 Tab 下线，不再是可产出的 key，
      // 正向断言三入口可见即锁定当前面板闭集。
      await $(TestKeys.createActionWrite).tap();
      await $(TestKeys.createPage)
          .waitUntilVisible(timeout: const Duration(seconds: 10));
      expect($(TestKeys.createMomentInput).visible, isTrue);
    },
  );
}
