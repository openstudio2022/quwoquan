import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/user/models/profile_mode.dart';
import 'package:quwoquan_app/ui/user/providers/profile_state_provider.dart';
import 'package:quwoquan_app/ui/user/widgets/circle_card.dart';

class ProfileCirclesTab extends ConsumerWidget {
  const ProfileCirclesTab({
    super.key,
    required this.mode,
    required this.userId,
    required this.isDark,
  });

  final ProfileMode mode;
  final String userId;
  final bool isDark;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(profileNotifierProvider(userId)).state;
    final fgSecondary = AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary);

    if (state.circles.isEmpty) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.group_outlined, size: AppSpacing.xl * 2, color: fgSecondary),
            SizedBox(height: AppSpacing.md),
            Text(
              mode == ProfileMode.mine ? '还没加入圈子' : 'Ta 还没加入圈子',
              style: TextStyle(fontSize: AppTypography.md, color: fgSecondary),
            ),
            if (mode == ProfileMode.mine) ...[
              SizedBox(height: AppSpacing.md),
              TextButton(
                onPressed: () => context.go('/circles'),
                child: Text(
                  '去发现圈子',
                  style: TextStyle(
                    fontSize: AppTypography.md,
                    fontWeight: AppTypography.semiBold,
                    color: AppColors.primaryColor,
                  ),
                ),
              ),
            ],
          ],
        ),
      );
    }

    return ListView.separated(
      padding: EdgeInsets.all(AppSpacing.containerMd),
      itemCount: state.circles.length,
      separatorBuilder: (_, __) => SizedBox(height: AppSpacing.sm),
      itemBuilder: (context, index) {
        final circle = state.circles[index];
        return CircleCard(
          name: circle['name']?.toString() ?? '',
          coverUrl: circle['coverUrl']?.toString() ?? '',
          isDark: isDark,
          onTap: () => context.push('/circle/${circle['id']}'),
        );
      },
    );
  }
}
