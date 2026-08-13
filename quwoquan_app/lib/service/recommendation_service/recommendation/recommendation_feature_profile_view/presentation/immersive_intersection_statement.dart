import 'package:flutter/cupertino.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/domain/intersection_statement_synthesizer.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/presentation/interactive_intersection_text.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/presentation/intersection_statement_row.dart'
    show primaryDisplayableIntersectionActionHint;
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';

class ImmersiveIntersectionStatement extends StatelessWidget {
  const ImmersiveIntersectionStatement({
    super.key,
    required this.reason,
    this.contextObjectName = '',
    this.contextObjectTarget,
    this.onSpanTap,
    this.onFallbackTap,
    this.onActionHintTap,
  });

  final IntersectionReason reason;
  final String contextObjectName;
  final IntersectionTarget? contextObjectTarget;
  final void Function(IntersectionTextSpan span)? onSpanTap;
  final VoidCallback? onFallbackTap;

  /// 主行动命中回调（交集 CTA 一级化）。非空时按七触点共用口径
  /// （primaryDisplayableIntersectionActionHint）在单句尾部渲染一个主行动 pill，
  /// 文案只用云侧 hint.label；保持「一句主句 + 一个主动作」，不渲染第二动作。
  final void Function(IntersectionActionHint hint)? onActionHintTap;

  @override
  Widget build(BuildContext context) {
    final displayReason = displayReadyIntersectionReason(
      reason,
      contextObjectTarget: contextObjectTarget,
    );
    if (displayReason == null) {
      return const SizedBox.shrink();
    }
    final fallback = displayReason.primaryText.trim();
    if (fallback.isEmpty) {
      return const SizedBox.shrink();
    }
    final statement = InteractiveIntersectionText(
      spans: displayReason.primarySpans,
      fallbackText: fallback,
      maxLines: 1,
      overflow: TextOverflow.ellipsis,
      onSpanTap: onSpanTap,
      onFallbackTap: onFallbackTap,
      accentFontWeight: AppTypography.medium,
      baseStyle: TextStyle(
        color: AppColors.worksBodyText.withValues(alpha: 0.82),
        fontSize: AppTypography.base,
        fontWeight: AppTypography.regular,
        height: AppSpacing.textLineHeightBody,
        letterSpacing: 0,
      ),
    );
    final Widget statementChild = onFallbackTap == null
        ? statement
        : GestureDetector(
            behavior: HitTestBehavior.opaque,
            onTap: onFallbackTap,
            child: statement,
          );
    final actionHint = onActionHintTap == null
        ? null
        : primaryDisplayableIntersectionActionHint(displayReason.actionHints);
    final Widget content = actionHint == null
        ? statementChild
        : Row(
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              Expanded(child: statementChild),
              SizedBox(width: AppSpacing.intraGroupSm),
              _ImmersiveActionHintPill(
                hint: actionHint,
                onTap: () => onActionHintTap!(actionHint),
              ),
            ],
          );
    return Semantics(
      key: const ValueKey('immersive-intersection-statement'),
      button: onSpanTap != null || onFallbackTap != null,
      child: content,
    );
  }
}

/// 沉浸暗色语境下的主行动 pill：低饱和半透明底 + 云侧 label 单行文本。
/// 不做动效、不发光，服从 L0 氛围层「简洁不突兀」的呈现约束。
class _ImmersiveActionHintPill extends StatelessWidget {
  const _ImmersiveActionHintPill({required this.hint, required this.onTap});

  final IntersectionActionHint hint;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final label = hint.label.trim();
    if (label.isEmpty) {
      return const SizedBox.shrink();
    }
    return Semantics(
      key: const ValueKey('immersive-intersection-action'),
      button: true,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: onTap,
        child: Container(
          constraints: BoxConstraints(
            minHeight: AppSpacing.minInteractiveSize / 2,
          ),
          padding: EdgeInsets.symmetric(
            horizontal: AppSpacing.containerXs,
            vertical: AppSpacing.intraGroupXs / 2,
          ),
          decoration: BoxDecoration(
            color: AppColors.worksBodyText.withValues(alpha: 0.16),
            borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
          ),
          alignment: Alignment.center,
          child: Text(
            label,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              color: AppColors.worksBodyText.withValues(alpha: 0.95),
              fontSize: AppTypography.sm,
              fontWeight: AppTypography.medium,
              height: AppSpacing.textLineHeightCaption,
            ),
          ),
        ),
      ),
    );
  }
}
