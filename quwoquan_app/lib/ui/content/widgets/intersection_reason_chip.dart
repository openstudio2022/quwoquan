import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';

/// 内容卡交集理由位（一行只读 displayText）。
///
/// 单列 / 多列 / 沉浸 viewer / 转发卡 / 内容详情页**同一口径**：
/// - 只读消费 [IntersectionReason.displayText]，端不本地拼装交集句（G2）；
/// - 取首条理由的 `displayText`（[primaryText] 为唯一口径真相源）；
/// - 无来源 / 文案为空 → 不展示（[fromReasons] 返回 null，调用方据此不插入）。
class IntersectionReasonChip extends StatelessWidget {
  const IntersectionReasonChip({
    super.key,
    required this.text,
    required this.isDark,
  });

  static const Key chipKey = ValueKey<String>('intersection-reason-chip');

  final String text;
  final bool isDark;

  /// 交集理由位口径真相源：取首条 `displayText`（trim）；
  /// 空 / 无来源 → null（不展示）。所有承载交集理由位的 surface 必须经此函数解析。
  static String? primaryText(List<IntersectionReason>? reasons) {
    if (reasons == null || reasons.isEmpty) return null;
    final text = reasons.first.displayText.trim();
    return text.isEmpty ? null : text;
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
