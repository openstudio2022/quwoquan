import 'package:flutter/material.dart';

class AppTypography {
  static const double xs = 10.0;
  static const double sm = 12.0;
  static const double md = 14.0;
  static const double base = 14.0;
  static const double lg = 16.0;
  static const double xl = 18.0;
  static const double xxl = 20.0;

  static const double title = xl;
  static const double sectionTitle = lg;
  static const double body = base;
  static const double secondary = sm;
  static const double caption = xs;

  /// 工具面板功能项文案保持与发现页主体一致。
  static const double toolPanelItemLabel = base;
  static const double toolPanelCategoryLabel = base;
  static const double actionCount = lg;

  static const FontWeight normal = FontWeight.w400;
  static const FontWeight medium = FontWeight.w500;
  static const FontWeight semiBold = FontWeight.w600;
  static const FontWeight bold = FontWeight.w700;
  static const FontWeight extraBold = FontWeight.w800;
  static const FontWeight black = FontWeight.w900;

  static double responsive(
    BuildContext context, {
    required double compact,
    required double regular,
    required double expanded,
  }) {
    final width = MediaQuery.sizeOf(context).width;
    if (width < 360) return compact;
    if (width >= 600) return expanded;
    return regular;
  }
}
