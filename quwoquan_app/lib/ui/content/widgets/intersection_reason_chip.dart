import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/components/object_page/evidence_group.dart';
import 'package:quwoquan_app/components/object_page/intersection_object_kind.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';

/// 内容卡交集理由位 / post 作者信任徽标（一行克制摘要）。
///
/// 单列 / 多列 / 沉浸 viewer / 转发卡 / 内容详情页**同一口径**：
/// - 只读消费云侧 [IntersectionReason] 的最强证据组，端不本地拼装事实（G2）；
/// - 取最强证据组短句 + 计数（如「共同关注 4」），不再用「N 个交集点」空数字；
/// - 无来源 / 无可展示证据 → 不展示（[fromReasons] 返回 null，调用方据此不插入）。
class IntersectionReasonChip extends StatelessWidget {
  const IntersectionReasonChip({
    super.key,
    required this.text,
    required this.isDark,
    this.kind,
    this.weightTier = '',
  });

  static const Key chipKey = ValueKey<String>('intersection-reason-chip');
  static const Key iconKey = ValueKey<String>('intersection-reason-chip-icon');
  static const Key textKey = ValueKey<String>('intersection-reason-chip-text');

  final String text;
  final bool isDark;
  final UnifiedObjectKind? kind;
  final String weightTier;

  /// 交集理由位口径真相源：云侧主交集结论句 [IntersectionReason.primaryText] 直出，
  /// 缺省回退连接说明 connectionSummary；端不本地拼装事实（G2）。
  /// 无来源 / 无可展示结论句 → null（不展示）。
  /// 所有承载交集理由位的 surface 必须经此函数解析（四口径一致）。
  static String? primaryText(List<IntersectionReason>? reasons) {
    if (reasons == null || reasons.isEmpty) return null;
    final first = reasons.first;
    final primary = first.primaryText.trim();
    if (primary.isNotEmpty) return primary;
    final summary = first.connectionSummary.trim();
    if (summary.isNotEmpty) return summary;
    return null;
  }

  /// 旅程高亮锚（§7.3）：徽标对应的最强证据组 kind；点击跳作者主页时透传，
  /// 对象页据此自动展开并高亮同一证据组，旅程无断点。
  static String? primaryKind(List<IntersectionReason>? reasons) {
    if (reasons == null || reasons.isEmpty) return null;
    final groups = EvidenceGroup.fromReason(reasons.first);
    if (groups.isEmpty) return null;
    final kind = groups.first.kind.trim();
    return kind.isEmpty ? null : kind;
  }

  /// 便捷构造：无来源返回 null，调用方据此「不展示」，保证四口径一致。
  static Widget? fromReasons(
    List<IntersectionReason>? reasons, {
    required bool isDark,
    Key? key,
  }) {
    final text = primaryText(reasons);
    if (text == null) return null;
    final first = reasons?.isNotEmpty == true ? reasons!.first : null;
    return IntersectionReasonChip(
      key: key,
      text: text,
      isDark: isDark,
      weightTier: first?.weightTier ?? '',
      kind: first == null
          ? null
          : UnifiedObjectKind.resolve(
              objectKind: first.objectKind,
              relationKind: first.relationKind,
            ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final resolvedTier = _resolveWeightTier(weightTier);
    final isLight = resolvedTier == _IntersectionReasonWeightTier.light;
    final accent = AppColors.iosAccent(context);
    final foreground = isLight ? AppColors.iosSecondaryLabel(context) : accent;
    final iconBackground = isLight
        ? AppColors.iosSecondaryFill(context)
        : accent.withValues(alpha: isDark ? 0.2 : 0.12);
    return Row(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.center,
      children: [
        Container(
          key: iconKey,
          width: AppSpacing.iconSmall,
          height: AppSpacing.iconSmall,
          alignment: Alignment.center,
          decoration: BoxDecoration(
            color: iconBackground,
            shape: BoxShape.circle,
          ),
          child: Icon(_icon, size: AppSpacing.iconXSmall, color: foreground),
        ),
        SizedBox(width: AppSpacing.intraGroupXs),
        Flexible(
          child: Text(
            key: textKey,
            text,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              fontSize: AppTypography.iosCaption1,
              fontWeight: isLight
                  ? AppTypography.regular
                  : AppTypography.medium,
              color: foreground,
              letterSpacing: -0.04,
            ),
          ),
        ),
      ],
    );
  }

  IconData get _icon {
    switch (kind) {
      case UnifiedObjectKind.person:
        return CupertinoIcons.person_fill;
      case UnifiedObjectKind.circle:
        return CupertinoIcons.person_2_fill;
      case UnifiedObjectKind.school:
        return CupertinoIcons.building_2_fill;
      case UnifiedObjectKind.place:
        return CupertinoIcons.location_solid;
      case UnifiedObjectKind.enterprise:
        return CupertinoIcons.briefcase_fill;
      case null:
        return CupertinoIcons.link;
    }
  }

  static _IntersectionReasonWeightTier _resolveWeightTier(String raw) {
    switch (raw.trim().toLowerCase()) {
      case 'light':
        return _IntersectionReasonWeightTier.light;
      case 'heavy':
      case '':
      default:
        return _IntersectionReasonWeightTier.heavy;
    }
  }
}

enum _IntersectionReasonWeightTier { heavy, light }
