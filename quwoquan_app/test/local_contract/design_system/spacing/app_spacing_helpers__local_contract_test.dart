import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/design_system/semantics/design_semantic_constants.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';

void main() {
  /// 在给定视口宽度下取一个真实 BuildContext，交给 [read] 求值。
  Future<T> atWidth<T>(
    WidgetTester tester,
    double width,
    T Function(BuildContext context) read,
  ) async {
    late T value;
    await tester.pumpWidget(
      MediaQuery(
        data: MediaQueryData(size: Size(width, 800)),
        child: Builder(
          builder: (context) {
            value = read(context);
            return const SizedBox.shrink();
          },
        ),
      ),
    );
    return value;
  }

  group('按钮高度档位 — 固定语义值，不受容器约束', () {
    test('标准模式逐档取值，未知档位回落 md', () {
      expect(
        AppSpacing.buttonHeightForSize(DesignSemanticConstants.xs),
        AppSpacing.buttonHeightXs,
      );
      expect(
        AppSpacing.buttonHeightForSize(DesignSemanticConstants.sm),
        AppSpacing.buttonHeightSm,
      );
      expect(
        AppSpacing.buttonHeightForSize(DesignSemanticConstants.md),
        AppSpacing.buttonHeightMd,
      );
      expect(
        AppSpacing.buttonHeightForSize(DesignSemanticConstants.lg),
        AppSpacing.buttonHeightLg,
      );
      expect(
        AppSpacing.buttonHeightForSize('xxl'),
        AppSpacing.buttonHeightMd,
      );
    });

    test('紧凑模式只压缩 sm/md/lg，xs 与标准模式同高', () {
      expect(
        AppSpacing.buttonHeightForSizeCompact(DesignSemanticConstants.xs),
        AppSpacing.buttonHeightXs,
      );
      expect(
        AppSpacing.buttonHeightForSizeCompact(DesignSemanticConstants.sm),
        AppSpacing.buttonHeightSmCompact,
      );
      expect(
        AppSpacing.buttonHeightForSizeCompact(DesignSemanticConstants.md),
        AppSpacing.buttonHeightMdCompact,
      );
      expect(
        AppSpacing.buttonHeightForSizeCompact(DesignSemanticConstants.lg),
        AppSpacing.buttonHeightLgCompact,
      );
      expect(
        AppSpacing.buttonHeightForSizeCompact('xxl'),
        AppSpacing.buttonHeightMdCompact,
      );

      // 紧凑模式在 sm 及以上必须严格更矮，否则「紧凑」语义失效。
      for (final size in const [
        DesignSemanticConstants.sm,
        DesignSemanticConstants.md,
        DesignSemanticConstants.lg,
      ]) {
        expect(
          AppSpacing.buttonHeightForSizeCompact(size),
          lessThan(AppSpacing.buttonHeightForSize(size)),
          reason: '$size 紧凑高度应低于标准高度',
        );
      }
    });
  });

  group('getSpacing — screenType 显式优先于 context 探测', () {
    test('tablet/desktop 命中响应式映射表', () {
      expect(
        AppSpacing.getSpacing(
          DesignSemanticConstants.intraGroup,
          DesignSemanticConstants.md,
          screenType: 'tablet',
        ),
        12.0,
      );
      expect(
        AppSpacing.getSpacing(
          DesignSemanticConstants.interGroup,
          DesignSemanticConstants.lg,
          screenType: 'desktop',
        ),
        40.0,
      );
    });

    test('mobile 回落到基础语义表', () {
      expect(
        AppSpacing.getSpacing(
          DesignSemanticConstants.container,
          DesignSemanticConstants.xs,
          screenType: 'mobile',
        ),
        8.0,
      );
      // 未知 screenType 与 mobile 同义（default 分支）。
      expect(
        AppSpacing.getSpacing(
          DesignSemanticConstants.container,
          DesignSemanticConstants.xs,
          screenType: 'watch',
        ),
        8.0,
      );
    });

    test('未知语义类型逐档回落到基础间距，未知档位回落 md', () {
      const fallbacks = {
        DesignSemanticConstants.xs: AppSpacing.xs,
        DesignSemanticConstants.sm: AppSpacing.sm,
        DesignSemanticConstants.md: AppSpacing.md,
        DesignSemanticConstants.lg: AppSpacing.lg,
        DesignSemanticConstants.xl: AppSpacing.xl,
      };
      fallbacks.forEach((size, expected) {
        expect(
          AppSpacing.getSpacing('unknownSemantic', size, screenType: 'mobile'),
          expected,
          reason: '未知语义类型的 $size 档应回落到基础间距',
        );
      });
      expect(
        AppSpacing.getSpacing(
          'unknownSemantic',
          'unknownSize',
          screenType: 'mobile',
        ),
        AppSpacing.md,
      );
    });

    testWidgets('screenType 缺席时按 context 宽度探测屏幕类型', (tester) async {
      // 同一语义档位在 mobile / tablet / desktop 三段各自取值。
      expect(
        await atWidth(
          tester,
          390,
          (context) => AppSpacing.getSpacing(
            DesignSemanticConstants.intraGroup,
            DesignSemanticConstants.md,
            context: context,
          ),
        ),
        8.0,
      );
      expect(
        await atWidth(
          tester,
          800,
          (context) => AppSpacing.getSpacing(
            DesignSemanticConstants.intraGroup,
            DesignSemanticConstants.md,
            context: context,
          ),
        ),
        12.0,
      );
      expect(
        await atWidth(
          tester,
          1400,
          (context) => AppSpacing.getSpacing(
            DesignSemanticConstants.intraGroup,
            DesignSemanticConstants.md,
            context: context,
          ),
        ),
        16.0,
      );
    });
  });

  testWidgets('紧凑按钮内边距只在 lg 档放宽水平间距', (tester) async {
    final lg = await atWidth(
      tester,
      390,
      (context) => AppSpacing.buttonPaddingCompact(
        context,
        DesignSemanticConstants.lg,
      ),
    );
    final md = await atWidth(
      tester,
      390,
      (context) => AppSpacing.buttonPaddingCompact(
        context,
        DesignSemanticConstants.md,
      ),
    );

    expect(lg, const EdgeInsets.symmetric(horizontal: 12.0, vertical: 4.0));
    expect(md, const EdgeInsets.symmetric(horizontal: 8.0, vertical: 4.0));
  });

  testWidgets('顶栏尾部热区内缩量 = 视觉边距 - 44 热区与 24 图标的半差', (tester) async {
    final (compactInset, compactAssistant) = await atWidth(
      tester,
      390,
      (context) => (
        AppSpacing.topBarTrailingButtonInset(context),
        AppSpacing.topBarTrailingAssistantButtonInset(context),
      ),
    );
    final (expandedInset, expandedAssistant) = await atWidth(
      tester,
      1200,
      (context) => (
        AppSpacing.topBarTrailingButtonInset(context),
        AppSpacing.topBarTrailingAssistantButtonInset(context),
      ),
    );

    expect(compactInset, 6.0);
    expect(expandedInset, 10.0);
    // 「小趣」圆标与顶栏图标同为 24px，两条内缩量必须一致。
    expect(compactAssistant, compactInset);
    expect(expandedAssistant, expandedInset);
  });

  testWidgets('Web PC 瀑布流列数与阅读宽度受内容最大宽度封顶', (tester) async {
    expect(
      await atWidth(tester, 320, AppSpacing.webPcMasonryColumns),
      2,
      reason: '窄屏可用宽度只够 1 列，但列数下限为 2',
    );
    expect(await atWidth(tester, 1200, AppSpacing.webPcMasonryColumns), 4);

    expect(
      await atWidth(tester, 320, AppSpacing.webPcReadingWidth),
      AppSpacing.webPcReadingMinWidth,
    );
    expect(
      await atWidth(tester, 1200, AppSpacing.webPcReadingWidth),
      AppSpacing.webPcReadingMaxWidth,
    );
  });

  testWidgets('关注流列数：手机恒单列，expanded 起复用网格列数', (tester) async {
    expect(await atWidth(tester, 390, AppSpacing.feedResponsiveColumns), 1);
    expect(
      await atWidth(tester, 599, AppSpacing.feedResponsiveColumns),
      1,
      reason: 'expandedBreakpoint 以下仍是单列',
    );
    expect(await atWidth(tester, 600, AppSpacing.feedResponsiveColumns), 2);
    expect(
      await atWidth(tester, 1400, AppSpacing.feedResponsiveColumns),
      AppSpacing.gridMaxColumns,
      reason: '宽屏受最大列数上限封顶',
    );
  });
}
