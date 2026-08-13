// spec_ref: specs/feature-tree/chat-conversation/realtime-call/call-experience/spec.md#gwt-013
//
// 呼出页重建面契约：
// 振铃计时每秒 tick 只允许重建隔离的时长子组件，不得整页重建
// OutgoingCallPage（对齐 voice/video 页的 CallDurationBadge 隔离模式）。
// 探针：页面顶层 build 产生的 Text 实例在 tick 前后必须 identical；
// 时长文本自身必须随 tick 推进。
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/presentation/outgoing_call_page.dart';

void main() {
  testWidgets('计时 tick 只重建时长子组件，不整页重建', (tester) async {
    await tester.pumpWidget(
      const ProviderScope(
        child: MaterialApp(home: OutgoingCallPage(callId: 'call-rebuild')),
      ),
    );
    // postFrameCallback 启动计时器。
    await tester.pump();
    await tester.pump();

    expect(find.text('00:00'), findsOneWidget);
    final titleBefore = tester.widget<Text>(
      find.text(CallText.callOutgoingCalling),
    );

    // fake async 推进 2 次 tick。
    await tester.pump(const Duration(seconds: 2));
    await tester.pump();

    expect(find.text('00:02'), findsOneWidget, reason: '时长子组件必须随 tick 推进');
    final titleAfter = tester.widget<Text>(
      find.text(CallText.callOutgoingCalling),
    );
    expect(
      identical(titleBefore, titleAfter),
      isTrue,
      reason: '计时 tick 不得整页重建呼出页（顶层 Text 实例应保持不变）',
    );

    // 清理计时器与页面。
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump(const Duration(seconds: 2));
  });
}
