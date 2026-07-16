import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_target.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_text_span.g.dart';
import 'package:quwoquan_app/cloud/services/content/intersection_statement_synthesizer.dart';
import 'package:quwoquan_app/components/object_page/interactive_intersection_text.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';

class ImmersiveIntersectionStatement extends StatelessWidget {
  const ImmersiveIntersectionStatement({
    super.key,
    required this.reason,
    this.contextObjectName = '',
    this.contextObjectTarget,
    this.onSpanTap,
    this.onFallbackTap,
  });

  final IntersectionReason reason;
  final String contextObjectName;
  final IntersectionTarget? contextObjectTarget;
  final void Function(IntersectionTextSpan span)? onSpanTap;
  final VoidCallback? onFallbackTap;

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
    final child = onFallbackTap == null
        ? statement
        : GestureDetector(
            behavior: HitTestBehavior.opaque,
            onTap: onFallbackTap,
            child: statement,
          );
    return Semantics(
      key: const ValueKey('immersive-intersection-statement'),
      button: onSpanTap != null || onFallbackTap != null,
      child: child,
    );
  }
}
