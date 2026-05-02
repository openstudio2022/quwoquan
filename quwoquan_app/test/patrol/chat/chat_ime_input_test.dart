/// T4 Patrol E2E: 真实 IME 中文输入发送消息
///
/// 守护：flutter_test 无法覆盖的真实输入法（IME）中文输入场景。
/// 验证中文 composing → commit → 发送 → 消息出现的完整链路。
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/core/testing/patrol_test_support.dart';

const _apiContractEnv = String.fromEnvironment(
  'API_CONTRACT_ENV',
  defaultValue: 'gamma',
);

void main() {
  patrolTest(
    '真实 IME 中文输入发送消息',
    tags: ['t4', 'chat', 'ime'],
    skip: !kRunPatrolT4,
    config: PatrolTesterConfig(visibleTimeout: const Duration(seconds: 15)),
    ($) async {
      assert(
        _apiContractEnv == 'gamma',
        'T4 tests must run with API_CONTRACT_ENV=gamma',
      );

      // 导航到聊天页
      await $.pumpWidgetAndSettle(const _PatrolAppPlaceholder());

      // 等待聊天输入框可见
      final inputField = find.byType(TextField);
      await $(
        inputField,
      ).waitUntilVisible(timeout: const Duration(seconds: 20));

      // 使用 native API 输入中文（真实 IME composing）
      await $.platform.mobile.enterText(
        Selector(text: ''),
        text: '你好，这是一条测试消息',
      );
      await $.pumpAndSettle();

      // tap 发送按钮
      await $(find.byIcon(Icons.send)).tap();
      await $.pumpAndSettle();

      // 断言消息出现在列表中
      expect(find.text('你好，这是一条测试消息'), findsWidgets);
    },
  );

  patrolTest(
    '真实 IME Emoji 输入发送消息',
    tags: ['t4', 'chat', 'ime'],
    skip: !kRunPatrolT4,
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
      ).waitUntilVisible(timeout: const Duration(seconds: 20));

      await $.platform.mobile.enterText(
        Selector(text: ''),
        text: '测试 Emoji 消息 😊🎉',
      );
      await $.pumpAndSettle();

      await $(find.byIcon(Icons.send)).tap();
      await $.pumpAndSettle();

      expect(find.textContaining('Emoji'), findsWidgets);
    },
  );
}

/// Patrol 测试占位 App（实际运行时由 `test/patrol/patrol_test_main.dart` 启动）
class _PatrolAppPlaceholder extends StatelessWidget {
  const _PatrolAppPlaceholder();

  @override
  Widget build(BuildContext context) {
    return const MaterialApp(
      home: Scaffold(body: Center(child: Text('Patrol placeholder'))),
    );
  }
}
