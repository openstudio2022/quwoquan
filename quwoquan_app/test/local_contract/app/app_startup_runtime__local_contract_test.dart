import 'dart:async';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:flutter/services.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/app/app_startup_runtime.dart';
import 'package:quwoquan_app/core/platform/startup_native_bridge.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  final runtime = AppStartupRuntime.instance;

  tearDown(() {
    runtime.resetForTesting();
    AppStartupRuntime.resetNativeTimingsBridgeForTesting();
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(_startupTimingsChannel, null);
  });

  test('native timing future 永久 pending 时超时并允许后续重试', () async {
    AppStartupRuntime.overrideNativeTimingsBridgeForTesting(
      _FakeNativeTimingBridge(
        Completer<NativeStartupProcessSegments?>().future,
      ),
    );

    await expectLater(
      runtime.hydrateNativeProcessSegments(
        budget: const Duration(milliseconds: 5),
      ),
      throwsA(isA<TimeoutException>()),
    );

    AppStartupRuntime.overrideNativeTimingsBridgeForTesting(
      _FakeNativeTimingBridge(
        Future<NativeStartupProcessSegments?>.value(
          const NativeStartupProcessSegments(
            elapsedSinceProcessStartMs: 7,
            deadlineOrigin: 'android_process',
          ),
        ),
      ),
    );

    await runtime.hydrateNativeProcessSegments(
      budget: const Duration(milliseconds: 20),
    );
    expect(
      runtime.deadlineOrigin,
      'fallbackDart',
      reason: 'late native hydration cannot rebase an already armed deadline',
    );
  });

  test('native timing bridge 抛错时不将 in-flight 状态永久锁死', () async {
    AppStartupRuntime.overrideNativeTimingsBridgeForTesting(
      _FakeNativeTimingBridge(
        Future<NativeStartupProcessSegments?>.error(
          StateError('bridge failure'),
        ),
      ),
    );

    await expectLater(
      runtime.hydrateNativeProcessSegments(
        budget: const Duration(milliseconds: 20),
      ),
      throwsA(isA<StateError>()),
    );

    AppStartupRuntime.overrideNativeTimingsBridgeForTesting(
      _FakeNativeTimingBridge(
        Future<NativeStartupProcessSegments?>.value(
          const NativeStartupProcessSegments(),
        ),
      ),
    );
    await runtime.hydrateNativeProcessSegments(
      budget: const Duration(milliseconds: 20),
    );
  });

  test('native timing hydration 不得重置已 arm 的 deadline origin', () async {
    runtime.markBootstrapStarted();
    final deadlineOriginBeforeHydration = runtime.deadlineOrigin;

    AppStartupRuntime.overrideNativeTimingsBridgeForTesting(
      _FakeNativeTimingBridge(
        Future<NativeStartupProcessSegments?>.value(
          const NativeStartupProcessSegments(
            elapsedSinceProcessStartMs: 5000,
            deadlineOrigin: 'android_process',
          ),
        ),
      ),
    );

    await runtime.hydrateNativeProcessSegments(
      budget: const Duration(milliseconds: 20),
    );

    expect(runtime.deadlineOrigin, deadlineOriginBeforeHydration);
    expect(runtime.deadlineElapsedSinceProcessStart, isA<Duration>());
  });

  test('每个 Dart 启动 attempt 记录环境摘要与脱敏缺失键', () async {
    final events = <Map<String, dynamic>>[];
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(_startupTimingsChannel, (call) async {
          if (call.method == 'recordStartupEvent') {
            events.add(
              Map<String, dynamic>.from(
                jsonDecode(call.arguments! as String) as Map<String, dynamic>,
              ),
            );
          }
          return null;
        });

    runtime.markBootstrapStarted();
    await Future<void>.delayed(Duration.zero);

    final attempt = events.singleWhere(
      (event) => event['eventName'] == 'startup_attempt_started',
    );
    final summary = CloudRuntimeConfig.runtimeDefineSummary;
    expect(attempt['attemptId'], matches(RegExp(r'^[A-Za-z0-9_-]{16,128}$')));
    expect(attempt['runtimeEnv'], summary['runtimeEnv']);
    expect(attempt['launchMode'], summary['launchMode']);
    expect(attempt['configurationState'], summary['configurationState']);
    expect(attempt['missingDefineKeys'] ?? '', summary['missingKeys']);
    expect(attempt.containsKey('CLOUD_GATEWAY_BASE_URL'), isFalse);
  });

  test('安全终态首帧会通知平台 watchdog，而欢迎首帧不会提前取消', () async {
    final events = <Map<String, dynamic>>[];
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(_startupTimingsChannel, (call) async {
          if (call.method == 'recordStartupEvent') {
            events.add(
              Map<String, dynamic>.from(
                jsonDecode(call.arguments! as String) as Map<String, dynamic>,
              ),
            );
          }
          return null;
        });

    runtime.markFirstFramePainted();
    await Future<void>.delayed(Duration.zero);
    expect(
      events.where((event) => event['eventName'] == 'startup_safe_terminal'),
      isEmpty,
    );

    runtime.markShellFirstPainted();
    await Future<void>.delayed(Duration.zero);
    final safeTerminalEvents = events
        .where((event) => event['eventName'] == 'startup_safe_terminal')
        .toList(growable: false);
    expect(safeTerminalEvents, hasLength(1));
    final safeTerminalEvent = safeTerminalEvents.single;
    expect(safeTerminalEvent['eventName'], 'startup_safe_terminal');
    expect(safeTerminalEvent['surface'], 'router_shell');
    expect(safeTerminalEvent['elapsedMs'], isA<int>());
    expect(safeTerminalEvent['elapsedMs'] as int, greaterThanOrEqualTo(0));
  });

  test('首页内容首帧与欢迎遮罩移除必须同时成立才记录真实可用', () {
    runtime.markHomeFeedContentPainted();
    expect(runtime.snapshotProperties(phase: 'assert')['homeReadyMs'], isNull);

    runtime.markWelcomeOverlayRemoved();
    expect(
      runtime.snapshotProperties(phase: 'assert')['homeReadyMs'],
      isA<int>(),
    );
  });
}

const MethodChannel _startupTimingsChannel = MethodChannel(
  'quwoquan/startup/timings',
);

final class _FakeNativeTimingBridge implements StartupTimingsNativeBridge {
  const _FakeNativeTimingBridge(this._result);

  final Future<NativeStartupProcessSegments?> _result;

  @override
  Future<NativeStartupProcessSegments?> readProcessSegments() => _result;
}
