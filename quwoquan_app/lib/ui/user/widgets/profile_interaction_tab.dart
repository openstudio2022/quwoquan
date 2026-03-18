import 'package:flutter/material.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/user/generated/user_profile_ui_config.g.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/components/navigation/secondary_capsule_tab_bar.dart';
import 'package:quwoquan_app/core/models/user_profile_route_extra.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/user/models/profile_mode.dart';
import 'package:quwoquan_app/ui/user/models/profile_tab.dart';
import 'package:quwoquan_app/ui/user/providers/profile_state_provider.dart';

class ProfileInteractionTab extends ConsumerStatefulWidget {
  const ProfileInteractionTab({
    super.key,
    required this.mode,
    required this.userId,
    required this.isDark,
    this.inlineScroll = false,
    this.secondaryTabBarKey,
    this.onSecondaryHorizontalDragEnd,
  });

  final ProfileMode mode;
  final String userId;
  final bool isDark;
  final bool inlineScroll;
  final GlobalKey? secondaryTabBarKey;
  final GestureDragEndCallback? onSecondaryHorizontalDragEnd;

  @override
  ConsumerState<ProfileInteractionTab> createState() =>
      _ProfileInteractionTabState();
}

class _ProfileInteractionTabState extends ConsumerState<ProfileInteractionTab> {
  List<UserProfileSubTabConfig> get _interactionFilters =>
      UserProfileUIConfig.interactionSubTabs;

  List<ProfileInteractionActivityViewData>? _items;
  bool _loading = true;
  InteractionSubTab? _loadedSubTab;
  InteractionDirection? _loadedDirection;

  @override
  void initState() {
    super.initState();
    final state = ref.read(profileNotifierProvider(widget.userId)).state;
    _loadedSubTab = state.interactionSubTab;
    _loadedDirection = state.interactionDirection;
    _load();
  }

  Future<void> _load() async {
    final notifier = ref.read(profileNotifierProvider(widget.userId));
    final direction = notifier.state.interactionDirection;
    final subTab = notifier.state.interactionSubTab;
    _loadedDirection = direction;
    _loadedSubTab = subTab;
    final repo = ref.read(userProfileRepositoryProvider);
    setState(() => _loading = true);
    try {
      final list = direction == InteractionDirection.received
          ? await repo.listProfileInteractionReceivedView(widget.userId)
          : await repo.listProfileInteractionSentView(widget.userId);

      final filtered = list.where((item) {
        return item.activityType == _activityTypeForSubTab(subTab);
      }).toList();

      if (mounted) {
        setState(() {
          _items = filtered;
          _loading = false;
        });
      }
    } catch (_) {
      if (mounted) {
        setState(() {
          _items = [];
          _loading = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final notifier = ref.watch(profileNotifierProvider(widget.userId));
    final state = notifier.state;
    _scheduleReloadIfNeeded(state);
    final fg = AppColorsFunctional.getColor(
      widget.isDark,
      ColorType.foregroundPrimary,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      widget.isDark,
      ColorType.foregroundSecondary,
    );
    final primary = AppColors.primaryColor;
    final border = AppColorsFunctional.getColor(
      widget.isDark,
      ColorType.borderPrimary,
    );
    final activeIndex = _interactionFilters.indexWhere(
      (filter) => _interactionSubTabForId(filter.id) == state.interactionSubTab,
    );

    final header = SizedBox(
      key: const ValueKey<String>('profile-interaction-secondary-tabs'),
      child: SecondaryCapsuleTabBar(
        key: widget.secondaryTabBarKey,
        isDark: widget.isDark,
        tabs: _interactionFilters
            .map(
              (filter) => UITextConstants.contentLabelForKey(filter.labelKey),
            )
            .toList(growable: false),
        activeIndex: activeIndex < 0 ? 0 : activeIndex,
        onTap: (index) {
          notifier.setInteractionSubTab(
            _interactionSubTabForId(_interactionFilters[index].id),
          );
        },
        trailing: widget.mode == ProfileMode.mine
            ? Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  _DirectionChip(
                    label: '收到',
                    isActive:
                        state.interactionDirection ==
                        InteractionDirection.received,
                    onTap: () {
                      notifier.setInteractionDirection(
                        InteractionDirection.received,
                      );
                    },
                    fg: fg,
                    primary: primary,
                    border: border,
                  ),
                  SizedBox(width: AppSpacing.xs),
                  _DirectionChip(
                    label: '发出',
                    isActive:
                        state.interactionDirection == InteractionDirection.sent,
                    onTap: () {
                      notifier.setInteractionDirection(
                        InteractionDirection.sent,
                      );
                    },
                    fg: fg,
                    primary: primary,
                    border: border,
                  ),
                  SizedBox(width: AppSpacing.containerMd),
                ],
              )
            : null,
        showTrailingDivider: widget.mode == ProfileMode.mine,
        variant: SecondaryCapsuleTabBarVariant.inlineMuted,
        onHorizontalDragEnd: widget.onSecondaryHorizontalDragEnd,
      ),
    );

    final body = _loading
        ? Center(child: CupertinoActivityIndicator())
        : _items == null || _items!.isEmpty
        ? Center(
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Icon(
                  _emptyStateIcon(state.interactionSubTab),
                  size: AppSpacing.xl * 2,
                  color: fgSecondary,
                ),
                SizedBox(height: AppSpacing.md),
                Text(
                  _emptyStateTitle(state.interactionSubTab),
                  style: TextStyle(
                    fontSize: AppTypography.md,
                    color: fgSecondary,
                  ),
                ),
              ],
            ),
          )
        : ListView.separated(
            physics: widget.inlineScroll
                ? const NeverScrollableScrollPhysics()
                : const BouncingScrollPhysics(
                    parent: AlwaysScrollableScrollPhysics(),
                  ),
            shrinkWrap: widget.inlineScroll,
            padding: EdgeInsets.fromLTRB(
              AppSpacing.containerMd,
              AppSpacing.intraGroupSm,
              AppSpacing.containerMd,
              AppSpacing.containerMd,
            ),
            itemCount: _items!.length,
            separatorBuilder: (context, index) =>
                SizedBox(height: AppSpacing.sm),
            itemBuilder: (context, i) {
              final item = _items![i];
              final userId = item.actorProfileSubjectId;
              final nickname = item.actorDisplayName;
              final avatarUrl = item.actorAvatarUrl;
              final targetTitle = item.targetContentSummary;
              return CupertinoButton(
                padding: EdgeInsets.zero,
                onPressed: () {
                  if (userId.isNotEmpty) {
                    context.push(
                      AppRoutePaths.userProfile(username: userId),
                      extra: UserProfileRouteExtra(
                        avatar: avatarUrl.isNotEmpty ? avatarUrl : null,
                        displayName: nickname.isNotEmpty ? nickname : null,
                      ),
                    );
                  }
                },
                child: Row(
                  children: [
                    CircleAvatar(
                      radius: 24,
                      backgroundImage: avatarUrl.isNotEmpty
                          ? NetworkImage(avatarUrl)
                          : null,
                      onBackgroundImageError: (error, stackTrace) {},
                      child: avatarUrl.isEmpty
                          ? Icon(CupertinoIcons.person, color: fgSecondary)
                          : null,
                    ),
                    SizedBox(width: AppSpacing.containerSm),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            nickname,
                            style: TextStyle(
                              fontSize: AppTypography.md,
                              fontWeight: AppTypography.semiBold,
                              color: fg,
                            ),
                          ),
                          if (targetTitle.isNotEmpty)
                            Text(
                              targetTitle,
                              style: TextStyle(
                                fontSize: AppTypography.sm,
                                color: fgSecondary,
                              ),
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                            ),
                        ],
                      ),
                    ),
                  ],
                ),
              );
            },
          );

    if (widget.inlineScroll) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          header,
          SizedBox(height: AppSpacing.intraGroupXs),
          body,
        ],
      );
    }

    return Column(
      children: [
        header,
        Expanded(child: body),
      ],
    );
  }

  InteractionSubTab _interactionSubTabForId(String id) {
    switch (id) {
      case 'comments':
        return InteractionSubTab.comments;
      case 'shares':
        return InteractionSubTab.shares;
      case 'likes':
      default:
        return InteractionSubTab.likes;
    }
  }

  String _activityTypeForSubTab(InteractionSubTab subTab) {
    switch (subTab) {
      case InteractionSubTab.likes:
        return 'like';
      case InteractionSubTab.comments:
        return 'comment';
      case InteractionSubTab.shares:
        return 'share';
    }
  }

  IconData _emptyStateIcon(InteractionSubTab subTab) {
    switch (subTab) {
      case InteractionSubTab.likes:
        return Icons.favorite_border;
      case InteractionSubTab.comments:
        return Icons.chat_bubble_outline;
      case InteractionSubTab.shares:
        return Icons.repeat;
    }
  }

  String _emptyStateTitle(InteractionSubTab subTab) {
    switch (subTab) {
      case InteractionSubTab.likes:
        return '暂无点赞记录';
      case InteractionSubTab.comments:
        return '暂无评论记录';
      case InteractionSubTab.shares:
        return '暂无转发记录';
    }
  }

  void _scheduleReloadIfNeeded(ProfileState state) {
    if (_loadedSubTab == state.interactionSubTab &&
        _loadedDirection == state.interactionDirection) {
      return;
    }
    _loadedSubTab = state.interactionSubTab;
    _loadedDirection = state.interactionDirection;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) {
        _load();
      }
    });
  }
}

/// 方向切换 chip（接收/发送），保持现有圆角胶囊样式。
class _DirectionChip extends StatelessWidget {
  const _DirectionChip({
    required this.label,
    required this.isActive,
    required this.onTap,
    required this.fg,
    required this.primary,
    required this.border,
  });

  final String label;
  final bool isActive;
  final VoidCallback onTap;
  final Color fg;
  final Color primary;
  final Color border;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.containerSm,
          vertical: AppSpacing.intraGroupXs + 1,
        ),
        decoration: BoxDecoration(
          color: isActive
              ? primary.withValues(alpha: 0.08)
              : Colors.transparent,
          borderRadius: BorderRadius.circular(AppSpacing.circularBorderRadius),
          border: Border.all(
            color: isActive
                ? primary.withValues(alpha: 0.18)
                : border.withValues(alpha: 0.18),
            width: AppSpacing.intraGroupXs / 4,
          ),
        ),
        child: Text(
          label,
          style: TextStyle(
            fontSize: AppTypography.sm,
            fontWeight: isActive
                ? AppTypography.semiBold
                : AppTypography.normal,
            color: isActive ? primary : fg,
          ),
        ),
      ),
    );
  }
}
