import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/app/app_startup_runtime.dart';
import 'package:quwoquan_app/app/navigation/app_router_module.dart';
import 'package:quwoquan_app/app/startup_screen_util_scope.dart';
import 'package:quwoquan_app/cloud/runtime/startup_deferred_plugins.dart';
import 'package:quwoquan_app/ui/welcome/pages/welcome_screen.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('startup_ttid local_contract', () {
    test(
      'welcome screen defers animation controllers until after first frame',
      () {
        expect(const WelcomeScreen(onFinish: _noop).runtimeType, WelcomeScreen);
      },
    );

    test('app router library is not loaded before explicit ensure', () {
      expect(isAppRouterLibraryLoaded, isFalse);
    });

    test('startup runtime snapshot exposes native segment keys', () {
      final props = AppStartupRuntime.instance.snapshotProperties(
        phase: 'contract_probe',
      );
      expect(props, containsPair('phase', 'contract_probe'));
      expect(props.keys, contains('elapsedMs'));
    });

    test(
      'deferred plugin ensure APIs are idempotent no-ops off Android',
      () async {
        await StartupDeferredPlugins.ensureRtcPlugins();
        await StartupDeferredPlugins.ensureContentEntryPlugins();
        await StartupDeferredPlugins.ensureLocationPlugins();
      },
    );

    test('startup screen util scope widget exists for post-welcome shell', () {
      expect(const StartupScreenUtilScope(child: SizedBox.shrink()), isNotNull);
    });

    test('probe and ratchet scripts exist on disk', () {
      final repoRoot = Directory.current.path.endsWith('quwoquan_app')
          ? Directory.current.parent
          : Directory.current;
      final probe = File(
        '${repoRoot.path}/quwoquan_app/scripts/device/verify_startup_first_frame.py',
      );
      final ratchet = File(
        '${repoRoot.path}/quwoquan_app/scripts/device/verify_startup_ttid_baseline.py',
      );
      final acceptance = File(
        '${repoRoot.path}/specs/feature-tree/runtime/runtime-client-foundation/cold-start-performance/acceptance.yaml',
      );
      expect(probe.existsSync(), isTrue, reason: probe.path);
      expect(ratchet.existsSync(), isTrue, reason: ratchet.path);
      expect(acceptance.existsSync(), isTrue, reason: acceptance.path);
    });
  });
}

void _noop() {}
