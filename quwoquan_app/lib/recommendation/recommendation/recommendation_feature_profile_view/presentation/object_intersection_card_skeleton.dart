import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

/// 对象页交集卡加载骨架（V4 · 商用完整态）。
///
/// 设计（专业设计师视角：精致 / 一致）：
/// - 与 [ObjectIntersectionCard] 同材质同圆角，loading 期不留白、不闪烁布局；
/// - 标题占位 + N 行「头像簇 + 短句条」占位，呼吸式微脉动；
/// - 三对象页（用户/圈子/实体）loading 共用同一骨架，避免各页各态。
class ObjectIntersectionCardSkeleton extends StatefulWidget {
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
  State<ObjectIntersectionCardSkeleton> createState() =>
      _ObjectIntersectionCardSkeletonState();
}

class _ObjectIntersectionCardSkeletonState
    extends State<ObjectIntersectionCardSkeleton>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 1100),
  )..repeat(reverse: true);

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final surface = AppColorsFunctional.getColor(
      widget.isDark,
      ColorType.backgroundSecondary,
    );
    final rowCount = widget.rows <= 0 ? 3 : widget.rows;
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
      child: FadeTransition(
        opacity: Tween<double>(begin: 0.45, end: 0.9).animate(_controller),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            _bar(context, width: AppSpacing.oneHundred, height: AppSpacing.md),
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
      child: FadeTransition(
        opacity: Tween<double>(begin: 0.45, end: 0.9).animate(_controller),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            _bar(
              context,
              width: double.infinity,
              height: AppSpacing.objectIntersectionCardWideCoverHeight,
            ),
            SizedBox(height: AppSpacing.containerSm),
            _bar(context, width: AppSpacing.oneHundred, height: AppSpacing.md),
            SizedBox(height: AppSpacing.two),
            _bar(context, width: double.infinity, height: AppSpacing.sm),
            SizedBox(height: AppSpacing.intraGroupSm),
            _bar(context, width: AppSpacing.oneHundred, height: AppSpacing.sm),
          ],
        ),
      ),
    );
  }

  Widget _rowSkeleton(BuildContext context) {
    return Row(
      children: <Widget>[
        Container(
          width: AppSpacing.avatarUserSm,
          height: AppSpacing.avatarUserSm,
          decoration: BoxDecoration(
            color: _fill(context),
            shape: BoxShape.circle,
          ),
        ),
        SizedBox(width: AppSpacing.intraGroupSm),
        Expanded(
          child: _bar(context, width: double.infinity, height: AppSpacing.sm),
        ),
      ],
    );
  }

  Widget _bar(
    BuildContext context, {
    required double width,
    required double height,
  }) {
    return Container(
      width: width,
      height: height,
      decoration: BoxDecoration(
        color: _fill(context),
        borderRadius: BorderRadius.circular(AppSpacing.radiusTwo),
      ),
    );
  }

  Color _fill(BuildContext context) =>
      AppColors.iosFill(context).withValues(alpha: widget.isDark ? 0.5 : 0.7);
}
