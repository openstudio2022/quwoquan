import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/ui/discovery/widgets/unified_object_card.dart';

/// 今日交集顶部横滑流。
///
/// 只读消费 [IntersectionReason]，以「统一对象推荐卡」承载人/地点事物/圈子/组织四类对象
/// （同一卡语言）。数据来源 = 当前 feed 各帖聚合出的去重交集理由，不引入第二套业务列表
/// （与 Mock 隔离一致）。仅渲染带 `actionTargetId` 的对象理由；无可展示对象时整条不展示。
class TodayIntersectionRail extends StatelessWidget {
  const TodayIntersectionRail({
    super.key,
    required this.reasons,
    required this.isDark,
    this.onReasonTap,
    this.onReasonAction,
  });

  static const Key railKey = ValueKey<String>('home-today-intersection-rail');

  final List<IntersectionReason> reasons;
  final bool isDark;

  /// 点击对象卡卡体：跳转对应对象/聚合页（路由由父层按 metadata 解析，不在此硬编码 path）。
  final void Function(IntersectionReason reason)? onReasonTap;

  /// 点击对象卡行动按钮（关注/加入/加好友）：交集行动回流由父层处理（trackFollow）。
  final void Function(IntersectionReason reason)? onReasonAction;

  @override
  Widget build(BuildContext context) {
    final objectReasons = reasons
        .where((reason) => reason.actionTargetId.trim().isNotEmpty)
        .toList(growable: false);
    if (objectReasons.isEmpty) return const SizedBox.shrink();
    final fg = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );

    return Padding(
      key: railKey,
      padding: EdgeInsets.only(
        top: AppSpacing.interGroupSm,
        bottom: AppSpacing.intraGroupSm,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: EdgeInsets.fromLTRB(
              AppSpacing.containerMd,
              AppSpacing.zero,
              AppSpacing.containerMd,
              AppSpacing.intraGroupSm,
            ),
            child: Row(
              children: [
                Icon(
                  CupertinoIcons.sparkles,
                  size: AppSpacing.fourteen,
                  color: _accent,
                ),
                SizedBox(width: AppSpacing.intraGroupXs),
                Text(
                  UITextConstants.homeTodayIntersection,
                  style: TextStyle(
                    fontSize: AppTypography.iosSubheadline,
                    fontWeight: AppTypography.semiBold,
                    color: fg,
                    letterSpacing: -0.18,
                  ),
                ),
              ],
            ),
          ),
          SizedBox(
            height: AppSpacing.homeObjectCardRailHeight,
            child: ListView.separated(
              scrollDirection: Axis.horizontal,
              physics: const BouncingScrollPhysics(),
              padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerMd),
              itemCount: objectReasons.length,
              separatorBuilder: (_, _) =>
                  SizedBox(width: AppSpacing.intraGroupSm),
              itemBuilder: (context, index) {
                final reason = objectReasons[index];
                return UnifiedObjectCard(
                  key: ValueKey<String>('home-today-intersection-object-$index'),
                  reason: reason,
                  isDark: isDark,
                  onOpen: onReasonTap == null
                      ? null
                      : () => onReasonTap!(reason),
                  onAction: onReasonAction == null
                      ? null
                      : () => onReasonAction!(reason),
                );
              },
            ),
          ),
        ],
      ),
    );
  }

  Color get _accent =>
      isDark ? AppColors.iosAccentDark : AppColors.primaryColor;
}
