import 'dart:math' as math;

import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/ui/welcome/welcome_appearance.dart';
import 'package:quwoquan_app/ui/welcome/widgets/welcome_flower_mark.dart';

/// 欢迎终态品牌簇：花瓣 + slogan。
///
/// 垂直位置用视口分数对齐（不依赖 SafeArea 顶 inset），供 Flutter 欢迎页与
/// 原生 launch 导出共用，保证接管瞬间几何同构。
///
/// 无障碍：整个品牌簇只暴露一个完整语义
/// 「趣我圈，遇见同趣，绽放热爱」，八片花瓣不单独进入焦点。
class WelcomeBrandCluster extends StatelessWidget {
  const WelcomeBrandCluster({
    super.key,
    required this.flower,
    this.alignment = viewportAlignment,
  });

  /// 相对全屏视口的品牌簇锚点（略偏上，规格 -0.10 ~ -0.12 取下限）。
  static const Alignment viewportAlignment = Alignment(0, -0.12);

  final Widget flower;
  final Alignment alignment;

  /// 品牌簇单一无障碍语义。
  static String get semanticLabel =>
      '${FoundationText.welcomeTitle}，${FoundationText.welcomeMainSlogan}';

  /// 图一高保花朵可见直径：约占屏宽 40%，clamp 132 ~ 168dp。
  static double flowerVisibleDiameterFor(double viewportWidth) {
    return (viewportWidth * AppSpacing.welcomeFlowerWidthFraction).clamp(
      AppSpacing.welcomeFlowerMinDiameter,
      AppSpacing.welcomeFlowerMaxDiameter,
    );
  }

  /// painter 画布边长：画布大于花朵可见直径（花瓣绘制留呼吸边），
  /// 按 painter 几何常量换算，保证可见花朵精确等于目标直径。
  static double flowerCanvasDimensionFor(double viewportWidth) {
    return flowerVisibleDiameterFor(viewportWidth) *
        (AppSpacing.welcomeGraphicDiameter /
            WelcomeFlowerMarkPainter.flowerVisualDiameter);
  }

  /// 花朵可见边缘到 slogan 的布局间距 = 视觉间距 - 画布内衬。
  static double flowerSloganLayoutGapFor(double viewportWidth) {
    final canvasInset =
        (flowerCanvasDimensionFor(viewportWidth) -
            flowerVisibleDiameterFor(viewportWidth)) /
        2;
    return math.max(0.0, AppSpacing.welcomeFlowerSloganVisualGap - canvasInset);
  }

  /// slogan 静态终态文案（导出位图 / 运行时共用；单行、单色高亮、无装饰）。
  static Widget buildSlogan(BuildContext context) {
    return FittedBox(
      // 极端字体缩放时优先整体缩小字号，保证一行不截断、不贴边。
      fit: BoxFit.scaleDown,
      child: Text(
        FoundationText.welcomeMainSlogan,
        maxLines: 1,
        textAlign: TextAlign.center,
        style: TextStyle(
          fontFamily: AppTypography.welcomeBrandFontFamily,
          fontSize: AppTypography.welcomeSloganResponsive(context),
          fontWeight: AppTypography.welcomeSloganWeight,
          color: AppColors.welcomeForeground,
          height: AppTypography.lineHeightTight,
          letterSpacing: 0,
          decoration: TextDecoration.none,
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final viewportWidth = MediaQuery.sizeOf(context).width;
    return Semantics(
      label: semanticLabel,
      container: true,
      excludeSemantics: true,
      child: Padding(
        padding: EdgeInsets.symmetric(horizontal: AppSpacing.lg),
        child: Align(
          alignment: alignment,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              SizedBox.square(
                dimension: flowerCanvasDimensionFor(viewportWidth),
                child: flower,
              ),
              SizedBox(height: flowerSloganLayoutGapFor(viewportWidth)),
              buildSlogan(context),
            ],
          ),
        ),
      ),
    );
  }
}

/// 底部品牌名「趣我圈」：品牌落款，视觉中心约在屏幕高度 90%。
///
/// 结构固定为「贴底透明条 + 条内顶对齐文字」，原生 launch 的底部条位图
/// 与 Android `gravity=bottom` / iOS bottom 约束按同一几何贴装。
/// 品牌语义已由 [WelcomeBrandCluster] 单一语义承载，此处不重复暴露。
class WelcomeBrandFooter extends StatelessWidget {
  const WelcomeBrandFooter({super.key, this.stripBoundaryKey});

  /// 供原生资产导出使用：只包住贴底条本体的 RepaintBoundary key。
  final Key? stripBoundaryKey;

  /// 品牌名单行高度。
  static double get textLineHeight =>
      AppTypography.welcomeBrandName * AppTypography.lineHeightTight;

  /// 品牌名文字到屏底的留白：视觉中心距屏底约 10% 屏高
  /// （即中心位于约 90% 屏高），同时不进入底部安全区。
  static double resolveBottomPadding({
    required double viewportHeight,
    required double bottomInset,
  }) {
    final centerFromBottom = math.max(
      viewportHeight * AppSpacing.welcomeBrandFooterCenterFromBottomFraction,
      bottomInset +
          AppSpacing.welcomeBrandFooterSafeAreaGap +
          textLineHeight / 2,
    );
    return centerFromBottom - textLineHeight / 2;
  }

  /// 贴底条总高（文字行 + 文字下方留白），852 基准约 96dp。
  static double resolveStripHeight({
    required double viewportHeight,
    required double bottomInset,
  }) {
    return resolveBottomPadding(
          viewportHeight: viewportHeight,
          bottomInset: bottomInset,
        ) +
        textLineHeight;
  }

  @override
  Widget build(BuildContext context) {
    final media = MediaQuery.of(context);
    final stripHeight = resolveStripHeight(
      viewportHeight: media.size.height,
      bottomInset: media.padding.bottom,
    );
    return ExcludeSemantics(
      child: Align(
        alignment: Alignment.bottomCenter,
        child: RepaintBoundary(
          key: stripBoundaryKey,
          child: SizedBox(
            width: media.size.width,
            height: stripHeight,
            child: Align(
              alignment: Alignment.topCenter,
              child: SizedBox(
                height: textLineHeight,
                child: FittedBox(
                  fit: BoxFit.scaleDown,
                  child: Text(
                    FoundationText.welcomeTitle,
                    maxLines: 1,
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      fontFamily: AppTypography.welcomeBrandFontFamily,
                      fontSize: AppTypography.welcomeBrandName,
                      fontWeight: AppTypography.welcomeBrandNameWeight,
                      color: AppColors.welcomeForegroundMuted,
                      height: AppTypography.lineHeightTight,
                      letterSpacing: 0,
                      decoration: TextDecoration.none,
                    ),
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// 欢迎页静态帧：深蓝渐变背景 + 品牌簇 + 底部品牌名。
///
/// 运行时欢迎页、原生 launch 位图导出与 golden 测试共用本组件，
/// 保证「原生启动图 = Flutter 首帧」由构造同源保证而非人工对齐。
class WelcomeStaticFrame extends StatelessWidget {
  const WelcomeStaticFrame({
    super.key,
    required this.flower,
    this.backgroundBoundaryKey,
    this.clusterBoundaryKey,
    this.footerBoundaryKey,
  });

  final Widget flower;
  final Key? backgroundBoundaryKey;
  final Key? clusterBoundaryKey;
  final Key? footerBoundaryKey;

  @override
  Widget build(BuildContext context) {
    final appearance = WelcomeAppearance.of(context);
    return Stack(
      fit: StackFit.expand,
      children: [
        RepaintBoundary(
          key: backgroundBoundaryKey,
          child: DecoratedBox(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: <Color>[
                  appearance.gradientStart,
                  appearance.background,
                  appearance.gradientEnd,
                ],
              ),
            ),
          ),
        ),
        RepaintBoundary(
          key: clusterBoundaryKey,
          child: WelcomeBrandCluster(flower: flower),
        ),
        WelcomeBrandFooter(stripBoundaryKey: footerBoundaryKey),
      ],
    );
  }
}
