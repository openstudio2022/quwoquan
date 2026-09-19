import 'dart:async';

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_config.dart';
import 'package:quwoquan_app/runtime/shell/startup/app_bootstrap.dart';
import 'package:quwoquan_app/runtime/shell/startup/app_startup_runtime.dart';

import '../../support/runtime/config/runtime_package_test_hydration.dart';

// spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-008
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  testWidgets('真实startup scope仅安装一次，R1同代，runtime替换/根重建新代且dispose失效', (
    tester,
  ) async {
    await hydrateRuntimePackageForTests();
    AppStartupRuntime.instance.resetForTesting();
    AppStartupRuntime.instance.markBootstrapStarted();
    final scopes = <StartupScopeLifecycle>[];
    var disposed = 0;
    configureAppStartupScope(() {
      final scope = installingStartupScopeLifecycle!;
      expect(scope.isCurrent, isTrue);
      expect(scope.confirmedAttempt, isNull);
      scopes.add(scope);
      scheduleMicrotask(() => expect(installingStartupScopeLifecycle, isNull));
      return StartupScopeComposition(
        dispose: () {
          expect(scope.isCurrent, isFalse);
          disposed++;
        },
      );
    });
    Widget root(String child) => AppStartupScope(
      runtimeIdentity: CloudRuntimeConfig.runtimeConfigPackageDigest,
      childBuilder: (_) =>
          Directionality(textDirection: TextDirection.ltr, child: Text(child)),
    );
    await tester.pumpWidget(root('R0'));
    final first = scopes.single;
    expect(first.generation, greaterThan(0));
    expect(installingStartupScopeLifecycle, isNull);
    await tester.pumpWidget(root('R1'));
    expect(scopes, hasLength(1));
    expect(first.isCurrent, isTrue);
    await hydrateRuntimePackageForTests();
    expect(first.isCurrent, isFalse);
    await tester.pumpWidget(root('runtime changed'));
    expect(scopes, hasLength(2));
    expect(scopes.last.generation, greaterThan(first.generation));
    expect(disposed, 1);
    await tester.pumpWidget(const SizedBox.shrink());
    expect(scopes.last.isCurrent, isFalse);
    expect(disposed, 2);
    await tester.pumpWidget(root('new root'));
    expect(scopes, hasLength(3));
    expect(scopes.last.generation, greaterThan(scopes[1].generation));
    expect(first.requireCurrent, throwsStateError);
    await tester.pumpWidget(const SizedBox.shrink());
    configureAppStartupScope(() => StartupScopeComposition(dispose: () {}));
    AppStartupRuntime.instance.resetForTesting();
  });
}
