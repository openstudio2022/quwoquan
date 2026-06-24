import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/services/user/following_subject_repository.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/widgets/app_cached_network_image.dart';

final followingSubjectsProvider = FutureProvider<List<FollowingSubjectItem>>((
  ref,
) async {
  return ref
      .watch(followingSubjectRepositoryProvider)
      .listFollowingSubjects(limit: 20);
});

class FollowingSubjectStrip extends ConsumerWidget {
  const FollowingSubjectStrip({
    super.key,
    required this.isDark,
    this.onSubjectOpen,
  });

  final bool isDark;
  final void Function(FollowingSubjectItem item)? onSubjectOpen;

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
                  UITextConstants.followingSubjectStripTitle,
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
                error: (_, _) => _FollowingSubjectEmptyState(isDark: isDark),
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
                            'following-subject-${item.subjectTypeWire}-${item.subjectId}',
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
    FollowingSubjectItem item,
  ) {
    if (onSubjectOpen != null) {
      onSubjectOpen!(item);
    } else {
      final location = switch (item.subjectType) {
        FollowingSubjectType.user => AppRoutePaths.userProfile(
          username: item.targetObjectId,
        ),
        FollowingSubjectType.circle => AppRoutePaths.circleDetail(
          id: item.targetObjectId,
        ),
        FollowingSubjectType.homepage => AppRoutePaths.homepageDetail(
          id: item.targetObjectId,
        ),
      };
      context.push(location);
    }
    unawaited(
      ref
          .read(followingSubjectRepositoryProvider)
          .markFollowingSubjectVisited(subject: item)
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

  final FollowingSubjectItem item;
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
                      'following-subject-type-${item.subjectTypeWire}-${item.subjectId}',
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

  final FollowingSubjectType type;
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
      FollowingSubjectType.user => AppColors.iosAccent(context),
      FollowingSubjectType.circle => AppColors.success,
      FollowingSubjectType.homepage => AppColors.warning,
    };
  }

  IconData get _icon {
    return switch (type) {
      FollowingSubjectType.user => CupertinoIcons.person_fill,
      FollowingSubjectType.circle => CupertinoIcons.person_2_fill,
      FollowingSubjectType.homepage => CupertinoIcons.location_solid,
    };
  }

  String get _label {
    return switch (type) {
      FollowingSubjectType.user => '用户',
      FollowingSubjectType.circle => '圈子',
      FollowingSubjectType.homepage => '对象',
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

  final FollowingSubjectItem item;
  final bool isDark;

  @override
  Widget build(BuildContext context) {
    final url = item.visualUrl;
    final radius = item.subjectType == FollowingSubjectType.user
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

  IconData _fallbackIcon(FollowingSubjectType type) {
    return switch (type) {
      FollowingSubjectType.user => CupertinoIcons.person_fill,
      FollowingSubjectType.circle => CupertinoIcons.person_2_fill,
      FollowingSubjectType.homepage => CupertinoIcons.location_solid,
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
            UITextConstants.followingSubjectEmptyTitle,
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
            UITextConstants.followingSubjectEmptySubtitle,
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
