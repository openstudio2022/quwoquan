part of 'app_spacing.dart';

/// 响应式内容网格的固定列宽和列数边界。
final class _AppSpacingGridValues {
  const _AppSpacingGridValues._();

  /// Post 预览网格的最佳列宽（理想单列内容宽度），用于计算列数。
  static const double idealColumnWidth = 220.0;

  /// Post 预览网格的最小列数。
  static const int minColumns = 2;

  /// Post 预览网格的最大列数，避免 iPad/桌面出现 5-6 列的过密卡片。
  static const int maxColumns = 4;
}
