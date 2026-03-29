// ignore_for_file: unnecessary_underscores
import 'dart:math' as math;
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

/// 群聊九宫格组合头像
///
/// 按成员数量自适应布局：品字(3)/4宫格/5宫格/6宫格/7格/8格/9宫格。
/// 成员按加入顺序排列，无头像成员跳过。
class GroupAvatarGrid extends StatelessWidget {
  const GroupAvatarGrid({
    super.key,
    required this.size,
    required this.avatarUrls,
    this.borderRadius,
    this.innerGap,
    this.backgroundColor,
  });

  final double size;
  final List<String> avatarUrls;
  final double? borderRadius;
  final double? innerGap;
  final Color? backgroundColor;

  @override
  Widget build(BuildContext context) {
    final isDark =
        CupertinoTheme.of(context).brightness == Brightness.dark;
    return LayoutBuilder(
      builder: (context, constraints) {
        final resolvedSize = _resolveRenderSize(constraints);
        final radius = math.min(
          borderRadius ?? (AppSpacing.borderRadius - AppSpacing.one),
          resolvedSize / 2,
        );
        final gap = innerGap ?? 2.0;
        final validUrls = avatarUrls.where((u) => u.isNotEmpty).toList();
        final count = math.min(validUrls.length, 9);

        if (count == 0) {
          return _buildSingleFallback(resolvedSize, radius, isDark);
        }

        if (count == 1) {
          return _buildSingleAvatar(validUrls[0], resolvedSize, radius, isDark);
        }

        final rows = _getLayout(count);
        final maxCols = count <= 4 ? 2 : 3;
        // WeChat style: fixed padding around the grid
        final double padding = resolvedSize * 0.05;
        final double innerSize = resolvedSize - padding * 2;

        final cellSize = (innerSize - gap * (maxCols - 1)) / maxCols;
        final totalHeight = rows.length * cellSize + (rows.length - 1) * gap;

        return SizedBox(
          width: resolvedSize,
          height: resolvedSize,
          child: DecoratedBox(
            decoration: BoxDecoration(
              color:
                  backgroundColor ??
                  AppColorsFunctional.getColor(isDark, ColorType.surfaceMuted),
              borderRadius: BorderRadius.circular(radius),
            ),
            child: ClipRRect(
              borderRadius: BorderRadius.circular(radius),
              child: Center(
                child: SizedBox(
                  height: totalHeight,
                  width: innerSize,
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: _buildRows(
                      validUrls,
                      rows,
                      cellSize,
                      gap,
                      innerSize,
                      isDark,
                    ),
                  ),
                ),
              ),
            ),
          ),
        );
      },
    );
  }

  double _resolveRenderSize(BoxConstraints constraints) {
    final width = constraints.hasBoundedWidth
        ? math.min(size, constraints.maxWidth)
        : size;
    final height = constraints.hasBoundedHeight
        ? math.min(size, constraints.maxHeight)
        : size;
    final resolved = math.min(width, height);
    return resolved.isFinite && resolved > 0 ? resolved : size;
  }

  /// 返回每行的列数
  List<int> _getLayout(int count) {
    switch (count) {
      case 2:
        return [2];
      case 3:
        return [1, 2];
      case 4:
        return [2, 2];
      case 5:
        return [2, 3];
      case 6:
        return [3, 3];
      case 7:
        return [1, 3, 3];
      case 8:
        return [2, 3, 3];
      default:
        return [3, 3, 3];
    }
  }

  List<Widget> _buildRows(
    List<String> urls,
    List<int> rows,
    double cellSize,
    double gap,
    double totalWidth,
    bool isDark,
  ) {
    final widgets = <Widget>[];
    int urlIndex = 0;

    for (int r = 0; r < rows.length; r++) {
      if (r > 0) widgets.add(SizedBox(height: gap));

      final colCount = rows[r];
      final rowWidth = colCount * cellSize + (colCount - 1) * gap;
      final rowChildren = <Widget>[];

      for (int c = 0; c < colCount && urlIndex < urls.length; c++) {
        if (c > 0) rowChildren.add(SizedBox(width: gap));
        rowChildren.add(_buildCell(urls[urlIndex], cellSize, isDark));
        urlIndex++;
      }

      widgets.add(
        SizedBox(
          width: totalWidth,
          height: cellSize,
          child: Center(
            child: SizedBox(
              width: rowWidth,
              height: cellSize,
              child: Row(mainAxisSize: MainAxisSize.min, children: rowChildren),
            ),
          ),
        ),
      );
    }

    return widgets;
  }

  Widget _buildCell(String url, double cellSize, bool isDark) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(AppSpacing.one),
      child: Image.network(
        url,
        width: cellSize,
        height: cellSize,
        fit: BoxFit.cover,
        errorBuilder: (_, __, _) => Container(
          width: cellSize,
          height: cellSize,
          color: AppColorsFunctional.getColor(
            isDark,
            ColorType.backgroundTertiary,
          ),
          child: Icon(
            Icons.person,
            size: cellSize * 0.5,
            color: AppColorsFunctional.getColor(
              isDark,
              ColorType.foregroundSecondary,
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildSingleFallback(double resolvedSize, double radius, bool isDark) {
    return SizedBox(
      width: resolvedSize,
      height: resolvedSize,
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: AppColorsFunctional.getColor(
            isDark,
            ColorType.backgroundTertiary,
          ),
          borderRadius: BorderRadius.circular(radius),
        ),
        child: Center(
          child: Icon(
            Icons.group,
            size: resolvedSize * 0.5,
            color: AppColorsFunctional.getColor(
              isDark,
              ColorType.foregroundSecondary,
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildSingleAvatar(
    String url,
    double resolvedSize,
    double radius,
    bool isDark,
  ) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(radius),
      child: Image.network(
        url,
        width: resolvedSize,
        height: resolvedSize,
        fit: BoxFit.cover,
        errorBuilder: (_, __, _) =>
            _buildSingleFallback(resolvedSize, radius, isDark),
      ),
    );
  }
}
