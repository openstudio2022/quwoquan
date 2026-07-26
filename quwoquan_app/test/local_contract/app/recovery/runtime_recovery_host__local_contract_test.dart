// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/unrecoverable-runtime-recovery/spec.md#gwt-001
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/app/recovery/runtime_recovery_host.dart';

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
}
