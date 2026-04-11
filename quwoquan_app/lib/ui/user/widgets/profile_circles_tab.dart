import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/user/models/profile_mode.dart';
import 'package:quwoquan_app/ui/user/providers/profile_state_provider.dart';
import 'package:quwoquan_app/ui/user/widgets/circle_compact_card.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_ios_components.dart';

class ProfileCirclesTab extends ConsumerWidget {
  const ProfileCirclesTab({
    super.key,
    required this.mode,
    required this.userId,
    required this.isDark,
    this.inlineScroll = false,
  });

  final ProfileMode mode;
  final String userId;
  final bool isDark;
  final bool inlineScroll;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(profileNotifierProvider(userId));
    final fgSecondary = AppColors.iosSecondaryLabel(context);
    if (state.isLoading && state.circles.isEmpty) {
      return Padding(
        padding: EdgeInsets.symmetric(vertical: AppSpacing.interGroupXl),
        child: Center(child: CupertinoActivityIndicator()),
      );
    }

    if (state.circles.isEmpty) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: <Widget>[
            Container(
              width: AppSpacing.avatarCircleLg,
              height: AppSpacing.avatarCircleLg,
              decoration: BoxDecoration(
                color: AppColors.iosFill(context),
                shape: BoxShape.circle,
              ),
              child: Icon(
                CupertinoIcons.group,
                size: AppSpacing.iconMedium,
                color: fgSecondary,
              ),
            ),
            SizedBox(height: AppSpacing.containerSm),
            Text(
              mode == ProfileMode.mine ? '还没加入圈子' : 'Ta 还没加入圈子',
              style: TextStyle(
                fontSize: AppTypography.iosSubheadline,
                color: fgSecondary,
              ),
            ),
            if (mode == ProfileMode.mine) ...[
              SizedBox(height: AppSpacing.md),
              ProfileIosActionButton(
                label: '去发现圈子',
                icon: CupertinoIcons.compass,
                onPressed: () => context.go(AppRoutePaths.circles),
                style: ProfileIosActionStyle.tinted,
                expand: false,
              ),
            ],
          ],
        ),
      );
    }

    return ListView.separated(
      physics: inlineScroll
          ? const NeverScrollableScrollPhysics()
          : const BouncingScrollPhysics(
              parent: AlwaysScrollableScrollPhysics(),
            ),
      shrinkWrap: inlineScroll,
      padding: EdgeInsets.fromLTRB(
        AppSpacing.containerMd,
        AppSpacing.intraGroupSm,
        AppSpacing.containerMd,
        AppSpacing.containerMd,
      ),
      itemCount: state.circles.length,
      separatorBuilder: (context, index) => SizedBox(height: AppSpacing.sm),
      itemBuilder: (context, index) {
        final circle = state.circles[index];
        return CircleCompactCard(
          name: circle.name,
          coverUrl: circle.coverUrl ?? '',
          postCount: circle.postCount,
          isDark: isDark,
          onTap: () => context.push(AppRoutePaths.circleDetail(id: circle.id)),
        );
      },
    );
  }
}
