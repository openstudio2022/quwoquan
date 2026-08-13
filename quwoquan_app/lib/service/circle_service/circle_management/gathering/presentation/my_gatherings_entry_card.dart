import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/l10n/copy/gathering_text_constants.dart';
import 'package:quwoquan_app/runtime/di/app_providers_app_state.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/application/my_gatherings_provider.dart';

/// 我的主页「我的行动」单行入口（REQ-008）。
///
/// 恒为一行入口（无行动时不渲染空列表、不占首屏空间）；仅当读面成功返回且
/// 存在即将开始的公开行动时叠加「N 个即将开始」徽标。读面加载中或失败时
/// 降级为纯入口行——绝不阻塞主页首屏，也不伪造计数。
class MyGatheringsEntryCard extends ConsumerWidget {
  const MyGatheringsEntryCard({super.key, required this.isDark});

  static const Key cardKey = ValueKey<String>('my-gatherings-entry-card');

  final bool isDark;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final personaId = ref.watch(currentUserIdProvider);
    final page = ref.watch(myGatheringsProvider(personaId));
    final upcomingCount = switch (page) {
      AsyncData(:final value) => value.items
          .where(
            (card) => myGatheringsSegmentOf(card) == MyGatheringsSegment.upcoming,
          )
          .length,
      _ => 0,
    };
    final secondary = AppColors.iosSecondaryLabel(context);
    return Padding(
      padding: EdgeInsets.only(top: AppSpacing.interGroupSm),
      child: CupertinoButton(
        key: MyGatheringsEntryCard.cardKey,
        padding: EdgeInsets.zero,
        minimumSize: Size.square(AppSpacing.minInteractiveSize),
        onPressed: () => context.push(AppRoutePaths.myGatherings()),
        child: Container(
          width: double.infinity,
          padding: EdgeInsets.symmetric(
            horizontal: AppSpacing.containerMd,
            vertical: AppSpacing.containerSm,
          ),
          decoration: BoxDecoration(
            color: AppColors.iosProfileSurface(context),
            borderRadius: BorderRadius.circular(AppSpacing.radiusTwentyFour),
            border: Border.all(
              color: AppColors.iosCardBorder(context),
              width: AppSpacing.hairline,
            ),
          ),
          child: Row(
            children: <Widget>[
              Icon(
                CupertinoIcons.calendar,
                size: AppSpacing.iconSmall,
                color: AppColors.iosAccent(context),
              ),
              SizedBox(width: AppSpacing.intraGroupSm),
              Text(
                GatheringText.myGatheringsTitle,
                style: TextStyle(
                  fontSize: AppTypography.iosSubheadline,
                  fontWeight: AppTypography.semiBold,
                  color: AppColors.iosLabel(context),
                ),
              ),
              SizedBox(width: AppSpacing.intraGroupSm),
              Expanded(
                child: Text(
                  upcomingCount > 0
                      ? GatheringText.myGatheringsUpcomingBadge(upcomingCount)
                      : GatheringText.myGatheringsEntryHint,
                  key: const ValueKey<String>('my-gatherings-entry-summary'),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  textAlign: TextAlign.end,
                  style: TextStyle(
                    fontSize: AppTypography.iosFootnote,
                    color: upcomingCount > 0
                        ? AppColors.iosAccent(context)
                        : secondary,
                  ),
                ),
              ),
              SizedBox(width: AppSpacing.intraGroupSm),
              Icon(
                CupertinoIcons.chevron_forward,
                size: AppSpacing.iconSmall,
                color: AppColors.iosTertiaryLabel(context),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
