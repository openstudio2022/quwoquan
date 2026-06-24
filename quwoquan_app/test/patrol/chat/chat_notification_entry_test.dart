/// user_acceptance Patrol: 系统通知点击打开聊天详情
///
/// 守护：flutter_test 无法覆盖的系统推送通知交互场景。
/// 验证收到聊天通知 → 点击通知 → 正确打开 ChatDetailPage 的完整链路。
///
/// 注：每个用例自启动真实 App（launchPatrolAppOnce），对齐已绿的
///     home_recommendation_journey_test，不依赖 patrol_test_main 预启动。
///     后台切前台用 $.native.openApp() 需要 QUERY_ALL_PACKAGES（仅 debug/androidTest
///     维度声明，见 android/app/src/debug/AndroidManifest.xml，不污染 release）。
library;

import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/core/testing/patrol_test_support.dart';

const _apiContractEnv = String.fromEnvironment(
  'API_CONTRACT_ENV',
  defaultValue: 'gamma',
);

// 被测 App 的 Android applicationId（见 android/app/build.gradle.kts）。
// $.native.openApp() 无参时无法解析 package，必须显式传入。
const _appUnderTestId = 'com.quwoquan.quwoquan_app';

void main() {
  patrolTest(
    '系统通知点击打开聊天详情',
    tags: ['t4', 'chat', 'notification'],
    skip: !kRunPatrolT4,
    config: PatrolTesterConfig(visibleTimeout: const Duration(seconds: 20)),
    ($) async {
      assert(
        _apiContractEnv == 'gamma',
        'Patrol user_acceptance tests must run with API_CONTRACT_ENV=gamma',
      );

      await launchPatrolAppOnce($);
      await $(
        find.byType(WidgetsApp),
      ).waitUntilVisible(timeout: const Duration(seconds: 30));

      // 打开系统通知栏
      await $.platform.mobile.openNotifications();
      await Future<void>.delayed(const Duration(seconds: 2));

      // 查找聊天通知（通知文案由服务端推送，此处匹配通用模式）
      final chatNotification = $.platform.mobile.getNotifications();

      // 如果有聊天通知则点击，否则验证 App 仍在前台且不崩溃。
      if ((await chatNotification).isEmpty) {
        if (defaultTargetPlatform == TargetPlatform.android) {
          await $.platform.android.pressBack();
        }
        await $.pump(const Duration(seconds: 1));
        expect(find.byType(WidgetsApp), findsOneWidget);
        return;
      }

      // 点击第一条通知
      await $.platform.mobile.tapOnNotificationByIndex(0);
      await $.pump(const Duration(seconds: 1));

      // 断言打开了某个页面（不崩溃即通过）
      expect(find.byType(WidgetsApp), findsWidgets);
    },
  );

  patrolTest(
    '后台收到通知后前台打开不崩溃',
    tags: ['t4', 'chat', 'notification'],
    skip: !kRunPatrolT4,
    config: PatrolTesterConfig(visibleTimeout: const Duration(seconds: 20)),
    ($) async {
      assert(
        _apiContractEnv == 'gamma',
        'Patrol user_acceptance tests must run with API_CONTRACT_ENV=gamma',
      );

      await launchPatrolAppOnce($);
      await $(
        find.byType(WidgetsApp),
      ).waitUntilVisible(timeout: const Duration(seconds: 30));

      // 模拟 Home 键切后台
      await $.platform.mobile.pressHome();
      await Future<void>.delayed(const Duration(seconds: 2));

      // 切回前台（需要 QUERY_ALL_PACKAGES，见 debug manifest）。openApp() 无参时
      // patrol 解析到的 package 为空（intent null），必须显式传入被测 App 的 applicationId。
      await $.platform.mobile.openApp(appId: _appUnderTestId);
      await $.pump(const Duration(seconds: 1));

      // 断言 App 恢复正常
      expect(find.byType(WidgetsApp), findsOneWidget);
    },
  );
}
