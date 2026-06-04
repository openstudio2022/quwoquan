import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/components/object_page/intersection_entity.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';

/// 首页 / 频道交集推荐模块。
///
/// 取代旧的大卡 + 关注按钮 demo：模块头用红色数字标注「N 位与你有交集」，
/// 横滑 [IntersectionEntity]（真实头像 + 名字 + 维度 chip + 共同点安静 chip，
/// 概率交集标「推荐」）。点卡进入对象页（由父层 [onReasonTap] 路由），
/// 无大行动按钮 —— 关注/加入归属对象页内行动。
class IntersectionSpotlightModule extends StatelessWidget {
  const IntersectionSpotlightModule({
    super.key,
    required this.reasons,
    required this.isDark,
    this.title,
    this.onReasonTap,
  });

  static const Key moduleKey = ValueKey<String>('home-intersection-spotlight');

  final List<IntersectionReason> reasons;
  final bool isDark;
  final String? title;
  final void Function(IntersectionReason reason)? onReasonTap;

  @override
  Widget build(BuildContext context) {
    final objectReasons = reasons
        .where((reason) => reason.actionTargetId.trim().isNotEmpty)
        .take(4)
        .toList(growable: false);
    if (objectReasons.isEmpty) return const SizedBox.shrink();

    final surface = AppColors.iosProfileSurface(context);
    final accent = AppColors.iosAccent(context);

    return Padding(
      key: moduleKey,
      padding: EdgeInsets.fromLTRB(
        AppSpacing.feedContentHorizontal(context),
        AppSpacing.intraGroupSm,
        AppSpacing.feedContentHorizontal(context),
        AppSpacing.intraGroupSm,
      ),
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: surface,
          borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
          border: Border.all(
            color: accent.withValues(alpha: isDark ? 0.24 : 0.12),
            width: AppSpacing.hairline,
          ),
        ),
        child: Padding(
          padding: EdgeInsets.all(AppSpacing.containerSm),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              _buildHeader(context, accent, objectReasons.length),
              SizedBox(height: AppSpacing.intraGroupSm),
              SingleChildScrollView(
                scrollDirection: Axis.horizontal,
                physics: const BouncingScrollPhysics(),
                child: Row(
                  children: <Widget>[
                    for (var i = 0; i < objectReasons.length; i++) ...<Widget>[
                      IntersectionEntity(
                        key: ValueKey<String>('spotlight-object-$i'),
                        reason: objectReasons[i],
                        isDark: isDark,
                        density: IntersectionEntityDensity.spotlight,
                        onTap: onReasonTap == null
                            ? null
                            : () => onReasonTap!(objectReasons[i]),
                      ),
                      if (i != objectReasons.length - 1)
                        SizedBox(width: AppSpacing.intraGroupSm),
                    ],
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildHeader(BuildContext context, Color accent, int count) {
    final heading = title ?? UITextConstants.homeTodayIntersection;
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Container(
          width: AppSpacing.buttonHeightMd,
          height: AppSpacing.buttonHeightMd,
          alignment: Alignment.center,
          decoration: BoxDecoration(
            color: accent.withValues(alpha: 0.12),
            borderRadius: BorderRadius.circular(AppSpacing.radiusEighteen),
          ),
          child: Icon(
            CupertinoIcons.circle_grid_hex,
            size: AppSpacing.iconSmall,
            color: accent,
          ),
        ),
        SizedBox(width: AppSpacing.intraGroupSm),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              Row(
                children: <Widget>[
                  Flexible(
                    child: Text(
                      heading,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: AppTypography.iosSubheadline,
                        fontWeight: AppTypography.bold,
                        color: AppColors.iosLabel(context),
                      ),
                    ),
                  ),
                  SizedBox(width: AppSpacing.intraGroupXs),
                  _CountBadge(count: count),
                ],
              ),
              SizedBox(height: AppSpacing.two),
              Text(
                UITextConstants.intersectionSpotlightHeaderPrefix,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  fontSize: AppTypography.iosCaption1,
                  color: AppColors.iosSecondaryLabel(context),
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

/// 模块头红色计数：仅用于「N 位与你有交集」的红数字。
class _CountBadge extends StatelessWidget {
  const _CountBadge({required this.count});

  final int count;

  @override
  Widget build(BuildContext context) {
    return Text(
      '$count',
      style: TextStyle(
        fontSize: AppTypography.iosNavTitle,
        fontWeight: AppTypography.bold,
        color: AppColors.error,
      ),
    );
  }
}
