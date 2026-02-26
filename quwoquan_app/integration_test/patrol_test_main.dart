/// Patrol integration test entry point.
///
/// Patrol 3.x + integration_test 要求 main() 调用真实 app，否则 FTL 上测试在空白屏运行。
/// 每个 patrolTest 直接与已启动的 App 交互，不需要在 test 内再 pumpWidget。
///
/// 执行方式（本地，需连接真机或模拟器）：
///   patrol test test/patrol/ \
///     --dart-define=ENV=staging \
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
  // staging 环境通过 dart-define ENV=staging 注入
  app.main();
}
