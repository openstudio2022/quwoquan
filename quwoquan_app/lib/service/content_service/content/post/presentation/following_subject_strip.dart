import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:uuid/uuid.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_behavior_repository.dart'
    show ReferralSource;
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/runtime/errors/runtime_error_display.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/design_system/media/app_cached_network_image.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle/application/public/circle_detail_page_route_extra.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

final followingSubjectsProvider =
    FutureProvider<List<FollowingSubjectItemView>>((ref) async {
      final slice = await ref
          .watch(followingSubjectQueryProvider)
          .listFollowingSubjects(ListFollowingSubjectsQuery(limit: 20));
      return slice.items;
    });

class FollowingSubjectStrip extends ConsumerWidget {
  const FollowingSubjectStrip({
    super.key,
    required this.isDark,
    this.onSubjectOpen,
  });

  final bool isDark;
  final void Function(FollowingSubjectItemView item)? onSubjectOpen;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final asyncItems = ref.watch(followingSubjectsProvider);
    return Padding(
      padding: EdgeInsets.fromLTRB(
        AppSpacing.feedContentHorizontal(context),
        AppSpacing.intraGroupSm,
        AppSpacing.feedContentHorizontal(context),
        AppSpacing.interGroupSm,
      ),
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: AppColorsFunctional.getColor(
            isDark,
            ColorType.surfaceElevated,
          ),
          borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
          boxShadow: isDark
              ? null
              : [
                  BoxShadow(
                    color: AppColors.black.withValues(alpha: 0.04),
                    blurRadius: 14,
                    offset: const Offset(0, 6),
                  ),
                ],
        ),
        child: Padding(
          padding: EdgeInsets.symmetric(vertical: AppSpacing.intraGroupMd),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Padding(
                padding: EdgeInsets.symmetric(
                  horizontal: AppSpacing.containerMd,
                ),
                child: Text(
                  DiscoveryText.followingSubjectStripTitle,
                  style: TextStyle(
                    fontSize: AppTypography.iosSubheadline,
                    fontWeight: AppTypography.semiBold,
                    color: AppColorsFunctional.getColor(
                      isDark,
                      ColorType.foregroundPrimary,
                    ),
                  ),
                ),
              ),
              SizedBox(height: AppSpacing.intraGroupSm),
              asyncItems.when(
                loading: () => const _FollowingSubjectSkeletonStrip(),
                error: (error, _) => AppSectionErrorState(
                  semantic: runtimeErrorSemantic(
                    context,
                    error: error,
                    category: UiErrorCategory.pageLoad,
                    scope: UiErrorScope.section,
                  ),
                  onAction: (action) async {
                    if (action.type == UiErrorActionType.retry) {
                      ref.invalidate(followingSubjectsProvider);
                    }
                  },
                ),
                data: (items) {
                  if (items.isEmpty) {
                    return _FollowingSubjectEmptyState(isDark: isDark);
                  }
                  return SizedBox(
                    height: AppSpacing.avatarRailHeight,
                    child: ListView.separated(
                      padding: EdgeInsets.symmetric(
                        horizontal: AppSpacing.containerMd,
                      ),
                      scrollDirection: Axis.horizontal,
                      itemBuilder: (context, index) {
                        final item = items[index];
                        return FollowingSubjectAvatarTile(
                          key: ValueKey<String>(
                            'following-subject-${item.subjectType.wireName}-${item.subjectId}',
                          ),
                          item: item,
                          isDark: isDark,
                          onTap: () => _openSubject(context, ref, item),
                        );
                      },
                      separatorBuilder: (_, _) =>
                          SizedBox(width: AppSpacing.interGroupMd),
                      itemCount: items.length,
                    ),
                  );
                },
              ),
            ],
          ),
        ),
      ),
    );
  }

  void _openSubject(
    BuildContext context,
    WidgetRef ref,
    FollowingSubjectItemView item,
  ) {
    if (onSubjectOpen != null) {
      onSubjectOpen!(item);
    } else {
      switch (item.subjectType) {
        case FollowSubjectKind.persona:
          context.push(
            AppRoutePaths.userProfile(userHandle: item.targetObjectId),
          );
        case FollowSubjectKind.circle:
          context.push(
            AppRoutePaths.circleDetail(id: item.targetObjectId),
            extra: const CircleDetailPageRouteExtra(
              referralSource: ReferralSource.organicFeed,
            ),
          );
        case FollowSubjectKind.homepage:
          context.push(AppRoutePaths.homepageDetail(id: item.targetObjectId));
        case FollowSubjectKind.location:
          context.push(
            AppRoutePaths.locationPlaceLanding(
              placeId: item.targetObjectId,
              name: item.displayName,
              source: ReferralSource.organicFeed.name,
            ),
          );
      }
    }
    // R20/R21 · 关注频道点击埋点（红点命中时带 unread 信号，驱动频道价值漏斗）。
    unawaited(
      ref
          .read(journeyEventTrackerProvider)
          .trackAction(
            journey: 'following_channel',
            action: item.hasUnreadChanges
                ? 'open_subject_with_unread'
                : 'open_subject',
            pageName: 'HomePage',
            targetType: item.subjectType.wireName,
            targetKey: item.subjectId,
          ),
    );
    final clientRequestId = const Uuid().v4();
    unawaited(
      ref
          .read(followedSubjectVisitCommandWriterProvider)
          .markFollowedSubjectVisited(
            MarkFollowedSubjectVisitedCommand(
              subjectId: item.subjectId,
              subjectType: item.subjectType,
              visitedAt: DateTime.now().toUtc(),
              clientRequestId: clientRequestId,
            ),
          )
          .whenComplete(() => ref.invalidate(followingSubjectsProvider)),
    );
  }
}

class FollowingSubjectAvatarTile extends StatelessWidget {
  const FollowingSubjectAvatarTile({
    super.key,
    required this.item,
    required this.isDark,
    required this.onTap,
  });

  final FollowingSubjectItemView item;
  final bool isDark;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return CupertinoButton(
      padding: EdgeInsets.zero,
      minimumSize: Size.zero,
      onPressed: onTap,
      child: SizedBox(
        width: AppSpacing.avatarUserXl,
        child: Column(
          children: [
            Stack(
              clipBehavior: Clip.none,
              children: [
                _FollowingSubjectAvatar(item: item, isDark: isDark),
                Positioned(
                  right: -AppSpacing.two,
                  bottom: -AppSpacing.two,
                  child: _FollowingSubjectTypeBadge(
                    key: ValueKey<String>(
                      'following-subject-type-${item.subjectType.wireName}-${item.subjectId}',
                    ),
                    type: item.subjectType,
                    isDark: isDark,
                  ),
                ),
                if (item.hasUnreadChanges)
                  const Positioned(
                    right: 1,
                    top: 1,
                    child: FollowingSubjectUnreadDot(),
                  ),
              ],
            ),
            SizedBox(height: AppSpacing.intraGroupXs),
            Text(
              item.displayName,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: AppTypography.iosCaption1,
                color: AppColorsFunctional.getColor(
                  isDark,
                  ColorType.foregroundPrimary,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _FollowingSubjectTypeBadge extends StatelessWidget {
  const _FollowingSubjectTypeBadge({
    super.key,
    required this.type,
    required this.isDark,
  });

  final FollowSubjectKind type;
  final bool isDark;

  @override
  Widget build(BuildContext context) {
    final accent = _accentColor(context);
    return Semantics(
      label: _label,
      child: Container(
        width: AppSpacing.buttonHeightXs,
        height: AppSpacing.buttonHeightXs,
        alignment: Alignment.center,
        decoration: BoxDecoration(
          color: AppColors.iosSystemBackground(context),
          borderRadius: BorderRadius.circular(AppSpacing.radiusNinetyNine),
          border: Border.all(color: accent, width: AppSpacing.one),
          boxShadow: isDark
              ? null
              : [
                  BoxShadow(
                    color: AppColors.black.withValues(alpha: 0.08),
                    blurRadius: AppSpacing.six,
                    offset: const Offset(AppSpacing.zero, AppSpacing.two),
                  ),
                ],
        ),
        child: Icon(_icon, size: AppSpacing.fourteen, color: accent),
      ),
    );
  }

  Color _accentColor(BuildContext context) {
    return switch (type) {
      FollowSubjectKind.persona => AppColors.iosAccent(context),
      FollowSubjectKind.circle => AppColors.success,
      FollowSubjectKind.homepage => AppColors.warning,
      FollowSubjectKind.location => AppColors.iosSystemCyanAccent,
    };
  }

  IconData get _icon {
    return switch (type) {
      FollowSubjectKind.persona => CupertinoIcons.person_fill,
      FollowSubjectKind.circle => CupertinoIcons.person_2_fill,
      FollowSubjectKind.homepage => CupertinoIcons.house_fill,
      FollowSubjectKind.location => CupertinoIcons.location_solid,
    };
  }

  String get _label {
    return switch (type) {
      FollowSubjectKind.persona => ContentText.followingSubjectTypeUser,
      FollowSubjectKind.circle => ContentText.followingSubjectTypeCircle,
      FollowSubjectKind.homepage ||
      FollowSubjectKind.location => ContentText.followingSubjectTypeObject,
    };
  }
}

class FollowingSubjectUnreadDot extends StatelessWidget {
  const FollowingSubjectUnreadDot({super.key});

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.error,
        shape: BoxShape.circle,
        border: Border.all(color: AppColors.white, width: AppSpacing.two),
      ),
      child: const SizedBox(width: AppSpacing.md, height: AppSpacing.md),
    );
  }
}

class _FollowingSubjectAvatar extends StatelessWidget {
  const _FollowingSubjectAvatar({required this.item, required this.isDark});

  final FollowingSubjectItemView item;
  final bool isDark;

  @override
  Widget build(BuildContext context) {
    final avatarUrl = item.avatarUrl?.trim() ?? '';
    final coverUrl = item.coverUrl?.trim() ?? '';
    final url = avatarUrl.isNotEmpty ? avatarUrl : coverUrl;
    final radius = item.subjectType == FollowSubjectKind.persona
        ? AppSpacing.radiusTwentyEight
        : AppSpacing.radiusTen;
    return ClipRRect(
      borderRadius: BorderRadius.circular(radius),
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: AppColorsFunctional.getColor(isDark, ColorType.surfaceMuted),
        ),
        child: SizedBox(
          width: AppSpacing.avatarUserLg,
          height: AppSpacing.avatarUserLg,
          child: url.isEmpty
              ? Icon(
                  _fallbackIcon(item.subjectType),
                  color: AppColorsFunctional.getColor(
                    isDark,
                    ColorType.foregroundSecondary,
                  ),
                  size: AppSpacing.lg,
                )
              : AppCachedNetworkImage(
                  imageUrl: url,
                  cdnPreset: CdnImagePreset.thumbnail,
                  fit: BoxFit.cover,
                  errorWidget: Icon(
                    _fallbackIcon(item.subjectType),
                    color: AppColorsFunctional.getColor(
                      isDark,
                      ColorType.foregroundSecondary,
                    ),
                    size: AppSpacing.lg,
                  ),
                ),
        ),
      ),
    );
  }

  IconData _fallbackIcon(FollowSubjectKind type) {
    return switch (type) {
      FollowSubjectKind.persona => CupertinoIcons.person_fill,
      FollowSubjectKind.circle => CupertinoIcons.person_2_fill,
      FollowSubjectKind.homepage => CupertinoIcons.house_fill,
      FollowSubjectKind.location => CupertinoIcons.location_solid,
    };
  }
}

class _FollowingSubjectSkeletonStrip extends StatelessWidget {
  const _FollowingSubjectSkeletonStrip();

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: AppSpacing.avatarRailHeight,
      child: ListView.separated(
        padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerMd),
        scrollDirection: Axis.horizontal,
        itemBuilder: (_, _) => const _FollowingSubjectSkeletonTile(),
        separatorBuilder: (_, _) => SizedBox(width: AppSpacing.interGroupMd),
        itemCount: 5,
      ),
    );
  }
}

class _FollowingSubjectSkeletonTile extends StatelessWidget {
  const _FollowingSubjectSkeletonTile();

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: AppSpacing.avatarUserXl,
      child: Column(
        children: [
          ClipRRect(
            borderRadius: BorderRadius.circular(AppSpacing.radiusTwentyEight),
            child: ColoredBox(
              color: AppColors.gridImagePlaceholderLight.withValues(alpha: 0.5),
              child: const SizedBox(
                width: AppSpacing.avatarUserLg,
                height: AppSpacing.avatarUserLg,
              ),
            ),
          ),
          SizedBox(height: AppSpacing.intraGroupXs),
          ClipRRect(
            borderRadius: BorderRadius.circular(AppSpacing.radiusTwo),
            child: ColoredBox(
              color: AppColors.gridImagePlaceholderLight.withValues(alpha: 0.5),
              child: const SizedBox(
                width: AppSpacing.minInteractiveSize,
                height: AppSpacing.ten,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _FollowingSubjectEmptyState extends StatelessWidget {
  const _FollowingSubjectEmptyState({required this.isDark});

  final bool isDark;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerMd),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            DiscoveryText.followingSubjectEmptyTitle,
            style: TextStyle(
              fontSize: AppTypography.iosSubheadline,
              fontWeight: AppTypography.semiBold,
              color: AppColorsFunctional.getColor(
                isDark,
                ColorType.foregroundPrimary,
              ),
            ),
          ),
          SizedBox(height: AppSpacing.intraGroupXs),
          Text(
            DiscoveryText.followingSubjectEmptySubtitle,
            style: TextStyle(
              fontSize: AppTypography.iosFootnote,
              color: AppColorsFunctional.getColor(
                isDark,
                ColorType.foregroundSecondary,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
