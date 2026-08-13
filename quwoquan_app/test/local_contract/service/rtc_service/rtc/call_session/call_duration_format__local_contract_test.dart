// spec_ref: specs/feature-tree/chat-conversation/realtime-call/call-experience/spec.md#gwt-011
// spec_ref: specs/feature-tree/chat-conversation/realtime-call/call-experience/spec.md#gwt-011.t1
// spec_ref: specs/feature-tree/chat-conversation/realtime-call/call-experience/spec.md#gwt-011.t2
// spec_ref: specs/feature-tree/chat-conversation/realtime-call/call-experience/spec.md#gwt-011.t3
//
// 通话时长展示单一真相源契约：
// >1h 通话必须渲染 HH:MM:SS（历史缺陷：ActiveCallBar/PiP 自写格式化
// 丢弃小时位）；ActiveCallBar 与 PiP 计时必须与 formatCallDuration 同源。
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/application/active_call_service.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/application/call_timer_provider.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/presentation/active_call_bar.dart';
import 'package:quwoquan_app/runtime/platform/platform_providers.dart';
import 'package:quwoquan_app/runtime/platform/screen_wake_gateway.dart';

void main() {
  test('formatCallDuration 覆盖秒/分/时边界', () {
    expect(formatCallDuration(Duration.zero), '00:00');
    expect(formatCallDuration(const Duration(seconds: 59)), '00:59');
    expect(formatCallDuration(const Duration(minutes: 59, seconds: 59)), '59:59');
    expect(formatCallDuration(const Duration(hours: 1)), '01:00:00');
    expect(
      formatCallDuration(const Duration(minutes: 61, seconds: 5)),
      '01:01:05',
      reason: '61 分钟通话不得丢弃小时位显示为 01:05',
    );
    expect(
      formatCallDuration(const Duration(hours: 10, minutes: 2, seconds: 3)),
      '10:02:03',
    );
  });

  test('CallTimerState.formattedTime 与 formatCallDuration 同源', () {
    const state = CallTimerState(elapsed: Duration(minutes: 61, seconds: 5));
    expect(state.formattedTime, formatCallDuration(state.elapsed));
  });

  testWidgets('ActiveCallBar 对 61 分钟通话渲染 HH:MM:SS', (tester) async {
    final container = ProviderContainer(
      overrides: [
        screenWakeGatewayProvider.overrideWithValue(
          const UnsupportedScreenWakeGateway(),
        ),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: MaterialApp(home: Scaffold(body: ActiveCallBar(onTap: () {}))),
      ),
    );
    container.read(activeCallProvider.notifier).startCall(
      callId: 'call-timer-hours',
      callType: 'audio',
    );
    // fake async 推进 61 分钟：通话计时器逐秒 tick 到 01:01:05。
    await tester.pump(const Duration(minutes: 61, seconds: 5));
    await tester.pump();

    expect(
      find.textContaining('01:01:05'),
      findsOneWidget,
      reason: '通话条必须显示小时位',
    );
    expect(find.textContaining(CallText.callOngoing), findsOneWidget);

    container.read(activeCallProvider.notifier).endCall();
    await tester.pump();
  });
}
