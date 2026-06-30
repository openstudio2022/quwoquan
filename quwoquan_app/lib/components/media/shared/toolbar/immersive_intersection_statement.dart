import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_text_span.g.dart';
import 'package:quwoquan_app/components/object_page/interactive_intersection_text.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';

class ImmersiveIntersectionStatement extends StatelessWidget {
  const ImmersiveIntersectionStatement({
    super.key,
    required this.reason,
    this.onSpanTap,
    this.onFallbackTap,
  });

  final IntersectionReason reason;
  final void Function(IntersectionTextSpan span)? onSpanTap;
  final VoidCallback? onFallbackTap;

  @override
  Widget build(BuildContext context) {
    final fallback = reason.primaryText.trim();
    if (reason.primarySpans.isEmpty && fallback.isEmpty) {
      return const SizedBox.shrink();
    }
    return Semantics(
      key: const ValueKey('immersive-intersection-statement'),
      button: onSpanTap != null || onFallbackTap != null,
      child: InteractiveIntersectionText(
        spans: reason.primarySpans,
        fallbackText: fallback,
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
        onSpanTap: onSpanTap,
        onFallbackTap: onFallbackTap,
        accentFontWeight: AppTypography.medium,
        baseStyle: TextStyle(
          color: AppColors.worksBodyText.withValues(alpha: 0.82),
          fontSize: AppTypography.xxs,
          fontWeight: AppTypography.regular,
          height: AppSpacing.textLineHeightFootnote,
          letterSpacing: -0.04,
        ),
      ),
    );
  }
}
