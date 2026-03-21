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
import 'package:quwoquan_app/ui/user/widgets/profile_ios_components.dart';

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
    final fgSecondary = AppColors.iosSecondaryLabel(context);
    final activeIndex = _interactionFilters.indexWhere(
      (filter) => _interactionSubTabForId(filter.id) == state.interactionSubTab,
    );
    final directionToggleWidth = (MediaQuery.sizeOf(context).width * 0.34)
        .clamp(116.0, 156.0)
        .toDouble();

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
            ? Padding(
                padding: EdgeInsets.only(right: AppSpacing.containerMd),
                child: SizedBox(
                  width: directionToggleWidth,
                  child: FittedBox(
                    fit: BoxFit.scaleDown,
                    alignment: Alignment.centerRight,
                    child:
                        CupertinoSlidingSegmentedControl<InteractionDirection>(
                          groupValue: state.interactionDirection,
                          backgroundColor: AppColors.iosFill(context),
                          thumbColor: AppColors.iosGroupedSurface(context),
                          children: <InteractionDirection, Widget>{
                            InteractionDirection.received: Padding(
                              padding: EdgeInsets.symmetric(
                                horizontal: AppSpacing.sm,
                                vertical: AppSpacing.intraGroupXs,
                              ),
                              child: Text(
                                '收到',
                                style: TextStyle(
                                  fontSize: AppTypography.iosCaption1,
                                  fontWeight: AppTypography.medium,
                                  color: fg,
                                ),
                              ),
                            ),
                            InteractionDirection.sent: Padding(
                              padding: EdgeInsets.symmetric(
                                horizontal: AppSpacing.sm,
                                vertical: AppSpacing.intraGroupXs,
                              ),
                              child: Text(
                                '发出',
                                style: TextStyle(
                                  fontSize: AppTypography.iosCaption1,
                                  fontWeight: AppTypography.medium,
                                  color: fg,
                                ),
                              ),
                            ),
                          },
                          onValueChanged: (value) {
                            if (value != null) {
                              notifier.setInteractionDirection(value);
                            }
                          },
                        ),
                  ),
                ),
              )
            : null,
        showTrailingDivider: widget.mode == ProfileMode.mine,
        variant: SecondaryCapsuleTabBarVariant.iosProfile,
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
                  size: AppSpacing.iconLarge,
                  color: fgSecondary,
                ),
                SizedBox(height: AppSpacing.md),
                Text(
                  _emptyStateTitle(state.interactionSubTab),
                  style: TextStyle(
                    fontSize: AppTypography.iosSubheadline,
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
                        profileSubjectId: userId,
                        avatar: avatarUrl.isNotEmpty ? avatarUrl : null,
                        displayName: nickname.isNotEmpty ? nickname : null,
                      ),
                    );
                  }
                },
                child: ProfileIosSectionCard(
                  padding: EdgeInsets.all(AppSpacing.containerSm),
                  backgroundColor: AppColors.iosGroupedSurface(context),
                  borderColor: AppColors.iosSeparator(
                    context,
                  ).withValues(alpha: 0.16),
                  child: Row(
                    children: <Widget>[
                      CircleAvatar(
                        radius: 24,
                        backgroundImage: avatarUrl.isNotEmpty
                            ? NetworkImage(avatarUrl)
                            : null,
                        backgroundColor: AppColors.iosFill(context),
                        onBackgroundImageError: (error, stackTrace) {},
                        child: avatarUrl.isEmpty
                            ? Icon(
                                CupertinoIcons.person_crop_circle_fill,
                                color: fgSecondary,
                              )
                            : null,
                      ),
                      SizedBox(width: AppSpacing.containerSm),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: <Widget>[
                            Text(
                              nickname,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: TextStyle(
                                fontSize: AppTypography.iosSubheadline,
                                fontWeight: AppTypography.semiBold,
                                color: fg,
                                letterSpacing: -0.18,
                              ),
                            ),
                            if (targetTitle.isNotEmpty) ...<Widget>[
                              SizedBox(height: AppSpacing.intraGroupXs),
                              Text(
                                targetTitle,
                                style: TextStyle(
                                  fontSize: AppTypography.iosFootnote,
                                  color: fgSecondary,
                                ),
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                              ),
                            ],
                          ],
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
        return CupertinoIcons.heart;
      case InteractionSubTab.comments:
        return CupertinoIcons.chat_bubble;
      case InteractionSubTab.shares:
        return CupertinoIcons.arrowshape_turn_up_right;
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
