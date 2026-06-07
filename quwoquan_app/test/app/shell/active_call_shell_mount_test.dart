import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/app_router.dart';
import 'package:quwoquan_app/cloud/rtc/incoming_call_coordinator.dart';
import 'package:quwoquan_app/core/services/active_call_service.dart';
import 'package:quwoquan_app/ui/rtc/widgets/active_call_bar.dart';
import 'package:quwoquan_app/ui/rtc/widgets/pip_call_overlay.dart';

class _TestActiveCallNotifier extends ActiveCallNotifier {
  _TestActiveCallNotifier(this._initial);
  final ActiveCallState _initial;
  @override
  ActiveCallState build() => _initial;
}

/// 复现 shell 全局挂载层：ActiveCallBar（顶部回流条）+ PipCallOverlay（悬浮窗）
/// 在同一帧由唯一外壳承载，二者只随 [activeCallProvider] 状态显隐。
Widget _buildMountLayer({
  required ActiveCallState callState,
  VoidCallback? onReturn,
  VoidCallback? onHangup,
}) {
  return ProviderScope(
    overrides: [
      activeCallProvider.overrideWith(
        () => _TestActiveCallNotifier(callState),
      ),
    ],
    child: MaterialApp(
      home: Scaffold(
        body: Stack(
          children: [
            const SizedBox.expand(),
            Column(
              children: [
                ActiveCallBar(onTap: onReturn ?? () {}),
                const Expanded(child: SizedBox.shrink()),
              ],
            ),
            PipCallOverlay(
              onReturnToCall: onReturn ?? () {},
              onHangup: onHangup ?? () {},
            ),
          ],
        ),
      ),
    ),
  );
}

void main() {
  // ──────────────────────────────────────────────────────────────────
  // B1 根因①：incomingCallCoordinatorProvider 不再依赖未实现的
  // goRouterProvider 占位，必须能直接通过 appRouterProvider 解析。
  // ──────────────────────────────────────────────────────────────────
  group('B1 全局挂载 — 协调器装配', () {
    test('incomingCallCoordinatorProvider 经 appRouterProvider 装配，不依赖占位', () {
      // 用最小 GoRouter override appRouterProvider，避免拉起真实路由/CallKit
      // 平台依赖；只验证协调器装配指向 appRouterProvider（旧 goRouterProvider
      // 占位已删除），解析不抛 UnimplementedError。
      final container = ProviderContainer(
        overrides: [
          appRouterProvider.overrideWithValue(
            GoRouter(
              routes: [
                GoRoute(
                  path: '/',
                  builder: (context, state) => const SizedBox.shrink(),
                ),
              ],
            ),
          ),
        ],
      );
      addTearDown(container.dispose);

      final coordinator = container.read(incomingCallCoordinatorProvider);
      expect(coordinator, isA<IncomingCallCoordinator>());
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // B1 根因②：登录态 -> 协调器唯一启停。避免重复 start（多重来电监听）
  // 与漏 stop（登出后仍响铃）。
  // ──────────────────────────────────────────────────────────────────
  group('B1 全局挂载 — 登录态唯一启停', () {
    test('游客态：不启动、不停止', () {
      final d = resolveIncomingCallSync(boundUserId: '', nextUserId: '');
      expect(d.shouldStart, isFalse);
      expect(d.shouldStop, isFalse);
      expect(d.boundUserId, '');
    });

    test('登录：启动一次并绑定用户', () {
      final d = resolveIncomingCallSync(boundUserId: '', nextUserId: 'u1');
      expect(d.shouldStart, isTrue);
      expect(d.shouldStop, isFalse);
      expect(d.boundUserId, 'u1');
    });

    test('同一用户重复同步：幂等，不重复 start', () {
      final d = resolveIncomingCallSync(boundUserId: 'u1', nextUserId: 'u1');
      expect(d.shouldStart, isFalse);
      expect(d.shouldStop, isFalse);
      expect(d.boundUserId, 'u1');
    });

    test('切换用户：先停旧再启新', () {
      final d = resolveIncomingCallSync(boundUserId: 'u1', nextUserId: 'u2');
      expect(d.shouldStop, isTrue);
      expect(d.shouldStart, isTrue);
      expect(d.boundUserId, 'u2');
    });

    test('登出：停止并解绑，不再 start', () {
      final d = resolveIncomingCallSync(boundUserId: 'u1', nextUserId: '');
      expect(d.shouldStop, isTrue);
      expect(d.shouldStart, isFalse);
      expect(d.boundUserId, '');
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // B1 挂载层：来电条 + PiP 悬浮窗在同一外壳唯一承载，按状态显隐与回流。
  // ──────────────────────────────────────────────────────────────────
  group('B1 全局挂载 — 来电条/PiP 唯一挂载与回流', () {
    testWidgets('无通话：来电条与 PiP 均不渲染内容', (tester) async {
      await tester.pumpWidget(
        _buildMountLayer(callState: const ActiveCallState(isInCall: false)),
      );
      await tester.pump();

      expect(find.byType(ActiveCallBar), findsOneWidget);
      expect(find.byType(PipCallOverlay), findsOneWidget);
      expect(find.textContaining('通话中'), findsNothing);
    });

    testWidgets('通话中：来电条唯一可见并支持点击回流', (tester) async {
      var returned = false;
      await tester.pumpWidget(
        _buildMountLayer(
          callState: const ActiveCallState(
            callId: 'call_001',
            callType: 'video',
            isInCall: true,
            elapsed: Duration(seconds: 12),
          ),
          onReturn: () => returned = true,
        ),
      );
      await tester.pump();

      expect(find.byType(ActiveCallBar), findsOneWidget);
      expect(find.textContaining('点击返回'), findsOneWidget);

      await tester.tap(find.byType(ActiveCallBar));
      await tester.pump();
      expect(returned, isTrue);
    });

    testWidgets('PiP 模式：悬浮窗唯一渲染并支持回流', (tester) async {
      var returned = false;
      await tester.pumpWidget(
        _buildMountLayer(
          callState: const ActiveCallState(
            callId: 'call_001',
            callType: 'video',
            isInCall: true,
            isPipMode: true,
            elapsed: Duration(seconds: 30),
          ),
          onReturn: () => returned = true,
        ),
      );
      await tester.pump();

      expect(find.byType(PipCallOverlay), findsOneWidget);
      // PiP 悬浮窗子树内承载时长文本（00:30 也出现在顶部来电条，故限定到 PiP）。
      expect(
        find.descendant(
          of: find.byType(PipCallOverlay),
          matching: find.textContaining('00:30'),
        ),
        findsOneWidget,
      );

      await tester.tap(find.byType(GestureDetector).last);
      await tester.pump();
      expect(returned, isTrue);
    });
  });
}
