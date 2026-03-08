import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';

enum NetworkQuality {
  good,
  slight,
  weak,
  poor;

  Color get color => switch (this) {
        NetworkQuality.good => AppColors.success,
        NetworkQuality.slight => AppColors.warning,
        NetworkQuality.weak => const Color(0xFFFF6B35),
        NetworkQuality.poor => AppColors.error,
      };

  int get barCount => switch (this) {
        NetworkQuality.good => 4,
        NetworkQuality.slight => 3,
        NetworkQuality.weak => 2,
        NetworkQuality.poor => 1,
      };
}

class CallQualityNotifier extends Notifier<NetworkQuality> {
  @override
  NetworkQuality build() => NetworkQuality.good;

  void update(NetworkQuality quality) => state = quality;
}

final callQualityProvider =
    NotifierProvider<CallQualityNotifier, NetworkQuality>(
  CallQualityNotifier.new,
);

class CallQualityIndicator extends ConsumerWidget {
  const CallQualityIndicator({
    super.key,
    this.quality,
  });

  final NetworkQuality? quality;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final NetworkQuality effectiveQuality =
        quality ?? ref.watch(callQualityProvider);
    return SizedBox(
      width: AppSpacing.iconMedium,
      height: AppSpacing.iconSmall,
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.end,
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: List.generate(4, (index) {
          final barIndex = index + 1;
          final isActive = barIndex <= effectiveQuality.barCount;
          final barHeight = AppSpacing.xs + (barIndex * AppSpacing.three);

          return AnimatedContainer(
            duration: const Duration(milliseconds: 300),
            width: AppSpacing.three,
            height: barHeight,
            decoration: BoxDecoration(
              color: isActive
                  ? effectiveQuality.color
                  : AppColors.white.withValues(alpha: 0.3),
              borderRadius: BorderRadius.circular(AppSpacing.one),
            ),
          );
        }),
      ),
    );
  }
}
