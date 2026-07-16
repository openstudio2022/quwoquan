import 'dart:io';

import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/ui/welcome/pages/welcome_screen.dart';
import 'package:quwoquan_app/ui/welcome/welcome_motion_timeline.dart';
import 'package:quwoquan_app/ui/welcome/widgets/welcome_brand_cluster.dart';
import 'package:quwoquan_app/ui/welcome/widgets/welcome_flower_mark.dart';

void main() {
  const timing = StartupWelcomeTiming.test();

  Widget wrap(
    WidgetTester tester, {
    VoidCallback? onFinish,
    WelcomeFlowMode flowMode = WelcomeFlowMode.startup,
    bool shellEntryReady = false,
    Duration initialProcessElapsed = Duration.zero,
    StartupWelcomeTiming startupTiming = timing,
    ValueChanged<WelcomeSequenceEvent>? onEvent,
    bool disableAnimations = false,
  }) {
    final clockOrigin = tester.binding.clock.now();
    return CupertinoApp(
      builder: (context, child) => MediaQuery(
        data: MediaQueryData(
          size: const Size(393, 852),
          disableAnimations: disableAnimations,
        ),
        child: child!,
      ),
      home: WelcomeScreen(
        onFinish: onFinish ?? () {},
        flowMode: flowMode,
        shellEntryReady: shellEntryReady,
        timing: startupTiming,
        elapsedSinceProcessStart: () =>
            initialProcessElapsed +
            tester.binding.clock.now().difference(clockOrigin),
        deadlineOrigin: () => 'test_process',
        onSequenceEvent: onEvent,
      ),
    );
  }

  List<double> petalBloomAmounts(WidgetTester tester) => tester
      .widget<WelcomeFlowerMark>(find.byType(WelcomeFlowerMark))
      .petalBloomAmounts;

  Future<void> pumpFor(
    WidgetTester tester,
    Duration duration, {
    Duration step = const Duration(milliseconds: 5),
  }) async {
    var elapsed = Duration.zero;
    while (elapsed < duration) {
      final remaining = duration - elapsed;
      final frame = remaining < step ? remaining : step;
      await tester.pump(frame);
      elapsed += frame;
    }
    await tester.pump();
  }

  Future<void> pumpUntil(
    WidgetTester tester,
    bool Function() condition, {
    Duration timeout = const Duration(milliseconds: 400),
  }) async {
    var elapsed = Duration.zero;
    while (!condition() && elapsed < timeout) {
      await tester.pump(const Duration(milliseconds: 5));
      elapsed += const Duration(milliseconds: 5);
    }
    await tester.pump();
  }

  group('WelcomeMotionTimeline', () {
    test('全开终态严格为 1，花苞态为历史 0.561 视觉因子', () {
      expect(
        WelcomeMotionTimeline.petalBloomAmounts(
          phase: WelcomeMotionPhase.nativeStatic,
          phaseProgress: 0,
        ),
        everyElement(1),
      );
      expect(
        WelcomeMotionTimeline.petalBloomAmounts(
          phase: WelcomeMotionPhase.budPause,
          phaseProgress: 0.5,
        ),
        everyElement(0),
      );
      expect(
        WelcomeMotionTimeline.petalBloomAmounts(
          phase: WelcomeMotionPhase.openSettle,
          phaseProgress: 1,
        ),
        everyElement(1),
      );
      expect(
        WelcomeFlowerMarkPainter.visualFactorFor(0),
        closeTo(0.561024, 0.000001),
      );
    });

    test('聚拢严格 7→0，绽放严格 0→7', () {
      const production = StartupWelcomeTiming.production;
      for (var position = 0; position < 7; position++) {
        final gatherElapsedUs =
            production.gatherPetalStagger.inMicroseconds * (position + 1) - 1;
        final gathering = WelcomeMotionTimeline.petalBloomAmounts(
          phase: WelcomeMotionPhase.gathering,
          phaseProgress:
              gatherElapsedUs / production.gatheringDuration.inMicroseconds,
        );
        expect(
          gathering[WelcomeMotionTimeline.gatheringOrder[position]],
          lessThan(1),
        );
        expect(
          gathering[WelcomeMotionTimeline.gatheringOrder[position + 1]],
          1,
        );

        final bloomElapsedUs =
            production.bloomPetalStagger.inMicroseconds * (position + 1) - 1;
        final blooming = WelcomeMotionTimeline.petalBloomAmounts(
          phase: WelcomeMotionPhase.blooming,
          phaseProgress:
              bloomElapsedUs / production.bloomingDuration.inMicroseconds,
        );
        expect(
          blooming[WelcomeMotionTimeline.bloomingOrder[position]],
          greaterThan(0),
        );
        expect(blooming[WelcomeMotionTimeline.bloomingOrder[position + 1]], 0);
      }
    });

    test('绽放中段波次肉眼可辨，且每片花瓣径向运动单调', () {
      final halfway = WelcomeMotionTimeline.petalBloomAmounts(
        phase: WelcomeMotionPhase.blooming,
        phaseProgress: 0.5,
      ).map(WelcomeFlowerMarkPainter.visualFactorFor).toList();
      expect(
        halfway.reduce((a, b) => a > b ? a : b) -
            halfway.reduce((a, b) => a < b ? a : b),
        greaterThanOrEqualTo(0.20),
      );

      for (var petal = 0; petal < WelcomeMotionTimeline.petalCount; petal++) {
        var previousGatherRadius = double.infinity;
        var previousBloomRadius = 0.0;
        for (var step = 0; step <= 100; step++) {
          final progress = step / 100;
          final gathering = WelcomeMotionTimeline.petalBloomAmounts(
            phase: WelcomeMotionPhase.gathering,
            phaseProgress: progress,
          );
          final gatherRadius = WelcomeFlowerMarkPainter.geometryFor(
            bloomAmount: gathering[petal],
          ).centerRadius;
          expect(gatherRadius, lessThanOrEqualTo(previousGatherRadius + 1e-9));
          previousGatherRadius = gatherRadius;

          final blooming = WelcomeMotionTimeline.petalBloomAmounts(
            phase: WelcomeMotionPhase.blooming,
            phaseProgress: progress,
          );
          final bloomRadius = WelcomeFlowerMarkPainter.geometryFor(
            bloomAmount: blooming[petal],
          ).centerRadius;
          expect(bloomRadius, greaterThanOrEqualTo(previousBloomRadius - 1e-9));
          previousBloomRadius = bloomRadius;
        }
      }
    });

    test('花瓣全程等比且固定角度，不发生单轴伸缩', () {
      const expectedAspect =
          AppSpacing.welcomePetalWidth / AppSpacing.welcomePetalHeight;
      for (var step = 0; step <= 100; step++) {
        final geometry = WelcomeFlowerMarkPainter.geometryFor(
          bloomAmount: step / 100,
        );
        final aspect = geometry.size.width / geometry.size.height;
        expect(
          ((aspect - expectedAspect) / expectedAspect).abs(),
          lessThanOrEqualTo(0.005),
        );
      }
      for (
        var index = 0;
        index < WelcomeFlowerMarkPainter.petalCount;
        index++
      ) {
        expect(
          (WelcomeFlowerMarkPainter.petalRotations[index] - index * 45).abs(),
          lessThanOrEqualTo(0.5),
        );
      }
    });

    test('生产时间契约为一轮 1480ms、3s 目标、6s 硬门、最多两次重放', () {
      const production = StartupWelcomeTiming.production;
      expect(production.gatheringDuration.inMilliseconds, 415);
      expect(production.bloomingDuration.inMilliseconds, 815);
      expect(production.primaryCycleDuration.inMilliseconds, 1480);
      expect(production.replayCycleDuration.inMilliseconds, 1390);
      expect(production.softEntryTarget, const Duration(seconds: 3));
      expect(production.hardEntryDeadline, const Duration(seconds: 6));
      expect(production.maxReplayCount, 2);
    });
  });

  group('WelcomeScreen startup state machine', () {
    testWidgets('Flutter 第一帧即为完整品牌全开终态且不显示启动提示', (tester) async {
      await tester.pumpWidget(wrap(tester));

      expect(find.byType(WelcomeBrandCluster), findsOneWidget);
      expect(find.text(UITextConstants.welcomeTitle), findsOneWidget);
      expect(find.text(UITextConstants.welcomeMainSlogan), findsOneWidget);
      expect(petalBloomAmounts(tester), everyElement(1));
      expect(
        find.text(UITextConstants.startupStillStartingInline),
        findsNothing,
      );
    });

    testWidgets('ready 很早也完整播放首轮，只在最终全开边界退出一次', (tester) async {
      var finishCount = 0;
      final events = <WelcomeSequenceEvent>[];
      await tester.pumpWidget(
        wrap(
          tester,
          shellEntryReady: true,
          onFinish: () => finishCount++,
          onEvent: events.add,
        ),
      );
      await tester.pump();
      await pumpFor(tester, const Duration(milliseconds: 45));
      expect(finishCount, 0);
      expect(
        events.any((event) => event.phase == WelcomeMotionPhase.gathering),
        isTrue,
      );

      await pumpUntil(tester, () => finishCount == 1);
      expect(
        finishCount,
        1,
        reason: events
            .map((event) => '${event.phase.name}:${event.cycleIndex}')
            .join(','),
      );
      expect(events.last.exitReason, WelcomeExitReason.readyPrimary);
      expect(events.last.phase, WelcomeMotionPhase.finished);
      expect(events.last.toProperties()['exitReason'], 'ready_primary');
      expect(events.last.toProperties()['motionSpecVersion'], 'petal_bloom_v2');
      expect(events.last.toProperties(), contains('welcomeExitMs'));
      expect(petalBloomAmounts(tester), everyElement(1));
      await pumpFor(tester, const Duration(seconds: 1));
      expect(
        finishCount,
        1,
        reason: events
            .map((event) => '${event.phase.name}:${event.cycleIndex}')
            .join(','),
      );
    });

    testWidgets('动画中 readiness 只锁存，到本轮 openSettle 后才退出', (tester) async {
      var finishCount = 0;
      final ready = ValueNotifier<bool>(false);
      final events = <WelcomeSequenceEvent>[];
      addTearDown(ready.dispose);
      final origin = tester.binding.clock.now();

      await tester.pumpWidget(
        CupertinoApp(
          home: ValueListenableBuilder<bool>(
            valueListenable: ready,
            builder: (context, value, _) => WelcomeScreen(
              onFinish: () => finishCount++,
              flowMode: WelcomeFlowMode.startup,
              shellEntryReady: value,
              timing: timing,
              elapsedSinceProcessStart: () =>
                  tester.binding.clock.now().difference(origin),
              deadlineOrigin: () => 'test_process',
              onSequenceEvent: events.add,
            ),
          ),
        ),
      );
      await tester.pump();
      await pumpFor(tester, const Duration(milliseconds: 25));
      ready.value = true;
      await tester.pump();
      expect(finishCount, 0);

      await pumpUntil(tester, () => finishCount == 1);
      expect(finishCount, 1);
      expect(events.last.exitReason, WelcomeExitReason.readyPrimary);
      expect(events.last.readyAtCycleStart, isFalse);
      expect(events.last.readyAtCycleEnd, isTrue);
    });

    testWidgets('未 ready 才显示单行提示，最多两次重放后进入降级 Shell', (tester) async {
      var finishCount = 0;
      final events = <WelcomeSequenceEvent>[];
      await tester.pumpWidget(
        wrap(tester, onFinish: () => finishCount++, onEvent: events.add),
      );
      await tester.pump();
      await pumpFor(tester, const Duration(milliseconds: 45));
      expect(
        find.text(UITextConstants.startupStillStartingInline),
        findsNothing,
      );

      await pumpUntil(
        tester,
        () => find
            .text(UITextConstants.startupStillStartingInline)
            .evaluate()
            .isNotEmpty,
      );
      final hint = tester.widget<Text>(
        find.text(UITextConstants.startupStillStartingInline),
      );
      expect(hint.maxLines, 1);
      expect(hint.overflow, TextOverflow.ellipsis);

      await pumpUntil(tester, () => finishCount == 1);
      expect(finishCount, 1);
      expect(events.last.replayCount, 2);
      expect(events.last.exitReason, WelcomeExitReason.degraded);
      expect(
        events
            .where((event) => event.phase == WelcomeMotionPhase.gathering)
            .map((event) => event.cycleIndex)
            .toSet(),
        <int>{0, 1, 2},
      );
    });

    testWidgets('剩余预算不足 0.65 个首轮时保持全开短停后按 deadline 退出', (tester) async {
      var finishCount = 0;
      final events = <WelcomeSequenceEvent>[];
      await tester.pumpWidget(
        wrap(
          tester,
          initialProcessElapsed: const Duration(milliseconds: 260),
          onFinish: () => finishCount++,
          onEvent: events.add,
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 15));

      expect(finishCount, 1);
      expect(events.last.exitReason, WelcomeExitReason.deadline);
      expect(petalBloomAmounts(tester), everyElement(1));
      expect(
        events.any((event) => event.phase == WelcomeMotionPhase.gathering),
        isFalse,
      );
    });

    testWidgets('预算可压缩时仍完整聚拢再绽放，并记录 animationCompressed', (tester) async {
      var finishCount = 0;
      final events = <WelcomeSequenceEvent>[];
      await tester.pumpWidget(
        wrap(
          tester,
          initialProcessElapsed: const Duration(milliseconds: 235),
          onFinish: () => finishCount++,
          onEvent: events.add,
        ),
      );
      await tester.pump();
      await pumpFor(tester, const Duration(milliseconds: 65));

      expect(finishCount, 1);
      expect(events.any((event) => event.animationCompressed), isTrue);
      expect(
        events.any((event) => event.phase == WelcomeMotionPhase.budPause),
        isTrue,
      );
      expect(petalBloomAmounts(tester), everyElement(1));
    });

    testWidgets('deadline 与 readiness 同帧竞争时 terminal latch 只回调一次', (
      tester,
    ) async {
      var finishCount = 0;
      final ready = ValueNotifier<bool>(false);
      addTearDown(ready.dispose);
      final origin = tester.binding.clock.now();
      await tester.pumpWidget(
        CupertinoApp(
          home: ValueListenableBuilder<bool>(
            valueListenable: ready,
            builder: (context, value, _) => WelcomeScreen(
              onFinish: () => finishCount++,
              flowMode: WelcomeFlowMode.startup,
              shellEntryReady: value,
              timing: timing,
              elapsedSinceProcessStart: () =>
                  const Duration(milliseconds: 290) +
                  tester.binding.clock.now().difference(origin),
            ),
          ),
        ),
      );
      await tester.pump();
      ready.value = true;
      await tester.pump(const Duration(milliseconds: 20));
      await tester.pump(const Duration(seconds: 1));
      expect(finishCount, 1);
    });

    testWidgets('/welcome entry 模式固定一轮退出，不依赖 startup readiness', (
      tester,
    ) async {
      var finishCount = 0;
      final events = <WelcomeSequenceEvent>[];
      await tester.pumpWidget(
        wrap(
          tester,
          flowMode: WelcomeFlowMode.entry,
          shellEntryReady: false,
          onFinish: () => finishCount++,
          onEvent: events.add,
        ),
      );
      await tester.pump();
      await pumpUntil(tester, () => finishCount == 1);

      expect(finishCount, 1);
      expect(events.last.exitReason, WelcomeExitReason.entryComplete);
      expect(events.last.replayCount, 0);
      expect(
        find.text(UITextConstants.startupStillStartingInline),
        findsNothing,
      );
    });

    testWidgets('reduced motion 保持全开静态帧并快速进入，不无限等待', (tester) async {
      var finishCount = 0;
      final events = <WelcomeSequenceEvent>[];
      await tester.pumpWidget(
        wrap(
          tester,
          disableAnimations: true,
          onFinish: () => finishCount++,
          onEvent: events.add,
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 15));

      expect(finishCount, 1);
      expect(events.last.exitReason, WelcomeExitReason.degraded);
      expect(events.last.motionReduced, isTrue);
      expect(petalBloomAmounts(tester), everyElement(1));
    });

    testWidgets('后台暂停动画，恢复时若超过硬期限直接退出', (tester) async {
      var finishCount = 0;
      final events = <WelcomeSequenceEvent>[];
      await tester.pumpWidget(
        wrap(tester, onFinish: () => finishCount++, onEvent: events.add),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 25));
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
      await tester.pump(const Duration(milliseconds: 400));
      expect(finishCount, 0);

      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      await tester.pump();
      expect(finishCount, 1);
      expect(events.last.exitReason, WelcomeExitReason.deadline);
    });

    testWidgets('dispose 后不发生 controller 或 timer 回写', (tester) async {
      await tester.pumpWidget(wrap(tester));
      await tester.pump(const Duration(milliseconds: 20));
      await tester.pumpWidget(const SizedBox.shrink());
      await tester.pump(const Duration(seconds: 1));
      expect(tester.takeException(), isNull);
    });
  });

  test('花瓣绘制只做同比例二维开放，禁止透视、单轴伸缩和二次 easing', () {
    final source = _readAppFile(
      'lib/ui/welcome/widgets/welcome_flower_mark.dart',
    );
    expect(source, contains('canvas.scale(visualFactor)'));
    expect(source, contains('historicalBudVisualFactor = 0.561024'));
    expect(source, isNot(contains('Matrix4')));
    expect(source, isNot(contains('setEntry')));
    expect(source, isNot(contains('rotateX')));
    expect(source, isNot(contains('rotateY')));
    expect(source, isNot(contains('Curves.')));
    expect(source, isNot(contains('scaleY')));
  });

  test('全开首帧与最终全开 golden 字节一致', () {
    final first = File(
      'test/local_contract/ui/welcome/goldens/welcome_flower_full_open.png',
    );
    final finalFrame = File(
      'test/local_contract/ui/welcome/goldens/welcome_flower_final_open.png',
    );
    expect(first.readAsBytesSync(), finalFrame.readAsBytesSync());
  });
}

String _readAppFile(String relativePath) {
  final direct = File(relativePath);
  if (direct.existsSync()) {
    return direct.readAsStringSync();
  }
  return File('quwoquan_app/$relativePath').readAsStringSync();
}
