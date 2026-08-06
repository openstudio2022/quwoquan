import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle_membership/application/public/circle_membership_ports.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_behavior_repository.dart'
    show ReferralSource;
import 'package:quwoquan_app/service/circle_service/circle_management/circle/application/public/circle_detail_page_route_extra.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/application/public/profile_mode.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle_membership/presentation/circle_compact_card.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/feedback/app_request_feedback.dart';
import 'package:quwoquan_app/design_system/object_page/profile_ios_components.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef _ProfileCirclesRequest = ({
  PersonaCircleMembershipQuery query,
  String userId,
});

final _profileCirclesProvider = FutureProvider.autoDispose
    .family<List<PersonaCircleSlice>, _ProfileCirclesRequest>((
      ref,
      request,
    ) async {
      final page = await request.query.listPersonaCircles(
        PersonaCircleListQuery(personaId: request.userId, limit: 100),
      );
      return page.items;
    });

class ProfileCirclesTab extends ConsumerWidget {
  const ProfileCirclesTab({
    super.key,
    required this.mode,
    required this.userId,
    required this.isDark,
    required this.membershipQuery,
    this.inlineScroll = false,
  });

  final ProfileMode mode;
  final String userId;
  final bool isDark;
  final PersonaCircleMembershipQuery membershipQuery;
  final bool inlineScroll;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final asyncCircles = ref.watch(
      _profileCirclesProvider((query: membershipQuery, userId: userId)),
    );
    final fgSecondary = AppColors.iosSecondaryLabel(context);
    return asyncCircles.when(
      loading: () => Padding(
        padding: EdgeInsets.symmetric(vertical: AppSpacing.interGroupXl),
        child: AppRequestFeedback.section(),
      ),
      error: (_, _) => Padding(
        padding: EdgeInsets.symmetric(vertical: AppSpacing.interGroupXl),
        child: AppRequestFeedback.section(),
      ),
      data: (circles) {
        if (circles.isEmpty) {
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
                  mode == ProfileMode.mine
                      ? ProfileText.profileCirclesEmptyMineTitle
                      : ProfileText.profileCirclesEmptyOtherTitle,
                  style: TextStyle(
                    fontSize: AppTypography.iosSubheadline,
                    color: fgSecondary,
                  ),
                ),
                if (mode == ProfileMode.mine) ...[
                  SizedBox(height: AppSpacing.md),
                  ProfileIosActionButton(
                    label: ProfileText.profileStatsDiscoverCircles,
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
          itemCount: circles.length,
          separatorBuilder: (context, index) => SizedBox(height: AppSpacing.sm),
          itemBuilder: (context, index) {
            final circle = circles[index];
            return CircleCompactCard(
              name: circle.name,
              coverUrl: circle.coverUrl ?? '',
              postCount: circle.postCount,
              isDark: isDark,
              onTap: () => context.push(
                AppRoutePaths.circleDetail(id: circle.circleId),
                extra: const CircleDetailPageRouteExtra(
                  referralSource: ReferralSource.authorProfile,
                ),
              ),
            );
          },
        );
      },
    );
  }
}
