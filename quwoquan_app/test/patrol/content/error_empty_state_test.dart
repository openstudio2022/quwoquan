/// T4 Patrol E2E: 错误/空状态展示
///
/// 对应 e2e.yaml 场景：error_empty_state_ui [test_type: ui_journey]
///
/// 守护：
///   - post_not_found 等空态按 ContentUIConfig.empty_states 展示
///   - 错误态使用内联占位或 SnackBar 符合 error-and-permission-semantics
///
/// 注：App 已由 test/patrol/patrol_test_main.dart 的 app.main() 启动。
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/core/testing/patrol_test_support.dart';
import 'package:quwoquan_app/core/test_keys.dart';

void main() {
  patrolTest(
    'error_empty_state_ui',
    tags: ['t4', 'content'],
    skip: !kRunPatrolT4,
    ($) async {
      // 等待发现页加载后断言空态/错误态能力（具体断言待 T4 环境补齐）
      await $(
        TestKeys.discoveryPage,
      ).waitUntilVisible(timeout: const Duration(seconds: 15));
      expect($(TestKeys.discoveryPage).visible, isTrue);
    },
  );
}
