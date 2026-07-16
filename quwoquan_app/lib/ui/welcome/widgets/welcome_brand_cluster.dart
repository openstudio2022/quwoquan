import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/ui/welcome/welcome_appearance.dart';

/// 欢迎终态品牌簇：花瓣 + 标题 + slogan。
///
/// 垂直位置用视口分数对齐（不依赖 SafeArea 顶 inset），供 Flutter 欢迎页与
/// 原生 launch 导出共用，保证接管瞬间几何同构。
class WelcomeBrandCluster extends StatelessWidget {
  const WelcomeBrandCluster({
    super.key,
    required this.flower,
    required this.typography,
    this.alignment = viewportAlignment,
  });

  /// 相对全屏视口的品牌簇锚点（略偏上，与历史 Spacer 2:3 视觉重心接近）。
  static const Alignment viewportAlignment = Alignment(0, -0.12);

  final Widget flower;
  final Widget typography;
  final Alignment alignment;

  /// 静态终态文案（导出位图 / 首帧无动画控制器时共用）。
  static Widget buildTypography(
    WelcomeAppearance appearance, {
    String? fontFamily,
  }) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        ShaderMask(
          shaderCallback: (bounds) => LinearGradient(
            begin: Alignment.centerLeft,
            end: Alignment.centerRight,
            stops: const [0.0, 0.48, 1.0],
            colors: [
              AppColors.welcomeTitleGradientEnd,
              AppColors.welcomeTitleGradientMid,
              AppColors.welcomeForeground,
            ],
          ).createShader(bounds),
          child: Text(
            UITextConstants.welcomeTitle,
            style: TextStyle(
              fontFamily: fontFamily,
              fontSize: AppTypography.welcomeHeroTitle,
              fontWeight: AppTypography.black,
              color: AppColors.white,
              letterSpacing: 0,
              decoration: TextDecoration.none,
            ),
          ),
        ),
        SizedBox(height: AppSpacing.md),
        Text(
          UITextConstants.welcomeMainSlogan,
          style: TextStyle(
            fontFamily: fontFamily,
            fontSize: AppTypography.xl,
            fontWeight: AppTypography.medium,
            color: appearance.foregroundMuted,
            letterSpacing: 0,
            decoration: TextDecoration.none,
          ),
          textAlign: TextAlign.center,
        ),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.symmetric(horizontal: AppSpacing.lg),
      child: Align(
        alignment: alignment,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            flower,
            SizedBox(height: AppSpacing.xl + AppSpacing.sm),
            typography,
          ],
        ),
      ),
    );
  }
}
