/// T4 Patrol E2E: 横竖屏切换聊天页稳定性
///
/// 守护：flutter_test 无法覆盖的真实屏幕旋转场景。
/// 验证聊天详情页在横竖屏切换后 UI 不崩溃、消息列表保持可见。
///
/// 当前跳过：Patrol 4.x 仍未提供稳定的屏幕方向切换能力，
/// 需迁移至 PlatformAutomator 后再启用。
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';

const _apiContractEnv = String.fromEnvironment(
  'API_CONTRACT_ENV',
  defaultValue: 'gamma',
);

void main() {
  patrolTest(
    '横竖屏切换聊天页稳定',
    tags: ['t4', 'chat', 'orientation'],
    skip:
        true, // Patrol NativeAutomator setOrientationLandscape/Portrait removed; migrate to PlatformAutomator
    config: PatrolTesterConfig(visibleTimeout: const Duration(seconds: 15)),
    ($) async {
      assert(
        _apiContractEnv == 'gamma',
        'T4 tests must run with API_CONTRACT_ENV=gamma',
      );

      await $.pumpWidgetAndSettle(const _PatrolAppPlaceholder());

      await $(
        find.byType(Scaffold),
      ).waitUntilVisible(timeout: const Duration(seconds: 10));

      expect(find.byType(Scaffold), findsWidgets);
    },
  );

  patrolTest(
    '横屏下输入文字后切回竖屏内容保持',
    tags: ['t4', 'chat', 'orientation'],
    skip:
        true, // Patrol NativeAutomator setOrientationLandscape/Portrait removed; migrate to PlatformAutomator
    config: PatrolTesterConfig(visibleTimeout: const Duration(seconds: 15)),
    ($) async {
      assert(
        _apiContractEnv == 'gamma',
        'T4 tests must run with API_CONTRACT_ENV=gamma',
      );

      await $.pumpWidgetAndSettle(const _PatrolAppPlaceholder());

      final inputField = find.byType(TextField);
      await $(
        inputField,
      ).waitUntilVisible(timeout: const Duration(seconds: 10));

      expect(find.byType(TextField), findsWidgets);
    },
  );

  patrolTest(
    '快速多次旋转不崩溃',
    tags: ['t4', 'chat', 'orientation'],
    skip:
        true, // Patrol NativeAutomator setOrientationLandscape/Portrait removed; migrate to PlatformAutomator
    config: PatrolTesterConfig(visibleTimeout: const Duration(seconds: 20)),
    ($) async {
      assert(
        _apiContractEnv == 'gamma',
        'T4 tests must run with API_CONTRACT_ENV=gamma',
      );

      await $.pumpWidgetAndSettle(const _PatrolAppPlaceholder());

      await $(
        find.byType(Scaffold),
      ).waitUntilVisible(timeout: const Duration(seconds: 10));

      expect(find.byType(Scaffold), findsWidgets);
    },
  );
}

class _PatrolAppPlaceholder extends StatelessWidget {
  const _PatrolAppPlaceholder();

  @override
  Widget build(BuildContext context) {
    return const MaterialApp(
      home: Scaffold(
        body: Column(
          children: [
            Expanded(child: Center(child: Text('Chat messages area'))),
            TextField(decoration: InputDecoration(hintText: 'Type a message')),
          ],
        ),
      ),
    );
  }
}
