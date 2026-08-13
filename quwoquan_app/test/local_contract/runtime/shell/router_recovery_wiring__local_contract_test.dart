// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/unrecoverable-runtime-recovery/spec.md

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

/// Router 错误页接线合约（静态）。
///
/// `app_router_recovery_page.dart` 是 GoRouter errorPageBuilder 的唯一接线：
/// 路由解析失败必须落到 runtime/shell/recovery 拥有的 StartupRecoveryPage
/// canonical 恢复面，禁止替换为裸占位或第二套错误页。
void main() {
  test('GoRouter errorPageBuilder 挂载 canonical 恢复页', () {
    final wiring = File(
      'lib/runtime/di/navigation/app_router_recovery_page.dart',
    ).readAsStringSync();
    expect(wiring, contains('StartupRecoveryPage.routerError()'));
    expect(wiring, contains('_buildRouterRecoveryPage'));

    final router = File(
      'lib/runtime/di/navigation/app_router.dart',
    ).readAsStringSync();
    expect(
      router,
      contains('errorPageBuilder'),
      reason: 'GoRouter 必须声明 errorPageBuilder',
    );
    expect(
      router,
      contains('_buildRouterRecoveryPage()'),
      reason: 'errorPageBuilder 必须使用 recovery wiring，禁止内联第二套错误页',
    );
  });
}
