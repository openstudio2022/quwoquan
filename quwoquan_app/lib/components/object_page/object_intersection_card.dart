import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/content/widgets/intersection_reason_chip.dart';

/// 对象页统一交集卡（V3，合规共享层）。
///
/// 三对象页共用同一结构与口径：
/// - 用户主页：`你们的交集`
/// - 地点和事物页：`你和这里的交集`
/// - 圈子/组织页：`你认识的人有 N 个在这`
///
/// 文案口径约束（全局验收 G2 / 军规 R27）：
/// - 标题 [title]、更多入口文案 [moreLabel] 由调用方按对象类型传入（UITextConstants / l10n），
///   组件本身不硬编码业务中文；
/// - 每条交集点只读消费 [IntersectionReason.displayText]，端不本地拼装交集句；
/// - 无来源（reasons 为空或 displayText 全空）→ [fromReasons] 返回 null，调用方据此不展示。
class ObjectIntersectionCard extends StatelessWidget {
  const ObjectIntersectionCard({
    super.key,
    required this.title,
    required this.reasons,
    required this.isDark,
    this.sharedCount,
    this.maxVisible = 3,
    this.moreLabel,
    this.onReasonTap,
    this.onMoreTap,
  });

  static const Key cardKey = ValueKey<String>('object-intersection-card');

  final String title;
  final List<IntersectionReason> reasons;
  final bool isDark;

  /// 交集点总数（如「128 个交集点」中的 128），来自云侧；不展示则传 null。
  final int? sharedCount;
  final int maxVisible;

  /// 「查看全部」入口文案（调用方传 UITextConstants）；为空则不展示更多入口。
  final String? moreLabel;
  final void Function(IntersectionReason reason)? onReasonTap;
  final VoidCallback? onMoreTap;

  /// 便捷构造：过滤无 displayText 的来源，全空则返回 null（不展示，保证 G2）。
  static Widget? fromReasons({
    required String title,
    required List<IntersectionReason>? reasons,
    required bool isDark,
    int? sharedCount,
    int maxVisible = 3,
    String? moreLabel,
    void Function(IntersectionReason reason)? onReasonTap,
    VoidCallback? onMoreTap,
    Key? key,
  }) {
    final usable = (reasons ?? const <IntersectionReason>[])
        .where((r) => r.displayText.trim().isNotEmpty)
        .toList();
    if (usable.isEmpty) return null;
    return ObjectIntersectionCard(
      key: key ?? cardKey,
      title: title,
      reasons: usable,
      isDark: isDark,
      sharedCount: sharedCount,
      maxVisible: maxVisible,
      moreLabel: moreLabel,
      onReasonTap: onReasonTap,
      onMoreTap: onMoreTap,
    );
  }

  @override
  Widget build(BuildContext context) {
    final accent = isDark ? AppColors.iosAccentDark : AppColors.primaryColor;
    final surface = AppColorsFunctional.getColor(
      isDark,
      ColorType.backgroundSecondary,
    );
    final fgPrimary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final visible = reasons.take(maxVisible).toList();
    final hasMore =
        moreLabel != null && onMoreTap != null && reasons.length > maxVisible;

    return Container(
      decoration: BoxDecoration(
        color: surface,
        borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
      ),
      padding: EdgeInsets.all(AppSpacing.containerMd),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Row(
            children: [
              Icon(
                CupertinoIcons.sparkles,
                size: AppSpacing.iconMedium,
                color: accent,
              ),
              SizedBox(width: AppSpacing.intraGroupSm),
              Expanded(
                child: Text(
                  title,
                  style: TextStyle(
                    fontSize: AppTypography.base,
                    fontWeight: AppTypography.semiBold,
                    color: fgPrimary,
                  ),
                ),
              ),
              if (sharedCount != null && sharedCount! > 0)
                Text(
                  '$sharedCount',
                  style: TextStyle(
                    fontSize: AppTypography.lg,
                    fontWeight: AppTypography.bold,
                    color: accent,
                  ),
                ),
            ],
          ),
          SizedBox(height: AppSpacing.intraGroupSm),
          ...visible.map(
            (r) => Padding(
              padding: EdgeInsets.symmetric(vertical: AppSpacing.intraGroupXs),
              child: GestureDetector(
                behavior: HitTestBehavior.opaque,
                onTap: onReasonTap == null ? null : () => onReasonTap!(r),
                child: Row(
                  children: [
                    Expanded(
                      child: IntersectionReasonChip(
                        text: r.displayText,
                        isDark: isDark,
                      ),
                    ),
                    if (onReasonTap != null)
                      Icon(
                        CupertinoIcons.chevron_forward,
                        size: AppSpacing.fourteen,
                        color: fgSecondary,
                      ),
                  ],
                ),
              ),
            ),
          ),
          if (hasMore) ...[
            SizedBox(height: AppSpacing.intraGroupSm),
            GestureDetector(
              behavior: HitTestBehavior.opaque,
              onTap: onMoreTap,
              child: Text(
                moreLabel!,
                style: TextStyle(
                  fontSize: AppTypography.sm,
                  fontWeight: AppTypography.medium,
                  color: accent,
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }
}
