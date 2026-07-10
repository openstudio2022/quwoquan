import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/ui/rtc/models/call_state.dart';
import 'package:quwoquan_app/ui/rtc/widgets/call_controls_bar.dart';

Widget _buildBar({
  CallType callType = CallType.video,
  VoidCallback? onHangup,
  VoidCallback? onInvite,
}) {
  return ProviderScope(
    child: MaterialApp(
      builder: (context, child) => MediaQuery(
        data: const MediaQueryData(size: Size(1200, 800)),
        child: child!,
      ),
      home: Scaffold(
        body: SizedBox(
          width: 1200,
          height: 200,
          child: CallControlsBar(
            callType: callType,
            onHangup: onHangup,
            onInvite: onInvite,
            autoHide: false,
          ),
        ),
      ),
    ),
  );
}

void main() {
  // ──────────────────────────────────────────────────────────────────
  // 渲染契约
  // ──────────────────────────────────────────────────────────────────
  group('CallControlsBar — 渲染契约', () {
    testWidgets('video 模式渲染 6 个控制按钮', (tester) async {
      await tester.pumpWidget(_buildBar(callType: CallType.video));
      await tester.pump();

      expect(find.byType(CallControlsBar), findsOneWidget);

      expect(find.byIcon(CupertinoIcons.mic), findsOneWidget);
      expect(find.byIcon(CupertinoIcons.video_camera_solid), findsOneWidget);
      expect(find.byIcon(CupertinoIcons.switch_camera), findsOneWidget);
      expect(find.byIcon(CupertinoIcons.person_add), findsOneWidget);
      expect(find.byIcon(CupertinoIcons.speaker_1), findsOneWidget);
      expect(find.byIcon(CupertinoIcons.phone_down_fill), findsOneWidget);
    });

    testWidgets('voice 模式隐藏摄像头和翻转按钮', (tester) async {
      await tester.pumpWidget(_buildBar(callType: CallType.audio));
      await tester.pump();

      expect(find.byType(CallControlsBar), findsOneWidget);

      expect(find.byIcon(CupertinoIcons.switch_camera), findsNothing);

      expect(find.byIcon(CupertinoIcons.mic), findsOneWidget);
      expect(find.byIcon(CupertinoIcons.person_add), findsOneWidget);
      expect(find.byIcon(CupertinoIcons.phone_down_fill), findsOneWidget);
    });

    testWidgets('挂断按钮文本显示 "挂断"', (tester) async {
      await tester.pumpWidget(_buildBar());
      await tester.pump();

      expect(find.text('挂断'), findsOneWidget);
    });

    testWidgets('静音按钮默认显示 "静音"', (tester) async {
      await tester.pumpWidget(_buildBar());
      await tester.pump();

      expect(find.text('静音'), findsOneWidget);
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // 交互契约
  // ──────────────────────────────────────────────────────────────────
  group('CallControlsBar — 交互契约', () {
    testWidgets('点击挂断触发 onHangup 回调', (tester) async {
      var hangupCalled = false;
      await tester.pumpWidget(
        _buildBar(onHangup: () => hangupCalled = true),
      );
      await tester.pump();

      await tester.tap(find.byIcon(CupertinoIcons.phone_down_fill));
      await tester.pump();

      expect(hangupCalled, isTrue);
    });

    testWidgets('点击邀请触发 onInvite 回调', (tester) async {
      var inviteCalled = false;
      await tester.pumpWidget(
        _buildBar(onInvite: () => inviteCalled = true),
      );
      await tester.pump();

      await tester.tap(find.byIcon(CupertinoIcons.person_add));
      await tester.pump();

      expect(inviteCalled, isTrue);
    });

    testWidgets('video 模式下可见翻转按钮', (tester) async {
      await tester.pumpWidget(_buildBar(callType: CallType.video));
      await tester.pump();

      expect(find.byIcon(CupertinoIcons.switch_camera), findsOneWidget);
      expect(find.text('翻转'), findsOneWidget);
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // 错误态渲染
  // ──────────────────────────────────────────────────────────────────
  group('CallControlsBar — 错误态渲染', () {
    testWidgets('无 onHangup 回调时不崩溃', (tester) async {
      await tester.pumpWidget(_buildBar(onHangup: null));
      await tester.pump();

      expect(find.byType(CallControlsBar), findsOneWidget);

      await tester.tap(find.byIcon(CupertinoIcons.phone_down_fill));
      await tester.pump();
    });

    testWidgets('无 onInvite 回调时不崩溃', (tester) async {
      await tester.pumpWidget(_buildBar(onInvite: null));
      await tester.pump();

      await tester.tap(find.byIcon(CupertinoIcons.person_add));
      await tester.pump();

      expect(find.byType(CallControlsBar), findsOneWidget);
    });

    testWidgets('audio 模式显示开启视频选项', (tester) async {
      await tester.pumpWidget(_buildBar(callType: CallType.audio));
      await tester.pump();

      expect(find.text('开启视频'), findsOneWidget);
    });
  });
}
