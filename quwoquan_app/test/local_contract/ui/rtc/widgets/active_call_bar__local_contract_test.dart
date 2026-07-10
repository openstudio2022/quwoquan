import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/services/active_call_service.dart';
import 'package:quwoquan_app/ui/rtc/widgets/active_call_bar.dart';

Widget _buildBar({
  VoidCallback? onTap,
  ActiveCallState? initialState,
}) {
  return ProviderScope(
    overrides: [
      if (initialState != null)
        activeCallProvider.overrideWith(() {
          return _TestActiveCallNotifier(initialState);
        }),
    ],
    child: MaterialApp(
      home: Scaffold(
        body: ActiveCallBar(
          onTap: onTap ?? () {},
        ),
      ),
    ),
  );
}

class _TestActiveCallNotifier extends ActiveCallNotifier {
  _TestActiveCallNotifier(this._initial);

  final ActiveCallState _initial;

  @override
  ActiveCallState build() => _initial;
}

void main() {
  // ──────────────────────────────────────────────────────────────────
  // 渲染契约
  // ──────────────────────────────────────────────────────────────────
  group('ActiveCallBar — 渲染契约', () {
    testWidgets('通话中显示绿色背景', (tester) async {
      await tester.pumpWidget(_buildBar(
        initialState: const ActiveCallState(
          callId: 'call_001',
          callType: 'video',
          isInCall: true,
          elapsed: Duration(minutes: 2, seconds: 30),
        ),
      ));
      await tester.pump();

      expect(find.byType(ActiveCallBar), findsOneWidget);
      expect(find.byType(Container), findsWidgets);
    });

    testWidgets('计时器显示正确格式 MM:SS', (tester) async {
      await tester.pumpWidget(_buildBar(
        initialState: const ActiveCallState(
          callId: 'call_001',
          callType: 'audio',
          isInCall: true,
          elapsed: Duration(minutes: 5, seconds: 42),
        ),
      ));
      await tester.pump();

      expect(find.textContaining('05:42'), findsOneWidget);
    });

    testWidgets('计时器零分零秒显示 00:00', (tester) async {
      await tester.pumpWidget(_buildBar(
        initialState: const ActiveCallState(
          callId: 'call_001',
          callType: 'audio',
          isInCall: true,
          elapsed: Duration.zero,
        ),
      ));
      await tester.pump();

      expect(find.textContaining('00:00'), findsOneWidget);
    });

    testWidgets('显示通话中文本', (tester) async {
      await tester.pumpWidget(_buildBar(
        initialState: const ActiveCallState(
          callId: 'call_001',
          callType: 'audio',
          isInCall: true,
          elapsed: Duration(seconds: 15),
        ),
      ));
      await tester.pump();

      expect(find.textContaining('通话中'), findsOneWidget);
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // 交互契约
  // ──────────────────────────────────────────────────────────────────
  group('ActiveCallBar — 交互契约', () {
    testWidgets('点击触发 onTap 回调', (tester) async {
      var tapCalled = false;
      await tester.pumpWidget(_buildBar(
        onTap: () => tapCalled = true,
        initialState: const ActiveCallState(
          callId: 'call_001',
          callType: 'video',
          isInCall: true,
          elapsed: Duration(minutes: 1),
        ),
      ));
      await tester.pump();

      await tester.tap(find.byType(GestureDetector).first);
      await tester.pump();

      expect(tapCalled, isTrue);
    });

    testWidgets('显示 "点击返回" 提示文本', (tester) async {
      await tester.pumpWidget(_buildBar(
        initialState: const ActiveCallState(
          callId: 'call_001',
          callType: 'audio',
          isInCall: true,
          elapsed: Duration(seconds: 30),
        ),
      ));
      await tester.pump();

      expect(find.textContaining('点击返回'), findsOneWidget);
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // 错误态渲染
  // ──────────────────────────────────────────────────────────────────
  group('ActiveCallBar — 错误态渲染', () {
    testWidgets('不在通话时不渲染 → SizedBox.shrink', (tester) async {
      await tester.pumpWidget(_buildBar(
        initialState: const ActiveCallState(isInCall: false),
      ));
      await tester.pump();

      expect(find.byType(ActiveCallBar), findsOneWidget);
      expect(find.textContaining('通话中'), findsNothing);
    });

    testWidgets('默认状态（无通话）不渲染内容', (tester) async {
      await tester.pumpWidget(_buildBar());
      await tester.pump();

      expect(find.textContaining('通话中'), findsNothing);
    });
  });
}
