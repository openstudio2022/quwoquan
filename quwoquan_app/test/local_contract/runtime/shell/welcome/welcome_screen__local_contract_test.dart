import 'dart:io';

import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/runtime/shell/welcome/welcome_screen.dart';
import 'package:quwoquan_app/runtime/shell/welcome/welcome_appearance.dart';
import 'package:quwoquan_app/runtime/shell/welcome/welcome_motion_timeline.dart';
import 'package:quwoquan_app/runtime/shell/welcome/welcome_brand_cluster.dart';
import 'package:quwoquan_app/runtime/shell/welcome/welcome_flower_mark.dart';

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
      expect(find.byType(WelcomeBrandFooter), findsOneWidget);
      expect(find.text(FoundationText.welcomeMainSlogan), findsOneWidget);
      // 「趣我圈」只作为底部品牌落款出现一次，不再有中央大标题。
      expect(find.text(FoundationText.welcomeTitle), findsOneWidget);
      expect(find.byType(ShaderMask), findsNothing);
      expect(petalBloomAmounts(tester), everyElement(1));
      expect(
        find.text(FoundationText.startupStillStartingInline),
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
      expect(events.last.toProperties()['motionSpec'], 'petal_bloom');
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
        find.text(FoundationText.startupStillStartingInline),
        findsNothing,
      );

      await pumpUntil(
        tester,
        () => find
            .text(FoundationText.startupStillStartingInline)
            .evaluate()
            .isNotEmpty,
      );
      final hint = tester.widget<Text>(
        find.text(FoundationText.startupStillStartingInline),
      );
      expect(hint.maxLines, 1);
      expect(hint.overflow, TextOverflow.ellipsis);
      // 提示固定挂在底部品牌名上方，出现时不推动品牌名重新布局。
      final hintRect = tester.getRect(
        find.text(FoundationText.startupStillStartingInline),
      );
      final brandRect = tester.getRect(find.text(FoundationText.welcomeTitle));
      expect(hintRect.bottom, lessThan(brandRect.top));

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
        find.text(FoundationText.startupStillStartingInline),
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

    testWidgets('后台暂停不取消硬截止，超时仍退出', (tester) async {
      var finishCount = 0;
      final events = <WelcomeSequenceEvent>[];
      await tester.pumpWidget(
        wrap(tester, onFinish: () => finishCount++, onEvent: events.add),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 25));
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
      // 硬截止在后台继续计时（test hardEntryDeadline=300ms）。
      await tester.pump(const Duration(milliseconds: 400));
      expect(finishCount, 1);
      expect(events.last.exitReason, WelcomeExitReason.deadline);

      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      await tester.pump();
      expect(finishCount, 1);
    });

    testWidgets('onWelcomeVisible 抛错仍启动并 finish，不永久停在终态', (tester) async {
      var finishCount = 0;
      await tester.pumpWidget(
        CupertinoApp(
          home: WelcomeScreen(
            onFinish: () => finishCount++,
            flowMode: WelcomeFlowMode.startup,
            shellEntryReady: true,
            timing: timing,
            elapsedSinceProcessStart: () => Duration.zero,
            deadlineOrigin: () => 'test_process',
            onWelcomeVisible: () {
              throw StateError('welcome visible side effect failed');
            },
          ),
        ),
      );
      await tester.pump();
      await pumpUntil(tester, () => finishCount == 1);
      expect(finishCount, 1);
      expect(tester.takeException(), isNull);
    });

    testWidgets('exit 观测回调抛错仍保证 onFinish 只回调一次', (tester) async {
      var finishCount = 0;
      await tester.pumpWidget(
        wrap(
          tester,
          shellEntryReady: true,
          onFinish: () => finishCount++,
          onEvent: (event) {
            if (event.exitReason != null) {
              throw StateError('sequence telemetry failed');
            }
          },
        ),
      );
      await tester.pump();
      await pumpUntil(tester, () => finishCount == 1);
      expect(finishCount, 1);
      await pumpFor(tester, const Duration(milliseconds: 200));
      expect(finishCount, 1);
    });

    testWidgets('dispose 后不发生 controller 或 timer 回写', (tester) async {
      await tester.pumpWidget(wrap(tester));
      await tester.pump(const Duration(milliseconds: 20));
      await tester.pumpWidget(const SizedBox.shrink());
      await tester.pump(const Duration(seconds: 1));
      expect(tester.takeException(), isNull);
    });
  });

  group('WelcomeScreen 布局与无障碍契约', () {
    Future<void> pumpFrozenFrame(
      WidgetTester tester, {
      Size viewport = const Size(393, 852),
      TextScaler? textScaler,
    }) async {
      tester.view.devicePixelRatio = 1.0;
      tester.view.physicalSize = viewport;
      addTearDown(tester.view.resetDevicePixelRatio);
      addTearDown(tester.view.resetPhysicalSize);
      await tester.binding.setSurfaceSize(viewport);
      addTearDown(() => tester.binding.setSurfaceSize(null));
      await tester.pumpWidget(
        CupertinoApp(
          builder: (context, child) => MediaQuery(
            data: MediaQuery.of(
              context,
            ).copyWith(textScaler: textScaler ?? TextScaler.noScaling),
            child: child!,
          ),
          home: WelcomeScreen(
            onFinish: () {},
            flowMode: WelcomeFlowMode.frozen,
            timing: timing,
            elapsedSinceProcessStart: () => Duration.zero,
            deadlineOrigin: () => 'test_process',
          ),
        ),
      );
    }

    test('花朵可见直径按图一占屏宽 40%，小屏下限 132、大屏上限 168', () {
      expect(AppSpacing.welcomeFlowerWidthFraction, 0.40);
      expect(
        WelcomeBrandCluster.flowerVisibleDiameterFor(393),
        closeTo(393 * AppSpacing.welcomeFlowerWidthFraction, 0.001),
      );
      expect(
        WelcomeBrandCluster.flowerVisibleDiameterFor(320),
        AppSpacing.welcomeFlowerMinDiameter,
      );
      expect(
        WelcomeBrandCluster.flowerVisibleDiameterFor(600),
        AppSpacing.welcomeFlowerMaxDiameter,
      );
      // 画布按 painter 几何换算，可见花朵直径精确等于目标值。
      final canvas = WelcomeBrandCluster.flowerCanvasDimensionFor(393);
      expect(
        canvas *
            WelcomeFlowerMarkPainter.flowerVisualDiameter /
            AppSpacing.welcomeGraphicDiameter,
        closeTo(WelcomeBrandCluster.flowerVisibleDiameterFor(393), 0.001),
      );
    });

    testWidgets('图一品牌视觉使用正式授权字体、深蓝 token 与唯一花瓣终态', (tester) async {
      await pumpFrozenFrame(tester);

      final slogan = tester.widget<Text>(
        find.text(FoundationText.welcomeMainSlogan),
      );
      expect(slogan.style?.fontFamily, AppTypography.welcomeBrandFontFamily);
      expect(
        slogan.style?.fontSize,
        AppTypography.welcomeSloganResponsive(
          tester.element(find.text(FoundationText.welcomeMainSlogan)),
        ),
      );
      expect(slogan.style?.fontSize, 32);
      expect(slogan.style?.fontWeight, FontWeight.w600);
      expect(slogan.style?.color, AppColors.welcomeForeground);

      final context = tester.element(find.byType(WelcomeFlowerMark));
      final runtimeAppearance = WelcomeAppearance.of(context);
      expect(
        identical(runtimeAppearance, WelcomeAppearance.brandMark()),
        isTrue,
      );
      expect(runtimeAppearance.petalOpacity, 1);
      expect(AppColors.welcomeGradientStart, const Color(0xFF0B70F5));
      expect(AppColors.welcomeBackground, const Color(0xFF075DE7));
      expect(AppColors.welcomeGradientEnd, const Color(0xFF053FC2));
      expect(AppColors.welcomeForeground, const Color(0xFFF7FAFF));
      expect(AppColors.welcomeForegroundMuted, const Color(0xFFD5E7FF));
    });

    test('图一近白文案在最亮与最暗品牌蓝上均满足 WCAG 对比度', () {
      expect(
        _contrastRatio(
          AppColors.welcomeForeground,
          AppColors.welcomeGradientStart,
        ),
        greaterThanOrEqualTo(3),
      );
      expect(
        _contrastRatio(
          AppColors.welcomeForegroundMuted,
          AppColors.welcomeGradientEnd,
        ),
        greaterThanOrEqualTo(4.5),
      );
    });

    testWidgets('图一标准屏品牌簇保持 40% 花朵、80% slogan 与 40dp 视觉间距', (tester) async {
      const viewport = Size(360, 800);
      await pumpFrozenFrame(tester, viewport: viewport);

      final flowerRect = tester.getRect(find.byType(WelcomeFlowerMark));
      final flowerVisibleDiameter =
          WelcomeBrandCluster.flowerVisibleDiameterFor(viewport.width);
      final flowerVisibleBottom =
          flowerRect.center.dy + flowerVisibleDiameter / 2;
      final sloganRect = tester.getRect(
        find.text(FoundationText.welcomeMainSlogan),
      );

      expect(
        flowerVisibleDiameter / viewport.width,
        closeTo(AppSpacing.welcomeFlowerWidthFraction, 0.001),
      );
      expect(sloganRect.width / viewport.width, inInclusiveRange(0.78, 0.82));
      expect(
        sloganRect.top - flowerVisibleBottom,
        closeTo(AppSpacing.welcomeFlowerSloganVisualGap, 0.5),
      );
      expect(flowerRect.center.dx, closeTo(viewport.width / 2, 0.5));
      expect(sloganRect.center.dx, closeTo(viewport.width / 2, 0.5));
    });

    testWidgets('品牌名视觉中心位于屏幕高度 89%~91%，花朵画布消费响应式直径', (tester) async {
      await pumpFrozenFrame(tester);

      final footerCenter = tester.getCenter(
        find.text(FoundationText.welcomeTitle),
      );
      expect(footerCenter.dy / 852, inInclusiveRange(0.89, 0.91));
      expect(footerCenter.dx, closeTo(393 / 2, 0.5));

      final flowerSize = tester.getSize(find.byType(WelcomeFlowerMark));
      expect(
        flowerSize.width,
        closeTo(WelcomeBrandCluster.flowerCanvasDimensionFor(393), 0.5),
      );

      // slogan 一行居中，位于花朵下方、品牌名上方。
      final sloganRect = tester.getRect(
        find.text(FoundationText.welcomeMainSlogan),
      );
      final flowerRect = tester.getRect(find.byType(WelcomeFlowerMark));
      expect(sloganRect.top, greaterThan(flowerRect.bottom - 0.5));
      expect(sloganRect.bottom, lessThan(footerCenter.dy));
      expect(sloganRect.center.dx, closeTo(393 / 2, 0.5));
    });

    testWidgets('品牌簇只暴露单一完整语义，花瓣与品牌名不重复进入焦点', (tester) async {
      final semantics = tester.ensureSemantics();
      await pumpFrozenFrame(tester);

      expect(
        find.bySemanticsLabel(WelcomeBrandCluster.semanticLabel),
        findsOneWidget,
      );
      // slogan / 品牌名文本不得再单独暴露语义节点。
      expect(
        find.bySemanticsLabel(FoundationText.welcomeMainSlogan),
        findsNothing,
      );
      expect(find.bySemanticsLabel(FoundationText.welcomeTitle), findsNothing);
      semantics.dispose();
    });

    testWidgets('极端文字缩放优先缩小字号，不截断、不溢出', (tester) async {
      await pumpFrozenFrame(
        tester,
        viewport: const Size(320, 568),
        textScaler: const TextScaler.linear(2),
      );
      await tester.pump();

      expect(tester.takeException(), isNull);
      final sloganRect = tester.getRect(
        find.text(FoundationText.welcomeMainSlogan),
      );
      expect(sloganRect.width, lessThanOrEqualTo(320));
    });

    testWidgets('横屏视口花朵触及 168 上限，布局不越界不闪退', (tester) async {
      await pumpFrozenFrame(tester, viewport: const Size(852, 393));
      await tester.pump();

      expect(tester.takeException(), isNull);
      final flowerRect = tester.getRect(find.byType(WelcomeFlowerMark));
      expect(
        flowerRect.width,
        closeTo(WelcomeBrandCluster.flowerCanvasDimensionFor(852), 0.5),
      );
      expect(flowerRect.top, greaterThanOrEqualTo(0));
      final sloganRect = tester.getRect(
        find.text(FoundationText.welcomeMainSlogan),
      );
      expect(sloganRect.bottom, lessThanOrEqualTo(393));
    });
  });

  test('花瓣绘制只做同比例二维开放，禁止透视、单轴伸缩和二次 easing', () {
    final source = _readAppFile(
      'lib/runtime/shell/welcome/welcome_flower_mark.dart',
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

  test('信息结构简化防回归：无大标题、无小趣低语、无按钮与装饰层', () {
    final welcome = _readAppFile('lib/runtime/shell/welcome/welcome_screen.dart');
    final cluster = _readAppFile(
      'lib/runtime/shell/welcome/welcome_brand_cluster.dart',
    );
    for (final source in <String>[welcome, cluster]) {
      expect(source, isNot(contains('ShaderMask')));
      expect(source, isNot(contains('assistantWhisper')));
      expect(source, isNot(contains('welcomeButtonLabel')));
      expect(source, isNot(contains('welcomeHeroTitle')));
      expect(source, isNot(contains('decorSoftBlob')));
    }
    // 品牌深蓝不随系统主题切换；状态栏浅色内容同源固定。
    final appearance = _readAppFile('lib/runtime/shell/welcome/welcome_appearance.dart');
    expect(appearance, isNot(contains('isDark')));
    expect(appearance, isNot(contains('Brightness')));
    expect(welcome, contains('SystemUiOverlayStyle'));
    expect(welcome, contains('statusBarIconBrightness: Brightness.light'));
  });

  test('品牌字体为仓内 OFL 固定资产，不保留临时 fallback 风险', () {
    final typography = _readAppFile(
      'lib/design_system/typography/app_typography.dart',
    );
    final manifest = _readAppFile('assets/fonts/bundled_fonts_manifest.yaml');
    expect(typography, contains("welcomeBrandFontFamily = 'Noto Sans SC'"));
    expect(typography, isNot(contains('开发态')));
    expect(typography, isNot(contains('正式授权品牌字体到位后')));
    expect(manifest, contains('family: Noto Sans SC'));
    expect(manifest, contains('license: OFL-1.1'));
    expect(
      manifest,
      contains('pinnedCommit: 2894aab31764f10f29c421bdfd2340d3b382d384'),
    );
    expect(
      manifest,
      contains(
        'sha256: a3041811a78c361b1de50f953c805e0244951c21c5bd412f7232ef0d899af0da',
      ),
    );
  });

  test('欢迎退出防护：finish 不受 emit 阻断，Root 有绝对 deadline', () {
    final welcome = _readAppFile('lib/runtime/shell/welcome/welcome_screen.dart');
    expect(welcome, contains('scheduleMicrotask(() {'));
    expect(welcome, contains('widget.onFinish()'));
    expect(welcome, contains('观测回调失败不得阻断进入主壳'));
    expect(welcome, contains('可见回调失败不得阻断动效/退出'));
    expect(welcome, contains('不取消硬截止'));
    expect(welcome, contains('phaseDeadline'));

    final shell = _readAppFile('lib/runtime/di/shell/composition/quwoquan_app_shell.dart');
    expect(shell, contains('_armStartupDeadline'));
    expect(shell, contains('startup_absolute_deadline'));
    expect(shell, contains('StartupStateMachine'));
    expect(shell, contains('_completeStartupWelcome()'));
  });

  test('全开首帧与最终全开 golden 字节一致', () {
    final first = File(
      'test/local_contract/runtime/shell/welcome/goldens/welcome_flower_full_open.png',
    );
    final finalFrame = File(
      'test/local_contract/runtime/shell/welcome/goldens/welcome_flower_final_open.png',
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

double _contrastRatio(Color foreground, Color background) {
  final lighter = foreground.computeLuminance();
  final darker = background.computeLuminance();
  return (lighter + 0.05) / (darker + 0.05);
}
