// spec_ref: specs/feature-tree/chat-conversation/realtime-call/call-experience/spec.md#gwt-013
//
// Shell bindings 重建面契约：
// 通话计时 elapsed 每秒 tick、参与者变化与 PiP 显隐切换不得重建
// MainAppShellBindings（否则通话最小化期间 MainAppShell 每秒整树重建）；
// 只有通话开始/结束（callId/callType 结构变化）才允许重建。展示态由
// ActiveCallBar / PiP 浮层自行隔离 watch。
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/di/main_app_shell_dependencies.dart';
import 'package:quwoquan_app/runtime/platform/platform_providers.dart';
import 'package:quwoquan_app/runtime/platform/screen_wake_gateway.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/application/active_call_service.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  (ProviderContainer, List<MainAppShellBindings>) createHarness() {
    final container = ProviderContainer(
      overrides: [
        screenWakeGatewayProvider.overrideWithValue(
          const UnsupportedScreenWakeGateway(),
        ),
      ],
    );
    addTearDown(container.dispose);
    final rebuilds = <MainAppShellBindings>[];
    container.listen<MainAppShellBindings>(
      mainAppShellBindingsProvider,
      (previous, next) => rebuilds.add(next),
      fireImmediately: true,
    );
    return (container, rebuilds);
  }

  Future<void> flushMicrotasks() => Future<void>.delayed(Duration.zero);

  test('elapsed 每秒 tick 不重建 shell bindings', () async {
    final (container, rebuilds) = createHarness();
    final notifier = container.read(activeCallProvider.notifier);
    notifier.startCall(callId: 'call-shell-rebuild', callType: 'audio');
    await flushMicrotasks();
    final afterStart = rebuilds.length;
    expect(afterStart, 2, reason: '初始 + 通话开始各一次');

    // 真实计时 2 次 tick：bindings 不得随 elapsed 重建。
    await Future<void>.delayed(const Duration(milliseconds: 2100));
    expect(
      rebuilds.length,
      afterStart,
      reason: 'elapsed tick 不得整树重建 MainAppShell',
    );

    notifier.endCall();
    await flushMicrotasks();
    expect(rebuilds.length, afterStart + 1, reason: '通话结束允许重建一次');
    expect(rebuilds.last.activeCallRoute, isNull);
  });

  test('PiP 显隐切换不重建 shell bindings，结构事实保持可用', () async {
    final (container, rebuilds) = createHarness();
    final notifier = container.read(activeCallProvider.notifier);
    notifier.startCall(callId: 'call-shell-pip', callType: 'video');
    await flushMicrotasks();
    final afterStart = rebuilds.length;

    notifier.enterPipMode();
    await flushMicrotasks();
    notifier.exitPipMode();
    await flushMicrotasks();
    notifier.enterPipMode();
    await flushMicrotasks();

    expect(
      rebuilds.length,
      afterStart,
      reason: 'PiP 显隐由浮层自身 watch，不得重建 shell bindings',
    );
    expect(rebuilds.last.activeCallRoute?.callId, 'call-shell-pip');
    expect(rebuilds.last.activeCallRoute?.isVideo, isTrue);

    notifier.endCall();
    await flushMicrotasks();
  });
}
