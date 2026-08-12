// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/unrecoverable-runtime-recovery/spec.md#gwt-001
// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/unrecoverable-runtime-recovery/spec.md#gwt-002
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/shell/recovery/recovery_operation_gateway.dart';
import 'package:quwoquan_app/runtime/shell/recovery/recovery_state_machine.dart';
import 'package:quwoquan_app/runtime/shell/recovery/runtime_recovery_host.dart';
import 'package:quwoquan_app/runtime/shell/recovery/startup_recovery_controller.dart';

void main() {
  testWidgets('runtime recovery disposes the failed root and re-enters once', (
    tester,
  ) async {
    var generation = 0;
    final reentryFlags = <bool>[];
    await tester.pumpWidget(
      RuntimeRecoveryHost(
        childBuilder: (_, isRuntimeReentry) {
          reentryFlags.add(isRuntimeReentry);
          return MaterialApp(
            home: Builder(
              builder: (context) => Scaffold(
                body: Column(
                  children: <Widget>[
                    Text('shell-${generation++}'),
                    TextButton(
                      onPressed: () =>
                          RuntimeRecoveryCoordinator.instance.enter(
                            error: const UnrecoverableRuntimeException(
                              cause: 'broken container',
                              source: 'test_runtime_boundary',
                            ),
                            stack: StackTrace.current,
                            source: 'test_runtime_boundary',
                          ),
                      child: const Text('fail'),
                    ),
                    TextButton(
                      onPressed: RuntimeRecoveryCoordinator
                          .instance
                          .markSafeShellReady,
                      child: const Text('safe'),
                    ),
                  ],
                ),
              ),
            ),
          );
        },
      ),
    );

    await tester.tap(find.text('fail'));
    await tester.pump();
    expect(find.text('应用暂时无法继续使用'), findsOneWidget);
    expect(find.text('重新进入应用'), findsOneWidget);

    await tester.tap(find.text('重新进入应用'));
    await tester.pump();
    expect(find.text('正在重新进入应用'), findsOneWidget);
    expect(find.text('使用网页版'), findsOneWidget);
    expect(reentryFlags, contains(true));

    RuntimeRecoveryCoordinator.instance.markSafeShellReady();
    await tester.pump();
    expect(find.text('应用暂时无法继续使用'), findsNothing);
    expect(find.textContaining('shell-'), findsOneWidget);

    await tester.tap(find.text('fail'));
    await tester.pump();
    expect(find.text('应用暂时无法继续使用'), findsOneWidget);
    expect(find.text('正在检查可用版本'), findsOneWidget);
    expect(find.text('重新进入应用'), findsNothing);
    expect(reentryFlags.where((flag) => flag), hasLength(1));
  });

  testWidgets('runtime re-entry deadline falls through to version recovery', (
    tester,
  ) async {
    await tester.pumpWidget(
      RuntimeRecoveryHost(
        reentryDeadline: const Duration(milliseconds: 1),
        childBuilder: (_, _) => MaterialApp(
          home: Scaffold(
            body: TextButton(
              onPressed: () => RuntimeRecoveryCoordinator.instance.enter(
                error: const UnrecoverableRuntimeException(
                  cause: 'broken container',
                  source: 'test_runtime_boundary',
                ),
                stack: StackTrace.current,
                source: 'test_runtime_boundary',
              ),
              child: const Text('fail'),
            ),
          ),
        ),
      ),
    );

    await tester.tap(find.text('fail'));
    await tester.pump();
    await tester.tap(find.text('重新进入应用'));
    await tester.pump(const Duration(milliseconds: 2));

    expect(find.text('应用暂时无法继续使用'), findsOneWidget);
    expect(find.text('正在检查可用版本'), findsOneWidget);
    expect(find.text('重新进入应用'), findsNothing);
    expect(find.text('使用网页版'), findsOneWidget);
  });

  testWidgets('minimum-build 426 replaces business UI with required update', (
    tester,
  ) async {
    await tester.pumpWidget(
      RuntimeRecoveryHost(
        clientUpgradeControllerFactory: () => StartupRecoveryController(
          initialSnapshot: const RecoverySnapshot(
            phase: RecoveryPhase.runtimeUpdateRequired,
            updateState: RecoveryUpdateState.required,
            updateUrl: 'https://cdn.quwoquan.com/download/android/latest.json',
            recoveryUrl: 'https://quwoquan.com/',
          ),
          requiredUpdateOnly: true,
        ),
        childBuilder: (_, _) => MaterialApp(
          home: Scaffold(
            body: Column(
              children: <Widget>[
                const Text('ordinary-business-inline-error'),
                TextButton(
                  onPressed: () => RuntimeRecoveryCoordinator.instance
                      .enterClientUpgradeRequired(
                        error: StateError('HTTP 426'),
                        stack: StackTrace.current,
                        source: 'gateway_minimum_build',
                        failureCode: 'GATEWAY.USER.client_upgrade_required',
                      ),
                  child: const Text('receive-426'),
                ),
              ],
            ),
          ),
        ),
      ),
    );

    await tester.tap(find.text('receive-426'));
    await tester.pump();

    expect(find.text('ordinary-business-inline-error'), findsNothing);
    expect(find.text('当前版本需要更新'), findsOneWidget);
    expect(find.text('更新后即可继续使用'), findsOneWidget);
    expect(find.text('前往更新'), findsOneWidget);
    expect(find.text('重新进入应用'), findsNothing);
    expect(find.textContaining('继续使用当前版本'), findsNothing);
  });
}
