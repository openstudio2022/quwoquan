import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/ui/rtc/providers/call_timer_provider.dart';

/// Displays call duration as HH:MM:SS or MM:SS.
class CallDurationBadge extends ConsumerWidget {
  const CallDurationBadge({
    super.key,
    this.textColor,
    this.fontSize,
    this.showBackground = false,
  });

  final Color? textColor;
  final double? fontSize;
  final bool showBackground;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final timer = ref.watch(callTimerProvider);

    final text = Text(
      timer.formattedTime,
      style: TextStyle(
        color: textColor ?? AppColors.white,
        fontSize: fontSize ?? AppTypography.md,
        fontWeight: AppTypography.medium,
        fontFeatures: const [FontFeature.tabularFigures()],
      ),
    );

    if (!showBackground) return text;

    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.sm,
        vertical: AppSpacing.xs,
      ),
      decoration: BoxDecoration(
        color: AppColors.overlayMedium,
        borderRadius: BorderRadius.circular(AppSpacing.smallBorderRadius),
      ),
      child: text,
    );
  }
}
