// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/page-horizontal-quality/spec.md#gwt-003.t1
// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/page-horizontal-quality/spec.md#gwt-003.t2
// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/page-horizontal-quality/spec.md#gwt-003.t3
import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/design_system/feedback/skeleton/app_skeleton.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';

void main() {
  testWidgets('shimmer 以统一节奏脉冲且骨架不进入 semantics tree', (tester) async {
    await tester.pumpWidget(
      const CupertinoApp(
        home: AppSkeletonShimmer(
          child: AppSkeletonBlock(width: 100, height: 40),
        ),
      ),
    );

    final opacityAtStart = tester
        .widget<Opacity>(
          find
              .descendant(
                of: find.byType(AppSkeletonShimmer),
                matching: find.byType(Opacity),
              )
              .first,
        )
        .opacity;
    await tester.pump(AppSkeletonShimmer.pulseDuration);
    final opacityAtPeak = tester
        .widget<Opacity>(
          find
              .descendant(
                of: find.byType(AppSkeletonShimmer),
                matching: find.byType(Opacity),
              )
              .first,
        )
        .opacity;

    // 脉冲在声明的谷值与峰值之间往复。
    expect(opacityAtStart, AppSkeletonShimmer.minOpacity);
    expect(opacityAtPeak, AppSkeletonShimmer.maxOpacity);

    // 骨架对辅助技术不可见。
    expect(
      find.descendant(
        of: find.byType(AppSkeletonShimmer),
        matching: find.byType(ExcludeSemantics),
      ),
      findsOneWidget,
    );
  });

  testWidgets('disableAnimations 为真时骨架静止在峰值透明度', (tester) async {
    await tester.pumpWidget(
      const CupertinoApp(
        home: MediaQuery(
          data: MediaQueryData(disableAnimations: true),
          child: AppSkeletonShimmer(
            child: AppSkeletonBlock(width: 100, height: 40),
          ),
        ),
      ),
    );

    final opacity = tester
        .widget<Opacity>(
          find
              .descendant(
                of: find.byType(AppSkeletonShimmer),
                matching: find.byType(Opacity),
              )
              .first,
        )
        .opacity;
    expect(opacity, AppSkeletonShimmer.maxOpacity);

    // 静止：多帧后透明度不变，且没有活动的动画计时器。
    await tester.pump(AppSkeletonShimmer.pulseDuration);
    expect(
      tester
          .widget<Opacity>(
            find
                .descendant(
                  of: find.byType(AppSkeletonShimmer),
                  matching: find.byType(Opacity),
                )
                .first,
          )
          .opacity,
      AppSkeletonShimmer.maxOpacity,
    );
    expect(tester.hasRunningAnimations, isFalse);
  });

  testWidgets('块/行/圆位使用设计系统 token 圆角与填充色', (tester) async {
    await tester.pumpWidget(
      const CupertinoApp(
        home: Column(
          children: <Widget>[
            AppSkeletonBlock(width: 80, height: 48),
            AppSkeletonLine(width: 120),
            AppSkeletonCircle(size: 40),
          ],
        ),
      ),
    );

    final block = tester.widget<Container>(
      find
          .descendant(
            of: find.byType(AppSkeletonBlock).first,
            matching: find.byType(Container),
          )
          .first,
    );
    final blockDecoration = block.decoration! as BoxDecoration;
    expect(
      blockDecoration.borderRadius,
      BorderRadius.circular(AppSpacing.smallBorderRadius),
    );

    final circle = tester.widget<Container>(
      find
          .descendant(
            of: find.byType(AppSkeletonCircle),
            matching: find.byType(Container),
          )
          .first,
    );
    expect((circle.decoration! as BoxDecoration).shape, BoxShape.circle);

    // 行占位默认行高来自 token。
    final lineSize = tester.getSize(find.byType(AppSkeletonLine));
    expect(lineSize.height, AppSpacing.ten);
  });
}
