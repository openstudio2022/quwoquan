@Tags(<String>['serial', 'visual'])
library;

import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/runtime/shell/welcome/welcome_appearance.dart';
import 'package:quwoquan_app/runtime/shell/welcome/welcome_motion_timeline.dart';
import 'package:quwoquan_app/runtime/shell/welcome/welcome_brand_cluster.dart';
import 'package:quwoquan_app/runtime/shell/welcome/welcome_flower_mark.dart';

void main() {
  setUpAll(() async {
    final loader = FontLoader(AppTypography.welcomeBrandFontFamily)
      ..addFont(
        rootBundle.load('assets/fonts/noto_sans_sc/NotoSansSC[wght].ttf'),
      );
    await loader.load();
  });

  for (final viewport in const <Size>[
    Size(360, 800),
    Size(393, 852),
    Size(430, 932),
  ]) {
    testWidgets('全开终态 ${viewport.width}x${viewport.height}', (tester) async {
      await tester.binding.setSurfaceSize(viewport);
      addTearDown(() => tester.binding.setSurfaceSize(null));
      await tester.pumpWidget(
        _GoldenHost(
          child: RepaintBoundary(
            key: const ValueKey<String>('viewport-final-frame'),
            child: const _StaticFinalFrame(),
          ),
        ),
      );
      await tester.pump();

      await expectLater(
        find.byKey(const ValueKey<String>('viewport-final-frame')),
        matchesGoldenFile(
          'goldens/welcome_final_${viewport.width.toInt()}x'
          '${viewport.height.toInt()}.png',
        ),
      );
    });
  }

  final keyframes = <String, List<double>>{
    'full_open': WelcomeMotionTimeline.petalBloomAmounts(
      phase: WelcomeMotionPhase.handoffHold,
      phaseProgress: 0,
    ),
    'gathering_25': WelcomeMotionTimeline.petalBloomAmounts(
      phase: WelcomeMotionPhase.gathering,
      phaseProgress: 0.25,
    ),
    'gathering_50': WelcomeMotionTimeline.petalBloomAmounts(
      phase: WelcomeMotionPhase.gathering,
      phaseProgress: 0.5,
    ),
    'bud_peak': WelcomeMotionTimeline.petalBloomAmounts(
      phase: WelcomeMotionPhase.budPause,
      phaseProgress: 0.5,
    ),
    'blooming_25': WelcomeMotionTimeline.petalBloomAmounts(
      phase: WelcomeMotionPhase.blooming,
      phaseProgress: 0.25,
    ),
    'blooming_50': WelcomeMotionTimeline.petalBloomAmounts(
      phase: WelcomeMotionPhase.blooming,
      phaseProgress: 0.5,
    ),
    'blooming_75': WelcomeMotionTimeline.petalBloomAmounts(
      phase: WelcomeMotionPhase.blooming,
      phaseProgress: 0.75,
    ),
    'final_open': WelcomeMotionTimeline.petalBloomAmounts(
      phase: WelcomeMotionPhase.openSettle,
      phaseProgress: 1,
    ),
  };

  for (final entry in keyframes.entries) {
    testWidgets('花瓣关键帧 ${entry.key}', (tester) async {
      await tester.binding.setSurfaceSize(const Size(240, 240));
      addTearDown(() => tester.binding.setSurfaceSize(null));
      await tester.pumpWidget(
        _GoldenHost(
          child: Builder(
            builder: (context) => ColoredBox(
              color: WelcomeAppearance.of(context).background,
              child: Center(
                child: RepaintBoundary(
                  key: const ValueKey<String>('flower-keyframe'),
                  child: SizedBox.square(
                    dimension: AppSpacing.welcomeGraphicDiameter,
                    child: WelcomeFlowerMark(
                      appearance: WelcomeAppearance.of(context),
                      petalBloomAmounts: entry.value,
                    ),
                  ),
                ),
              ),
            ),
          ),
        ),
      );
      await tester.pump();

      await expectLater(
        find.byKey(const ValueKey<String>('flower-keyframe')),
        matchesGoldenFile('goldens/welcome_flower_${entry.key}.png'),
      );
    });
  }
}

class _GoldenHost extends StatelessWidget {
  const _GoldenHost({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    return CupertinoApp(
      theme: const CupertinoThemeData(
        textTheme: CupertinoTextThemeData(
          textStyle: TextStyle(
            fontFamily: AppTypography.welcomeBrandFontFamily,
            decoration: TextDecoration.none,
          ),
        ),
      ),
      home: child,
    );
  }
}

/// 与运行时/原生导出共用 [WelcomeStaticFrame]，golden 即首帧终态真相源。
class _StaticFinalFrame extends StatelessWidget {
  const _StaticFinalFrame();

  @override
  Widget build(BuildContext context) {
    return WelcomeStaticFrame(
      flower: WelcomeFlowerMark(appearance: WelcomeAppearance.of(context)),
    );
  }
}
