import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/recommendation/recommendation/recommendation_feature_profile_view/presentation/intersection_icon_resolver.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';

/// T2：类型图标的零发版视觉扩展位（§21.5.2）。
///
/// 「新增一个交集类型的图标和配色不需要发端」这条承诺由三件事支撑：
/// - tone 由云侧指派**色号名**，端持 light/dark 成对调色板按主题取色。云侧不能下发
///   色值：同一色值在明暗模式下明度是反的，且它同时用作圆底填充与描边，失败是静默的；
/// - 图标资源走远程 alpha 蒙版图 + `BlendMode.srcIn` 着色，因此远程新图标与既有
///   glyph 共享同一套设计语言，而不是一枚风格外挂的全彩贴纸；
/// - 云侧没给资源、资源在加载中、资源加载失败，三种情况一律回落本地 glyph，
///   冷缓存与断网表现和改造前一致。
Future<void> _pump(
  WidgetTester tester,
  Widget child, {
  Brightness brightness = Brightness.light,
}) async {
  await tester.pumpWidget(
    ProviderScope(
      child: CupertinoApp(
        theme: CupertinoThemeData(brightness: brightness),
        home: CupertinoPageScaffold(child: Center(child: child)),
      ),
    ),
  );
  await tester.pump(const Duration(milliseconds: 200));
}

Color _glyphColor(WidgetTester tester) =>
    tester.widget<Icon>(find.byType(Icon)).color!;

void main() {
  group('tone 由云侧指派色号、端持成对调色板', () {
    testWidgets('云侧 tone 覆盖 iconKey 的本地默认色', (tester) async {
      // iconKey=place 在注册表里是 tea；云侧显式指派 clay 时必须以云侧为准，
      // 这样「给新 kind 换一个已有色调」不需要发端。
      await _pump(
        tester,
        const IntersectionTypeIcon(iconKey: 'place', tone: 'clay'),
      );
      expect(_glyphColor(tester), AppColors.profileIntersectionClayLight);
    });

    testWidgets('同一 tone 在明暗模式取不同色值（云侧不下发色值的理由）', (tester) async {
      await _pump(tester, const IntersectionTypeIcon(tone: 'sage'));
      final light = _glyphColor(tester);
      await _pump(
        tester,
        const IntersectionTypeIcon(tone: 'sage'),
        brightness: Brightness.dark,
      );
      expect(_glyphColor(tester), isNot(light));
      expect(light, AppColors.profileIntersectionSageLight);
    });

    testWidgets('未认识的 tone 回落中性 stone，不留下不可读的颜色', (tester) async {
      await _pump(
        tester,
        const IntersectionTypeIcon(tone: 'neon_future_v9'),
      );
      expect(_glyphColor(tester), AppColors.profileIntersectionStoneLight);
    });
  });

  group('远程图标资源', () {
    testWidgets('云侧未下发资源 → 直接渲染本地 glyph', (tester) async {
      await _pump(tester, const IntersectionTypeIcon(iconKey: 'place'));
      expect(find.byType(Icon), findsOneWidget);
      expect(find.byType(ColorFiltered), findsNothing);
    });

    testWidgets('云侧下发资源 → 经 srcIn 以 tone 着色，加载期间仍是 glyph', (tester) async {
      await _pump(
        tester,
        const IntersectionTypeIcon(
          iconKey: 'place',
          tone: 'clay',
          assetUrl: 'intersection/icon/wormhole.png',
        ),
      );
      final filtered = tester.widget<ColorFiltered>(
        find.byType(ColorFiltered),
      );
      expect(
        filtered.colorFilter,
        ColorFilter.mode(
          AppColors.profileIntersectionClayLight,
          BlendMode.srcIn,
        ),
      );
      // 测试环境不会真正取到网络图，占位即 glyph —— 与断网/冷缓存路径同一条。
      expect(find.byType(Icon), findsOneWidget);
    });

    testWidgets('未登记 iconKey + 远程资源 → 仍可渲染，不空图标', (tester) async {
      await _pump(
        tester,
        const IntersectionTypeIcon(
          iconKey: 'wormhole',
          tone: 'stone',
          assetUrl: 'intersection/icon/wormhole.png',
        ),
      );
      expect(find.byType(ColorFiltered), findsOneWidget);
      expect(find.byType(Icon), findsOneWidget);
    });
  });
}
