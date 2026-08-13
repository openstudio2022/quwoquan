// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/error-permission-display-semantics/spec.md#gwt-001
import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/layout/app_scaffold.dart';
import 'package:quwoquan_app/design_system/semantics/navigation_semantic_constants.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/media_viewer_toolbar.dart';

BoxDecoration _circleDecorationWithin(WidgetTester tester, Finder ancestor) {
  final decorated = tester
      .widgetList(
        find.descendant(
          of: ancestor,
          matching: find.byWidgetPredicate((widget) {
            final decoration = switch (widget) {
              Container(:final decoration) => decoration,
              DecoratedBox(:final decoration) => decoration,
              _ => null,
            };
            return decoration is BoxDecoration &&
                decoration.shape == BoxShape.circle;
          }),
        ),
      )
      .first;
  return switch (decorated) {
    Container(:final decoration) => decoration! as BoxDecoration,
    DecoratedBox(:final decoration) => decoration as BoxDecoration,
    _ => throw StateError('no circular decoration found'),
  };
}

void main() {
  testWidgets('ImmersiveToolbarIconButton 默认渲染半透明暗色圆形背板', (tester) async {
    await tester.pumpWidget(
      CupertinoApp(
        home: Center(
          child: ImmersiveToolbarIconButton(
            icon: CupertinoIcons.back,
            onPressed: () {},
          ),
        ),
      ),
    );

    final decoration = _circleDecorationWithin(
      tester,
      find.byType(ImmersiveToolbarIconButton),
    );
    // 白色图标叠在浅色媒体或加载失败退化背景上时，暗底保证返回出路永远可见。
    expect(
      decoration.color,
      AppNavigationSemanticConstants.chromeActionBackground(
        surface: AppChromeSurface.immersive,
      ),
    );
    expect(decoration.color, AppColors.overlayLight);
    final icon = tester.widget<Icon>(
      find.descendant(
        of: find.byType(ImmersiveToolbarIconButton),
        matching: find.byType(Icon),
      ),
    );
    expect(icon.color, AppColors.white);
  });

  testWidgets('MediaViewerTopBar 返回按钮携带暗底背板', (tester) async {
    await tester.pumpWidget(
      CupertinoApp(
        home: MediaViewerTopBar(
          onBack: () {},
          onMore: () {},
          positionText: '1/3',
          authorName: 'author',
          toolbarMode: 'backOnly',
        ),
      ),
    );

    final backButton = find
        .ancestor(
          of: find.byIcon(CupertinoIcons.back),
          matching: find.byType(ImmersiveToolbarIconButton),
        )
        .first;
    final decoration = _circleDecorationWithin(tester, backButton);
    expect(decoration.color, AppColors.overlayLight);
  });

  testWidgets('AppNavigationBarIconButton immersive 表面渲染暗底与白色图标', (tester) async {
    await tester.pumpWidget(
      CupertinoApp(
        home: Center(
          child: AppNavigationBarIconButton(
            icon: CupertinoIcons.back,
            onPressed: () {},
            surface: AppChromeSurface.immersive,
          ),
        ),
      ),
    );

    final decoration = _circleDecorationWithin(
      tester,
      find.byType(AppNavigationBarIconButton),
    );
    expect(decoration.color, AppColors.overlayLight);
    final icon = tester.widget<Icon>(
      find.descendant(
        of: find.byType(AppNavigationBarIconButton),
        matching: find.byType(Icon),
      ),
    );
    expect(icon.color, AppColors.white);
  });

  testWidgets('AppNavigationBarIconButton standard 表面保持透明背景', (tester) async {
    await tester.pumpWidget(
      CupertinoApp(
        home: Center(
          child: AppNavigationBarIconButton(
            icon: CupertinoIcons.back,
            onPressed: () {},
          ),
        ),
      ),
    );

    final decoration = _circleDecorationWithin(
      tester,
      find.byType(AppNavigationBarIconButton),
    );
    expect(decoration.color, AppColors.transparent);
  });
}
