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
  // 让首帧、路由与异步初始化有机会完成，再进入可见性断言。
  await $.pumpAndSettle();
}

final class _PatrolWelcomeCompletedNotifier extends WelcomeCompletedNotifier {
  @override
  bool build() => true;
}
