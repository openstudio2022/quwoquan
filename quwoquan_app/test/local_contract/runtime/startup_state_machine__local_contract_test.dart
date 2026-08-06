import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/shell/startup/startup_state_machine.dart';
import '../../support/runtime/errors/runtime_failure_fixtures.dart';

void main() {
  group('StartupStateMachine', () {
    test('欢迎完成、Router 和 overlay 只按单向终态推进', () {
      final machine = StartupStateMachine();

      expect(machine.snapshot.phase, StartupRootPhase.welcome);
      expect(machine.requestWelcomeCompletion(), isTrue);
      expect(machine.requestWelcomeCompletion(), isFalse);

      final firstAttempt = machine.beginRouterLoad();
      expect(machine.snapshot.phase, StartupRootPhase.routerLoading);
      expect(machine.snapshot.welcomeOverlayVisible, isTrue);

      expect(machine.markRouterReady(firstAttempt), isTrue);
      expect(machine.snapshot.phase, StartupRootPhase.routerShell);
      expect(machine.beginOverlayFade(), isTrue);
      expect(machine.snapshot.welcomeOverlayOpacity, 0);
      expect(machine.removeWelcomeOverlay(), isTrue);
      expect(machine.snapshot.welcomeOverlayVisible, isFalse);
      expect(machine.removeWelcomeOverlay(), isFalse);
    });

    test('过期 Router 回调不能覆盖更新后的安全终态', () {
      final machine = StartupStateMachine();
      machine.requestWelcomeCompletion();
      final firstAttempt = machine.beginRouterLoad();

      machine.forceSafeRecovery(
        testRuntimeFailure(code: 'OPS.SYSTEM.startup_router_unavailable'),
      );
      expect(machine.snapshot.phase, StartupRootPhase.safeRecovery);
      expect(
        machine.markRouterReady(firstAttempt),
        isFalse,
        reason: '旧 deferred future 完成后不得夺回安全恢复页',
      );

      final retryAttempt = machine.beginRouterLoad();
      expect(retryAttempt, greaterThan(firstAttempt));
      expect(
        machine.markRouterFailure(
          retryAttempt,
          testRuntimeFailure(code: 'OPS.SYSTEM.startup_router_unavailable'),
        ),
        isTrue,
      );
      expect(machine.snapshot.phase, StartupRootPhase.safeRecovery);
    });

    test('真实 Router Shell 后不会被迟到 deadline 覆盖', () {
      final machine = StartupStateMachine();
      machine.requestWelcomeCompletion();
      final attempt = machine.beginRouterLoad();
      machine.markRouterReady(attempt);

      machine.forceSafeRecovery(
        testRuntimeFailure(code: 'OPS.SYSTEM.startup_router_unavailable'),
      );

      expect(machine.snapshot.phase, StartupRootPhase.routerShell);
    });
  });
}
