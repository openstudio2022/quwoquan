library;

import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/app/providers/welcome_state_provider.dart';
import 'package:quwoquan_app/app_bootstrap.dart';

/// T4 Patrol tests should only run under `patrol test`.
///
/// We guard them behind an explicit dart-define so `flutter test` can run the
/// regular test suite without trying to execute native Patrol flows.
const bool kRunPatrolT4 = bool.fromEnvironment('RUN_T4_PATROL');

bool _patrolAppStarted = false;

Future<void> launchPatrolAppOnce(PatrolIntegrationTester $) async {
  if (!_patrolAppStarted) {
    _patrolAppStarted = true;
    await runQuwoquanApp(
      providerScopeOverrides: [
        welcomeCompletedProvider.overrideWith(
          _PatrolWelcomeCompletedNotifier.new,
        ),
      ],
    );
  }
  // gamma 远端冷启动会带来持续中的初始化任务，直接等待全局 settle
  // 容易把 T4 卡死在启动阶段。这里仅给首帧和首轮路由足够时间，
  // 后续由具体用例等待目标元素出现。
  await $.pump();
  await $.pump(const Duration(milliseconds: 300));
  await $.pump(const Duration(seconds: 1));
}

final class _PatrolWelcomeCompletedNotifier extends WelcomeCompletedNotifier {
  @override
  bool build() => true;
}
