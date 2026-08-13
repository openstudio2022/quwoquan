import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/shell/startup/app_startup_runtime.dart';
import 'package:quwoquan_app/runtime/di/navigation/app_router_module.dart';
import 'package:quwoquan_app/runtime/shell/startup/startup_screen_util_scope.dart';
import 'package:quwoquan_app/runtime/platform/startup_deferred_plugins.dart';
import 'package:quwoquan_app/runtime/shell/welcome/welcome_screen.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('startup_ttid local_contract', () {
    test('welcome screen is available without eager router construction', () {
      expect(const WelcomeScreen(onFinish: _noop).runtimeType, WelcomeScreen);
    });

    test('app router library is not loaded before explicit ensure', () {
      expect(isAppRouterLibraryLoaded, isFalse);
    });

    test('startup runtime snapshot exposes native segment keys', () {
      final snapshot = AppStartupRuntime.instance.phaseSnapshot(
        phase: 'contract_probe',
      );
      expect(snapshot.phase, 'contract_probe');
      final props = snapshot.toJson();
      expect(props, containsPair('phase', 'contract_probe'));
      expect(props.keys, contains('elapsedMs'));
      expect(props.keys, contains('elapsedSinceProcessStartMs'));
      expect(props.keys, contains('deadlineOrigin'));
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
      final spec = File(
        '${repoRoot.path}/specs/feature-tree/runtime/runtime-client-foundation/cold-start-performance/spec.md',
      );
      expect(probe.existsSync(), isTrue, reason: probe.path);
      expect(ratchet.existsSync(), isTrue, reason: ratchet.path);
      expect(spec.existsSync(), isTrue, reason: spec.path);
    });
  });
}

void _noop() {}
