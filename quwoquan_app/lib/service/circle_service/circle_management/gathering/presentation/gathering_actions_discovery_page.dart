import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/providers/theme_provider.dart';
import 'package:quwoquan_app/design_system/semantics/settings_semantic_constants.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/l10n/copy/app_concept_constants.dart';
import 'package:quwoquan_app/l10n/copy/gathering_text_constants.dart';
import 'package:quwoquan_app/runtime/auth/auth_gate.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/runtime/di/recommendation_presentation_slots.dart'
    show gatheringRecommendationSlots;
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/presentation/my_gatherings_entry_card.dart';

/// 线下行动与发现（底栏「行动」tab）。
///
/// 交集主线的 L2 目的地层：把「线上遇见的心动」承接为「线下一起完成的事」。
/// 首版只组合既有对象级读面——交集收件箱卡（recommendation）、我的行动入口
/// （circle.gathering）、兴趣配对导流与发起行动 CTA；不建立第二套业务查询。
/// 游客可浏览页面与兴趣配对；「我的交集/我的行动/发起行动」等账号态动作
/// 才触发登录（关闭回本页安全态，成功进入目标路由）。
class GatheringActionsDiscoveryPage extends ConsumerWidget {
  const GatheringActionsDiscoveryPage({super.key});

  static const Key pageKey = ValueKey<String>('gathering-actions-discovery');

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final isDark = ref.watch(isDarkProvider);
    final isAuthenticated = ref
        .watch(authSessionControllerProvider)
        .isAuthenticated;
    final horizontal = AppSpacing.feedContentHorizontal(context);
    return Container(
      key: GatheringActionsDiscoveryPage.pageKey,
      color: SettingsSemanticConstants.conversationSheetCardSurface(isDark),
      child: SafeArea(
        bottom: false,
        child: ListView(
          padding: EdgeInsets.fromLTRB(
            horizontal,
            AppSpacing.interGroupSm,
            horizontal,
            AppSpacing.interGroupXl,
          ),
          children: [
            Text(
              AppConceptConstants.offlineActionsPageTitle,
              style: TextStyle(
                fontSize: AppTypography.iosTitle2,
                fontWeight: AppTypography.bold,
                color: AppColors.iosLabel(context),
              ),
            ),
            SizedBox(height: AppSpacing.intraGroupXs),
            Text(
              GatheringText.actionsDiscoverySubtitle,
              style: TextStyle(
                fontSize: AppTypography.iosSubheadline,
                color: AppColors.iosSecondaryLabel(context),
              ),
            ),
            SizedBox(height: AppSpacing.interGroupSm),
            _ActionsEntryCard(
              itemKey: const ValueKey<String>('actions-discover-interest'),
              icon: CupertinoIcons.person_2,
              title: GatheringText.actionsDiscoverInterestTitle,
              subtitle: GatheringText.actionsDiscoverInterestSubtitle,
              onTap: () => context.push(AppRoutePaths.interestMatch),
            ),
            SizedBox(height: AppSpacing.intraGroupSm),
            _ActionsEntryCard(
              itemKey: const ValueKey<String>('actions-create-gathering'),
              icon: CupertinoIcons.flag,
              title: GatheringText.actionsCreateEntryTitle,
              subtitle: GatheringText.actionsCreateEntrySubtitle,
              onTap: () => _openCreateGathering(context, ref),
            ),
            if (isAuthenticated) ...[
              SizedBox(height: AppSpacing.intraGroupSm),
              gatheringRecommendationSlots.buildMyIntersection(isDark: isDark),
              MyGatheringsEntryCard(isDark: isDark),
            ] else ...[
              SizedBox(height: AppSpacing.intraGroupSm),
              _ActionsEntryCard(
                itemKey: const ValueKey<String>('actions-guest-login'),
                icon: CupertinoIcons.lock,
                title: GatheringText.actionsGuestIntroTitle,
                subtitle: GatheringText.actionsGuestIntroSubtitle,
                onTap: () => _loginForMyGatherings(context, ref),
              ),
            ],
          ],
        ),
      ),
    );
  }

  Future<void> _openCreateGathering(BuildContext context, WidgetRef ref) async {
    final authenticated = ref
        .read(authSessionControllerProvider)
        .isAuthenticated;
    if (authenticated) {
      await context.push(AppRoutePaths.gatheringCreate);
      return;
    }
    // 发起行动是账号态具体动作：登录成功进入创建流程，关闭回本页安全态
    // （本页游客可浏览，不会再次触发登录门）。
    await requireLogin(
      ref,
      context,
      AuthGateReason.generic,
      redirect: AppRoutePaths.gatheringCreate,
      dismissFallback: AppRoutePaths.home,
    );
  }

  Future<void> _loginForMyGatherings(BuildContext context, WidgetRef ref) {
    // 登录成功直达「我的行动」；关闭回本页安全态。
    return requireLogin(
      ref,
      context,
      AuthGateReason.generic,
      redirect: AppRoutePaths.myGatherings(),
      dismissFallback: AppRoutePaths.home,
    );
  }
}

class _ActionsEntryCard extends StatelessWidget {
  const _ActionsEntryCard({
    required this.itemKey,
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.onTap,
  });

  final Key itemKey;
  final IconData icon;
  final String title;
  final String subtitle;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final secondary = AppColors.iosSecondaryLabel(context);
    return CupertinoButton(
      key: itemKey,
      padding: EdgeInsets.zero,
      minimumSize: Size.square(AppSpacing.minInteractiveSize),
      onPressed: onTap,
      child: Container(
        padding: EdgeInsets.all(AppSpacing.containerMd),
        decoration: BoxDecoration(
          color: AppColors.iosGroupedSurface(context),
          borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
        ),
        child: Row(
          children: [
            Icon(
              icon,
              size: AppSpacing.iconMedium,
              color: AppColors.primaryColor,
            ),
            SizedBox(width: AppSpacing.intraGroupSm),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    style: TextStyle(
                      fontSize: AppTypography.iosBody,
                      fontWeight: AppTypography.semiBold,
                      color: AppColors.iosLabel(context),
                    ),
                  ),
                  SizedBox(height: AppSpacing.intraGroupXs),
                  Text(
                    subtitle,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: AppTypography.iosFootnote,
                      color: secondary,
                    ),
                  ),
                ],
              ),
            ),
            Icon(
              CupertinoIcons.chevron_forward,
              size: AppSpacing.iconSmall,
              color: secondary,
            ),
          ],
        ),
      ),
    );
  }
}
