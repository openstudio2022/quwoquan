/// 宿主测试树的全局前置：先水合 runtime package，再运行任何用例。
///
/// 生产上 `CloudRuntimeConfig` 的取值只来自冷启动原生 activation 交出的
/// signed package，宿主测试没有该事务，因此在这里统一走同一条 resolver
/// 校验链完成水合。放在 `flutter_test_config.dart` 而不是逐个 `setUp`，
/// 是为了让「配置来源单轨」成为整棵树的不可绕过前置，而不是各测试自行
/// 决定要不要水合。
library;

import 'dart:async';

import 'support/runtime/config/runtime_package_test_hydration.dart';

Future<void> testExecutable(FutureOr<void> Function() testMain) async {
  await hydrateRuntimePackageForTests();
  await testMain();
}
