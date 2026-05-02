/// Patrol test entry point.
///
/// Patrol 4.x 仍要求 main() 调用真实 app，否则 T4 用例会在空白屏运行。
/// 本仓库将 Patrol 用例保留在 `test/patrol/`，并通过 `pubspec.yaml` 的
/// `patrol.test_directory` 指向该目录。
///
/// 执行方式（本地，需连接真机或模拟器）：
///   patrol test test/patrol/ \
///     --dart-define=APP_RUNTIME_ENV=gamma \
///     --dart-define=API_CONTRACT_ENV=gamma \
///     --dart-define=RUN_T4_PATROL=true \
///     --dart-define=TEST_AUTH_TOKEN=YOUR_TOKEN
///
/// 执行方式（Firebase Test Lab）：
///   由 .github/workflows/e2e.yaml 在 pre-release tag 时触发。
library;

import 'package:integration_test/integration_test.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/main.dart' as app;

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  patrolSetUp(() async {
    // 全局 setUp hook（每个 patrolTest 前触发）
    // 可在此清除路由栈、重置本地状态等
  });

  patrolTearDown(() async {
    // 全局 tearDown hook（每个 patrolTest 后触发）
  });

  // 启动真实 App（含 Riverpod ProviderScope、GoRouter、ScreenUtil 等完整初始化）
  // 目标环境通过 APP_RUNTIME_ENV/API_CONTRACT_ENV 注入。
  app.main();
}
