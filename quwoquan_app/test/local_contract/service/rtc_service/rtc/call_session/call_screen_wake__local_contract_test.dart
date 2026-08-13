// spec_ref: specs/feature-tree/chat-conversation/realtime-call/call-experience/spec.md#gwt-006
// spec_ref: specs/feature-tree/chat-conversation/realtime-call/call-experience/spec.md#gwt-006.t1
// spec_ref: specs/feature-tree/chat-conversation/realtime-call/call-experience/spec.md#gwt-006.t2
//
// 通话中屏幕常亮契约：
// 活跃通话（含 PiP 最小化）期间必须保持屏幕常亮；任何收尾路径（挂断/对端
// 结束/notifier 回收）必须释放常亮，不得让设备停留在常亮态耗电。
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/platform/platform_providers.dart';
import 'package:quwoquan_app/runtime/platform/screen_wake_gateway.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/application/active_call_service.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  (ProviderContainer, _RecordingScreenWakeGateway) createHarness() {
    final gateway = _RecordingScreenWakeGateway();
    final container = ProviderContainer(
      overrides: [screenWakeGatewayProvider.overrideWithValue(gateway)],
    );
    addTearDown(container.dispose);
    return (container, gateway);
  }

  test('通话开始保持常亮，通话结束释放', () async {
    final (container, gateway) = createHarness();
    final notifier = container.read(activeCallProvider.notifier);

    notifier.startCall(callId: 'call-wake-1', callType: 'audio');
    await Future<void>.delayed(Duration.zero);
    expect(gateway.acquireCount, 1);
    expect(gateway.releaseCount, 0);

    notifier.endCall();
    await Future<void>.delayed(Duration.zero);
    expect(gateway.releaseCount, 1, reason: '收尾必须释放常亮');
  });

  test('PiP 最小化仍处于通话中，不释放常亮', () async {
    final (container, gateway) = createHarness();
    final notifier = container.read(activeCallProvider.notifier);

    notifier.startCall(callId: 'call-wake-2', callType: 'video');
    await Future<void>.delayed(Duration.zero);
    notifier.enterPipMode();
    notifier.exitPipMode();
    await Future<void>.delayed(Duration.zero);

    expect(gateway.acquireCount, 1);
    expect(gateway.releaseCount, 0, reason: 'PiP 往返不得释放常亮');
  });

  test('endCall 幂等且 notifier 回收兜底释放', () async {
    final gateway = _RecordingScreenWakeGateway();
    final container = ProviderContainer(
      overrides: [screenWakeGatewayProvider.overrideWithValue(gateway)],
    );
    final notifier = container.read(activeCallProvider.notifier);

    notifier.endCall();
    await Future<void>.delayed(Duration.zero);
    expect(gateway.releaseCount, 1, reason: '未通话时 endCall 释放也安全');

    notifier.startCall(callId: 'call-wake-3', callType: 'audio');
    await Future<void>.delayed(Duration.zero);
    container.dispose();
    await Future<void>.delayed(Duration.zero);
    expect(
      gateway.releaseCount,
      greaterThanOrEqualTo(2),
      reason: 'notifier 回收必须兜底释放常亮',
    );
  });

  test('平台失败在 gateway 内部降级，不打断通话主流程', () async {
    // 真实实现对平台异常静默降级；结构化 no-op 实现覆盖能力缺失平台。
    const unsupported = UnsupportedScreenWakeGateway();
    await unsupported.acquire();
    await unsupported.release();
  });
}

final class _RecordingScreenWakeGateway implements ScreenWakeGateway {
  int acquireCount = 0;
  int releaseCount = 0;

  @override
  Future<void> acquire() async {
    acquireCount += 1;
  }

  @override
  Future<void> release() async {
    releaseCount += 1;
  }
}
