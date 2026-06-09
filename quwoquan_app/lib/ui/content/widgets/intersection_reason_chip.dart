import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/components/object_page/evidence_group.dart';
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
  });

  static const Key chipKey = ValueKey<String>('intersection-reason-chip');

  final String text;
  final bool isDark;

  /// 交集理由位口径真相源：取首条理由的最强证据组短句 + 计数（事实优先）；
  /// 如「共同关注 4」；无来源 / 无可展示证据 → null（不展示）。
  /// 所有承载交集理由位的 surface 必须经此函数解析（四口径一致）。
  static String? primaryText(List<IntersectionReason>? reasons) {
    if (reasons == null || reasons.isEmpty) return null;
    final first = reasons.first;
    // 兼容旧契约：当云侧尚未下发结构化 intersectionPoints，只给了 displayText 时，
    // 保持原句直出，不在端侧额外拼接 sharedCount，避免把
    // 「你和 TA 都来自同一校园」误变成「你和 TA 都来自同一校园 2」。
    final displayOnly = first.displayText.trim();
    if (displayOnly.isNotEmpty && first.intersectionPoints.isEmpty) {
      return displayOnly;
    }
    final groups = EvidenceGroup.fromReason(reasons.first);
    if (groups.isEmpty) return null;
    final g = groups.first;
    return g.count > 0 ? '${g.label} ${g.count}' : g.label;
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
    return IntersectionReasonChip(key: key, text: text, isDark: isDark);
  }

  @override
  Widget build(BuildContext context) {
    final accent = isDark ? AppColors.iosAccentDark : AppColors.primaryColor;
    return Row(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.center,
      children: [
        Icon(CupertinoIcons.link, size: AppSpacing.fourteen, color: accent),
        SizedBox(width: AppSpacing.intraGroupXs),
        Flexible(
          child: Text(
            text,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              fontSize: AppTypography.iosCaption1,
              fontWeight: AppTypography.medium,
              color: accent,
              letterSpacing: -0.04,
            ),
          ),
        ),
      ],
    );
  }
}
