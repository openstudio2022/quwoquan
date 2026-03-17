import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/user/models/profile_mode.dart';
import 'package:quwoquan_app/ui/user/providers/profile_state_provider.dart';
import 'package:quwoquan_app/ui/user/widgets/circle_compact_card.dart';

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
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );

    if (state.circles.isEmpty) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              Icons.group_outlined,
              size: AppSpacing.xl * 2,
              color: fgSecondary,
            ),
            SizedBox(height: AppSpacing.md),
            Text(
              mode == ProfileMode.mine ? '还没加入圈子' : 'Ta 还没加入圈子',
              style: TextStyle(fontSize: AppTypography.md, color: fgSecondary),
            ),
            if (mode == ProfileMode.mine) ...[
              SizedBox(height: AppSpacing.md),
              CupertinoButton(
                padding: EdgeInsets.zero,
                onPressed: () => context.go(AppRoutePaths.circles),
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
      physics: const BouncingScrollPhysics(
        parent: AlwaysScrollableScrollPhysics(),
      ),
      padding: EdgeInsets.all(AppSpacing.containerMd),
      itemCount: state.circles.length,
      separatorBuilder: (context, index) => SizedBox(height: AppSpacing.sm),
      itemBuilder: (context, index) {
        final circle = state.circles[index];
        final postCount = circle['postCount'] as int? ?? 0;
        return CircleCompactCard(
          name: circle['name']?.toString() ?? '',
          coverUrl: circle['coverUrl']?.toString() ?? '',
          postCount: postCount,
          isDark: isDark,
          onTap: () => context.push(
            AppRoutePaths.circleDetail(id: '${circle['id']}'),
          ),
        );
      },
    );
  }
}
