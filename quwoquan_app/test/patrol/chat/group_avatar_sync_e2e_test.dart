/// T4 Patrol E2E: 群头像同步旅程入口
library;

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/core/testing/patrol_test_support.dart';

void main() {
  patrolTest(
    '群头像同步旅程可启动应用',
    tags: ['t4', 'chat', 'avatar'],
    skip: !kRunPatrolT4,
    config: PatrolTesterConfig(visibleTimeout: const Duration(seconds: 20)),
    ($) async {
      // 真实群头像同步正确性由 chat-avatar probe 覆盖；
      // Patrol 侧确保同一套远端配置下应用可成功启动并进入可渲染状态。
      await launchPatrolAppOnce($);
      await $.pump(const Duration(seconds: 2));

      expect(find.byType(WidgetsApp), findsOneWidget);
    },
  );
}
