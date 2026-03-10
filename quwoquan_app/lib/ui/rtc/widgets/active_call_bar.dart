import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/services/active_call_service.dart';

/// Top blue bar shown when navigating away from an active call.
/// Tap to return to the call page.
class ActiveCallBar extends ConsumerWidget {
  const ActiveCallBar({
    super.key,
    required this.onTap,
  });

  final VoidCallback onTap;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final callState = ref.watch(activeCallProvider);
    if (!callState.isInCall) return const SizedBox.shrink();

    final elapsed = callState.elapsed;
    final minutes = elapsed.inMinutes.remainder(60).toString().padLeft(2, '0');
    final seconds = elapsed.inSeconds.remainder(60).toString().padLeft(2, '0');

    return GestureDetector(
      onTap: onTap,
      child: Container(
        width: double.infinity,
        height: AppSpacing.twentyEight,
        color: AppColors.primaryColor,
        child: Center(
          child: Text(
            '通话中 $minutes:$seconds 点击返回',
            style: TextStyle(
              color: AppColors.white,
              fontSize: AppTypography.sm,
              fontWeight: AppTypography.medium,
              fontFeatures: const [FontFeature.tabularFigures()],
            ),
          ),
        ),
      ),
    );
  }
}
