/// Patrol test entry point.
///
/// Patrol 4.x 仍要求 main() 调用真实 app，否则 user_acceptance Patrol 用例会在空白屏运行。
/// `pubspec.yaml` 的 `patrol.test_directory` 仅保留 Patrol runner shell；真实用例按
/// 对象或跨对象 Journey 分布在 `test/user_acceptance/**`，由目标文件显式触发。
///
/// 执行方式（本地，需连接真机或模拟器）：
///   patrol test --target test/user_acceptance/CANONICAL_TARGET \
///     --dart-define=APP_RUNTIME_ENV=gamma \
///     --dart-define=API_CONTRACT_ENV=gamma \
///     --dart-define=RUN_PATROL_ACCEPTANCE=true \
///     --dart-define=TEST_AUTH_TOKEN=YOUR_TOKEN
///
/// 执行方式（Firebase Test Lab）：
///   由 .github/workflows/e2e.yaml 在 pre-release tag 时触发。
library;

import 'package:integration_test/integration_test.dart';
import 'package:patrol/patrol.dart';

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  patrolSetUp(() async {
    // 全局 setUp hook（每个 patrolTest 前触发）
    // 可在此清除路由栈、重置本地状态等
  });

  patrolTearDown(() async {
    // 全局 tearDown hook（每个 patrolTest 后触发）
  });
}
