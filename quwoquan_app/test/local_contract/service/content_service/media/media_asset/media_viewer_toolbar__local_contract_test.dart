// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/error-permission-display-semantics/spec.md#gwt-001
// spec_ref: specs/feature-tree/discovery-content/dual-rail-discovery-redesign/works-immersive-viewer/spec.md#gwt-018
// spec_ref: specs/feature-tree/discovery-content/dual-rail-discovery-redesign/works-immersive-viewer/spec.md#gwt-018.t2
import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/layout/app_scaffold.dart';
import 'package:quwoquan_app/design_system/semantics/navigation_semantic_constants.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
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

Icon _iconWithin(WidgetTester tester, Finder ancestor) {
  return tester.widget<Icon>(
    find.descendant(of: ancestor, matching: find.byType(Icon)),
  );
}

void main() {
  testWidgets('ImmersiveToolbarIconButton 无暗底填充，白图标携带语义投影', (tester) async {
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
    // 沉浸导航钮不再用暗色圆底（REQ-019）；浅色媒体上的可见性由投影承接。
    expect(
      decoration.color,
      AppNavigationSemanticConstants.chromeActionBackground(
        surface: AppChromeSurface.immersive,
      ),
    );
    expect(decoration.color, AppColors.transparent);
    final icon = _iconWithin(tester, find.byType(ImmersiveToolbarIconButton));
    expect(icon.color, AppColors.white);
    expect(
      icon.shadows,
      AppNavigationSemanticConstants.chromeActionIconShadows(
        surface: AppChromeSurface.immersive,
      ),
    );
    expect(icon.shadows, isNotEmpty, reason: '白色图标失去暗底后必须有投影保证返回出路可见。');
  });

  testWidgets('ImmersiveToolbarIconButton 保持 44pt 最小触控热区', (tester) async {
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

    final button = tester.widget<CupertinoButton>(
      find.descendant(
        of: find.byType(ImmersiveToolbarIconButton),
        matching: find.byType(CupertinoButton),
      ),
    );
    expect(
      button.minimumSize!.width,
      greaterThanOrEqualTo(AppSpacing.minInteractiveSize),
    );
    expect(
      button.minimumSize!.height,
      greaterThanOrEqualTo(AppSpacing.minInteractiveSize),
    );
  });

  testWidgets('MediaViewerTopBar 返回按钮无暗底且带投影', (tester) async {
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
    expect(decoration.color, AppColors.transparent);
    expect(_iconWithin(tester, backButton).shadows, isNotEmpty);
  });

  testWidgets('AppNavigationBarIconButton immersive 表面透明底、白图标带投影', (tester) async {
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
    expect(decoration.color, AppColors.transparent);
    final icon = _iconWithin(tester, find.byType(AppNavigationBarIconButton));
    expect(icon.color, AppColors.white);
    expect(
      icon.shadows,
      AppNavigationSemanticConstants.chromeActionIconShadows(
        surface: AppChromeSurface.immersive,
      ),
    );
  });

  testWidgets('AppNavigationBarIconButton standard 表面透明背景且无投影', (tester) async {
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
    final icon = _iconWithin(tester, find.byType(AppNavigationBarIconButton));
    expect(icon.shadows, anyOf(isNull, isEmpty));
  });
}
