// GENERATED FILE — DO NOT EDIT BY HAND.
// Sources: 各 Surface owner 的 ui_config.yaml（逐项来源见下方）。
// Regenerate: make codegen-app

import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show ContentUiSurface;

/// 布局家族不代表对象类型或卡片配方。
enum SurfaceLayoutKind { responsiveGrid, fullBleedPager, objectShell }

final class SurfaceResponsiveGrid {
  const SurfaceResponsiveGrid({
    required this.expandedBreakpointDp,
    required this.minColumns,
    required this.maxColumns,
    required this.idealColumnWidthDp,
  });

  final double expandedBreakpointDp;
  final int minColumns;
  final int maxColumns;
  final double idealColumnWidthDp;
}

/// 纯配置与视口函数；不接收 ContentType 或 FeedPresentationRecipe。
final class SurfaceLayoutPolicy {
  const SurfaceLayoutPolicy._({
    required this.layoutKind,
    required this.compactColumns,
    required this.chromeFamily,
    required this.recipeDrivenChrome,
    this.responsiveGrid,
  });

  final SurfaceLayoutKind layoutKind;
  final int compactColumns;
  final String chromeFamily;
  final bool recipeDrivenChrome;
  final SurfaceResponsiveGrid? responsiveGrid;

  /// widthDp 必须是扣除页面外围留白后的有限非负可用宽度。
  int columnsForWidth(double widthDp) {
    if (!widthDp.isFinite || widthDp < 0) {
      throw ArgumentError.value(widthDp, 'widthDp', '须为有限非负宽度');
    }
    final grid = responsiveGrid;
    if (grid == null || widthDp < grid.expandedBreakpointDp) {
      return compactColumns;
    }
    final idealColumns = widthDp / grid.idealColumnWidthDp;
    return idealColumns.clamp(grid.minColumns, grid.maxColumns).floor();
  }

  /// 穷尽 canonical Surface；新增枚举成员而未重生成将编译失败。
  static SurfaceLayoutPolicy forSurface(ContentUiSurface surface) =>
      switch (surface) {
        // Source: content/content/post/ui_config.yaml
        ContentUiSurface.homeFeed => const SurfaceLayoutPolicy._(
          layoutKind: SurfaceLayoutKind.responsiveGrid,
          compactColumns: 1,
          chromeFamily: "feed_presentation_recipe",
          recipeDrivenChrome: true,
          responsiveGrid: SurfaceResponsiveGrid(
            expandedBreakpointDp: 600,
            minColumns: 2,
            maxColumns: 4,
            idealColumnWidthDp: 220,
          ),
        ),
        // Source: user/account/user_account/ui_config.yaml
        ContentUiSurface.profileWorks => const SurfaceLayoutPolicy._(
          layoutKind: SurfaceLayoutKind.responsiveGrid,
          compactColumns: 2,
          chromeFamily: "preview_grid_card",
          recipeDrivenChrome: false,
          responsiveGrid: SurfaceResponsiveGrid(
            expandedBreakpointDp: 600,
            minColumns: 2,
            maxColumns: 4,
            idealColumnWidthDp: 220,
          ),
        ),
        // Source: content/content/post/ui_config.yaml
        ContentUiSurface.mediaImmersive => const SurfaceLayoutPolicy._(
          layoutKind: SurfaceLayoutKind.fullBleedPager,
          compactColumns: 1,
          chromeFamily: "immersive_media_pager",
          recipeDrivenChrome: false,
        ),
        // Source: content/content/post/ui_config.yaml
        ContentUiSurface.articleReader => const SurfaceLayoutPolicy._(
          layoutKind: SurfaceLayoutKind.fullBleedPager,
          compactColumns: 1,
          chromeFamily: "article_document_reader",
          recipeDrivenChrome: false,
        ),
        // Source: entity/entity_homepage/homepage/ui_config.yaml
        ContentUiSurface.homepageDetail => const SurfaceLayoutPolicy._(
          layoutKind: SurfaceLayoutKind.objectShell,
          compactColumns: 1,
          chromeFamily: "homepage_object_shell",
          recipeDrivenChrome: false,
        ),
      };
}
