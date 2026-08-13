import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/feedback/skeleton/app_skeleton.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';

/// 对象页交集卡加载骨架（V4 · 商用完整态）。
///
/// 设计（专业设计师视角：精致 / 一致）：
/// - 与 [ObjectIntersectionCard] 同材质同圆角，loading 期不留白、不闪烁布局；
/// - 标题占位 + N 行「头像簇 + 短句条」占位，脉动由统一 [AppSkeletonShimmer] 承载；
/// - 三对象页（用户/圈子/实体）loading 共用同一骨架，避免各页各态。
class ObjectIntersectionCardSkeleton extends StatelessWidget {
  const ObjectIntersectionCardSkeleton({
    super.key,
    required this.isDark,
    this.rows = 3,
  });

  static const Key skeletonKey = ValueKey<String>(
    'object-intersection-card-skeleton',
  );

  final bool isDark;
  final int rows;

  @override
  Widget build(BuildContext context) {
    final surface = AppColorsFunctional.getColor(
      isDark,
      ColorType.backgroundSecondary,
    );
    final rowCount = rows <= 0 ? 3 : rows;
    final isWide =
        MediaQuery.sizeOf(context).width >= AppSpacing.wideBreakpoint;
    if (isWide) {
      return _buildWideSkeleton(context, surface);
    }
    return Container(
      key: ObjectIntersectionCardSkeleton.skeletonKey,
      decoration: BoxDecoration(
        color: surface,
        borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
      ),
      padding: EdgeInsets.all(AppSpacing.containerMd),
      child: AppSkeletonShimmer(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            const AppSkeletonLine(
              width: AppSpacing.oneHundred,
              height: AppSpacing.md,
            ),
            SizedBox(height: AppSpacing.intraGroupSm),
            for (var i = 0; i < rowCount; i++) ...<Widget>[
              if (i > 0) SizedBox(height: AppSpacing.intraGroupSm),
              _rowSkeleton(context),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildWideSkeleton(BuildContext context, Color surface) {
    return Container(
      key: ObjectIntersectionCardSkeleton.skeletonKey,
      decoration: BoxDecoration(
        color: surface,
        borderRadius: BorderRadius.circular(
          AppSpacing.contentPreviewCornerRadius,
        ),
      ),
      padding: EdgeInsets.all(AppSpacing.containerMd),
      child: AppSkeletonShimmer(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            const AppSkeletonBlock(
              width: double.infinity,
              height: AppSpacing.objectIntersectionCardWideCoverHeight,
            ),
            SizedBox(height: AppSpacing.containerSm),
            const AppSkeletonLine(
              width: AppSpacing.oneHundred,
              height: AppSpacing.md,
            ),
            SizedBox(height: AppSpacing.two),
            const AppSkeletonLine(
              width: double.infinity,
              height: AppSpacing.sm,
            ),
            SizedBox(height: AppSpacing.intraGroupSm),
            const AppSkeletonLine(
              width: AppSpacing.oneHundred,
              height: AppSpacing.sm,
            ),
          ],
        ),
      ),
    );
  }

  Widget _rowSkeleton(BuildContext context) {
    return const Row(
      children: <Widget>[
        AppSkeletonCircle(size: AppSpacing.avatarUserSm),
        SizedBox(width: AppSpacing.intraGroupSm),
        Expanded(
          child: AppSkeletonLine(width: double.infinity, height: AppSpacing.sm),
        ),
      ],
    );
  }
}
